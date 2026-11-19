"""In-vehicle multi-chip workload placement.

Real, documented gap (not invented): a modern vehicle runs several heterogeneous
chips (a perception SoC, a separate NPU, a general MCU...) and, per published
research (DAVOS, arXiv 2601.05072, 2026), "resource management, data movement,
and scheduling decisions are made independently across stacks" today -- no
joint placement. This module applies the project's placement idea -- one task,
several devices, lowest finish time -- to that gap: given a task graph and a
declared chip catalogue, place each task on the chip that finishes it earliest
without violating dependency order.

Software only. There is no automotive silicon here to run anything on, same
honesty as the generated-only CUDA/HIP/Triton kernel back ends: chip throughput
and power numbers are declared inputs you supply (a datasheet, or your own
bench), never measured by this module and never presented as real-vehicle
results. No ISO 26262 or other safety certification claim is made.
"""

from dataclasses import dataclass


class PlacementError(Exception):
    pass


@dataclass(frozen=True)
class Chip:
    name: str
    flops_per_s: float
    power_w: float
    supports_npu: bool = False


@dataclass(frozen=True)
class Task:
    name: str
    flops: float
    needs_npu: bool = False
    after: tuple[str, ...] = ()


@dataclass(frozen=True)
class Placement:
    task: str
    chip: str
    start_s: float
    finish_s: float


def _eligible(task: Task, chips: tuple[Chip, ...]) -> tuple[Chip, ...]:
    out = tuple(c for c in chips if not task.needs_npu or c.supports_npu)
    if not out:
        raise PlacementError(f"no chip in the catalogue supports task {task.name!r} (needs_npu=True)")
    return out


def place(tasks: tuple[Task, ...], chips: tuple[Chip, ...]) -> tuple[Placement, ...]:
    """Topological placement: each ready task goes on the eligible chip that
    finishes it earliest, given its dependencies' finish times and when that
    chip is next free. Raises PlacementError on an unknown dependency, a cycle,
    an empty chip catalogue, or a task no chip in the catalogue can run."""
    if not chips:
        raise PlacementError("empty chip catalogue")
    by_name = {t.name: t for t in tasks}
    if len(by_name) != len(tasks):
        raise PlacementError("duplicate task name")
    for t in tasks:
        for dep in t.after:
            if dep not in by_name:
                raise PlacementError(f"task {t.name!r} depends on unknown task {dep!r}")
    free_at = {c.name: 0.0 for c in chips}
    finish_of: dict[str, float] = {}
    placed: dict[str, Placement] = {}
    remaining = dict(by_name)
    while remaining:
        ready = [t for t in remaining.values() if all(d in finish_of for d in t.after)]
        if not ready:
            raise PlacementError("dependency cycle among: " + ", ".join(sorted(remaining)))
        for t in ready:
            best = None
            for c in _eligible(t, chips):
                ready_at = max(free_at[c.name], max((finish_of[d] for d in t.after), default=0.0))
                finish = ready_at + t.flops / c.flops_per_s
                if best is None or finish < best[1]:
                    best = (c, finish, ready_at)
            chip, finish, start = best
            placed[t.name] = Placement(t.name, chip.name, start, finish)
            free_at[chip.name] = finish
            finish_of[t.name] = finish
            del remaining[t.name]
    return tuple(placed[t.name] for t in tasks)


def total_energy_j(placements: tuple[Placement, ...], chips: tuple[Chip, ...]) -> float:
    """Sum of power x busy-time per chip -- declared power, not measured."""
    power = {c.name: c.power_w for c in chips}
    return sum((p.finish_s - p.start_s) * power[p.chip] for p in placements)


def makespan_s(placements: tuple[Placement, ...]) -> float:
    return max((p.finish_s for p in placements), default=0.0)
