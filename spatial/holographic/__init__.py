"""Spatial Holographic Engine — INTERFACE ONLY.

No display hardware exists in this project and no hologram is synthesised. This package
only fixes the data model (voxel grid, light-field specification) and computes the data
rates such displays would demand from the compute engine, so the requirement is explicit.
"""
from .model import VoxelGrid, LightFieldSpec, voxelize  # noqa: F401
