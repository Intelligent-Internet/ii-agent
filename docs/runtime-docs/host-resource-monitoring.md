# Host Resource Monitoring (Integrated)

**Purpose:** Specify the in-backend resource/health monitor that provides advance warning of kernel memory fragmentation, disk pressure, and dockerd stalls — the conditions that led to the 2026-04-23 force-reboot.

**Scope:** Runtime monitoring integrated into the backend's sandbox reaper loop. Does **not** cover WSL config (see [wsl2-host-configuration.md](wsl2-host-configuration.md)) or network topology (see [sandbox-networking-design.md](sandbox-networking-design.md)).

**Status:** Design agreed 2026-04-23. Implementation tracked in [../impl-docs/sandbox-robustness-impl-tracker.md](../impl-docs/sandbox-robustness-impl-tracker.md).

---

## Why integrated (vs. sidecar)

The 2026-04-23 incident exposed the real question: **is the backend a reliable vantage point for host health?**

### Pros of integrated monitoring (chosen)

- **Backpressure.** Can pause pool warming, throttle sandbox creation, open the circuit breaker *before* dockerd stalls. A sidecar can only warn, not act.
- **Unified lifecycle.** No extra container, no extra supervisor. The existing orphan-cleanup loop already runs every 60 s; adding a monitoring phase is zero operational overhead.
- **Shared logger + Redis + DB.** Metrics land in the same log stream as the rest of the backend; easy to correlate with agent runs and sandbox lifecycle events.
- **Visibility to the app.** `sandbox_status` can return a "degraded" flag; the frontend can show a warning banner when the host is under memory pressure.
- **Matches the user's stated preference** (2026-04-23 discussion).

### Cons accepted

- **Blind spot if backend is wedged.** If the event loop is stuck, the monitor stops. This is exactly what happened on Apr 23.
- **Coupling.** Kernel-metric plumbing is technically "infrastructure", and we're putting it in the application. Justified because the backend is the only consumer that can *act* on the signal.

### Mitigation for the blind spot

Two layers:

1. **Cheap external heartbeat.** The existing `./scripts/stack_control.sh verify` can be run from a Windows scheduled task every 5 min. If it fails twice in a row, notify (how is a separate question).
2. **Kernel log shipping.** Run `journalctl -f -k -p warning` into a file that can be tailed by another process. Kernel `order:N: page allocation failure` is the canonical advance signal; journald captures it regardless of backend state.

These are tracked as separate line items in the impl tracker (low priority, defer until we see if integrated alone is enough).

## What we monitor

All metrics are read from `/proc`. **Verified 2026-04-23 from inside `ii-agent-local-backend-1`:** `/proc/buddyinfo`, `/proc/pagetypeinfo`, `/proc/vmstat`, and `/proc/meminfo` are readable and reflect the host kernel. `/proc/sys/vm/compact_memory` is **not** writable (procfs mounted read-only in containers); see "Compaction is kernel-managed, not backend-triggered" below.

### Memory fragmentation

Primary sources:
- `/proc/buddyinfo` — free blocks per order per zone.
- `/proc/pagetypeinfo` — per-migrate-type breakdown (Movable / Unmovable / Reclaimable).
- `/proc/vmstat` — `compact_fail`, `compact_stall`, `compact_success`, `allocstall_normal`.

Metrics exported (gauge unless noted):

| Metric | Source | What it tells us |
|---|---|---|
| `host.mem.available_mb` | `/proc/meminfo MemAvailable` | Total headroom |
| `host.buddy.normal.order_4..9` | `/proc/buddyinfo` | How many contiguous blocks remain at each size |
| `host.buddy.normal.unmovable_order_4plus` | `/proc/pagetypeinfo` | Unmovable high-order blocks (cannot be compacted) |
| `host.vmstat.compact_fail` (counter) | `/proc/vmstat` | Compaction attempts that failed |
| `host.vmstat.allocstall_normal` (counter) | `/proc/vmstat` | Kernel allocation stalls |
| `docker.call.timeout_total` (counter) | internal | `docker_call` wrapper timed out — dockerd under stress |
| `docker.call.duration_p99_seconds` | internal | If p99 climbs past 2 s, docker is getting slow |

### Docker daemon health

From the existing `docker_call` wrapper (already timing all Docker API calls at 8 s budget):
- Count of timeouts per minute.
- p50 / p95 / p99 duration.
- Count of `APIError` with "context deadline exceeded".

### Disk pressure (G: drive)

- `stat -f /` for the WSL ext4.vhdx utilisation (% full).
- `/proc/diskstats` for read/write queue depth as a proxy for HDD saturation.

Note: we can't easily read Windows-side HDD stats from inside the guest. Accept this gap; the backend-side symptom (Docker call p99 climbing) correlates well enough.

## Thresholds: baseline-driven, not hardcoded

**Problem with hardcoded thresholds.** An earlier draft proposed `order-7 < 20 => WATCH, < 10 => WARN, 0 => CRIT`. Observation 2026-04-23 showed healthy baseline already fluctuates (order-7 = 21, order-8 = 4 in one sample; order-7 = 49, order-8 = 21 in another). Hardcoded numbers will either false-alarm or never fire.

**Solution: sliding-window baseline + percentile-derived thresholds.**

The monitor maintains a ring buffer of samples covering a configurable retention window (default 48 h, tunable via `baseline_capture_retention_hours`). Each sample is `(timestamp, order_4..9_free, MemAvailable_mb, compact_fail_delta, allocstall_normal_delta, docker_call_p99_s)`. Samples are taken at `baseline_capture_interval_seconds` (default 60 s = aligned with reaper loop).

From the ring buffer the monitor derives, per metric:
- `p50` — typical behaviour
- `p05` — low watermark under normal load (used as WATCH floor for "free blocks" metrics where lower is worse)
- `p01` — stressed-but-OK (used as WARN floor)

Thresholds self-tune as follows:

| Level | Condition (example: order-7 free) | Sticky duration | Action |
|---|---|---|---|
| **OK** | above `max(hardcoded_floor, p05)` | — | None |
| **WATCH** | below `p05` for ≥ 120 s | 120 s | Log at INFO; pause pool pre-warm expansion |
| **WARN** | below `p01` OR `compact_fail` delta > 0 in window | 60 s | Log at WARNING; reject new non-essential sandbox creation; emit degraded flag |
| **CRIT** | below hardcoded floor (e.g. 0 for order-7) for 30 s OR `docker_call.timeout_total` incremented | 30 s | Log at ERROR; open pool circuit breaker: reject all new sandbox creation; existing sessions continue |

Hardcoded safety floors (applied in addition to percentile-derived values, to avoid "percentile creeps downward during a slow leak"):

- order-7 free: floor 2 for WARN, 0 for CRIT
- `MemAvailable_mb`: floor 1024 for WARN, 512 for CRIT
- `docker_call_p99_s`: 2.0 for WATCH, 4.0 for WARN, anything ≥ the `docker_call` wrapper's timeout (8 s) for CRIT
- `compact_fail` counter incrementing during a 5-min window: always WARN regardless of percentile

**Bootstrapping.** Until the ring buffer contains at least `min(2h, retention/4)` of samples, the monitor uses hardcoded floors only. Percentile logic turns on once enough data is collected; transition logged at INFO.

**Persistence (optional).** The ring buffer lives in memory. For operator convenience, on orderly shutdown the monitor can flush a compact JSON summary (`p05/p50/p95` per metric) to `baseline_capture_persist_path` (default disabled). This is strictly for post-incident forensics; we do not reload history across restarts — the window rebuilds naturally in a few hours.

### Compaction is kernel-managed, not backend-triggered

**Verified 2026-04-23:** `/proc/sys/vm/compact_memory` is mounted read-only inside the backend container (standard Docker hardening). The backend cannot trigger compaction even running as root.

Kernel 6.6 ships `vm.compaction_proactiveness` (0–100, default 20). Raising this via WSL-level sysctl to `50` enables aggressive background compaction managed by the kernel itself. This is strictly better than user-space triggering: the kernel knows when compaction is cheap, respects CPU pressure, and does not add user-space overhead.

Setting goes in the WSL host config (see [wsl2-host-configuration.md](wsl2-host-configuration.md)), not in the backend. The monitor **observes** compaction outcomes (`compact_success`, `compact_fail` deltas from `/proc/vmstat`) but does not trigger them.

### Page cache drop — never automatic

Explicitly excluded per user direction (2026-04-23). Documented as manual recovery in [wsl2-host-configuration.md](wsl2-host-configuration.md) only. Rationale: on the G: HDD, dropping page cache forces all subsequent reads from disk, which worsens the exact symptom we're trying to mitigate.

## Integration points

### Where the monitor lives

`src/ii_agent/agents/sandboxes/host_monitor.py` — new module.

Exposes:
- `async def sample_host_metrics() -> HostMetrics` — single read of all `/proc` sources.
- `class HostMetricsBuffer` — bounded ring buffer; `append(metrics)`, `percentile(metric, q)`, `is_warm()`.
- `class HostHealthState` — enum: OK / WATCH / WARN / CRIT (plus `BOOTSTRAP` while ring buffer not warm).
- `def evaluate(latest: HostMetrics, buffer: HostMetricsBuffer, prev: HostHealthState, cfg: HostMonitorConfig) -> HostHealthState` — deterministic, testable.
- *(No `maybe_compact` — kernel handles compaction; see above.)*

### How the reaper loop invokes it

`src/ii_agent/agents/sandboxes/orphan_cleanup.py::run_orphan_cleanup_loop` gains a new phase (phase 0, before everything else):

```python
# phase 0: host health sample + evaluation
metrics = await sample_host_metrics()
buffer.append(metrics)
state = evaluate(metrics, buffer, prev_state, cfg)
if state.changed(prev_state):
    logger.warning(...)  # log transitions
# No compaction trigger: kernel handles it via vm.compaction_proactiveness=50
if state >= WARN:
    pool_manager.set_degraded(state)
if state == CRIT:
    pool_manager.open_circuit_breaker()  # new method
```

### How other subsystems consume the state

- **Pool manager** (`pool.py`): reads `host_state` from a shared reference before warming new slots. If WARN or worse, skip.
- **Sandbox service** (`service.py::create_sandbox`): if CRIT, raise `SandboxUnavailableError` with a clear message.
- **Realtime handler** (`sandbox_status`): optional `degraded: bool` field in the status payload so the frontend can surface a banner.
- **Metrics export**: log line every 60 s at INFO with the current snapshot when state ≥ WATCH.

### Config (adds to `core/config/sandbox.py`)

| Setting | Default | Purpose |
|---|---|---|
| `host_monitor_enabled` | `true` | Feature flag |
| `host_monitor_proc_root` | `/proc` | Overridable for tests |
| `baseline_capture_enabled` | `true` | Enable sliding-window baseline |
| `baseline_capture_retention_hours` | `48` | Ring-buffer retention window |
| `baseline_capture_interval_seconds` | `60` | Sampling period (aligned with reaper) |
| `baseline_capture_persist_path` | `""` (disabled) | If set, path for shutdown percentile dump |
| `host_monitor_order7_crit_floor` | `0` | Hard CRIT floor regardless of percentile |
| `host_monitor_order7_warn_floor` | `2` | Hard WARN floor |
| `host_monitor_mem_available_warn_mb` | `1024` | Hard WARN floor for MemAvailable |
| `host_monitor_mem_available_crit_mb` | `512` | Hard CRIT floor for MemAvailable |
| `host_monitor_docker_p99_watch_s` | `2.0` | docker_call p99 WATCH |
| `host_monitor_docker_p99_warn_s` | `4.0` | docker_call p99 WARN |
| `host_monitor_transition_sticky_seconds` | `120` | Hysteresis to avoid thrashing |

## Testing

Unit tests (pure, no kernel required):
- Parse `/proc/buddyinfo` fixture → expected gauge values.
- Parse `/proc/pagetypeinfo` fixture → expected Unmovable counts.
- `evaluate()` truth table: for each threshold boundary, assert correct state.
- `maybe_compact()` rate-limit behaviour across fake clock.

Integration tests (require real `/proc`):
- Start the backend, let the loop run, assert at least one sample is logged.
- Write a contrived synthetic buddyinfo to a test root (`host_monitor_proc_root`) and assert the pool manager refuses to warm when CRIT.

## Deliberate non-goals

- **Not a Prometheus exporter.** If we want Prometheus later we can wrap this, but shipping a scrape target is a separate decision with its own ops cost.
- **Not a metrics dashboard.** Log lines are enough until we prove we need more.
- **Not an email / page alerter.** Log + WebSocket "degraded" flag is the contract. Ops layering (PagerDuty etc.) is out of scope.
- **Not Windows-host-aware.** We have no reliable channel from WSL guest to Windows perf counters. Accept the gap.

## Resolved questions (2026-04-23 verification)

1. **How is compaction triggered?** *Kernel-managed via `vm.compaction_proactiveness=50`.* Backend cannot write `/proc/sys/vm/compact_memory` (procfs read-only in container).
2. **Does CRIT force-retire existing standby sandboxes?** *No.* Existing sessions stay running; only new creation is refused. Retiring active sandboxes would cause user-visible session loss.
3. **Can the backend read `/proc/buddyinfo` from inside the container?** *Yes, verified.* Container `/proc/buddyinfo` and `/proc/vmstat` reflect host kernel state identically (tested: host and container returned the same `buddyinfo Node 0, zone Normal` row modulo transient slab activity in the DMA32 zone).
4. **What happens before the ring buffer is warm?** *Hardcoded safety floors only.* Percentile-derived thresholds engage after ≥ 25 % of retention window (default 12 h). Transition logged at INFO.

## Remaining open question

- **How are ring-buffer samples sized in memory?** At 60 s interval × 48 h = 2880 samples. Each sample ~80 bytes of packed data. ~230 KB total. Trivial. No action needed; note here for anyone later tempted to move to 10 s sampling.
