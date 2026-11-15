# Security policy

Spatial Computing is a research prototype. Its network components (`spatial serve compute`, `spatial serve memory`) **must not be exposed** to untrusted networks: the channel (SWP/2) is authenticated, encrypted (AES-256-GCM) and forward-secret (ephemeral X25519), and servers can issue scoped, expiring credentials with quotas and an audit log. None of this has had an independent security review.

## Reporting a vulnerability

Please use GitHub's private vulnerability reporting (Security tab, "Report a vulnerability") instead of a public issue. Include the version, how to reproduce, and the impact you expect.

## Known gaps

An independent review, certificate-based peer identity, a *signed* (not just hash-chained) audit log, durable revocation and usage counters, and hardening of the sandbox against a malicious binary are not done. They are listed in [ROADMAP.md](ROADMAP.md).
