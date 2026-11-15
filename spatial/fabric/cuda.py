"""NVIDIA backend through numba.cuda. WRITTEN BUT NEVER RUN ON REAL NVIDIA HARDWARE: this machine
has none. The planner treats this variant as unavailable unless numba reports a CUDA device, and the
first real run is test A2 in docs/TESTS_NOT_DONE.md."""
from __future__ import annotations


def available() -> bool:
    try:
        from numba import cuda
        return bool(cuda.is_available())
    except Exception:
        return False


def mandel(n: int, iters: int) -> int:
    import numpy as np
    from numba import cuda

    @cuda.jit
    def kern(out, n, iters):
        j, i = cuda.grid(2)
        if i >= n or j >= n:
            return
        ci = np.float32(-1.3) + np.float32(2.6) * np.float32(i) / np.float32(n)
        cr = np.float32(-2.0) + np.float32(2.6) * np.float32(j) / np.float32(n)
        zr = np.float32(0.0)
        zi = np.float32(0.0)
        k = 0
        while k < iters and zr * zr + zi * zi <= np.float32(4.0):
            t = zr * zr - zi * zi + cr
            zi = np.float32(2.0) * zr * zi + ci
            zr = t
            k += 1
        out[i, j] = k

    d = cuda.device_array((n, n), dtype=np.uint32)
    tpb = (16, 16)
    kern[((n + 15) // 16, (n + 15) // 16), tpb](d, n, iters)
    cuda.synchronize()
    return int(d.copy_to_host().astype(np.uint64).sum())
