# Changelog

## 0.20.0
- Kernel DSL: `batch_score`, a batch-scoring kernel (planner family `pk_batch_score`) — the same per-element placement problem as `mandelbrot`/`collatz`, applied to a batch-scoring shape (fraud/risk, ranking, recommendation, anomaly detection: any software that scores many independent items in a batch or a stream). Synthetic signals and weights, no trained model, no real data: it demonstrates that the planner places and measures a batch-scoring job exactly like it places a scientific kernel, on CPU and Metal, generated for CUDA/HIP/Triton too. Added to the console's curated job catalogue (`pk_batch_score_cpu`).
- Positioning: the planner's "one job, lowest measured cost" placement is not scientific-kernel-only; it is the same placement problem for any software that scores items in batch, independent of what domain the numbers represent.
- 260 tests (was 259).

## 0.19.0
- Kernel DSL: Triton back end (`to_triton()`), generated only, like CUDA and HIP: no NVIDIA, AMD, or Intel GPU and no `triton` package here, so this source has never been passed to `triton.jit`, compiled, or run. One Triton "program" per output pixel, same shape as the CUDA back end. Integer `//` truncates toward zero via a float32 cast (Triton's own `//` floors like Python); `and`/`or` become `&`/`|` after boolifying each side (tensors have no short-circuit evaluation); no reduction variant (Triton's cross-program reduction does not map onto the single-pass shared-memory shape the other back ends use). `run()`/`reduce()` refuse `"triton"` honestly, the same way they already refused `"cuda"`/`"hip"`; `"hip"` now gets the same honest message from `run()` too (it previously fell through to a generic "unknown device"). `tl`, `triton`, `out_ptr` added to the reserved names.
- 259 tests (was 257).

## 0.18.0
- Invoices: legal mentions by seller country (FR, DE, ES, IT, NL, BE, GB checklist: registration number, legal form, share capital, tax number), localized reverse-charge phrase, due date and service period, payment details (IBAN validated by its check digits, BIC), payment terms, French late-payment mentions; the operator warning names what is missing for the seller's country.
- E-invoicing: `GET /api/invoices/{id}/ubl` and `/api/credit-notes/{id}/ubl` return UBL 2.1 XML with the Peppol BIS 3.0 / EN 16931 identifiers. Generated files validate against the official OASIS UBL 2.1 schemas (in `tests/data/ubl`). Not checked against the Peppol Schematron business rules and not sent through any network (no Peppol access point, no Chorus Pro, no Factur-X).
- Customers: city, postal code and billing e-mail on the organization's billing details.
- Roles: per-app scope on members and invitations (a member limited to some apps sees only those; the others answer 404); Team page shows and edits it.
- Console service: `--embedded-hub` runs the fleet hub in the same process (one container, one command); `HUB_MASTER_KEY` environment variable for hosts that give secrets only that way; `--smtp-ca-file` for a private relay (certificates are always verified). Fly and Render templates in `deploy/`, **untested**.
- Remote desktop: `d.upload()` / `d.download()` and `spatial desktop --upload FILE` (single files, 16 MiB, safe names); `xcalc` added.
- Tests against real servers started in containers: Mailpit (SMTP, STARTTLS, login, certificate and password failures), stripe-mock (Stripe's own mock: checkout session and refund requests), Dex (a real OpenID Connect provider: authorization code with PKCE, RS256 verification against its keys, single-use state).
- SAML is deliberately not implemented: put an OpenID Connect broker (Dex, Keycloak) in front of your SAML identity provider.
- Full suite: 256 passed, 1 skipped.

## 0.17.0
- Console: OpenID Connect single sign-on (PKCE, RS256 verification); custom roles built from permissions with a no-escalation rule; VAT-number validation (format and check digits, optional VIES); credit notes with PDF and Stripe refunds; operator warnings; QR code for two-factor setup (own encoder, checked against the `qrcode` library module for module).
- Remote desktop: clipboard switch and a view-only password (`--no-clipboard`, `--view-link`), verified with a real RFB client.
- 61 platform tests (was 33); the full suite is 242 tests.

## 0.16.0
- Console: organizations with four roles and e-mailed invitations, an organization switcher, a Team page; two-factor sign-in (TOTP + recovery codes); e-mail verification; operator-set prices and tax in Admin (stored, validated, invoices keep issued prices); tax by customer country with a simplified reverse charge; gap-free numbered invoices with PDF; billing details; SMTP mail queue with retries; per-user and per-token rate limits; pagination; database migration of older versions.
- Remote desktop: `spatial.runtime.desktop` runs xterm, xclock or mousepad in a container and serves it through noVNC (loopback only, one-time password, no capabilities, read-only root).
- CLI: `spatial desktop`. 33 platform tests (was 18), plus a desktop test.

## 0.15.0
- New: console and account service (`spatial platform serve`): sign up / sign in / reset, apps linked to the fleet (tenant `appN`), API keys as scoped hub credentials shown once and revocable on the running hub, usage metering from the hub's `--usage-file`, free allowance and invoices, Stripe Checkout with a signed webhook (never marked paid without it), single-page console. 14 tests plus a driven browser session. See `docs/PLATFORM.md`.
- Console v2: Overview with a get-started checklist, Apps with tabs (Overview, Keys, Connect, Jobs, Settings), Jobs (curated workload catalogue with bounds), Fleet (your nodes and queue from the hub), API keys, Usage & billing, Settings (Profile, Security with sessions, Account tokens for a REST API, Activity, Data export and deletion), Admin. New app and new key open in place instead of redirecting. Docs and landing aligned: Console and REST API pages, "Get started" leads to sign-up when a console URL is configured.
- Podman 5.8.10 passes the container-route tests as well as Docker.
- Hub: `--usage-file`, `--revoked-file`; tenant is the part of the credential name before `:`.
- Production layout: `Dockerfile`, `docker-compose.yml` (hub, console, Caddy HTTPS), `deploy/`, `docs/DEPLOY.md`.
- Site: Console page, optional Sign in link (`CONSOLE_URL` at build time).
- Runtime: the `container` route now runs (static Linux ELF in Docker or Podman, read-only root, no network, no capabilities, non-root, memory and process limits; opt-in network and a shared folder copied in and back). Only a daemon that answers counts as available.
- `spatial serve hub` forwards the hub's own flags (`--state-file`, `--usage-file`, `--revoked-file`, `--peer`...): they were documented but rejected before (found while building the Docker image).
- AI: `spatial.ai.llm` client for a llama.cpp server; `benchmarks/bench_llm.py` measured prefix-cache reuse on a real model (946-token prompt: at least x41 on the prompt phase, identical answers 5 of 5).
- Wine: a graphical app window was seen (Notepad); helper `benchmarks/hardware/wine_windows.swift`.

## 0.14.0
- Hub: majority election for three or more hubs (`QuorumController`: terms, votes, lease, term file; election safety, not a replicated log).
- Hub: finished tasks and cache-affinity keys are capped (`--max-finished`, default 5,000). The soak test showed unbounded growth (+12.5 MiB/h) before.
- Kernels: whole-grid reductions with threadgroup shared memory on Metal (exact for integers), CPU reduction, HIP source generation, reserved-name checks.
- `benchmarks/soak.py` and `benchmarks/verify.py` with a weekly `verify.yml` workflow.
- Site: new pages Accelerators, Interconnect, Operations, Roadmap, Changelog in English and French; dashboard screenshot.

## 0.13.0
- Hub high availability: `--peer` / `--name` start an active/standby pair; the standby copies the state, promotes itself after 6 s of silence (epoch + 1), and agents and CLI accept `h1:p,h2:p`. A returning old active hub steps down. Measured about 6.7 s from `kill -9` to a task finishing on the survivor. No consensus: see `docs/HA.md`.
- Dashboard: `spatial dashboard` (read-only, 127.0.0.1 only, random key, Host check) and alerts: `spatial watch`, edge-triggered, optional webhook.
- Hub ops: `role`, `snapshot` (scope `fleet:replicate`), `queue`.

## 0.12.2
- Planner: when the two reduced probes cannot separate a fixed start-up cost from the per-unit speed (a flat or negative slope), it now probes once more at half size instead of scaling proportionally from the larger probe, which could overestimate a GPU's cost by up to the scale ratio. Seen as a flaky CPU-instead-of-GPU choice on a shared CI Mac; decision quality on the reference Mac unchanged (fabric 7 of 7).

## 0.12.1
- Protocol: handshake timeout (a silent peer used to hold a thread forever), 512-connection cap, listen backlog 1,024 (the default of 5 refused simultaneous reconnects), malformed authenticated records no longer kill the handler thread.
- Hub: `--state-file` persistence with atomic snapshots; running tasks requeued after a restart; late results accepted.
- New tests and benchmarks: `tests/test_hardening.py`, `benchmarks/bench_scale.py` (100, 300, 1,000 simulated agents), interconnect at N=6 and N=16.

## 0.12.0
- New: virtual interconnect (`spatial.interconnect`): ring, halving-doubling and tree all-reduce plus broadcast between processes over SWP/2, with an alpha-beta cost model. Measured: the shared-link model picked the fastest algorithm in 1 of 6 sizes; calibrated per algorithm, 4 of 6 on an unseen rank count. About 3,000x below NVLink 5 on bandwidth (vendor figure).
- New: portable kernels (`spatial.kernel`): one kernel source, Numba CPU, generated Metal and generated CUDA C (CUDA never run). Integer kernel bit-identical on CPU and Metal; planner families `pk_mandel` and `pk_collatz` (4 of 6 device choices right).
- Fleet hub: weighted fair share between tenants, all-or-nothing gang scheduling with node holds, cache-affinity routing. Still pull-based: nothing running is preempted.
- Docs: `docs/INTERCONNECT.md`, `docs/KERNELS.md` (includes why ZLUDA is not used).

## 0.11.0
- New: virtual accelerator fabric. The same job (`mandel_f32`) has CPU, Metal GPU and NVIDIA (`numba.cuda`, never run on real hardware) implementations; the planner picks by measured cost. 7 of 7 device choices correct on the reference Mac (CPU up to n = 600, Metal GPU from n = 1024). `spatial devices` lists the devices.
- Per-device prices (`Prices.device_usd_h`).
- Docs: `docs/FABRIC.md`.

## 0.10.0
- New: one objective for every engine. `spatial.unified.Planner` and `spatial optimize`: each engine proposes priced options for a job (compute/simulation/scientific/holographic families, fleet nodes, tiered memory, runtime routes, quantum backends, AI cache); one function ranks them by cost within the stated constraints; executing a plan records the estimate beside reality and calibrates the next one.
- Science, simulation and holographic workloads (heat, N-body, hologram, option pricing, ODE) join the allow-list, so the planner and the fleet can run them.
- Decision quality measured by running every option: 12 of 13 tuning cases and 12 of 12 held-out cases picked the truly fastest option (`benchmarks/bench_unified.py`).
- Docs: `docs/OBJECTIVE.md`.

## 0.9.0
- New: Spatial Fleet. `spatial agent` measures a machine continuously and runs allow-listed tasks; `spatial serve hub` stores the fleet's measurements, places tasks, and produces recommendations with evidence; `spatial fleet status|advise|submit|result`.
- Fix: the hash-chained ledger could break under concurrent writers (one thread per connection). Now locked; test added.
- Docs: `docs/INFRASTRUCTURE.md`.

## 0.8.0
- Core: SWP/2 with forward secrecy (ephemeral X25519 mixed with the secret); scoped credentials with expiry, quotas, revocation and a hash-chained audit log (`spatial token init|issue`, `--master-key-file` on every service).
- SPATIAL Q: commutation-aware optimizer rules, fuzz-tested.
- Benchmarks: CPU runs repeated 9 and 7 times with quartiles; new 24 GiB dataset-larger-than-RAM test.
- Docs: `docs/TESTS_NOT_DONE.md` and ready-to-run hardware scripts in `benchmarks/hardware/`.
- CI: Python 3.10, 3.11 and 3.13 added.

## 0.7.0
- SPATIAL Q: asymmetric readout error in the simulator (`readout=(p01, p10)`), motivated by real hardware data.
- Benchmark `bench_qpu.py`: one batched IBM job, ideal / depolarising / readout models fitted and compared (`docs/QPU.md`).

## 0.6.1
- Fix: the `qpu` backend now raises a clear BackendUnavailable when `qiskit-ibm-runtime` is not installed.

## 0.6.0
- SPATIAL Q: real QPU backend for IBM Quantum (`qpu` extra); refuses with the real reason when the token or instance is missing.
- Landing page reorganised around the seven engines and the shared core, with one measured proof per engine.
- Published on PyPI.

## 0.5.0
- Memory: several writers on shared pages (versioned compare-and-swap on the page server).
- SPATIAL Q: QIR adaptive profile for dynamic circuits; classical part compiled to Python bytecode (`--compiled`).
- Docs: `docs/LIMITATIONS.md`, current and in English.

## 0.4.0
- A real, tested component in every engine: AI (toy transformer with KV cache, restore vs recompute through the tiered store), Scientific (RK4 job), Simulation (N-body), Intelligence (predictor drives the scheduler), Holographic (hologram synthesis and numerical reconstruction).
- Runtime: Windows console binary verified under Wine.

## 0.3.0
- Runtime: sandboxed remote runner (`spatial serve runtime`), Linux ELF only, always inside a micro-VM; Wine route picks up a user-level Wine build.
- SPATIAL Q: OpenQASM 2 export (`spatial q qasm2`), shot cost from caller-supplied prices.
- Compute: `nvidia-smi` GPU detection (parser tested, not run on real hardware), `cost` objective in the scheduler.

## 0.2.0
- Core: SWP/1 encrypted protocol (AES-256-GCM), hash-chained ledger.
- Compute: priority task queue across workers with re-queue on failure.
- Memory: encrypted and replicated far tier.
- Runtime: read-only input files in the micro-VM.
- SPATIAL Q: sub-kernels with qubit parameters, depolarising noise, QIR base-profile export.

## 0.1.0
- First public release.
