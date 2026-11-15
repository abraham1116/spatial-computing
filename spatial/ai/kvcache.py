"""Toy causal transformer with a key/value cache, to MEASURE recompute versus restore.

A small random-weight decoder (NumPy, CPU). It is not a language model and its speed says
nothing about GPUs. It exists so the KV-cache mechanics are real and testable:
  * prefill(tokens) builds the per-layer K/V tensors;
  * continuing from a restored cache gives exactly the same logits as recomputing;
  * the cache can be parked in a TieredStore, so restore time and bytes are measured.
"""
from __future__ import annotations

import time

import numpy as np


class ToyTransformer:
    def __init__(self, layers: int = 4, d: int = 64, heads: int = 4, vocab: int = 256, seed: int = 0):
        rng = np.random.default_rng(seed)
        self.L, self.d, self.h, self.vocab = layers, d, heads, vocab
        g = lambda *s: (rng.standard_normal(s) / np.sqrt(s[0])).astype(np.float32)
        self.emb = g(vocab, d)
        self.W = [{k: g(d, d) for k in ("q", "k", "v", "o", "m1", "m2")} for _ in range(layers)]
        self.out = g(d, vocab)

    def _pos(self, i0: int, n: int) -> np.ndarray:
        pos = np.arange(i0, i0 + n)[:, None] / (10000 ** (np.arange(self.d)[None, :] / self.d))
        return np.sin(pos).astype(np.float32)

    def forward(self, tokens, cache: list | None = None):
        """Process `tokens` after the positions already in `cache`. Returns (logits of the last
        token, new cache). cache = [(K, V)] per layer, K and V of shape [positions, d]."""
        n0 = 0 if cache is None else cache[0][0].shape[0]
        x = self.emb[np.asarray(tokens)] + self._pos(n0, len(tokens))
        new, dh = [], self.d // self.h
        for li, w in enumerate(self.W):
            k_new, v_new = x @ w["k"], x @ w["v"]
            K = k_new if cache is None else np.concatenate([cache[li][0], k_new])
            V = v_new if cache is None else np.concatenate([cache[li][1], v_new])
            q = (x @ w["q"]).reshape(len(tokens), self.h, dh).transpose(1, 0, 2)
            Kh = K.reshape(-1, self.h, dh).transpose(1, 0, 2)
            Vh = V.reshape(-1, self.h, dh).transpose(1, 0, 2)
            att = q @ Kh.transpose(0, 2, 1) / np.sqrt(dh)
            mask = np.arange(K.shape[0])[None, :] > (n0 + np.arange(len(tokens)))[:, None]   # causal
            att = np.where(mask[None], np.float32(-1e30), att)
            att = np.exp(att - att.max(-1, keepdims=True))
            att /= att.sum(-1, keepdims=True)
            x = x + (att @ Vh).transpose(1, 0, 2).reshape(len(tokens), self.d) @ w["o"]
            x = x + np.maximum(x @ w["m1"], 0) @ w["m2"]
            x = x.astype(np.float32)          # keep the cache in one dtype (float32)
            new.append((K, V))
        return x[-1] @ self.out, new


def cache_to_pages(cache: list) -> list[bytes]:
    return [a.tobytes() for kv in cache for a in kv]


def cache_from_pages(pages: list[bytes], d: int) -> list:
    arrs = [np.frombuffer(p, dtype=np.float32).reshape(-1, d) for p in pages]
    return [(arrs[i], arrs[i + 1]) for i in range(0, len(arrs), 2)]


def measure_restore_vs_recompute(model: ToyTransformer, prefix, store, repeat: int = 3) -> dict:
    """Times, on this machine: recomputing the prefix cache versus restoring it from `store`."""
    t0 = time.perf_counter()
    _, cache = model.forward(prefix)
    recompute_s = time.perf_counter() - t0
    for _ in range(repeat - 1):
        t0 = time.perf_counter()
        model.forward(prefix)
        recompute_s = min(recompute_s, time.perf_counter() - t0)
    pages = cache_to_pages(cache)
    for i, p in enumerate(pages):
        store.put(i, p)
    restore_s = float("inf")
    for _ in range(repeat):
        t0 = time.perf_counter()
        restored = cache_from_pages([store.get(i) for i in range(len(pages))], model.d)
        restore_s = min(restore_s, time.perf_counter() - t0)
    return {"prefix_tokens": len(prefix), "cache_bytes": sum(map(len, pages)), "recompute_s": recompute_s,
            "restore_s": restore_s, "restore_faster": restore_s < recompute_s, "cache": cache, "restored": restored}
