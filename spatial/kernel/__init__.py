"""Portable kernels: write once in a typed Python subset, run on CPU (Numba), Metal, or emit CUDA C."""
from .dsl import Kernel, KernelError, kernel  # noqa: F401
from . import library  # noqa: F401
