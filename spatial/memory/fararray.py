"""FarArray: a 1-D numeric array whose pages live in a TieredStore.

Lets a workload address more data than its local RAM budget. Access outside the
hot tier is slower by a measured amount; this is tiering, not extra RAM.
"""
from __future__ import annotations

import numpy as np

from .tiered import TieredStore


class FarArray:
    def __init__(self, store: TieredStore, length: int, dtype=np.float64, page_items: int = 8192):
        self.store, self.length = store, length
        self.dtype = np.dtype(dtype)
        self.page_items = page_items
        self.npages = (length + page_items - 1) // page_items

    @classmethod
    def from_chunks(cls, store: TieredStore, chunks, length: int, dtype=np.float64,
                    page_items: int = 8192) -> "FarArray":
        """Build from an iterator of arrays of exactly `page_items` items (last may be shorter)."""
        fa = cls(store, length, dtype, page_items)
        for i, c in enumerate(chunks):
            store.put(i, np.ascontiguousarray(c, dtype=fa.dtype).tobytes())
        return fa

    def page(self, i: int) -> np.ndarray:
        return np.frombuffer(self.store.get(i), dtype=self.dtype)

    def __getitem__(self, idx: int):
        return self.page(idx // self.page_items)[idx % self.page_items]

    def sum(self) -> float:
        return float(sum(self.page(i).sum() for i in range(self.npages)))

    def take(self, indices: np.ndarray) -> np.ndarray:
        out = np.empty(len(indices), dtype=self.dtype)
        pages = indices // self.page_items
        offs = indices % self.page_items
        for j in range(len(indices)):
            out[j] = self.page(int(pages[j]))[offs[j]]
        return out
