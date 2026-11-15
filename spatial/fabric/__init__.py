"""Virtual accelerator fabric: describe a job once, run it on whichever device is cheapest.

Devices today: the CPU (Numba), a Metal GPU (macOS, compiled on first use), an NVIDIA GPU through
numba.cuda (code present, NEVER RUN on real NVIDIA hardware). This is not CUDA emulation and not
a translation layer: each device runs its own native implementation of the same job, and the
planner chooses by measured cost. See docs/FABRIC.md.
"""
from .devices import Device, discover  # noqa: F401
