import os

import numpy as np
import pytest

from spatial.memory import FarArray, FileBackend, RemoteBackend, TieredStore
from spatial.memory.pageserver import LocalPageServer

PAGE = 16384


def _pages(n, seed=0):
    rng = np.random.default_rng(seed)
    out = []
    for i in range(n):
        if i % 3 == 0:      # compressible
            out.append(np.repeat(rng.integers(0, 50, PAGE // 64, dtype=np.uint8), 64).tobytes())
        elif i % 3 == 1:    # duplicate content
            out.append(b"\x07" * PAGE)
        else:               # incompressible
            out.append(rng.bytes(PAGE))
    return out


@pytest.mark.parametrize("codec", ["lz4", "zlib1", "none"])
def test_roundtrip_through_all_tiers_file(tmp_path, codec):
    pages = _pages(60)
    st = TieredStore(hot_bytes=4 * PAGE, compressed_bytes=6 * PAGE,
                     far=FileBackend(str(tmp_path / "far.bin")), codec_name=codec)
    for i, p in enumerate(pages):
        st.put(i, p)
    for i in np.random.default_rng(1).permutation(60):
        assert st.get(int(i)) == pages[i]
    s = st.stats()
    assert s["far_hits"] > 0
    if codec != "none":      # with no compression the T1 budget holds too few pages to be hit here
        assert s["compressed_hits"] > 0
    assert s["hot_bytes"] <= 4 * PAGE
    assert s["logical_bytes"] == 60 * PAGE
    assert s["local_ram_bytes"] < s["logical_bytes"]     # the point of tiering
    st.close()


def test_dedup_counts_identical_pages(tmp_path):
    st = TieredStore(2 * PAGE, 64 * PAGE, FileBackend(str(tmp_path / "f")), dedup=True)
    for i in range(20):
        st.put(i, b"\x07" * PAGE)
    assert st.stats()["dedup_hits"] >= 10
    assert all(st.get(i) == b"\x07" * PAGE for i in range(20))
    st.close()


def test_overwrite_and_missing_key(tmp_path):
    st = TieredStore(2 * PAGE, 2 * PAGE, FileBackend(str(tmp_path / "f")))
    for i in range(12):
        st.put(i, bytes([i]) * PAGE)
    st.put(0, b"z" * PAGE)
    assert st.get(0) == b"z" * PAGE and st.stats()["logical_bytes"] == 12 * PAGE
    with pytest.raises(KeyError):
        st.get(999)
    st.close()


def test_full_without_far_tier_raises():
    st = TieredStore(PAGE, PAGE, far=None, codec_name="none")
    with pytest.raises(MemoryError):
        for i in range(8):
            st.put(i, os.urandom(PAGE))


def test_remote_backend_and_prefetch():
    pages = _pages(80, seed=3)
    with LocalPageServer() as ps:
        st = TieredStore(4 * PAGE, 4 * PAGE, RemoteBackend(ps.client(), "loopback"), prefetch=8)
        for i, p in enumerate(pages):
            st.put(i, p)
        for i in range(80):                      # sequential scan triggers read-ahead
            assert st.get(i) == pages[i]
        s = st.stats()
        assert s["prefetched"] > 0 and s["prefetch_used"] > 0
        assert s["far_backend"] == "loopback"
        st.close()


def test_fararray_matches_numpy(tmp_path):
    n, per = 200_000, 4096
    data = np.arange(n, dtype=np.float64) * 0.5
    st = TieredStore(8 * per * 8, 8 * per * 8, FileBackend(str(tmp_path / "f")))
    fa = FarArray.from_chunks(st, (data[i:i + per] for i in range(0, n, per)), n, page_items=per)
    assert fa.sum() == pytest.approx(float(data.sum()))
    idx = np.random.default_rng(0).integers(0, n, 500)
    assert np.array_equal(fa.take(idx), data[idx])
    st.close()


def test_clean_copy_retention_avoids_rewrites_and_stays_correct(tmp_path):
    pages = _pages(60, seed=9)
    st = TieredStore(4 * PAGE, 4 * PAGE, FileBackend(str(tmp_path / "f")), keep_far_copy=True)
    for i, p in enumerate(pages):
        st.put(i, p)
    for _ in range(2):
        for i in range(60):
            assert st.get(i) == pages[i]
    assert st.stats()["clean_evictions"] > 0
    st.put(5, b"n" * PAGE)                       # overwrite must invalidate the retained far copy
    for i in range(60):
        st.get(i)
    assert st.get(5) == b"n" * PAGE
    st.close()
