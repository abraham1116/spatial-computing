# Security policy

Spatial Computing is a research prototype. Its network components (`spatial serve compute`, `spatial serve memory`) **must not be exposed** to untrusted networks: the channel is authenticated and encrypted (AES-256-GCM keyed from the shared token) but has **no forward secrecy** and no per-user identity.

## Reporting a vulnerability

Please use GitHub's private vulnerability reporting (Security tab, "Report a vulnerability") instead of a public issue. Include the version, how to reproduce, and the impact you expect.

## Known gaps

Forward secrecy, per-user permissions, a signed audit log and a sandbox for arbitrary third-party workloads are not implemented. They are listed in [ROADMAP.md](ROADMAP.md).
