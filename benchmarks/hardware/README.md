# Hardware tests (ready to run, not yet run)

Scripts here need hardware or privileges that were not available when they were written. Each
one prints a JSON result and refuses to invent numbers: if the hardware is missing it says so
and exits with code 2. **None of them has run on the target hardware.** See
[`docs/TESTS_NOT_DONE.md`](../../docs/TESTS_NOT_DONE.md) for the full list, prerequisites and
acceptance criteria.

| Script | Needs | What it measures |
|---|---|---|
| `two_machines.py` | a second computer on the network | offload to a remote worker, remote page-server latency, over a real link |
| `gpu_node.py` | an NVIDIA GPU machine (Linux) | `spatial audit` GPU detection, matmul throughput, host-to-GPU bandwidth, prefill proxy, KV restore-vs-recompute inputs |
| `energy.sh` | administrator rights (`sudo powermetrics`) | package power during idle and during each compute strategy (macOS) |
