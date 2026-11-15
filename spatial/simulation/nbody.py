"""Gravitational N-body with a leapfrog (kick-drift-kick) integrator. Symplectic: total
energy oscillates but does not drift, which the test checks."""
from __future__ import annotations

import numpy as np


def accelerations(pos: np.ndarray, mass: np.ndarray, soft: float = 1e-3) -> np.ndarray:
    d = pos[None, :, :] - pos[:, None, :]
    r2 = (d ** 2).sum(-1) + soft ** 2
    np.fill_diagonal(r2, np.inf)
    return (d * (mass[None, :, None] / r2[..., None] ** 1.5)).sum(1)


def energy(pos, vel, mass, soft: float = 1e-3) -> float:
    kin = 0.5 * (mass * (vel ** 2).sum(-1)).sum()
    d = pos[None] - pos[:, None]
    r = np.sqrt((d ** 2).sum(-1) + soft ** 2)
    iu = np.triu_indices(len(mass), 1)
    return float(kin - (mass[iu[0]] * mass[iu[1]] / r[iu]).sum())


def leapfrog(pos, vel, mass, dt: float, steps: int, soft: float = 1e-3):
    pos, vel = pos.copy(), vel.copy()
    a = accelerations(pos, mass, soft)
    for _ in range(steps):
        vel += 0.5 * dt * a
        pos += dt * vel
        a = accelerations(pos, mass, soft)
        vel += 0.5 * dt * a
    return pos, vel
