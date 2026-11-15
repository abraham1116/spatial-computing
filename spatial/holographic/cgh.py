"""Computer-generated hologram (point-source method) and numerical reconstruction.

hologram(): complex field on the hologram plane from a cloud of point emitters,
            H(x, y) = sum_j a_j * exp(i k r_j) / r_j   (textbook Fresnel/Huygens model).
reconstruct(): angular-spectrum propagation of that field to a depth z; the intensity
            must peak where a point emitter sits. This is numerical optics on the CPU:
            it proves the synthesis maths, not a physical display (none exists here).
"""
from __future__ import annotations

import numpy as np


def hologram(points: np.ndarray, amplitudes: np.ndarray, n: int, pitch: float, wavelength: float) -> np.ndarray:
    """points [N,3] in metres (z > 0 in front of the plane); returns complex [n, n]."""
    k = 2 * np.pi / wavelength
    ax = (np.arange(n) - n / 2) * pitch
    X, Y = np.meshgrid(ax, ax, indexing="xy")
    H = np.zeros((n, n), dtype=complex)
    for (px, py, pz), a in zip(points, amplitudes):
        r = np.sqrt((X - px) ** 2 + (Y - py) ** 2 + pz ** 2)
        H += a * np.exp(1j * k * r) / r
    return H


def reconstruct(H: np.ndarray, z: float, pitch: float, wavelength: float) -> np.ndarray:
    """Back-propagate the hologram field by distance z (angular spectrum); returns intensity."""
    n = H.shape[0]
    fx = np.fft.fftfreq(n, d=pitch)
    FX, FY = np.meshgrid(fx, fx, indexing="xy")
    arg = 1 / wavelength ** 2 - FX ** 2 - FY ** 2
    kz = 2 * np.pi * np.sqrt(np.maximum(arg, 0))
    field = np.fft.ifft2(np.fft.fft2(H) * np.exp(-1j * kz * z) * (arg > 0))
    return np.abs(field) ** 2


def max_diffraction_angle(pitch: float, wavelength: float) -> float:
    """Half-angle (radians) a pixel pitch can diffract: sin(theta) = wavelength / (2 * pitch).
    Shows why holographic displays need sub-micron pixels for a wide field of view."""
    return float(np.arcsin(min(1.0, wavelength / (2 * pitch))))
