"""Spatial Simulation Engine — FIRST COMPONENTS ONLY.

One explicit 2-D heat-diffusion solver (NumPy and Numba variants producing the same
field), used to exercise the compute engine. No multiphysics, no digital twin.
"""
from .heat import step_numpy, step_numba, simulate, stable_dt  # noqa: F401
