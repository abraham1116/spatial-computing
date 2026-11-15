"""Spatial Simulation Engine — FIRST COMPONENTS ONLY.

An explicit 2-D heat-diffusion solver (NumPy and Numba variants producing the same field)
and a symplectic N-body integrator. No multiphysics, no digital twin.
"""
from .heat import step_numpy, step_numba, simulate, stable_dt  # noqa: F401
from . import nbody  # noqa: F401
