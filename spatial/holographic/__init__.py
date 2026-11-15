"""Spatial Holographic Engine — FIRST COMPONENTS (numerical only).

No display hardware exists in this project. cgh.py synthesises a point-cloud hologram and
reconstructs it numerically (verified by a test); the rest fixes the data model (voxel grid, light-field specification) and computes the data
rates such displays would demand from the compute engine, so the requirement is explicit.
"""
from .model import VoxelGrid, LightFieldSpec, voxelize  # noqa: F401
from .cgh import hologram, reconstruct, max_diffraction_angle  # noqa: F401
