# The infrastructure

What Spatial Computing is made of, how the parts talk, and what each one does and does not do. Status: v0.9.0, validated on one machine (see [TESTS_NOT_DONE.md](TESTS_NOT_DONE.md)).

## One objective

Every decision in this infrastructure answers the same question: **get the job done correctly at the lowest cost in dollars, within stated constraints, and prove it.** The planner (`spatial.unified`, `spatial optimize`) asks each engine for priced options and ranks them with one formula; the fleet hub's placement and recommendations use the same prices. See [OBJECTIVE.md](OBJECTIVE.md).

## One picture

```
                       operators (CLI: spatial fleet ...)
                                   |  fleet:read / fleet:submit
                                   v
   machine 1            +--------------------------+            machine N
 +-----------+  report  |   HUB                    |  report  +-----------+
 |  agent    |--------->|  nodes + time series     |<---------|  agent    |
 |  (measure |   poll   |  task queue + placement  |   poll   |           |
 |   + run   |<---------|  recommendations         |--------->|           |
 |  allow-   |  result  |  decision log (chained)  |  result  |           |
 |  listed   |--------->|  audit log (chained)     |<---------|           |
 |  tasks)   |          +--------------------------+          +-----------+
 +-----------+     all links: SWP/2 (AES-256-GCM, X25519, scoped credentials)
      |
      +-- local engines: compute (strategies), tiered memory, runtime (micro-VM/WASM/Wine),
          SPATIAL Q (classical + quantum), AI / scientific / simulation / intelligence / holographic
```

## Components

| Component | Role | Where |
|---|---|---|
| **Agent** | Runs on every machine. Measures CPU, RAM, swap, memory pressure and NVIDIA GPUs every few seconds, reports to the hub, asks the hub for work and runs it. Outbound connections only: it never listens. Keeps measurements in a ring buffer while the hub is down and delivers them, with their own timestamps, on reconnection. | `spatial.fleet.agent`, `spatial agent` |
| **Hub** | Stores the fleet's measurements, queues and places tasks, computes utilization and recommendations, logs every placement. Never changes a machine by itself. | `spatial.fleet.hub`, `spatial serve hub` |
| **Fleet CLI** | `spatial fleet status / advise / submit / result`: the operator's view. | `spatial.cli` |
| **Engines** | What runs on a machine: strategy comparison and cost (compute), tiers (memory), isolation (runtime), hybrid programs (SPATIAL Q), and the AI, scientific, simulation, intelligence and holographic components. | `spatial/*` |
| **Core** | Shared data model, the SWP/2 protocol, scoped credentials with quotas and revocation, hash-chained ledgers, engine status registry. | `spatial.core` |

## How a decision is made

1. Agents report: CPU %, cores, RAM free, GPU utilization, optional cost per hour (given by the operator).
2. The hub keeps a window of samples per node.
3. **Placement** is pull-based work stealing with rules: a node asks for work; it receives the best queued task it is *eligible* for (needs: GPU, minimum free RAM, label, pinned node); a node at 90 % CPU or more receives nothing. Order: the tenant with the lowest weighted usage first (fair share; a tenant is the credential name with scoped credentials), then priority, then arrival. A task with `needs: {affinity: key}` waits `affinity_wait_s` (default 5 s) for the node that last ran that key (a cache-affinity rule in the spirit of KV-aware routing), then anyone may take it. `submit_gang` queues a group that starts only when enough ready nodes exist for every member: the first start holds the other nodes for `gang_hold_s` (default 30 s). Tested with injected clocks and metrics; not stress-tested. Fair share uses one resource (compute-seconds), not DRF over several. Nothing running is ever preempted: agents execute tasks synchronously. Every placement is written to the decision log with its reason.
4. **Recommendations** come from the window: node down, memory pressure, underused GPUs, rebalance (a busy node next to an idle one), consolidation (the fleet's busy cores would fit on fewer nodes at a 60 % target, with RAM checked). Each recommendation shows its evidence and its assumptions. Cost estimates appear only if the operator gave prices.
5. **Proof**: a recommendation is an estimate. It becomes a result only when it is applied by the operator and the fleet is measured again (`spatial fleet status` before and after).

## Security model

- Encrypted, authenticated, forward-secret transport (SWP/2). Nothing travels in clear.
- Identity = the credential: with scoped credentials an agent cannot report as another node.
- Scopes: `fleet:report`, `fleet:work` (agents); `fleet:submit`, `fleet:read` (operators). An agent cannot read the fleet or submit tasks; a reader cannot inject measurements.
- Agents run only **allow-listed workloads** by name. No code travels to an agent. (The sandboxed runner, a separate service, is the only component that accepts a binary, and only inside a micro-VM.)
- Quotas, expiry, revocation, and an audit log (hash-chained, thread-safe within a process).
- Not independently reviewed. Not for untrusted networks.

## What was measured

| Measurement | Result (one 2017 MacBook Pro, loopback) |
|---|---|
| 12 identical tasks, 1 agent versus 3 agents placed by the hub | 7.2 s versus 4.3 s (x1.66; 1.79 in the first run) |
| Results equal to the reference | 12 of 12, both scenarios |
| Placement among the 3 agents | 6, 4 and 2 tasks |
| Decision log and audit log chains | intact |
| Agent offline then back | buffered measurements delivered in order, with their original times (test) |

The three agents ran on **one machine**, so the speed-up is bounded by its cores, and the hub sees three nodes that all report the same CPU load. This validates the chain (identity, scopes, placement, results, audit), not scaling.

## Limits

- Hub is a single process with in-memory state: no persistence of the time series, no high availability, no clustering.
- No dashboard UI (command line and JSON only).
- Recommendations are heuristics on CPU, RAM and GPU utilization; they know nothing about the applications' real requirements.
- Placement is pull-based and does not move running work.
- Agents measure NVIDIA GPUs through `nvidia-smi` only; never run on a real NVIDIA machine.
- Validated with up to 3 agents on one machine. Nothing is known about 100 or 1,000 nodes.
