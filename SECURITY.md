# Security policy

Spatial Computing is a research prototype. Its network components (`spatial serve compute`, `spatial serve memory`) **must not be exposed** to untrusted networks: the channel is authenticated (HMAC token) but **not encrypted**.

## Reporting a vulnerability

Please use GitHub's private vulnerability reporting (Security tab, "Report a vulnerability") instead of a public issue. Include the version, how to reproduce, and the impact you expect.

## Known gaps

Channel and page encryption, per-user permissions, a signed audit log and a sandbox for arbitrary third-party workloads are not implemented. They are listed in [ROADMAP.md](ROADMAP.md).
