from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class VoxelGrid:
    occupancy: np.ndarray        # bool [nx, ny, nz]
    origin: tuple[float, float, float]
    voxel_size: float

    @property
    def filled(self) -> int:
        return int(self.occupancy.sum())


def voxelize(points: np.ndarray, voxel_size: float) -> VoxelGrid:
    """Point cloud [N,3] -> occupancy grid."""
    lo = points.min(axis=0)
    idx = np.floor((points - lo) / voxel_size).astype(int)
    shape = tuple(idx.max(axis=0) + 1)
    occ = np.zeros(shape, dtype=bool)
    occ[idx[:, 0], idx[:, 1], idx[:, 2]] = True
    return VoxelGrid(occ, tuple(float(x) for x in lo), voxel_size)


@dataclass
class LightFieldSpec:
    """A multi-view (light-field) display: `views` distinct images per frame."""
    views_x: int
    views_y: int
    width: int
    height: int
    fps: float
    bytes_per_pixel: int = 3

    @property
    def pixels_per_second(self) -> float:
        return self.views_x * self.views_y * self.width * self.height * self.fps

    @property
    def raw_bytes_per_second(self) -> float:
        return self.pixels_per_second * self.bytes_per_pixel

    def vs_2d(self, width: int = 3840, height: int = 2160, fps: float = 60) -> float:
        """How many 2-D displays of the given format this represents in pixel rate."""
        return self.pixels_per_second / (width * height * fps)
