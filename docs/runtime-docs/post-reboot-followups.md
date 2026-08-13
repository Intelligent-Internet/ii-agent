# Post-Reboot Follow-Up Ledger

**Created:** 2026-04-23 after the WSL2 force-reboot incident.
**Purpose:** Track deferred mitigations surfaced during the pre-reboot log analysis. Revisit after further research / discussion.

## Incident one-liner

On 2026-04-23 between 10:50 and 11:33 the WSL2 guest became progressively unresponsive and had to be force-power-cycled by `wsl.exe`. Root cause: three kernel `order:7` page-allocation failures (contiguous 512 KB memory) driven by veth/bridge churn from sandbox lifecycle operations. One sandbox container got stuck during teardown because its network-namespace cleanup needed contiguous memory the kernel could not produce, dockerd held the container lock, and the backend (which issued synchronous Docker calls on the asyncio event loop) inherited the stall. The app appeared hung across the board even though only one container was actually sick.

See the prior conversation investigation for the full timeline. Phase 2 backend fixes (bounded executor + 8s timeouts, per-sandbox circuit breaker, TTL cache on `sandbox_status`, fail-fast `DockerSandbox.connect()`, startup reconciliation, 5 new orphan-cleanup phases) are **already landed**. This ledger tracks what was *not* done.

## Status key

| Symbol | Meaning |
|---|---|
| [ ] | Not started |
| [~] | Researching / discussing |
| [x] | Implemented |
| [!] | Blocked or needs decision |

---

## 1. Cap concurrent sandbox creation with an `asyncio.Semaphore`

**Status:** [ ]
**Priority:** High
**Category:** Backend

**Problem:** Pool warming + user traffic can kick off multiple `docker.containers.run()` calls simultaneously. Each one demands a large contiguous kernel allocation for veth setup. Parallel veth creation is the primary driver of `order:7` fragmentation pressure.

**Proposed fix:**

- Add `sandbox_concurrent_create_limit` setting (default **2**).
- Wrap sandbox creation in `agents/sandboxes/service.py::create_sandbox` with an `asyncio.Semaphore`.
- Expose the semaphore state as a log counter so we can confirm contention.

**Risk:** Longer wait times when the pool is cold. Mitigated by the pre-warmed pool: users typically get a pre-warmed sandbox, not a freshly-created one.

**Discussion notes:**

- Should the limit be adaptive (scale down when buddyinfo shows pressure)? Probably not in v1 — fixed limit is simpler and testable.

---

## 2. Shared sandbox bridge network (was Fix #12 in Phase 2)

**Status:** [~]  — User support confirmed 2026-04-23, scope under discussion
**Priority:** High
**Category:** Docker topology + backend

**Problem:** Each sandbox today joins the compose `ii-agent-local_default` bridge or spins its own bridge scaffolding. Teardown is serialized through the kernel RTNL lock and is the exact step that wedged on Apr 23.

**Proposed approach:**

- Create a single user-defined bridge `ii-sandboxes` at stack startup.
  - `driver=bridge`, `com.docker.network.bridge.enable_icc=false`, `com.docker.network.bridge.name=ii-sb0`, custom subnet outside the compose default.
- Sandboxes attach to this bridge instead of the compose network.
- Port publishing remains via host port mappings (`expose_port` unchanged).
- Teardown: removing a container deletes its veth but does not delete the bridge, cutting iptables/network-namespace churn roughly 80%.

**Risks + mitigations:**

- **Sandbox ↔ backend reachability:** Backend still needs to talk to sandbox-exposed ports. Either (a) attach backend to the `ii-sandboxes` bridge as a second network, or (b) rely on host port publishing. Prefer (a) — avoids localhost round-trips.
- **Sandbox ↔ sandbox reachability:** `icc=false` prevents cross-talk. Intentional.
- **Migration:** Existing stale sandboxes on the old network must be reaped before switchover. The new orphan-cleanup loop handles this.

**Open questions:**

- Does the A2A adapter sidecar need to be on the same bridge? (Probably yes, so its HTTP endpoint is reachable from sandbox-side backends.)
- Subnet choice — default Docker pool vs. explicit `172.30.0.0/16`? Prefer explicit for reproducibility.

---

## 3. Concurrent-creation semaphore vs. shared bridge — do both?

**Status:** [ ]
**Priority:** Decision needed

Both target veth churn but at different layers. Semaphore limits *rate of creation*; shared bridge limits *cost per creation/teardown*. They are complementary. Plan: ship semaphore first (small backend-only change), then shared bridge (touches compose + backend + existing data).

---

## 4. Host-side WSL2 kernel tuning

**Status:** [ ]  — Pending sign-off on numbers; see `wsl2-host-configuration.md` (to be created once agreed)
**Priority:** Medium
**Category:** Host / WSL

Current observed state (2026-04-23):

- `vm.min_free_kbytes` = 45056 (**45 MB** — far too low for a 32 GB guest running Docker).
- `/proc/buddyinfo` Normal zone: order 7 = 6 free, order 8 = 0. Danger zone.
- `.wslconfig` has `memory=32GB` (equal to host total) and no `processors=` (all 16 vCPUs to WSL).

Proposed settings (discussed 2026-04-23, awaiting sign-off):

- `vm.min_free_kbytes=262144` (256 MB reserved) — keeps more high-order blocks available.
- `vm.compact_unevictable_allowed=1` — allow kernel to compact even unevictable pages when needed.
- Periodic `echo 1 > /proc/sys/vm/compact_memory` on a 60 s timer (cheap proactive defrag).
- `.wslconfig`: `memory=24GB`, `processors=12`, `kernelCommandLine=transparent_hugepage=madvise cgroup_enable=memory`, `autoMemoryReclaim=gradual`, `sparseVhd=true`.

See the `wsl2-host-configuration.md` doc (to be written after sign-off) for the full rationale, rollback plan, and expected behaviour change.

---

## 5. Fragmentation + dockerd-stall monitoring

**Status:** [ ]
**Priority:** Medium
**Category:** Observability

**Problem:** We had no advance warning on Apr 23. The kernel page-allocation-failure messages were visible 45 min before the system became unusable — we just weren't watching.

**Metrics to expose as leading indicators:**

- `/proc/buddyinfo`: free block counts per order for the Normal zone (gauges for order 4, 5, 6, 7, 8, 9).
- `/proc/pagetypeinfo`: `Unmovable` blocks at order ≥ 4 (cannot be compacted, so they're the true scarcity signal).
- `/proc/vmstat`: `compact_fail`, `compact_stall`, `allocstall_normal` as counters.
- Backend: `docker_call` timeout count (already plumbed through the new bounded executor — just needs export).

**Alerting thresholds (first cut, tune later):**

- WARN when Normal-zone order-7 free blocks < 10 for 60 s.
- CRIT when Normal-zone order-7 free blocks == 0 for 30 s, OR any `docker_call` timeout.

**Delivery options (open question):**

- (a) Host-side bash sidecar sampling every 10 s, publishing to journald / a Prometheus textfile. Cheap, decoupled from app lifecycle.
- (b) New backend cron job (`workers/cron/jobs/kernel_health.py`) reading `/proc/buddyinfo` via a bind mount. Integrated with existing log pipeline.

Leaning towards (a) — a stuck backend would silently disable (b) which is exactly when we'd need the signal.

---

## Cross-cutting: what went right on Apr 23

Worth remembering — these worked:

- The kernel *did* log `order:7` failures clearly and early (10:50).
- `journalctl -b -1` preserved the full pre-reboot timeline across the forced reboot.
- WSL's `InitTerminateInstanceInternal` did eventually force a power-off, avoiding a permanently wedged VM.

The gaps were: nobody was reading those logs in real time, and the backend amplified the wedge instead of isolating it.

---

## Revisit schedule

Revisit this ledger after:
- Any future sandbox-cluster slowness incident.
- Any kernel page-allocation-failure seen in `dmesg`.
- Monthly operational review.

Link changes here to any design docs / implementation docs produced, rather than inlining them.

---

## Cross-references (added 2026-04-23)

Detailed designs and tracking now live in these companion docs:

- **Design:** [../design-docs/sandbox-shared-bridge-network.md](../design-docs/sandbox-shared-bridge-network.md) — decision record for the shared-bridge migration.
- **Runtime — networking:** [sandbox-networking-design.md](sandbox-networking-design.md) — Docker topology, feature impact, rollback.
- **Runtime — host tuning:** [wsl2-host-configuration.md](wsl2-host-configuration.md) — `.wslconfig`, sysctl, disaster recovery procedures.
- **Runtime — monitoring:** [host-resource-monitoring.md](host-resource-monitoring.md) — integrated monitor design, thresholds, actions.
- **Implementation tracker:** [../impl-docs/sandbox-robustness-impl-tracker.md](../impl-docs/sandbox-robustness-impl-tracker.md) — phased TODO list with quality gates.

Status of items in this ledger after 2026-04-23 discussion:

- **1. Concurrent-create semaphore** — scoped into Phase 1 of impl tracker.
- **2. Shared sandbox bridge network** — design approved; scoped into Phase 3.
- **3. Semaphore vs. shared bridge** — do both; Phase 1 first, then Phase 3.
- **4. WSL2 kernel tuning** — approved; scoped into Phase 4.
- **5. Fragmentation + stall monitoring** — integrated (not sidecar); scoped into Phase 2.

---

## Architectural Review Verdict — 2026-04-23 (after corrections)

**Context.** A prior self-review flagged 5 blocking design concerns and 9 smaller gaps. All 5 blocking items were investigated empirically and the design docs have been corrected accordingly.

### Blocking items — status

| # | Concern | Resolution |
|---|---|---|
| 1 | Design claimed shared bridge isolates RTNL lock contention; RTNL is actually global. | Corrected in both design docs. Real benefits (iptables chain size, IPAM isolation, ICC scoping, operational clarity) now accurately documented. Shared-bridge positioned as secondary defence-in-depth, not keystone fix. |
| 2 | Sandbox → infra service DNS reachability unverified. | Verified: sandbox image receives no infra-service env vars and no sandbox-side code references `postgres:`/`redis:`/`minio:`/`a2a-adapter:`/`backend:` hostnames. Single-network attach is safe. |
| 3 | `expose_port(external=False)` and `get_host()` network disambiguation unverified. | Verified latent bug: both iterate `NetworkSettings.Networks.values()` non-deterministically. `_wait_for_ready` already has correct prefer-configured pattern. Fix added as Phase 3 prerequisite. |
| 4 | Hardcoded fragmentation thresholds not data-driven. | Replaced with sliding-window percentile model. Retention tunable via `baseline_capture_retention_hours` (default 48 h). Hardcoded safety floors still apply to guard against slow downward drift. Bootstrap mode uses floors only until ring buffer warm. |
| 5 | `/proc/buddyinfo` readability + `compact_memory` writability from backend unverified. | Verified: `/proc/buddyinfo`, `/proc/pagetypeinfo`, `/proc/vmstat` all readable and reflect host. `/proc/sys/vm/compact_memory` is **read-only** (procfs ro-mount). **Design change:** compaction handled by kernel via `vm.compaction_proactiveness=50` (set in Phase 4 WSL config). Backend observes but does not trigger compaction. This is strictly better than user-space triggering. |

### Additional corrections prompted by verification

- Subnet for `ii-sandboxes` bridge changed from `172.30.0.0/16` to `10.88.0.0/24` — outside the crowded Docker 172.17–172.31 range; 254 addresses is ample.
- Monitor module removed `maybe_compact()` from its public interface (kernel handles it).
- New config settings documented: `baseline_capture_enabled`, `baseline_capture_retention_hours`, `baseline_capture_interval_seconds`, `baseline_capture_persist_path`, plus per-metric hard floors.

### Remaining minor gaps (tracked but not blocking)

Still on the list from the prior review, none gate implementation:

1. Semaphore scope: decide per-process vs. distributed. Single-backend dev deploy → per-process is sufficient. Revisit if/when we run multiple backend replicas.
2. Backpressure UX: frontend banner wording when `degraded=true` is a UX follow-up, not a design blocker.
3. Compaction runaway protection: N/A since we don't trigger compaction.
4. Backend downtime on bridge rollout: documented in runtime-docs rollback section; single compose restart.
5. docker-proxy process count on multi-bridge host: negligible (each published port spawns one proxy regardless of bridge; count unchanged).
6. Mid-migration orphan cleanup correctness: impl tracker Phase 3b has explicit check item.
7. Per-session IP stability: sandboxes are ephemeral; no code depends on stable IP across restarts.
8. Integration test harness for synthetic fragmentation: called out in Phase 2a unit tests (fixture-driven).

### Verdict: **GO** for phased implementation

All five blocking items are resolved with documented empirical evidence. The architecture is internally consistent and matches what the runtime supports. Recommended shipping order remains **Phase 1 → Phase 2 → Phase 3 → Phase 4**.

Before any code lands:

- Phase 1 (semaphore): no further design review needed.
- Phase 2 (monitor): Phase 2a tests must use percentile-based `evaluate()` from the start, not a placeholder hardcoded version.
- Phase 3 (bridge): Phase 3.prereq (fix `expose_port`/`get_host` disambiguation) must land first. Must be a separate commit from the compose change, since the disambiguation fix is a latent-bug fix in its own right.
- Phase 4 (WSL): host-side config change; can ship independently of backend code. Low risk, high value.

---

## Second-pass verdict — 2026-04-23 (re-review after corrections)

User directed a second review. Re-executed all five action steps; all corrections still valid.

### Re-verification (2026-04-23, second pass)

- `/proc/buddyinfo|pagetypeinfo|vmstat` readable from backend container ✓
- `/proc/sys/vm/compact_memory` still mounted `ro,nosuid,nodev,noexec` — not writable ✓ (design correctly uses kernel-managed `vm.compaction_proactiveness`)
- `kernel vm.compaction_proactiveness` = 20 currently (default); Phase 4 will raise to 50 ✓
- [src/ii_agent/agents/sandboxes/docker.py](src/ii_agent/agents/sandboxes/docker.py) still has the first-network-IP bug at `expose_port` and `get_host` ✓ (Phase 3.prereq correctly scoped)
- `10.88.0.0/24` still uncontested by Docker networks and WSL NAT ✓
- `host.docker.internal` resolves to `172.17.0.1` via `extra_hosts: [host.docker.internal:host-gateway]` — works on any user-defined bridge ✓

### New insights uncovered in second pass

1. **Orphan cleanup already detects missing bridges.** `_health_check_sandbox_rows` in [orphan_cleanup.py](../../src/ii_agent/agents/sandboxes/orphan_cleanup.py) already inspects `container.attrs.NetworkSettings.Networks` and marks rows deleted when the referenced network no longer exists. This means: if the new `ii-sandboxes` bridge is ever destroyed (manual `docker network rm`, catastrophic reboot mishandling), the cleanup loop will automatically recover stale DB rows. The migration introduces no new orphan-detection gap.
2. **Rollout covers both networks correctly via existing fallback.** During rollout, legacy sandboxes remain on `_default` while new ones land on `_ii-sandboxes`. The Phase 3.prereq disambiguation code (prefer configured, fallback to first non-empty) correctly handles both — legacy sandboxes fall through to the fallback branch; new sandboxes hit the preferred branch. No special drain logic required.
3. **Agent tools do not bridge sandbox→infra.** Backend-side tools run in the backend container and reach infra via service DNS. They never instruct the sandbox to reach `postgres:5432` etc. This was implied in the first-pass verification but worth making explicit.

### Re-issued verdict: **GO** (unchanged)

The design is internally consistent, matches the verified runtime environment, and introduces no regression paths that the existing orphan-cleanup machinery does not already handle. Proceed with the documented phased implementation:

- Phase 1 — concurrent-create semaphore (backend-only, low risk).
- Phase 2 — host monitor with sliding-window percentile thresholds (default 48 h retention, tunable).
- Phase 3 — shared-bridge migration (preceded by prereq disambiguation fix as a standalone commit).
- Phase 4 — WSL config (host-side, independent of backend code).

Awaiting explicit user go-ahead to begin writing Phase 1 code.

---

## 2026-04-23 — Phase 1 DONE (concurrent-create semaphore)

- Code: [src/ii_agent/agents/sandboxes/service.py](../../src/ii_agent/agents/sandboxes/service.py), [src/ii_agent/core/config/sandbox.py](../../src/ii_agent/core/config/sandbox.py)
- Unit tests: 7 new in [src/tests/unit/engine/test_sandbox_create_semaphore.py](../../src/tests/unit/engine/test_sandbox_create_semaphore.py), all pass; 53 sibling sandbox tests remain green.
- E2E inventory: SBOX-06 added to [scripts/local/test_e2e.py](../../scripts/local/test_e2e.py). Not executed — user directed deferral until all four phases land.
- Config: `sandbox_concurrent_create_limit` default 2, `sandbox_create_wait_log_threshold_ms` default 500; both tunable.
- Ruff clean. Backend rebuild in progress (intermittent compose cache interaction caused an extra rebuild cycle; final image reflects new sizes once current rebuild finishes).

## 2026-04-23 — Phase 6 design added (`stack_control.sh status` platform health)

User ask: "extend `stack_control.sh status` display with platform-specific data, such as 15-minute load factor, degree of memory fragmentation. Separate common linux checks from release-specific checks in a loosely coupled manner."

Design: [../design-docs/stack-control-platform-health.md](../design-docs/stack-control-platform-health.md). Tracked as Phase 6 (6.a–6.d) in the impl tracker.

Key shape:

- Backend-independent — pure bash + `/proc`, so it works when the backend is wedged (the exact 2026-04-23 failure mode).
- Three-tier module loading: `platform_checks_common.sh` (any Linux), `platform_checks_wsl.sh`, `platform_checks_ubuntu.sh`. Each module exports `applicable()` + `display()`; dispatcher skips non-applicable modules cleanly. Adding Debian / RHEL / Darwin is a drop-in file.
- Optional backend enrichment via new `GET /health/host` endpoint (Phase 2 dependency) — shows local-vs-backend snapshot reconciliation.
- 6.a + 6.b ship independently of Phase 2; 6.c requires Phase 2.

## 2026-04-23 — Phase 2 DONE (integrated host monitor)

- New module: [src/ii_agent/agents/sandboxes/host_monitor.py](../../src/ii_agent/agents/sandboxes/host_monitor.py) — pure /proc parsers, percentile-driven evaluator, in-process state holder, rolling DockerCallStats window, optional baseline summary persistence.
- Integration: orphan-cleanup sweep now runs a host_monitor sample as its first sub-phase; transitions are logged at INFO/WARNING/ERROR depending on severity. Pool `bootstrap()` / `ensure_full()` skip warming at WARN+. `SandboxService._create_provider` refuses creates at CRIT with `SandboxCreationError`. `sandbox_status` handler emits `degraded: bool` and `host_state: str | None`.
- Docker-call telemetry: `executor.py::docker_call` records wall-clock duration (incl. timeouts) into the shared rolling window so the evaluator sees dockerd slowness.
- Config: 15 new `host_monitor_*` / `baseline_capture_*` fields in [src/ii_agent/core/config/sandbox.py](../../src/ii_agent/core/config/sandbox.py). Defaults: buffer 48 h @ 60 s (2 880 samples), bootstrap fraction 0.25, order-7 WARN floor 2 / CRIT floor 0, MemAvailable WARN 1 GiB / CRIT 512 MiB, docker p99 WATCH 2 s / WARN 4 s.
- Tests: 38 unit tests (parsers, buffer, evaluator truth table, state holder, DockerCallStats) + 11 integration tests (synthetic /proc → phase runner → pool/service backpressure → docker_call timing). All 49 pass in ~2 s.
- Event schema: `SandboxStatusChangedEvent` gained `degraded: bool = False` and `host_state: str | None = None` (backward-compatible defaults; frontends that ignore them keep working).
- Ruff clean. Backend rebuild in progress to land the change in the live stack; SBOX-07 e2e registration deferred per user direction (e2e runs after all four phases).
- Known small gap: ring-buffer summary-on-shutdown helper exists (`persist_summary_to_path`) but is not yet wired to an orderly shutdown hook. Off-by-default via empty `baseline_capture_persist_path`; not a functional blocker.

## 2026-04-23 — `.wslconfig` `memory` 32 GB → 45 GB

- Host has 64 GB; previous `.wslconfig` capped WSL at 32 GB.
- Symptom: `docker compose build --no-cache backend` ran for 55+ min while the WSL guest sat at ~16 GB MemAvailable with growing swap (5.4 GB and rising). Build did not error; it was simply thrashing.
- Action: edited [`/mnt/c/Users/Myles Dear/.wslconfig`](file:///mnt/c/Users/Myles%20Dear/.wslconfig) — `memory=32GB` → `memory=45GB`. Swap settings unchanged (16 GB on G:). Leaves ~19 GB for Windows + Hyper-V overhead, sufficient on this user's workload.
- **Activation:** requires `wsl --shutdown` from PowerShell, then re-launch WSL. New `MemTotal` should read ~47 000 000 kB.
- Doc updated: [docs/runtime-docs/wsl2-host-configuration.md](wsl2-host-configuration.md) — host profile (32 GB → 64 GB), live-config snapshot, change log, and pressure-state baseline.
- Follow-up: capture a fresh "healthy state" buddyinfo / MemAvailable snapshot under the new 45 GB cap once the next stack start completes, and replace the 32 GB-era baseline numbers in `wsl2-host-configuration.md`.

## 2026-04-23 — Phase 4 DONE (WSL host sysctls)

- Created [scripts/99-ii-agent.conf](../../scripts/99-ii-agent.conf) and installed to `/etc/sysctl.d/`.
- Applied 6 settings: `vm.min_free_kbytes=262144` (was 45 056), `vm.compaction_proactiveness=50` (was 20), `vm.compact_unevictable_allowed=1` (already), `vm.swappiness=10` (was 60), `vm.dirty_background_ratio=5` (was 10), `vm.dirty_ratio=15` (was 20).
- Verified via `sudo sysctl --system` and `cat /proc/sys/vm/...`. All six values match the runtime-doc target.
- New healthy baseline captured (replacing the 32 GB-era numbers in [wsl2-host-configuration.md](wsl2-host-configuration.md)): MemAvailable 31 GB, swap idle, buddyinfo Normal zone has order-7=1 / order-8=2 / order-10=6098 — first time the host has had this much high-order headroom in this conversation.
- Tracker [Phase 4](../impl-docs/sandbox-robustness-impl-tracker.md#phase-4--wsl2-host-configuration--done-2026-04-23) marked DONE; one remaining `[ ]` is the deferred 24 h soak validation (no `dmesg` allocation failures).
- Not changed (yet, intentionally): the recommended `kernelCommandLine`, `autoMemoryReclaim=gradual`, `sparseVhd=true`, `processors=12` keys in `.wslconfig`. The runtime doc lists them as the target state; the live file currently only has memory + swap. Adding them is a low-risk follow-up but requires another `wsl --shutdown`.

## 2026-04-23 — Phase 6.a/6.b DONE (platform-health in `stack_control.sh status`)

- New library: [scripts/local/lib/platform_checks.sh](../../scripts/local/lib/platform_checks.sh) (dispatcher), [platform_checks_common.sh](../../scripts/local/lib/platform_checks_common.sh) (any Linux), [platform_checks_wsl.sh](../../scripts/local/lib/platform_checks_wsl.sh), [platform_checks_ubuntu.sh](../../scripts/local/lib/platform_checks_ubuntu.sh).
- Wired into `cmd_status` in [scripts/stack_control.sh](../../scripts/stack_control.sh); printed after the existing sandbox list. Added `--no-platform` flag for environments where `/proc` is unreadable or output is being parsed.
- Backend-independent — pure bash + `/proc` + coreutils. Survives the exact failure mode that motivated this work (backend wedged ⇒ blind to its own host).
- Live smoke: shows uptime/load, memory + swap, buddyinfo high-order summary, compact_fail/allocstall counters, root disk + inode pressure, then WSL kernel + sysctls + `/etc/wsl.conf` excerpt, then Ubuntu release + journald + sysctl drop-in presence + reboot-required flag, with a final rolled-up verdict line.
- Verdict thresholds are conservative hardcoded floors (per design); the backend's percentile-baseline evaluator (Phase 2) is strictly tighter on a per-host basis. The two are designed to agree in healthy state and diverge as a signal during incidents.
- Phase 6.c (`/health/host` endpoint + `platform_checks_backend.sh` consumer) is queued; needs the backend rebuild to land first so we can hit the live `HostMetricsBuffer`.
- Phase 6.d (JSON output) deferred until 6.c is in.

## 2026-04-23 — Phase 2 deployed + verified live

- Backend rebuilt (`./scripts/stack_control.sh rebuild backend --local`) — completed in ~43 min under the new 45 GB cap (vs 65+ min and counting at the 32 GB cap).
- `./scripts/stack_control.sh verify` — all four images (backend, frontend, sandbox, a2a-adapter) report **UP TO DATE**.
- Live import smoke check inside the running container succeeded: `HostHealthState` enum (BOOTSTRAP/OK/WATCH/WARN/CRIT), `get_host_state()` returns `BOOTSTRAP` initial state, `_run_host_monitor_phase` is callable, `sample_host_metrics` works against the real `/proc` and produces sane values (buddy_normal order-7=16 / order-8=5 / order-10=54; MemAvailable 26 GB; compact_fail=0; allocstall_normal=0).
- The Phase 2 background sweep will start sampling on its next tick; the rolling 48 h ring buffer will warm up over the next two days. Pool warming gates and `SandboxService._create_provider` CRIT gate are now active.

## 2026-04-23 — Phase 6.c DONE (backend host-monitor surfaced via `/health/host`)

- New FastAPI route `GET /health/host` on the backend ([src/ii_agent/app/health.py](./../../src/ii_agent/app/health.py)) returns a JSON snapshot of the live Phase 2 `HostMetricsBuffer`: `state`, `state_code`, `captured_at`, `buddyinfo.orders{4..10}`, `p99_docker_call_ms`, `docker_call_timeout_total`, `meminfo`, `vmstat`, `baseline_window_samples/capacity`, `baseline_warm`. Pure read; no mutation of the ring buffer.
- Backed by a new read-only accessor `get_host_monitor_buffer_snapshot()` on [orphan_cleanup.py](./../../src/ii_agent/agents/sandboxes/orphan_cleanup.py).
- New shell-side module [scripts/local/lib/platform_checks_backend.sh](./../../scripts/local/lib/platform_checks_backend.sh): `curl`-with-timeout consumer, pretty-prints the backend view, reconciles against the common module's local `/proc` view, contributes a module verdict to the roll-up.
- Dispatcher [platform_checks.sh](./../../scripts/local/lib/platform_checks.sh) hardened with a `set +e` guard so a non-zero return from any internal grep/test no longer aborts the sweep when sourced under `stack_control.sh`'s `set -euo pipefail` — without this fix only the first (common) module rendered.
- Fixed a pre-existing `REPO_ROOT` → `ROOT_DIR` typo in `stack_control.sh::cmd_status` that was emitting an `unbound variable` warning at the end of every status run.
- Backend rebuild path: `./scripts/stack_control.sh build backend --quick` completed in <5 min (only the two Python files changed; all apt/uv layers cached). Image reports `43 seconds ago` after build.
- Live smoke: `curl http://localhost:8000/health/host` returns JSON with `state=BOOTSTRAP`, `order-7=49`, `baseline_window_samples=1/2880 warm=false` on first request after backend start. `stack_control.sh status` renders all five sections (Common / WSL2 / Ubuntu / Backend / rollup) ending in `verdict: WARN` driven by 90% root disk usage.
- Full unit suite (1656 tests) remains green. Ruff clean on both touched Python files.
- Phase 6.d (`--json` output + `--strict` exit codes) remains queued.

## 2026-04-23 — Phase 6.d DONE (`--json` + `--strict` for `stack_control.sh status`)

- Each platform-checks module now exposes a `json_<name>` emitter alongside `display_<name>` / `verdict_<name>`. Bodies re-read `/proc` (cheap) so JSON mode is independent of having run the human path first.
- New aggregator [platform_checks_json](./../../scripts/local/lib/platform_checks.sh) emits one JSON document `{"verdict": …, "timestamp": …, "modules": {common, wsl, ubuntu, backend}}`. The roll-up verdict is parsed from each module's emitted `"verdict":"X"` field — `verdict_<name>` getters can't be read after `body=$(json_<name>)` because command substitution runs in a subshell and the global mutation never escapes. (Fixed mid-implementation; comment in the code calls it out.)
- [stack_control.sh::cmd_status](./../../scripts/stack_control.sh) gains two flags:
  - `--json` short-circuits the human path and emits the aggregated platform-health payload only. Compose ps + sandbox inventory deliberately omitted (heartbeat/CI consumers query them directly).
  - `--strict` translates the roll-up verdict into an exit code: `OK / WATCH / BOOTSTRAP → 0`, `WARN → 2`, `CRIT → 3`. Composable with text or JSON output, and with `--no-platform` (which yields exit 0 because the section is suppressed).
- Live smoke (current host verdict is WARN, driven by 90% root disk):
  - `status --json` prints a single-line JSON document, ~1500 bytes, parseable by `jq` / `python -m json.tool`.
  - `status --strict` exit code = 2.
  - `status --json --strict` exit code = 2.
  - `status --strict --no-platform` exit code = 0.
- No backend rebuild needed (shell-only change). No Python files touched, so no ruff or unit-test run required.

This completes Phase 6 (a/b/c/d). The platform-health subsystem is now operator-readable (`status`), heartbeat-ready (`--json`), and CI-ready (`--strict`). Phase 5 (external Windows heartbeat) is now unblocked but still deferred per the original plan until ≥1 month of production data exists.

## 2026-04-23 — Phase 6 polish: surface Windows-host `.wslconfig`

Cosmetic follow-up after operator review of `status` output. The WSL2 module previously printed `(no [wsl2]-tuning keys)` because it grepped `/etc/wsl.conf` (distro-side config — automount, boot, user) for the `[wsl2]` keys, which actually live in `%USERPROFILE%\.wslconfig` on the Windows host.

Changes in [scripts/local/lib/platform_checks_wsl.sh](./../../scripts/local/lib/platform_checks_wsl.sh):

- New `_wsl_host_config_path` resolves `%USERPROFILE%\.wslconfig` once per script run via `cmd.exe /c echo %USERPROFILE%`. Result is cached in `_WSL_HOST_CONFIG_RESOLVED` so display + JSON paths share the lookup. `cd /tmp` before the cmd call avoids the noisy "UNC paths not supported" warning. Honours an override env var `WSL_HOST_CONFIG_PATH` for tests / CI.
- New `_wsl_host_config_get` parses one key from the file with awk (comments and whitespace tolerant).
- `display_wsl` now emits a separate `host .wslconfig:` line listing `memory`, `processors`, `swap`, `swapFile`, `autoMemoryReclaim`, `sparseVhd`, `networkingMode` when set. The `/etc/wsl.conf:` line was retargeted to grep distro-side keys (`automount|boot|user|network|interop`) so it's no longer misleading.
- `json_wsl` gained a `host_config: {path, present, memory, processors, swap, swap_file, auto_memory_reclaim, sparse_vhd, networking_mode}` sub-object. Three states: `path:null` (interop unavailable), `present:false` (file missing), `present:true` with key fields populated.
- Verdict heuristic: when the file is present but `memory=` is unset, the module emits WATCH. WSL2's default of 50% host RAM has historically thrashed the buddy allocator on large hosts. Pure soft signal — never escalates past WATCH.

Live verification:

```
=== WSL2 Host ===
  kernel:        6.6.87.2-microsoft-standard-WSL2
  vm tuning:     compaction_proactiveness=50 (OK)  min_free_kbytes=262144 (OK)  swappiness=10 (OK)
  /etc/wsl.conf: (no distro-side keys set)
  host .wslconfig: /mnt/c/Users/Myles Dear/.wslconfig  memory=45GB swap=16GB swapFile=G:\\WSL\\swap.vhdx
```

JSON sub-object verified parseable with all three drift modes covered (override-path test forced WATCH on a fixture lacking `memory=`). Roll-up verdict still WARN (driven by 90% root disk), `wsl.verdict=OK` on this host. Shell-only change; no rebuild, no Python touched.

## 2026-04-24 — Phase 6.e DONE (pool self-heal + pool health surface)

Diagnosed during operator review of `stack_control.sh status` showing both pre-warmed pool sandboxes wedged in `initializing` state for 11h on a backend that had only been up 2h.

**Root cause:** Two `agent_sandboxes` rows were left in `pool_state=AVAILABLE, status=INITIALIZING, provider_sandbox_id=NULL` by a previous backend crash that died inside `_do_create_slot` between row insert and container-create. On restart, `_existing_live_slots()` filtered only on `pool_state == AVAILABLE` — both rows passed — so bootstrap logged "all 2 slots already populated" and never recreated. Orphan cleanup explicitly skips pool rows; the Docker-zombie sweep needs a `provider_sandbox_id` to compare against; stale-pause needs a `session_id`. The rows would have survived forever.

**Fix A (`src/ii_agent/agents/sandboxes/pool.py`):**
- New `reap_stuck_initializing()` marks DELETED any AVAILABLE+INITIALIZING row older than `_STUCK_INITIALIZING_THRESHOLD = 10 min`. Logs each reap as a WARNING.
- Rewrote `_existing_live_slots()` to be status-aware: AVAILABLE counts only when status=RUNNING, OR when status=INITIALIZING AND younger than the threshold. CLAIMED/RETIRING always count.
- Both `bootstrap()` and `ensure_full()` call the reap before slot enumeration.
- New `snapshot()` returns `{configured, ready, initializing, initializing_age_max_seconds, stuck_initializing, claimed, retiring, stuck_threshold_seconds, enabled}` for the new health endpoint.

**Pool health surface:**
- New `GET /health/sandbox-pool` in [src/ii_agent/app/health.py](../../src/ii_agent/app/health.py) wraps `snapshot()` with an `available=true/false` envelope.
- New [scripts/local/lib/platform_checks_pool.sh](../../scripts/local/lib/platform_checks_pool.sh) module renders the snapshot in `stack_control.sh status` text and JSON paths. Verdicts: `ready==configured`→OK, `stuck_initializing>0`→WARN, `ready<configured AND no stuck`→WATCH.
- Registered in [scripts/local/lib/platform_checks.sh](../../scripts/local/lib/platform_checks.sh) dispatcher (text + JSON).

**Tests:** 12 new in [src/tests/unit/agent/test_sandbox_pool.py](../../src/tests/unit/agent/test_sandbox_pool.py) covering reap, status-aware live slots, end-to-end zombie-reap-then-recreate, and snapshot. All 40 pool tests pass.

**Live verification:**
- Pre-fix: rows `8fa641b1...` (slot 0) and `4309a796...` (slot 1) both stuck INITIALIZING for 11h24m, no `provider_sandbox_id`.
- Post-rebuild logs: `Sandbox pool reap: slot=0 row=8fa641b1... stuck INITIALIZING since … — marking DELETED so the slot can be recreated`, then same for slot 1, then `Sandbox pool bootstrap: 2 slot(s) missing ([0, 1]) — creating in parallel`. New rows `8c7ad4f0...` and `5eaba3d4...` reached RUNNING ~110s later.
- `stack_control.sh status` then showed both standby slots as `running`.

The pool can no longer wedge on a previous-run crash. Fix is defence-in-depth: `_existing_live_slots()` would already prevent the bug even if the reap never ran, and the reap actively clears stuck rows so they don't accumulate.

## 2026-04-24 — Pool-claim self-deadlock incident (mitigated; design doc added)

**Severity:** P1 — one user session went silent for 12+ minutes; backend connection pool progressively wedged.

**Symptom.** Session `f3b46421-…` (deep_research agent) submitted a query at 14:12:15. Pool claim succeeded (sandbox `d8ae515d-…`, slot 0). MCP configuration logged at 14:12:17.899. Then total silence on the session for 12 minutes. A2A adapter sidecar inside the sandbox was healthy (`/health` 200) but never received a request. By 14:23, `pg_stat_activity` showed **17 stuck PID pairs**, each a `(idle in transaction SELECT, active UPDATE blocked on ShareLock)` pair on `agent_sandboxes.id`, with 8 ungranted `transactionid` ShareLocks. Cadence ~60s = orphan-cleanup loop replays of the same row-lock contention against new rows.

**Root cause.** `SandboxService.init_sandbox` step 7 (added in Phase 6.e to refresh `timeout_at` on freshly-claimed pool sandboxes) called `sandbox_mgr.set_timeout(...)` while the caller's transaction was still open with a row-lock on `agent_sandboxes.id` from `update_provider_info`. `DockerSandbox.set_timeout._persist_deadline` opens its **own** DB session via `get_db_session_local()` and `UPDATE`s the same row — which blocks waiting for the caller's row-lock. The caller is awaiting `set_timeout` and cannot commit. Postgres sees one waiter and one holder (not a detectable deadlock cycle) and waits indefinitely. asyncpg cancellation mid-EXECUTE does not reliably end the transaction, so each blocked attempt leaks two `idle in transaction` connections. After ~17 pairs the asyncpg `QueuePool` is exhausted and unrelated requests start blocking on session checkout.

**Mitigation deployed (working tree, restart on 2026-04-24 14:24):**

1. `init_sandbox` step 7: `await db.commit()` **before** calling `set_timeout` on the pool-claim path, releasing the row-lock so the second session's UPDATE can proceed. ([service.py](../../src/ii_agent/agents/sandboxes/service.py))
2. `DockerSandbox.set_timeout._persist_deadline` wrapped in `asyncio.wait_for(timeout=10.0)` so any future contention can never wedge the user-visible session-startup path indefinitely. On timeout, the in-memory `_timeout_handler` task still fires; only cross-restart durability of `timeout_at` is sacrificed. ([docker.py](../../src/ii_agent/agents/sandboxes/docker.py))

**Design doc:** [../design-docs/sandbox-pool-claim-self-deadlock.md](../design-docs/sandbox-pool-claim-self-deadlock.md) — full incident timeline, root cause analysis, why pre-existing safeguards (Phase 1 semaphore, Phase 2 host monitor, circuit breaker, etc.) did not catch this, and three recommended structural follow-ups.

**Post-restart verification (2026-04-24 14:24):** `pg_stat_activity` shows 0 idle-in-transaction connections; pool reports 2/2 ready; `stack_control.sh status` rolls up to OK on the sandbox-pool module. Backend has been processing new sessions normally since restart.

**Recommended follow-ups (tracked as Phase 6.f):**

1. **Pass `db` into `set_timeout`** — eliminate the second DB session entirely. Removes contention by construction rather than by ordering discipline. The proper structural fix.
2. **`SET LOCAL lock_timeout = '5s'` inside `_persist_deadline`** — belt-and-braces backstop for any remaining `db=None` callers.
3. **Regression test** in `src/tests/unit/agent/test_sandbox_service.py` asserting the commit-before-set_timeout call order on the pool-claim path. Locks in the ordering against future refactors.
4. **Connection-pool wedge alert** in the integrated host monitor (Phase 2) — surface asyncpg `QueuePool` checkout latency p99 as a CRIT-state input so future leaks become operator-visible in `stack_control.sh status` rather than producing silent user sessions.

These are not blocking — the deployed mitigation is sufficient for the observed failure mode — but should land before `prewarm_pool_size` is increased above 2 (more pool claims per minute → higher contention probability if discipline ever slips).
