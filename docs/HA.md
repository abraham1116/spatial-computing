# Hub high availability, dashboard and alerts

## High availability (active / standby)
```bash
spatial serve hub --token-file t --port 7700 --name a --peer HOST_B:7700 --state-file a.json
spatial serve hub --token-file t --port 7700 --name b --peer HOST_A:7700 --state-file b.json
spatial agent --hub HOST_A:7700,HOST_B:7700 --token-file agent.tok        # a list: the active hub is used
spatial fleet status --hub HOST_A:7700,HOST_B:7700 --token-file ops.tok
```
With scoped credentials, give the peers a token with scope `fleet:replicate` (`--peer-token-file`).

How it works (`spatial/fleet/ha.py`):
- Every hub starts as a standby. A standby polls its peers every second; if one is active it copies its state (`snapshot`). If no peer is active for 6 s (`--fail-after`), it promotes itself: epoch + 1, running tasks requeued.
- A standby answers only `ping` and `role`. Agents and clients connect to the first address that says it is active.
- An active hub that sees a peer with a higher epoch (at equal epoch: a smaller name) steps down, adopts that hub's state and becomes a standby. A restarted old active hub therefore does not take back the role.

Measured (`benchmarks/bench_ha.py`, two hub processes and one agent on one Mac, `kill -9` on the active hub, 3 trials): a new active hub in 5.4 to 5.7 s, a task submitted before the kill finished on the survivor 6.7 s after the kill in all 3 trials. Startup until exactly one hub is active: about 6.9 s.

## Three or more hubs: majority election (v0.14.0)
With two or more `--peer` entries the hub uses `QuorumController` instead (`spatial/fleet/ha.py`):
```bash
spatial serve hub --token-file t --port 7700 --name a --peer B:7700 --peer C:7700 --state-file a.json
```
- Raft-style terms and votes: a hub that hears no leader for a timeout (6 s plus a per-name jitter) becomes a candidate, increments the term and asks the others for votes. A majority wins. At most one leader per term; a hub votes once per term (term and vote are saved in `<state-file>.term`).
- A leader serves requests only while it has heard from a majority within the last half of `--fail-after` (a lease), so a hub cut off from the others refuses requests (`no quorum`) before a new leader can be elected, provided clocks tick at about the same rate. It steps down after `--fail-after` without a majority.
- A candidate whose newest task id is older than the voter's cannot win.
- State still moves by snapshot polling from the leader: up to one poll (1 s) of recent changes can be lost at a failover. This is **election safety, not a replicated log**, and not a Raft implementation (no log, no membership changes).
- Tested (`tests/test_quorum.py`): one leader and followers copying its state; leader killed, new leader with the state, old leader rejoining as follower; a leader cut off from the majority stops serving, then steps down; no leader without a majority; a lagging candidate refused; term and vote surviving a restart; and a randomized run of 220 rounds with random crashes and restarts of 5 hubs (28 events, 5 terms with a leader, no term ever had two leaders). All on one machine with a simulated clock and real loopback connections: no real partitions, no clock skew, no network delay.

### The two-hub mode is not consensus
- No quorum, no lease. Under a network partition both hubs can be active; when they see each other again the lower epoch steps down and **its state is discarded**. Results recorded only on the losing side are lost; tasks that ran there may run again (workloads are pure functions, so that is safe).
- Up to one poll (1 s) of state is lost at a failover; tasks running at that time are requeued (at-least-once).
- Two hubs only were tested, on one machine, with a clean kill. No test with real network partitions, clock skew or more than two hubs.
- If you need guaranteed single leadership, put the hub state behind etcd or a Raft library instead.

## Dashboard
```bash
spatial dashboard --hub HOST:7700 --token-file ops.tok       # prints http://127.0.0.1:PORT/?key=...
```
A read-only page: nodes with CPU bars, alerts, recommendations (with the reminder that savings are estimates), tenants and queue, hub role and epoch. It is served on **127.0.0.1 only** (there is no option to bind elsewhere), needs the random key printed at start, rejects requests whose Host header is not loopback (DNS rebinding), accepts GET only and sends no cookies. The dashboard process holds the hub credential: give it a token with scope `fleet:read` only. To look at it from another machine, use an SSH tunnel; do not put it on a public address.

## Alerts
`spatial watch` and the dashboard turn recommendations of severity high (default; `--min-severity` changes it) into events: one `firing` when a condition appears, one `resolved` when it clears, no repeats. `--webhook URL` POSTs each event as JSON. **A webhook sends fleet data (node names, text of the alert) to that URL**: use a destination you control. Only http and https URLs are accepted.

## Limits
- Alerts come from the hub's heuristics (node silent, memory pressure, underused GPU...): no custom rules, no routing, no acknowledgement, no history beyond the last 200 events in memory.
- The dashboard polls every 3 s and keeps no history of measurements; it is a live view, not monitoring storage.
- Looked at in one browser (headless Chrome) on one Mac; not tested on phones or with many nodes (1,000 nodes would make a long table).
