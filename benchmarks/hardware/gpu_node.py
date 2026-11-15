"""NVIDIA GPU node: detection, throughput, host<->GPU bandwidth, prefill proxy.

Needs a Linux machine with an NVIDIA GPU, the driver, and PyTorch with CUDA:
    pip install "spatial-computing" torch
    python3 benchmarks/hardware/gpu_node.py [--layers 32 --d 4096 --tokens 2048]

Outputs the inputs the private KV-cache policy needs (restore bandwidth to GPU memory, prefill
throughput) plus plain GPU numbers. It does NOT run a real language model: for that, run vLLM and
compare its prefix-cache behaviour with these measurements (see docs/TESTS_NOT_DONE.md, test G2).
"""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def need(msg):
    print(json.dumps({"ok": False, "error": msg}))
    sys.exit(2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--layers", type=int, default=32)
    ap.add_argument("--d", type=int, default=4096)
    ap.add_argument("--tokens", type=int, default=2048)
    a = ap.parse_args()
    try:
        import torch
    except ImportError:
        need("PyTorch is not installed")
    if not torch.cuda.is_available():
        need("no CUDA GPU visible to PyTorch")
    from spatial.compute.detect import detect_node
    node = detect_node()
    dev = torch.device("cuda")
    props = torch.cuda.get_device_properties(0)
    out = {"gpu": props.name, "vram_bytes": props.total_memory, "torch": torch.__version__,
           "audit_gpus": [(r.name, r.available) for r in node.resources if r.kind.value == "gpu"]}

    def timed(fn, reps=10):
        fn(); torch.cuda.synchronize()
        t = time.perf_counter()
        for _ in range(reps):
            fn()
        torch.cuda.synchronize()
        return (time.perf_counter() - t) / reps

    for dt, name in ((torch.float32, "fp32"), (torch.float16, "fp16"), (torch.bfloat16, "bf16")):
        n = 8192
        x, y = torch.randn(n, n, device=dev, dtype=dt), torch.randn(n, n, device=dev, dtype=dt)
        s = timed(lambda: x @ y)
        out[f"matmul_{name}_tflops"] = 2 * n ** 3 / s / 1e12
    for pinned in (False, True):                                    # restore path of a KV cache: host -> GPU
        buf = torch.empty(512 * 2 ** 20, dtype=torch.uint8, pin_memory=pinned)
        g = torch.empty_like(buf, device=dev)
        s = timed(lambda: g.copy_(buf, non_blocking=pinned), reps=5)
        out[f"host_to_gpu_GBps_{'pinned' if pinned else 'pageable'}"] = buf.numel() / s / 1e9
    layers = [torch.nn.Linear(a.d, a.d, bias=False).to(dev).half() for _ in range(a.layers)]
    x = torch.randn(a.tokens, a.d, device=dev, dtype=torch.float16)

    def prefill():
        h = x
        with torch.no_grad():
            for L in layers:
                h = torch.relu(L(h))
    s = timed(prefill, reps=3)
    out["prefill_proxy"] = {"layers": a.layers, "d": a.d, "tokens": a.tokens, "seconds": s, "tokens_per_s": a.tokens / s,
                            "note": "dense layers only, no attention: a proxy, not a model"}
    try:
        out["nvidia_smi"] = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total,utilization.gpu,power.draw",
                                            "--format=csv,noheader"], capture_output=True, text=True, timeout=20).stdout.strip()
    except Exception:
        pass
    print(json.dumps(out, indent=1))
    Path("benchmarks/results").mkdir(parents=True, exist_ok=True)
    Path("benchmarks/results/gpu_node.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
