"""Client for a real inference server that speaks the llama.cpp HTTP API (llama-server). Used to measure what the toy
KV-cache model only simulates: how much a cached prompt prefix really saves on a real model.

Only the standard library; the server is yours (a container, a local binary). Nothing is sent anywhere else.
"""
from __future__ import annotations

import json
import urllib.request


class LlmError(Exception):
    pass


class LlamaServer:
    def __init__(self, base_url: str = "http://127.0.0.1:8081", timeout: float = 600.0):
        if not base_url.startswith(("http://127.0.0.1", "http://localhost", "https://")):
            raise LlmError("refusing a plain-HTTP non-loopback server URL (use https or a loopback address)")
        self.base, self.timeout = base_url.rstrip("/"), timeout

    def _post(self, path: str, body: dict) -> dict:
        req = urllib.request.Request(self.base + path, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}, method="POST")
        try:
            return json.load(urllib.request.urlopen(req, timeout=self.timeout))
        except Exception as e:
            raise LlmError(f"{type(e).__name__}: {e}") from e

    def healthy(self) -> bool:
        try:
            return json.load(urllib.request.urlopen(self.base + "/health", timeout=5)).get("status") == "ok"
        except Exception:
            return False

    def complete(self, prompt: str, n_predict: int = 8, cache_prompt: bool = True, seed: int = 0) -> dict:
        """One greedy completion. Returns the text and the server's own timings (prompt tokens processed, cached
        tokens reused, milliseconds for the prompt and for the generated tokens)."""
        r = self._post("/completion", {"prompt": prompt, "n_predict": n_predict, "temperature": 0, "top_k": 1, "seed": seed,
                                       "cache_prompt": cache_prompt, "stream": False})
        t = r.get("timings", {})
        return {"text": r.get("content", ""), "prompt_tokens_processed": t.get("prompt_n"), "cached_tokens": t.get("cache_n", r.get("tokens_cached")),
                "prompt_ms": t.get("prompt_ms"), "predicted_n": t.get("predicted_n"), "predicted_ms": t.get("predicted_ms"),
                "total_prompt_tokens": r.get("tokens_evaluated")}
