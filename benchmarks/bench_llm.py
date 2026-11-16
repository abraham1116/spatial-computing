"""TEST H-8 / E1 — a REAL model behind a real inference server (llama.cpp's llama-server in a container, Qwen2.5-0.5B
Q4, CPU only): what does reusing a cached prompt prefix really save, and does it change the answer?
Method: one long shared prefix (a document) and several different questions. Each question is asked
(a) with prefix caching OFF (the whole prompt is recomputed), (b) with caching ON after the prefix was seen once.
Start the server first:  docker run -d -p 127.0.0.1:8081:8080 -v llmdata:/models ghcr.io/ggml-org/llama.cpp:server -m /models/model.gguf --host 0.0.0.0 -c 4096 -t 2
"""
from __future__ import annotations

import statistics
import sys

from common import save
from spatial.ai.llm import LlamaServer

DOC = ("Spatial Computing is a control layer for compute infrastructure. It measures machines, prices every way to run a job, "
       "chooses the cheapest option that stays correct, and records the estimate beside what really happened. " * 24)
QUESTIONS = ["Question: what does it measure? Answer:", "Question: what does it choose? Answer:", "Question: what does it record? Answer:",
             "Question: what does it price? Answer:", "Question: what stays correct? Answer:"]


def main():
    srv = LlamaServer(sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8081")
    if not srv.healthy():
        raise SystemExit("no llama-server answering: see the docstring for how to start one")
    prefix = DOC + "\n\n"
    srv.complete("warm up", 2, cache_prompt=False)
    rows, same = [], 0
    for q in QUESTIONS:
        off = srv.complete(prefix + q, 8, cache_prompt=False)                      # full recompute
        srv.complete(prefix + "Question: hello? Answer:", 1, cache_prompt=True)     # make sure the prefix is cached
        on = srv.complete(prefix + q, 8, cache_prompt=True)
        same += off["text"] == on["text"]
        rows.append({"question": q, "total_prompt_tokens": off["total_prompt_tokens"], "recompute_prompt_ms": off["prompt_ms"], "recompute_tokens": off["prompt_tokens_processed"],
                     "cached_prompt_ms": on["prompt_ms"], "cached_tokens_reused": on["cached_tokens"], "tokens_recomputed_with_cache": on["prompt_tokens_processed"],
                     "same_text": off["text"] == on["text"]})
        print(f"{rows[-1]['total_prompt_tokens']} prompt tokens: recompute {off['prompt_ms']:.0f} ms ({off['prompt_tokens_processed']} tokens)  "
              f"cached {on['prompt_ms']:.0f} ms ({on['prompt_tokens_processed']} tokens, {on['cached_tokens']} reused)  same answer: {off['text'] == on['text']}", flush=True)
    med = lambda k: statistics.median(r[k] for r in rows)
    out = {"model": "Qwen2.5-0.5B-Instruct Q4_K_M (llama.cpp server, CPU, 2 threads, in a VM on a 2017 MacBook Pro)", "rows": rows,
           "median_recompute_ms": med("recompute_prompt_ms"), "median_cached_ms": med("cached_prompt_ms"),
           "speedup_prompt_phase": med("recompute_prompt_ms") / max(1e-9, med("cached_prompt_ms")), "same_answer": f"{same}/{len(rows)}"}
    print(f"median prompt phase: recompute {out['median_recompute_ms']:.0f} ms, cached {out['median_cached_ms']:.0f} ms (x{out['speedup_prompt_phase']:.1f}); identical answers {out['same_answer']}")
    save("llm_kvcache", out)


if __name__ == "__main__":
    main()
