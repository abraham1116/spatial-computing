"""Spatial Resource Engine — user-space tiered memory (application-integrated far memory).

Tiers:
  T0 hot        : uncompressed pages in local RAM (LRU, byte budget)
  T1 compressed : compressed + content-deduplicated pages in local RAM (LRU, byte budget)
  T2 far        : compressed pages on a FarBackend (SSD file or remote page server)

HONESTY CONTRACT: T1 and T2 are NOT RAM. T1 trades CPU for space; T2 trades latency.
`stats()` always separates logical bytes from physical local RAM bytes, and every
access is timed per tier so the cost of leaving T0 is measured, never hidden.
This is an object store used through an API, not transparent kernel paging.
"""
from __future__ import annotations

import hashlib
import os
import time
import zlib
from collections import OrderedDict
from typing import Iterable, Protocol

try:
    import lz4.frame as _lz4
except Exception:  # pragma: no cover
    _lz4 = None


# ---------------------------------------------------------------- codecs
class Codec:
    name = "none"

    def enc(self, b: bytes) -> bytes:
        return b

    def dec(self, b: bytes) -> bytes:
        return b


class Lz4Codec(Codec):
    name = "lz4"

    def enc(self, b):
        return _lz4.compress(b, compression_level=0, store_size=True)

    def dec(self, b):
        return _lz4.decompress(b)


class ZlibCodec(Codec):
    name = "zlib1"

    def enc(self, b):
        return zlib.compress(b, 1)

    def dec(self, b):
        return zlib.decompress(b)


def codec(name: str) -> Codec:
    if name == "lz4":
        if _lz4 is None:
            raise RuntimeError("lz4 not installed")
        return Lz4Codec()
    return {"none": Codec, "zlib1": ZlibCodec}[name]()


# ---------------------------------------------------------------- far backends
class FarBackend(Protocol):
    name: str

    def put(self, key: int, blob: bytes) -> None: ...
    def get(self, key: int) -> bytes: ...
    def get_many(self, keys: list[int]) -> list[bytes | None]: ...
    def delete(self, key: int) -> None: ...
    def close(self) -> None: ...


class FileBackend:
    """Append-only log on local storage (SSD). Storage, not memory."""

    def __init__(self, path: str):
        self.name = "ssd-file"
        self.path = path
        self._f = open(path, "w+b", buffering=0)
        self._idx: dict[int, tuple[int, int]] = {}
        self._end = 0

    def put(self, key, blob):
        os.pwrite(self._f.fileno(), blob, self._end)
        self._idx[key] = (self._end, len(blob))
        self._end += len(blob)

    def get(self, key):
        off, ln = self._idx[key]
        return os.pread(self._f.fileno(), ln, off)

    def get_many(self, keys):
        return [self.get(k) if k in self._idx else None for k in keys]

    def delete(self, key):
        self._idx.pop(key, None)

    def close(self):
        self._f.close()
        try:
            os.unlink(self.path)
        except OSError:
            pass


class RemoteBackend:
    """Pages held in the RAM of a page server reached over SWP/0 (see pageserver.py)."""

    def __init__(self, client, label: str = "remote"):
        self.name = label
        self.c = client

    def put(self, key, blob):
        self.c.call({"op": "put", "key": key}, blob)

    def get(self, key):
        return self.c.call({"op": "get", "key": key})[1]

    def get_many(self, keys):
        rh, blob = self.c.call({"op": "get_many", "keys": keys})
        out, off = [], 0
        for ln in rh["lens"]:
            if ln < 0:
                out.append(None)
            else:
                out.append(blob[off:off + ln])
                off += ln
        return out

    def delete(self, key):
        self.c.call({"op": "del", "key": key})

    def close(self):
        self.c.close()


# ---------------------------------------------------------------- store
class _TierStat:
    __slots__ = ("hits", "ns")

    def __init__(self):
        self.hits = 0
        self.ns = 0

    def add(self, ns):
        self.hits += 1
        self.ns += ns


class TieredStore:
    def __init__(self, hot_bytes: int, compressed_bytes: int, far: FarBackend | None = None,
                 codec_name: str = "lz4", dedup: bool = True, prefetch: int = 0,
                 keep_latencies: bool = False, keep_far_copy: bool = False):
        self.keep_far_copy = keep_far_copy
        self.clean_evictions = self.far_writes = 0
        self.hot_cap, self.comp_cap = hot_bytes, compressed_bytes
        self.far = far
        self.codec = codec(codec_name)
        self.dedup = dedup
        self.prefetch = prefetch
        self._hot: OrderedDict[int, bytes] = OrderedDict()
        self._hot_bytes = 0
        self._comp: OrderedDict[int, bytes] = OrderedDict()   # key -> digest (dedup) or blob
        self._blobs: dict[bytes, list] = {}                   # digest -> [blob, refcount]
        self._comp_bytes = 0
        self._far_keys: dict[int, int] = {}   # key -> blob length
        self._far_bytes = 0
        self.logical_bytes = 0
        self._sizes: dict[int, int] = {}
        self.st = {"hot": _TierStat(), "compressed": _TierStat(), "far": _TierStat()}
        self.compress_ns = self.decompress_ns = 0
        self.raw_in = self.comp_out = 0
        self.dedup_hits = 0
        self.prefetched = self.prefetch_used = 0
        self._prefetched_keys: set[int] = set()
        self._last_far_key: int | None = None
        self.lat = {"hot": [], "compressed": [], "far": []} if keep_latencies else None

    # ---- internals
    def _comp_put(self, key: int, blob: bytes, digest: bytes | None):
        if self.dedup and digest is not None:
            ent = self._blobs.get(digest)
            if ent:
                ent[1] += 1
                self.dedup_hits += 1
            else:
                self._blobs[digest] = [blob, 1]
                self._comp_bytes += len(blob)
            self._comp[key] = digest
        else:
            self._comp[key] = blob
            self._comp_bytes += len(blob)
        self._evict_comp()

    def _comp_take(self, key: int) -> bytes:
        v = self._comp.pop(key)
        if self.dedup:
            ent = self._blobs[v]
            ent[1] -= 1
            blob = ent[0]
            if ent[1] == 0:
                del self._blobs[v]
                self._comp_bytes -= len(blob)
            return blob
        self._comp_bytes -= len(v)
        return v

    def _evict_comp(self):
        while self._comp_bytes > self.comp_cap and self._comp:
            k = next(iter(self._comp))
            blob = self._comp_take(k)
            if self.far is None:
                raise MemoryError("tiered store full and no far tier configured")
            if k in self._far_keys:          # clean copy already there: eviction is free
                self.clean_evictions += 1
                continue
            self.far.put(k, blob)
            self.far_writes += 1
            self._far_keys[k] = len(blob)
            self._far_bytes += len(blob)

    def _evict_hot(self):
        while self._hot_bytes > self.hot_cap and len(self._hot) > 1:
            k, raw = self._hot.popitem(last=False)
            self._hot_bytes -= len(raw)
            t = time.perf_counter_ns()
            blob = self.codec.enc(raw)
            self.compress_ns += time.perf_counter_ns() - t
            self.raw_in += len(raw)
            self.comp_out += len(blob)
            digest = hashlib.blake2b(raw, digest_size=16).digest() if self.dedup else None
            self._comp_put(k, blob, digest)

    def _admit(self, key: int, raw: bytes):
        self._hot[key] = raw
        self._hot_bytes += len(raw)
        self._evict_hot()

    def _drop(self, key: int):
        if key in self._hot:
            self._hot_bytes -= len(self._hot.pop(key))
        if key in self._comp:
            self._comp_take(key)
        if key in self._far_keys:            # also invalidates a retained clean copy
            self._far_bytes -= self._far_keys.pop(key)
            self.far.delete(key)

    # ---- API
    def put(self, key: int, raw: bytes) -> None:
        if key in self._sizes:
            self.logical_bytes -= self._sizes[key]
            self._drop(key)
        self._sizes[key] = len(raw)
        self.logical_bytes += len(raw)
        self._admit(key, raw)

    def get(self, key: int) -> bytes:
        t0 = time.perf_counter_ns()
        if key in self._hot:
            self._hot.move_to_end(key)
            raw = self._hot[key]
            tier = "hot"
        elif key in self._comp:
            blob = self._comp_take(key)
            t = time.perf_counter_ns()
            raw = self.codec.dec(blob)
            self.decompress_ns += time.perf_counter_ns() - t
            if key in self._prefetched_keys:
                self._prefetched_keys.discard(key)
                self.prefetch_used += 1
            self._admit(key, raw)
            tier = "compressed"
        elif key in self._far_keys:
            raw = self._far_fetch(key)
            tier = "far"
        else:
            raise KeyError(key)
        ns = time.perf_counter_ns() - t0
        self.st[tier].add(ns)
        if self.lat is not None:
            self.lat[tier].append(ns)
        return raw

    def _far_fetch(self, key: int) -> bytes:
        # Sequential detector: only read ahead when the previous far miss was key-1.
        seq = self.prefetch and self._last_far_key is not None and key == self._last_far_key + 1
        self._last_far_key = key
        if seq:
            extra = [k for k in range(key + 1, key + 1 + self.prefetch)
                     if k in self._far_keys and k not in self._hot and k not in self._comp]
            blobs = self.far.get_many([key] + extra)
            blob = blobs[0]
            for k, b in zip(extra, blobs[1:]):
                if b is None:
                    continue
                # Prefetched pages stay compressed in T1: cheap if never used.
                self._far_release(k)
                self._comp_put(k, b, hashlib.blake2b(b, digest_size=16).digest() if self.dedup else None)
                self._prefetched_keys.add(k)
                self.prefetched += 1
                self._last_far_key = k
        else:
            blob = self.far.get(key)
        self._far_release(key)
        t = time.perf_counter_ns()
        raw = self.codec.dec(blob)
        self.decompress_ns += time.perf_counter_ns() - t
        self._admit(key, raw)
        return raw

    def _far_release(self, key: int):
        """After a far read: drop the far copy, or keep it as a clean copy (keep_far_copy) so a
        later eviction of this unmodified page costs no network write."""
        if self.keep_far_copy:
            return
        self._far_bytes -= self._far_keys.pop(key)
        self.far.delete(key)

    def keys(self) -> Iterable[int]:
        return self._sizes.keys()

    def stats(self) -> dict:
        n = sum(s.hits for s in self.st.values()) or 1
        d = {
            "logical_bytes": self.logical_bytes,
            "local_ram_bytes": self._hot_bytes + self._comp_bytes,     # physical RAM really used
            "hot_bytes": self._hot_bytes, "compressed_tier_bytes": self._comp_bytes,
            "far_bytes": self._far_bytes, "far_backend": self.far.name if self.far else None,
            "codec": self.codec.name,
            "compression_ratio": round(self.raw_in / self.comp_out, 3) if self.comp_out else None,
            "dedup_hits": self.dedup_hits,
            "compress_cpu_s": self.compress_ns / 1e9, "decompress_cpu_s": self.decompress_ns / 1e9,
            "prefetched": self.prefetched, "prefetch_used": self.prefetch_used,
            "far_writes": self.far_writes, "clean_evictions": self.clean_evictions,
        }
        for name, s in self.st.items():
            d[f"{name}_hits"] = s.hits
            d[f"{name}_hit_ratio"] = round(s.hits / n, 4)
            d[f"{name}_mean_us"] = round(s.ns / s.hits / 1e3, 2) if s.hits else None
        if self.lat is not None:
            for name, xs in self.lat.items():
                if xs:
                    xs = sorted(xs)
                    d[f"{name}_p50_us"] = round(xs[len(xs) // 2] / 1e3, 2)
                    d[f"{name}_p99_us"] = round(xs[min(len(xs) - 1, int(len(xs) * 0.99))] / 1e3, 2)
        return d

    def close(self):
        if self.far:
            self.far.close()
