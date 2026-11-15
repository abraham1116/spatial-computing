"""Shared pages with several writers: optimistic concurrency on the page server.

Each page has a version. A write succeeds only if the writer saw the current version
(compare-and-swap); otherwise it re-reads and retries. This gives lost-update-free
read-modify-write for pages shared by several processes. It is NOT distributed shared
memory: every access is a network round trip, and there is one server (no consensus).
"""
from __future__ import annotations


class VersionConflict(Exception):
    pass


class SharedPages:
    def __init__(self, client):
        self.c = client
        self.conflicts = 0

    def read(self, key: int) -> tuple[bytes | None, int]:
        rh, blob = self.c.call({"op": "vget", "key": key})
        return (blob if rh["exists"] else None), rh["version"]

    def write(self, key: int, data: bytes, expected_version: int) -> int:
        try:
            rh, _ = self.c.call({"op": "vput", "key": key, "expected": expected_version}, data)
        except RuntimeError as e:
            if "VersionConflict" in str(e):
                raise VersionConflict(str(e)) from None
            raise
        return rh["version"]

    def update(self, key: int, fn, max_retries: int = 1000) -> bytes:
        """Atomically replace the page by fn(current bytes or None)."""
        for _ in range(max_retries):
            cur, ver = self.read(key)
            new = fn(cur)
            try:
                self.write(key, new, ver)
                return new
            except VersionConflict:
                self.conflicts += 1
        raise VersionConflict(f"page {key}: still contended after {max_retries} retries")
