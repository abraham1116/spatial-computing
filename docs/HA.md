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

### This is not consensus
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
