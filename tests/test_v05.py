"""v0.5: several writers on shared pages."""
import threading

import pytest

from spatial.memory import SharedPages, VersionConflict
from spatial.memory.pageserver import LocalPageServer


def test_two_writers_never_lose_an_update():
    with LocalPageServer() as ps:
        a, b = SharedPages(ps.client()), SharedPages(ps.client())
        inc = lambda cur: (int(cur or b"0") + 1).to_bytes(8, "big").lstrip(b"\0") or b"\0"
        inc = lambda cur: str(int(cur or b"0") + 1).encode()
        def work(sp):
            for _ in range(150):
                sp.update(7, inc)
        ts = [threading.Thread(target=work, args=(sp,)) for sp in (a, b)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        data, version = a.read(7)
        assert int(data) == 300 and version == 300          # no lost update
        assert a.conflicts + b.conflicts > 0                 # and they really did collide
        with pytest.raises(VersionConflict):
            a.write(7, b"stale", expected_version=1)
        assert a.read(99) == (None, 0)
