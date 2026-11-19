# In-vehicle multi-chip placement

`spatial.automotive.placement` applies this project's placement idea — one task,
several devices, lowest finish time — inside a vehicle instead of across a cloud.

## Why

A modern vehicle already runs several heterogeneous chips: a perception SoC, a
separate NPU, a general MCU. Per the DAVOS paper (arXiv 2601.05072, 2026),
today's vehicle software stacks make "resource management, data movement, and
scheduling decisions... independently across stacks" — no joint placement. The
HAL4SDV toolchain (DATE 2026) and a 2026 DRL-scheduling paper (<5 ms latency,
~40% power reduction on an automotive-grade heterogeneous platform) confirm this
is both a real, unsolved problem and one where placement choices measurably
matter. This module is the software side of that gap: a placement algorithm, not
a chip.

```bash
spatial automotive --file vehicle.json
```
```json
{
  "chips": [
    {"name": "mcu", "flops_per_s": 4e9, "power_w": 5.0},
    {"name": "npu", "flops_per_s": 2e9, "power_w": 15.0, "supports_npu": true}
  ],
  "tasks": [
    {"name": "camera_isp", "flops": 1e9},
    {"name": "segment", "flops": 2e9, "needs_npu": true, "after": ["camera_isp"]}
  ]
}
```

```python
from spatial.automotive import Chip, Task, place, makespan_s, total_energy_j
chips = (Chip("mcu", flops_per_s=4e9, power_w=5.0),
         Chip("npu", flops_per_s=2e9, power_w=15.0, supports_npu=True))
tasks = (Task("camera_isp", flops=1e9),
         Task("segment", flops=2e9, needs_npu=True, after=("camera_isp",)))
placements = place(tasks, chips)       # topological: dependencies, then earliest finish
makespan_s(placements)
total_energy_j(placements, chips)
```

## What this proves, and what it does not

It proves the placement algorithm is correct: dependency order is respected,
an NPU-only task never lands on a chip without one, and the choice among
eligible chips minimises finish time, all checked against known-by-hand
schedules in `tests/test_automotive.py`.

**It does not prove anything about a real vehicle.** There is no automotive
silicon here — same honesty as the generated-only CUDA/HIP/Triton kernel back
ends, which are never compiled or run. `flops_per_s` and `power_w` are inputs
you declare (a datasheet, or your own bench); this module never measures real
hardware and never claims a real-vehicle result. No safety certification
(ISO 26262 or otherwise) is implied.

## Limits

- Two resource dimensions only: raw throughput (`flops_per_s`) and a binary
  NPU requirement. No memory, bandwidth, thermal, or real-time deadline model.
- Power is `power_w x busy_time`, not a measured energy trace.
- No partial task splitting across chips, no data-transfer cost between chips.
