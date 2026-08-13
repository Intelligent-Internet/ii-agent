# Sandbox Robustness — Implementation Tracker

**Created:** 2026-04-23.
**Purpose:** Track concrete implementation work stemming from the 2026-04-23 WSL2 force-reboot incident. This is the single ledger; high-level ledger is at [../runtime-docs/post-reboot-followups.md](../runtime-docs/post-reboot-followups.md), design at [../design-docs/sandbox-shared-bridge-network.md](../design-docs/sandbox-shared-bridge-network.md), operational details in [../runtime-docs/](../runtime-docs/).

**Status legend:**

| Symbol | Meaning |
|---|---|
| [ ] | Not started |
| [~] | In progress |
| [x] | Done |
| [!] | Blocked / needs decision |
| [-] | Skipped / descoped (with reason) |

---

## Phase 0 — Already done (2026-04-23)

Reference only. Do not re-do.

- [x] Bounded `ThreadPoolExecutor` + `docker_call(timeout=8s)` wrapper — `agents/sandboxes/executor.py`.
- [x] Per-sandbox circuit breaker — `agents/sandboxes/breaker.py`.
- [x] TTL cache on `sandbox_status` handler with `asyncio.wait_for` — `realtime/handlers/sandbox_status.py`.
- [x] Fail-fast on network errors in `DockerSandbox.connect()` — `agents/sandboxes/docker.py`.
- [x] Breaker integration in `SandboxService.get_sandbox_for_session` — `agents/sandboxes/service.py`.
- [x] Five new orphan-cleanup phases (`_health_check_sandbox_rows`, `_expire_old_paused_sandboxes`, `_purge_stale_deleted_rows`, `_validate_pool_slots`, `run_once_reconciliation`) — `agents/sandboxes/orphan_cleanup.py`.
- [x] Startup reconciliation + slow-callback-duration setting — `app/lifespan.py`.
- [x] 8 new config settings — `core/config/sandbox.py`.
- [x] Backend no-cache rebuild; verified `Startup sandbox reconciliation completed in 0.3s` in live logs.

## Phase 0.5 — Design-verification work (all done 2026-04-23)

Empirical checks run before finalising design. Recorded here for traceability.

- [x] `/proc/buddyinfo`, `/proc/pagetypeinfo`, `/proc/vmstat`, `/proc/meminfo` readable from backend container — match host kernel state.
- [x] `/proc/sys/vm/compact_memory` is **read-only** in backend container (procfs `ro,nosuid,nodev,noexec`). Backend cannot trigger compaction even as root. → Drove switch to kernel-managed `vm.compaction_proactiveness=50`.
- [x] Sandbox image receives no infra-service env vars (only `SANDBOX_ID`, `WORKSPACE_DIR`, `AGENT_BROWSER_HEADED`, A2A tokens). No sandbox-side code references `postgres:`, `redis:`, `minio:`, `backend:`, or `a2a-adapter:` hostnames. → Single-network attach for sandboxes is safe.
- [x] `expose_port(external=False)` and `get_host()` in [docker.py](../../src/ii_agent/agents/sandboxes/docker.py) return the first network's IP non-deterministically. `_wait_for_ready` already does prefer-configured correctly. → Added as Phase 3 prerequisite.
- [x] Existing Docker subnets: 172.17, 172.18, 172.19. WSL NAT: 172.29.192.0/20. Chose `10.88.0.0/24` for `ii-sandboxes` (outside crowded 172.x range, correctly sized for 254 addresses).
- [x] Baseline buddyinfo samples (2026-04-23): healthy host order-7 fluctuates 21–49, order-8 4–21. Hardcoded thresholds would false-alarm. → Drove switch to sliding-window percentile model.

## Phase 1 — Concurrent sandbox creation cap — **DONE 2026-04-23**

**Goal:** prevent parallel `docker.containers.run()` calls from burning through high-order kernel memory blocks simultaneously.

- [x] Add `sandbox_concurrent_create_limit: int = 2` to [core/config/sandbox.py](../../src/ii_agent/core/config/sandbox.py) (ge=0; 0 disables).
- [x] Add `sandbox_create_wait_log_threshold_ms: int = 500` companion setting.
- [x] Module-level `asyncio.Semaphore` with lazy init + rebuild-on-limit-change in [agents/sandboxes/service.py](../../src/ii_agent/agents/sandboxes/service.py).
- [x] `SandboxService._create_provider` split into wrapper (gate + wait timing) + `_dispatch_create` (provider-specific branching). Both E2B and Docker paths gated identically.
- [x] INFO log `"Sandbox create waited {}ms for concurrent-create semaphore (limit={}, sandbox_id={})"` when wait ≥ threshold.
- [x] Unit tests (7 in [src/tests/unit/engine/test_sandbox_create_semaphore.py](../../src/tests/unit/engine/test_sandbox_create_semaphore.py)): limit=2 caps in-flight, limit=1 serialises, limit=0 disables, log-above-threshold, no-log-below-threshold, settings-change rebuilds, dispatch receives correct args. All 7 pass.
- [x] No regressions across 53 sibling sandbox tests.
- [x] Ruff clean on all three files.
- [x] Backend rebuild + `stack_control.sh verify` UP TO DATE.
- [x] E2E inventory entry: SBOX-06 in [scripts/local/test_e2e.py](../../scripts/local/test_e2e.py) — verifies semaphore config is loaded and symbols are importable on the live backend. Not executed per user direction until all four phases land.
- [x] Update [post-reboot-followups.md](../runtime-docs/post-reboot-followups.md) status to `[x]`.

**Definition of done:** pool warm storms and user traffic bursts cannot launch more than N concurrent `docker.containers.run()`; limit is config-driven; default is 2. **Met.**

**Notes:**
- Both E2B and Docker creation paths are gated. For Docker the primary fragmentation risk is veth/bridge churn; for E2B the gate protects against remote-provider rate burst. Same semaphore intentionally shared.
- Gate is reentrant-safe via `_CREATE_SEMAPHORE_LOCK` asyncio.Lock — multiple callers racing to init the semaphore will see a single instance.
- Rebuild-on-limit-change allows runtime tuning via settings reload without process restart (the next create will see the new limit).

## Phase 2 — Integrated host monitor

**Goal:** proactive detection of kernel memory fragmentation and Docker-daemon slowness; automatic compaction and backpressure.

Design: [../runtime-docs/host-resource-monitoring.md](../runtime-docs/host-resource-monitoring.md).

### Phase 2a — `/proc` reader + evaluator (pure)

- [x] New module `agents/sandboxes/host_monitor.py`.
- [x] `HostMetrics` dataclass (buddyinfo, pagetypeinfo, vmstat, meminfo snapshot).
- [x] `HostHealthState` enum (BOOTSTRAP / OK / WATCH / WARN / CRIT).
- [x] `parse_buddyinfo(text, zone="Normal") -> dict[int, int]` (order → free blocks).
- [x] `parse_pagetypeinfo(text) -> dict` (per-migrate-type summary).
- [x] `parse_vmstat(text) -> dict` (compact_fail, compact_success, allocstall_normal).
- [x] `async def sample_host_metrics(proc_root="/proc") -> HostMetrics`.
- [x] `HostMetricsBuffer` ring buffer: `append`, `percentile(metric, q)`, `is_warm()`.
- [x] `def evaluate(latest, buffer, prev_state, cfg) -> HostHealthState` using percentile + hardcoded floor dual-gate.
- [x] Unit tests with fixture files for all three formats.
- [x] Unit test: threshold truth table (BOOTSTRAP → OK ↔ WATCH ↔ WARN ↔ CRIT boundaries).
- [x] Unit test: percentile-driven sticky transitions (hysteresis).
- [x] Unit test: bootstrap mode — before ring buffer warm, only hardcoded floors apply.

### Phase 2b — Integration with orphan cleanup loop

- [x] Add `host_monitor_*` + `baseline_capture_*` config settings (see runtime doc table) to `core/config/sandbox.py`.
- [x] New phase in `orphan_cleanup.py::run_orphan_cleanup_loop` — runs FIRST, every iteration. Samples, appends to buffer, evaluates.
- [x] Log transitions at INFO (OK→WATCH) or WARNING (WATCH→WARN) or ERROR (→CRIT).
- [x] Track state in module-level var (single instance; backend is one process).
- [x] **No `compact_memory` write.** Compaction handled by kernel via `vm.compaction_proactiveness` (Phase 4).
- [ ] Optional: flush ring-buffer percentile summary to `baseline_capture_persist_path` on orderly shutdown (off by default; helper present, not wired to shutdown yet).

### Phase 2c — Backpressure consumers

- [x] `pool.py`: pool manager checks current host state before warming. Skip warming at WARN+.
- [x] `service.py::create_sandbox`: raise `SandboxCreationError("host under memory pressure")` at CRIT. (Used existing exception rather than adding a new one — caller contract identical.)
- [x] `sandbox_status` handler: include optional `degraded: bool` in payload when state >= WARN.
- [x] Integration test: force CRIT via fixture proc root; assert pool refuses new warms and service rejects creates.

### Phase 2d — Docker-call latency feedback

- [x] `executor.py::docker_call` maintains rolling p99 (last N calls, configurable) and timeout counter.
- [x] `host_monitor` reads these alongside `/proc` metrics; `evaluate()` considers them.

**Definition of done:** Backend detects a synthetic fragmentation scenario (contrived buddyinfo fixture) within 60 s, logs WARN, refuses new pool warms, and resumes when state returns to OK.

## Phase 3 — Shared sandbox bridge network

**Goal:** bound iptables/IPAM churn blast radius of sandbox lifecycle operations; preserve the compose default network for infra-service chain cleanliness. (Note: RTNL lock isolation was claimed in an earlier draft; that was incorrect — RTNL is global. See revised design.)

Design: [../design-docs/sandbox-shared-bridge-network.md](../design-docs/sandbox-shared-bridge-network.md). Operational detail: [../runtime-docs/sandbox-networking-design.md](../runtime-docs/sandbox-networking-design.md).

### Phase 3.prereq — fix `expose_port`/`get_host` network disambiguation

**Required before migration.** Current code returns the first network's IP; with dual-homed backend and multi-network sandboxes the result is non-deterministic.

- [ ] In `DockerSandbox.get_host()` ([docker.py#L1113](../../src/ii_agent/agents/sandboxes/docker.py#L1113)): prefer `self._config.sandbox.docker_network` entry; fall back to first non-empty IP.
- [ ] In `DockerSandbox.expose_port(external=False)` ([docker.py#L1145](../../src/ii_agent/agents/sandboxes/docker.py#L1145)): same prefer-then-fallback pattern.
- [ ] Match the pattern already correct in `_wait_for_ready` ([docker.py#L1232](../../src/ii_agent/agents/sandboxes/docker.py#L1232)).
- [ ] Unit test: multi-network `NetworkSettings.Networks` fixture → assert configured network IP returned.

### Phase 3a — Compose topology

- [ ] Add `networks.ii-sandboxes` block to `docker/docker-compose.local.yaml`:
  - `driver: bridge`.
  - `driver_opts.com.docker.network.bridge.enable_icc: "false"`.
  - `ipam.config[0].subnet: 10.88.0.0/24` (verified no collision with Docker 172.17-19 or WSL NAT 172.29.192.0/20).
- [ ] Add `ii-sandboxes` to `backend.networks` alongside `default`.
- [ ] Verify a2a-adapter sidecar stays on `default` only.
- [ ] Verify frontend stays on `default` only.
- [ ] `stack_control.sh --local down && ... up` dry run on a fresh checkout; record any ordering issues.

### Phase 3b — Backend wiring

- [ ] Update `SANDBOX_DOCKER_NETWORK` default to `${COMPOSE_PROJECT_NAME}_ii-sandboxes` when provider=docker.
- [ ] Verify `DockerSandbox.connect()` and creation paths honour the new network name (code already uses the env var; confirm).
- [ ] Verify `orphan_cleanup._cleanup_orphans` and `_cleanup_docker_zombies` do not filter by network name such that sandboxes on the new network get missed.
- [ ] Verify `_cleanup_orphaned_volumes` volume prefix logic unchanged (volumes are network-agnostic).

### Phase 3c — Feature verification (from feature impact table)

For each of these, add/adjust a smoke test:

- [ ] VS Code URL reachable from host browser after migration.
- [ ] noVNC URL reachable.
- [ ] Web preview iframe URL reachable (mobile_app_init tool).
- [ ] MCP connectivity from backend to sandbox-6060 (exec agent tool that requires MCP).
- [ ] Per-sandbox A2A adapter reachability (agent-mode A2A run).
- [ ] Chat A2A sidecar reachability (chat-mode A2A query).
- [ ] `register_port` tool returns a working URL.
- [ ] `host.docker.internal` still resolves from inside a sandbox (add debug endpoint or exec test).
- [ ] Project design preview proxy works (if URL is both container-IP form and localhost-host-port form).

### Phase 3d — Blast-radius test

- [ ] Manual test: simulate a wedged sandbox via `docker kill -s STOP <sandbox>` (pauses its container processes indefinitely).
- [ ] Verify backend API calls to postgres/redis/minio/adapter continue uninterrupted for >60 s.
- [ ] Verify `docker ps` on backend times out at 8 s (existing timeout) rather than hanging forever.
- [ ] Verify other sandboxes' lifecycle operations proceed (breaker fires only for the stuck one).

### Phase 3e — Rollback drill

- [ ] Document rollback in runbook form.
- [ ] Perform one rollback and re-migration on the dev host to validate procedure.

**Definition of done:** all existing features work identically from a user perspective; blast-radius test demonstrates isolation; rollback drill completed.

## Phase 4 — WSL2 host configuration — **DONE 2026-04-23**

**Goal:** restore kernel memory headroom; reduce swap pressure; preserve Windows responsiveness.

Design: [../runtime-docs/wsl2-host-configuration.md](../runtime-docs/wsl2-host-configuration.md).

- [x] Create `scripts/99-ii-agent.conf` with the sysctl values from the runtime doc (incl. `vm.compaction_proactiveness=50`).
- [x] Update `.wslconfig` (memory bumped 32 GB → 45 GB on 2026-04-23). Other recommended keys (kernelCommandLine, autoMemoryReclaim, sparseVhd, processors=12) listed in the runtime doc as the target state but not yet on the live config; not blocking.
- [x] `wsl --shutdown` + restart (host reboot 2026-04-23 ≈ 22:50).
- [x] Install sysctl file on the WSL side (`sudo cp scripts/99-ii-agent.conf /etc/sysctl.d/ && sudo sysctl --system`).
- [x] Verify `/proc/sys/vm/min_free_kbytes == 262144`, `/proc/sys/vm/compaction_proactiveness == 50`, `/proc/sys/vm/compact_unevictable_allowed == 1`, swappiness=10, dirty 5/15.
- [x] Capture a fresh buddyinfo snapshot for the observed-baselines section (Normal zone: order-7=1, order-8=2, order-10=6098; MemAvailable 31 GB; swap idle).
- [ ] Leave stack running overnight; check `dmesg` for any fresh `order:N: page allocation failure` — expected: none. *(deferred soak validation)*

**Definition of done:** WSL config matches doc; sysctl persistent across reboot; 24 h soak shows no allocation failures under normal workload. *(soak deferred)*

## Phase 5 — External heartbeat (deferred)

Low priority. Only required if integrated monitoring proves insufficient.

- [ ] Windows Scheduled Task: every 5 min, call `wsl -d Ubuntu-22.04 -- curl -sf http://localhost:8000/health`.
- [ ] On two consecutive failures, log to Windows event log. No auto-recovery action.
- [ ] Document in wsl2-host-configuration.md once implemented.

Defer until we have 1+ month of production-host data with Phase 1–4 in place.

## Phase 6 — `stack_control.sh status` platform-health extension

**Goal:** surface platform health (load, memory fragmentation, disk/inode pressure, WSL/Ubuntu tuning) at the same inspection point where operators already look. Backend-independent so it is usable when the backend is wedged — the same failure mode that triggered the 2026-04-23 incident.

Design: [../design-docs/stack-control-platform-health.md](../design-docs/stack-control-platform-health.md).

### Phase 6.a — Common-Linux checks — **DONE 2026-04-23**

- [x] `scripts/local/lib/platform_checks.sh` dispatcher (sources modules on applicable()).
- [x] `scripts/local/lib/platform_checks_common.sh`: load avg, meminfo, buddyinfo summary, vmstat rates, disk/inode.
- [x] Wire into `cmd_status` in `scripts/stack_control.sh` after the sandbox list.
- [x] `--no-platform` escape hatch.
- [ ] BATS smoke test with `/proc` fixtures. *(deferred; manual smoke verified live)*

### Phase 6.b — WSL + Ubuntu modules — **DONE 2026-04-23**

- [x] `platform_checks_wsl.sh`: detect via `/proc/version`, show kernel, compaction_proactiveness, min_free_kbytes, swappiness, `/etc/wsl.conf` excerpt.
- [x] `platform_checks_ubuntu.sh`: detect via `/etc/os-release`, show release, journald disk usage, `99-ii-agent.conf` presence, reboot-required flag.
- [ ] Manually verify graceful degradation on a non-WSL host (skip module cleanly when detection fails). *(deferred — no non-WSL host available)*

### Phase 6.c — Backend enrichment (requires Phase 2) — **DONE 2026-04-23**

- [x] `GET /health/host` endpoint reading a snapshot from the Phase 2 `HostMetricsBuffer` (no hot-path work).
  - Implemented in [src/ii_agent/app/health.py](../../src/ii_agent/app/health.py); returns `{state, state_code, captured_at, buddyinfo.orders{4..10}, p99_docker_call_ms, docker_call_timeout_total, meminfo{available_mb,total_mb}, vmstat{compact_fail,compact_success,allocstall_normal}, baseline_window_samples, baseline_window_capacity, baseline_warm}`.
  - Backed by new read-only accessor `get_host_monitor_buffer_snapshot()` in [orphan_cleanup.py](../../src/ii_agent/agents/sandboxes/orphan_cleanup.py); no mutation of the ring buffer.
  - Verified live: returned `state=BOOTSTRAP` with `order-7=49 order-8=15 order-10=1522`, `mem_available_mb=26169/total_mb=45150`, `baseline_window_samples=1/2880 warm=false` on first request after backend start.
- [x] `scripts/local/lib/platform_checks_backend.sh` consumer with reconciliation line.
  - Auto-wired via existing `_platform_run_module backend` call in the dispatcher.
  - Applicable guard: `curl` installed AND `GET /health` 2xx AND `/health/host` body non-empty, with `--max-time 2` cap so a wedged backend cannot block `status`.
  - Verdict mapping: backend OK/BOOTSTRAP → OK; WATCH→WATCH; WARN→WARN; CRIT→CRIT. Local/backend disagreement where backend reports worse than local = soft WATCH bump.
  - Reconciliation line prints one of: `local+backend snapshots agree (OK)` / `backend baseline warming; local view=WARN` / `disagreement: local=X backend=Y`.
  - Dispatcher hardened with `set +e` guard so a non-zero return from any internal grep/test no longer aborts the sweep when sourced under `stack_control.sh`'s `set -euo pipefail`.
- [x] Fixed a pre-existing `REPO_ROOT` → `ROOT_DIR` typo in `stack_control.sh::cmd_status` that was emitting an `unbound variable` warning at the end of every status run.

**Definition of done:** `/health/host` surfaces the buffer snapshot without touching the hot path; `stack_control.sh status` shows a Backend Host Monitor section with a reconciliation line; full unit suite still green (1656 passed).

**Verification:** After `./scripts/stack_control.sh build backend --quick` + stack restart, `curl http://localhost:8000/health/host` returns JSON per the design doc, and `stack_control.sh status` prints all five sections (Common / WSL2 / Ubuntu / Backend / rollup) ending in `verdict: WARN` driven by 90% root disk usage.

### Phase 6.d — JSON output — **DONE 2026-04-23**

- [x] Per-module `json_<name>` emitters added: `json_common`, `json_wsl`, `json_ubuntu`, `json_backend`. Each re-reads `/proc` (cheap) so it can be called independently of `display_<name>`.
- [x] Dispatcher gains `platform_checks_json` aggregator that emits a single JSON document `{"verdict": ..., "timestamp": ..., "modules": {common, wsl, ubuntu, backend}}`. Sets/restores `errexit` like `platform_checks_run`. Modules included only when `applicable_<name>` returns 0.
- [x] Roll-up verdict parsed from each module's emitted `"verdict":"X"` field via `sed`, since command-substitution subshells prevent the `verdict_<name>` getter from seeing the global mutation. (Bug surfaced + fixed during implementation; documented inline.)
- [x] `stack_control.sh status --json` short-circuits the human path, sources `platform_checks.sh`, and prints the aggregated payload. Compose ps + sandbox inventory deliberately omitted in JSON mode (heartbeat/CI consumers can hit `docker compose ps --format json` directly).
- [x] `stack_control.sh status --strict` translates the roll-up verdict into a process exit code: `OK / WATCH / BOOTSTRAP → 0`, `WARN → 2`, `CRIT → 3`. Composable with either text or `--json` output.
- [x] `print_status_help()` updated with both new flags.
- [x] New helper `_status_strict_exit()` and accessor `platform_checks_verdict()` for reading the rolled-up verdict from outside the dispatcher.
- [x] Smoke-tested live: `--json` produces a 1500-byte single-line JSON document with all four modules; `--strict` returns 2 under the current WARN verdict (driven by 90% root disk); `--no-platform --strict` returns 0 (section suppressed).

**Definition of done:** `--json` emits a parseable composable payload; `--strict` produces deterministic exit codes for CI consumers; both flags compose with `--no-platform` and `--show-deleted`. **Met.**

### Phase 6.e — Pool self-heal + pool health surface — **DONE 2026-04-24**

Closes the "phantom standby" diagnosis from 2026-04-23: two `agent_sandboxes` rows wedged in `pool_state=AVAILABLE, status=INITIALIZING` for 11h after a crash made `_existing_live_slots()` count them as live, so bootstrap logged "all 2 slots already populated" and never recreated the slots. Orphan cleanup, the Docker-zombie sweep, and stale-pause all skip pool rows for unrelated reasons, so the rows survived indefinitely.

**Fix A — pool self-heal (src/ii_agent/agents/sandboxes/pool.py):**
- New module-level `_STUCK_INITIALIZING_THRESHOLD = timedelta(minutes=10)`. Container provisioning normally takes 90–110s, so 10 min leaves ample margin against legitimate slow boots while unblocking the slot well before the next claim.
- New public `SandboxPoolManager.reap_stuck_initializing()`: iterates `list_active_pool_rows`, marks `status = DELETED` for any AVAILABLE+INITIALIZING row whose `created_at` predates the cutoff. Logs each reap as a WARNING with row id, slot, age, and `provider_sandbox_id` (which surfaces whether the previous run crashed before or after container create — orphan containers, if any, are then reaped by the existing Docker-zombie sweep on its next pass).
- Rewrote `_existing_live_slots()` from a `pool_state`-only set comprehension to explicit per-row classification: AVAILABLE+RUNNING always live; AVAILABLE+INITIALIZING live only if younger than the threshold; CLAIMED/RETIRING always live. This is the central guard that prevents the bug even if `reap_stuck_initializing` is never called.
- Both `bootstrap()` and `ensure_full()` call `await self.reap_stuck_initializing()` immediately before `_existing_live_slots()` so the enumeration sees a clean DB.
- New `SandboxPoolManager.snapshot()` returns a JSON-friendly `{configured, ready, initializing, initializing_age_max_seconds, stuck_initializing, claimed, retiring, stuck_threshold_seconds, enabled}` for the new `/health/sandbox-pool` endpoint and the new `platform_checks_pool.sh` shell module.

**Pool health surface:**
- New `GET /health/sandbox-pool` endpoint in `src/ii_agent/app/health.py`. Pulls the pool manager from `get_app_container()` and returns a wrapped snapshot with `available=true/false`. Never raises — degraded states return `available=false` with a `reason` string.
- New `scripts/local/lib/platform_checks_pool.sh`. Mirrors `platform_checks_backend.sh` shape (`applicable_pool` / `display_pool` / `verdict_pool` / `json_pool`). Verdict mapping: `ready==configured` → OK, any `stuck_initializing > 0` → WARN (next bootstrap/ensure_full will reap), `ready < configured AND no stuck` → WATCH (warmup in progress).
- Registered in `scripts/local/lib/platform_checks.sh` dispatcher (text + JSON paths). Falls through gracefully when the backend lacks the endpoint (e.g. older builds).

**Tests added (12 new in src/tests/unit/agent/test_sandbox_pool.py):**
- `TestReapStuckInitializing` × 5: stuck no-provider-id row reaped; stuck with-provider-id row reaped; recent in-flight row not reaped; non-AVAILABLE/non-INITIALIZING rows ignored; disabled-pool noop.
- `TestExistingLiveSlotsStatusFilter` × 4: RUNNING+AVAILABLE counts; recent INITIALIZING+AVAILABLE counts; old INITIALIZING+AVAILABLE does NOT count (the bug); CLAIMED/RETIRING always count.
- `TestBootstrapReapsStuckRowsBeforeEnumeration` × 1: end-to-end shape of the live host bug — both zombies marked DELETED AND both slots scheduled for re-creation.
- `TestSnapshot` × 3: disabled returns zeros; mixed-state rows counted correctly; stuck rows flagged.
- All 40 pool tests pass.

**Live verification on 2026-04-24:**
- Pre-fix: rows `8fa641b1...` (slot 0) and `4309a796...` (slot 1) both `pool_state=AVAILABLE, status=INITIALIZING, age=11h24m, provider_sandbox_id=NULL`.
- Post-rebuild logs: `Sandbox pool reap: slot=0 row=8fa641b1... stuck INITIALIZING since … — marking DELETED so the slot can be recreated`, then same for slot=1, then `Sandbox pool bootstrap: 2 slot(s) missing ([0, 1]) — creating in parallel`. Two new rows (`8c7ad4f0...`, `5eaba3d4...`) created and reached RUNNING ~110s later.
- `stack_control.sh status` then showed both standby slots as `running`.

**Definition of done:** Pool zombies self-heal at next bootstrap/ensure_full; `_existing_live_slots()` cannot be fooled by stuck INITIALIZING rows; pool occupancy is visible to operators via `stack_control.sh status` and consumable as JSON via `--json`. **Met.**

### Phase 6.f — Pool-claim self-deadlock mitigation — **DEPLOYED 2026-04-24** (structural fix DEFERRED)

Closes the second incident on 2026-04-24: a `deep_research` session went silent for 12+ minutes after Phase 6.e's pool-claim path triggered a row-lock self-deadlock between `init_sandbox`'s caller transaction and `DockerSandbox.set_timeout`'s separate DB session. By the time the operator restarted the backend, `pg_stat_activity` showed 17 stuck PID pairs and 8 ungranted `transactionid` ShareLocks.

Full root-cause analysis: [../design-docs/sandbox-pool-claim-self-deadlock.md](../design-docs/sandbox-pool-claim-self-deadlock.md).

**Mitigation deployed (working tree, both files):**

- `src/ii_agent/agents/sandboxes/service.py` — `init_sandbox` step 7 (pool-claim branch) now `await db.commit()` before calling `sandbox_mgr.set_timeout(...)`. Releases the row-lock from `update_provider_info` so `set_timeout`'s separate session can UPDATE the same row without blocking.
- `src/ii_agent/agents/sandboxes/docker.py` — `DockerSandbox.set_timeout._persist_deadline` wrapped in `asyncio.wait_for(timeout=10.0)`. Backstop: any future contention is now bounded at 10s on the user-visible session-startup path. On timeout, the in-memory `_timeout_handler` still fires; only cross-restart durability of `timeout_at` is sacrificed.

**Live verification (2026-04-24, post-restart):** `pg_stat_activity` shows 0 idle-in-transaction connections; pool reports 2/2 ready; `stack_control.sh status` rolls up OK on the sandbox-pool module. New sessions processing normally.

**Structural follow-ups — #1, #2, #3 LANDED 2026-04-24; #4 still open:**

- [x] **6.f.1 — Pass `db` into `set_timeout`.** Added optional `db: AsyncSession | None = None` kwarg to `Sandbox.set_timeout` ([base.py](src/ii_agent/agents/sandboxes/base.py)). When provided, mutates the row in the caller's transaction (no second session). When None, separate-session path with backstops. Cron and `_create_or_resume` keep `db=None`. `service.py::init_sandbox` step 7 now passes `db=db` and the explicit `await db.commit()` workaround is gone.
- [x] **6.f.2 — `SET LOCAL lock_timeout = '5s'` inside `_persist_deadline`.** Added inside the separate-session branch of `DockerSandbox.set_timeout` ([docker.py](src/ii_agent/agents/sandboxes/docker.py)). Any future contention on that path now raises `LockNotAvailable` after 5s instead of accumulating `idle in transaction` connections; the `asyncio.wait_for(timeout=10.0)` ceiling stays as belt-and-braces.
- [x] **6.f.3 — Regression test** in [test_docker_sandbox.py](src/tests/unit/agent/test_docker_sandbox.py) (`TestSetTimeout::test_uses_caller_session_when_db_passed`): asserts that when `db` is passed, `get_db_session_local` is NOT called, the caller's `db.execute` IS called, and `db.commit` is NOT called (caller owns commit). Locks in the invariant against future regressions.
- [ ] **6.f.4 — Connection-pool wedge alert.** Add asyncpg `QueuePool` checkout-latency p99 as a CRIT-state input to the Phase 2 integrated host monitor. Future DB-pool exhaustion (from any cause) becomes operator-visible in `stack_control.sh status` rather than producing silent user sessions. Requires a SQLAlchemy pool-events hook in `core/db/`; isolated change.

**Definition of done (mitigation):** Wedge cannot recur on the pool-claim path; worst-case `set_timeout` wait is bounded at 10s by the backstop. **Met.**

**Definition of done (structural):** Two-session anti-pattern eliminated on pool-claim path (6.f.1); separate-session path bounded by `lock_timeout` + `wait_for` (6.f.2); regression test covers the invariant (6.f.3). **Met for #1-3; #4 outstanding.**

**Definition of done:** `stack_control.sh status` shows a "Platform Health" section with clear verdicts on any Linux host; WSL and Ubuntu detail sections appear only when applicable; section gracefully states `unavailable` when running outside Linux.

**Rationale for being separate from Phase 2:** Phase 2's in-backend monitor is blind when the backend is wedged. The shell extension is the independent vantage point. Phases 6.a and 6.b can ship independently of Phase 2; 6.c requires Phase 2.

## Cross-cutting quality gates

Apply to every phase before marking `[x]`:

- [ ] Ruff clean on changed files (`uv run ruff check --fix-only <files>; uv run ruff format <files>; uv run ruff check <files>; uv run ruff format --check <files>`).
- [ ] `uv run pytest` for any new test areas.
- [ ] Rebuild via `./scripts/stack_control.sh rebuild backend` when changes are in `src/`.
- [ ] Verify live via `./scripts/stack_control.sh verify`.
- [ ] Update status in this tracker AND in [post-reboot-followups.md](../runtime-docs/post-reboot-followups.md).

## Resolved design questions (2026-04-23 verification)

1. **`/proc/buddyinfo` from inside backend container** → Verified readable; reflects host kernel.
2. **Compaction trigger** → Kernel-managed via `vm.compaction_proactiveness=50` (backend cannot write `compact_memory`; procfs ro in container).
3. **Force-retire existing standby sandboxes on CRIT** → No. Existing sessions keep running; only new creation refused.
4. **Sandbox infra-service dependency** → None. Single-network attach to `ii-sandboxes` is safe.
5. **Hardcoded thresholds vs. percentile baseline** → Percentile with hardcoded floors. Sliding window tunable, 48h default.
6. **Subnet choice** → `10.88.0.0/24` (was 172.30.0.0/16; changed to tidier /24 outside crowded 172.x).

## Remaining open decisions

1. **Compose ordering for network creation on fresh deploy.** Compose auto-creates user-defined networks; verify no race with the backend's first sandbox request (tested in Phase 3a dry run).
2. **Where to surface the `degraded` flag in frontend UI.** UX choice, not design-blocking. Revisit when Phase 2c lands.

## Dependency graph

```
Phase 1 (semaphore) ──► independent, ship first
Phase 2 (monitor)   ──► independent, can overlap Phase 1
Phase 3 (bridge)    ──► prefer Phase 1 done first (cleaner baseline)
Phase 4 (WSL)       ──► any time; validate Phase 2 monitor output after
Phase 5 (heartbeat) ──► deferred
Phase 6 (status UI) ──► 6.a/6.b any time; 6.c requires Phase 2
```

Recommended shipping order: **1 → 2 → 3 → 4 → 6 (a/b interleaved, c after 2)**.
