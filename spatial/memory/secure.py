"""Far-tier wrappers: encryption and replication.

EncryptedBackend  : pages are sealed with AES-256-GCM before they leave the process; the
                    page key is bound as associated data, so a page served under another
                    key (swap attack) or modified at rest fails to open.
ReplicatedBackend : every page is written to all replicas; reads fall back to the next
                    replica when one fails or returns a corrupted page.
Neither adds capacity: they add confidentiality and availability to the far tier.
"""
from __future__ import annotations

import os
import struct

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class PageIntegrityError(Exception):
    pass


class EncryptedBackend:
    def __init__(self, inner, key: bytes | None = None):
        self.inner = inner
        self.key = key or AESGCM.generate_key(bit_length=256)     # lives only in this process
        self._aead = AESGCM(self.key)
        self.name = f"encrypted({inner.name})"

    def put(self, key: int, blob: bytes) -> None:
        nonce = os.urandom(12)
        self.inner.put(key, nonce + self._aead.encrypt(nonce, blob, struct.pack(">q", key)))

    def _open(self, key: int, sealed: bytes) -> bytes:
        try:
            return self._aead.decrypt(sealed[:12], sealed[12:], struct.pack(">q", key))
        except InvalidTag:
            raise PageIntegrityError(f"far page {key} failed authentication")

    def get(self, key: int) -> bytes:
        return self._open(key, self.inner.get(key))

    def get_many(self, keys):
        return [None if b is None else self._open(k, b) for k, b in zip(keys, self.inner.get_many(keys))]

    def delete(self, key: int) -> None:
        self.inner.delete(key)

    def close(self) -> None:
        self.inner.close()


class ReplicatedBackend:
    def __init__(self, replicas: list):
        if len(replicas) < 2:
            raise ValueError("replication needs at least two backends")
        self.replicas = replicas
        self.name = "replicated(" + ",".join(r.name for r in replicas) + ")"
        self.failovers = 0
        self.write_errors = 0

    def put(self, key: int, blob: bytes) -> None:
        ok = 0
        for r in self.replicas:
            try:
                r.put(key, blob)
                ok += 1
            except Exception:
                self.write_errors += 1
        if ok == 0:
            raise IOError(f"far page {key}: no replica accepted the write")

    def get(self, key: int) -> bytes:
        last = None
        for i, r in enumerate(self.replicas):
            try:
                b = r.get(key)
                if i:
                    self.failovers += 1
                return b
            except Exception as e:
                last = e
        raise IOError(f"far page {key}: all replicas failed ({last})")

    def get_many(self, keys):
        return [self.get(k) for k in keys]

    def delete(self, key: int) -> None:
        for r in self.replicas:
            try:
                r.delete(key)
            except Exception:
                pass

    def close(self) -> None:
        for r in self.replicas:
            try:
                r.close()
            except Exception:
                pass
