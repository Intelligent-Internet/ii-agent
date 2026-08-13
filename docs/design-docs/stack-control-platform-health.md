# `stack_control.sh status` — Platform Health Extension

**Created:** 2026-04-23.
**Status:** Design — implementation queued (see impl tracker Phase 6).
**Relates to:** [../runtime-docs/host-resource-monitoring.md](../runtime-docs/host-resource-monitoring.md), [../runtime-docs/wsl2-host-configuration.md](../runtime-docs/wsl2-host-configuration.md), [../impl-docs/sandbox-robustness-impl-tracker.md](../impl-docs/sandbox-robustness-impl-tracker.md).

## Why extend `stack_control.sh status`

Phase 2 of the sandbox-robustness work adds an in-backend host monitor that reads `/proc/buddyinfo`, `/proc/pagetypeinfo`, `/proc/vmstat`, and `/proc/meminfo`, then derives a health state (OK / WATCH / WARN / CRIT) via a 48-hour sliding-window baseline.

That data exists *inside* the backend process. Two problems:

1. **If the backend is wedged, the in-process monitor is blind.** This is the exact failure mode that caused the 2026-04-23 force-reboot: the backend could not evaluate or report its own environment. An operator needs a path to inspect host health that does **not** depend on the backend being responsive.
2. **No operator-facing summary today.** `stack_control.sh status` currently shows only compose container state, service URLs, and a sandbox inventory. It says nothing about how close the platform is to resource exhaustion.

The extension makes platform health visible at the point where an operator is already looking — the same command they run to check whether the stack is up.

## Goals

1. **Backend-independent.** Checks run in pure bash / coreutils / `/proc`. No backend API dependency. Works even when every container is down.
2. **Loosely coupled layers.** Generic Linux checks work on any distro; release-specific checks are opt-in and skip cleanly when prerequisites are absent. The script does not hardcode "Ubuntu 22.04 + WSL2".
3. **Signal, not noise.** Every metric shown has a clear interpretation for the operator. No raw `/proc/vmstat` dumps.
4. **Fast.** Runs in < 500 ms. `stack_control.sh status` is an interactive command; users should not wait.
5. **Optional enrichment.** When backend is healthy, pull its authoritative `HostHealthState` (from Phase 2) and display alongside the local snapshot for cross-verification.

## Non-goals

- Replacing the in-backend monitor. The backend is authoritative because it owns history (48 h ring buffer) and can *act* on signals (throttle pool warms, refuse creates). The shell script shows a current snapshot only.
- Running from a cron / scheduled task. That is covered by Phase 5's external heartbeat.
- Alerting. `status` is inspection-only. Alerting belongs in the heartbeat or an external monitoring system.

## Architecture

### Layered checks

```
scripts/local/lib/platform_checks.sh          <- dispatcher
scripts/local/lib/platform_checks_common.sh   <- always loaded (any Linux)
scripts/local/lib/platform_checks_wsl.sh      <- loaded iff WSL detected
scripts/local/lib/platform_checks_ubuntu.sh   <- loaded iff os-release matches
scripts/local/lib/platform_checks_backend.sh  <- loaded iff backend healthy
```

Each module exports:

- `applicable()` — returns 0 if the module should run on this host, non-zero otherwise.
- `display(verbose_level)` — prints one section to stdout. `verbose_level` is `0` (summary) or `1` (detail); `status` uses `0` by default, `status --verbose` uses `1`.
- `(optional) verdict` — exits with a status code: 0=OK, 1=WATCH, 2=WARN, 3=CRIT. Dispatcher aggregates worst-case for the banner line.

The dispatcher in `platform_checks.sh`:

1. Always sources `platform_checks_common.sh`.
2. For each of `wsl`, `ubuntu`, `backend`, source the file iff it exists, then call `applicable`; if 0, call `display`.
3. Print a single rolled-up verdict line at the top.

Adding a new platform (e.g. Debian 12, RHEL 9, Alpine, Darwin) is a matter of dropping in another `platform_checks_<name>.sh` that implements the two required functions. No change to `stack_control.sh` itself.

### Common checks (any Linux)

Source: `/proc` only. No external binaries beyond `awk`, `grep`, `cat`, `df`, `uptime`.

| Signal | Source | Meaning |
|---|---|---|
| 1/5/15-min load avg | `/proc/loadavg` | Sustained CPU demand. 15-min ≥ `nproc` × 1.5 → WATCH; ≥ × 2 → WARN. |
| Memory pressure | `/proc/meminfo` | `MemAvailable` < 10 % of `MemTotal` → WARN; < 5 % → CRIT. |
| High-order fragmentation | `/proc/buddyinfo` (Normal zone) | Sum of free blocks at order ≥ 4 as a ratio to the sum at order 0. Low ratio + low raw count → WATCH/WARN. |
| Compaction failures | `/proc/vmstat compact_fail` | Rate of change since last run (needs small state file in `$TMPDIR`). |
| `allocstall_normal` | `/proc/vmstat allocstall_normal` | Rate of kernel allocation stalls. Rate > 0 → WATCH. |
| Swap in-use | `/proc/meminfo SwapTotal/SwapFree` | SwapUsed > 25 % of SwapTotal → WATCH; > 50 % → WARN. |
| Inode pressure | `df -i /` | Used inodes > 85 % → WARN. |
| Disk pressure (root fs) | `df -h /` | Used > 85 % → WARN; > 95 % → CRIT. |

Thresholds are hardcoded in the common module; they are conservative floors that apply on any Linux. The backend's percentile-baseline thresholds (Phase 2) are strictly tighter on a per-host basis.

### WSL-specific checks

Detection: `grep -qi microsoft /proc/version` or test `/proc/sys/fs/binfmt_misc/WSLInterop` exists. Both are cheap.

| Signal | Source | Meaning |
|---|---|---|
| WSL distro + kernel | `/proc/version`, `/etc/wsl.conf` if readable | Display line only. |
| ext4.vhdx size (best-effort) | `stat -c %s /mnt/wslg/doc` or similar probe | Cannot reliably read `.vhdx` size from inside WSL; show the mount point size from `df`. |
| `vm.compaction_proactiveness` | `/proc/sys/vm/compaction_proactiveness` | Target: 50 (Phase 4). Show current value with a note when < 30. |
| `vm.min_free_kbytes` | `/proc/sys/vm/min_free_kbytes` | Target: ≥ 262144 (Phase 4). |
| `vm.swappiness` | `/proc/sys/vm/swappiness` | Purely informational. |
| WSL memory setting (if `/etc/wsl.conf` readable) | `[wsl2] memory=` etc. | Informational display. |

Deliberately **not** included: calling out to `wsl.exe` or the Windows side. The shell runs inside the WSL guest; jumping the airgap slows the command down and fails unpredictably.

### Ubuntu-specific checks

Detection: `grep -q "ID=ubuntu" /etc/os-release` + optional version match.

| Signal | Source | Meaning |
|---|---|---|
| Distro + release | `/etc/os-release` | Display line only. |
| systemd journal size | `journalctl --disk-usage` if `journalctl` available | Flag if > 1 GB and persistent journal is configured. |
| `/etc/sysctl.d/99-ii-agent.conf` presence | `ls` | Indicates Phase 4 runtime config is installed. |
| Kernel updates pending | `/var/run/reboot-required` | Shows if a kernel update needs a restart. |

This module is release-agnostic within Ubuntu — it does not hardcode 22.04. Signals that only matter on specific releases are gated by reading `VERSION_ID` from `/etc/os-release`.

### Backend enrichment

When `curl -sf http://localhost:${BACKEND_PORT:-8000}/health` succeeds, call a new endpoint that surfaces Phase 2 state.

Proposed endpoint: `GET /health/host` → JSON:

```json
{
  "state": "OK | WATCH | WARN | CRIT | BOOTSTRAP",
  "captured_at": "2026-04-23T19:45:12Z",
  "buddyinfo": {"zone": "Normal", "orders": {"4": 128, "5": 64, "6": 32, "7": 16, "8": 8, "9": 2}},
  "p99_docker_call_ms": 180,
  "compact_fail_rate_per_min": 0.0,
  "meminfo": {"available_mb": 8192, "total_mb": 24576},
  "baseline_window_samples": 2880,
  "baseline_warm": true
}
```

Backend side: thin read-only accessor on the `HostMetricsBuffer` from Phase 2. No additional work in the hot path.

Shell side: pretty-print `state` with colour; show "(backend snapshot matches local snapshot)" or "(disagreement: local=WARN backend=OK)" when the two views disagree — a disagreement is itself a signal (ring buffer might be stale, or local check fired on a transient spike).

When backend is unreachable, the module prints `backend unreachable — local snapshot only` and exits cleanly.

## Output format

```
=== ii-agent local stack status ===
(existing compose ps)
(existing service URLs)

=== Platform Health ===                                 [verdict: WATCH]
  host:          Ubuntu 22.04.5 LTS (WSL2 on Windows)
  uptime:        3d 4h 22m  load 1/5/15: 0.42 / 0.88 / 1.45
  cpu:           12 vCPU  load_factor_15m: 0.12 (OK)
  memory:        18.2G available / 24G total  (76% free, OK)
                 swap 0.1G / 2G  (5% used, OK)
  fragmentation: order-4+ free: 1820 blocks  ratio_vs_order0: 0.034  (WATCH)
                 compact_fail_rate: 0.0/min   allocstall: 0.0/min
  disk:          root 62G/250G (25%, OK)   inodes 128k/16M (<1%, OK)

=== WSL2 Host ===
  kernel:        5.15.167.4-microsoft-standard-WSL2
  vm tuning:     compaction_proactiveness=50  min_free_kbytes=262144  swappiness=10
  wsl.conf:      memory=24GB vCPU=12 autoMemoryReclaim=gradual

=== Ubuntu Release ===
  release:       22.04.5 LTS (Jammy)
  sysctl drop-in: /etc/sysctl.d/99-ii-agent.conf  (present)
  reboot-required: no

=== Backend Host Monitor ===
  state:         WATCH (last transition: 14m ago from OK)
  baseline:      warm (2880 samples / 48h)
  p99 docker_call: 180ms  (OK threshold: 500ms)
  note:          local+backend snapshots agree
```

`status --quiet` collapses to one line:

```
platform: WATCH (host=WATCH, backend=WATCH — fragmentation approaching baseline floor)
```

## Implementation phases

### Phase 6.a — Scaffolding (shell side)

- Create `scripts/local/lib/platform_checks.sh` dispatcher.
- Create `scripts/local/lib/platform_checks_common.sh` with the Any-Linux checks.
- Wire into `stack_control.sh::cmd_status` after the existing sandbox list.
- Add `stack_control.sh status --no-platform` escape hatch for environments where `/proc` is unreadable.
- Unit-style test: run `status` on the current host, snapshot output, smoke-check contents.

### Phase 6.b — WSL + Ubuntu modules

- `platform_checks_wsl.sh`: detection + the signals in the table above.
- `platform_checks_ubuntu.sh`: detection + the signals in the table above.
- Manual verification on the dev host.
- (Later) Manual verification on a non-WSL Ubuntu host to confirm graceful degradation.

### Phase 6.c — Backend enrichment (requires Phase 2)

- Add `GET /health/host` endpoint reading from the `HostMetricsBuffer` snapshot.
- Add `platform_checks_backend.sh` consumer.
- Print the reconciliation line (`local+backend snapshots agree` / disagreement details).

### Phase 6.d — JSON output mode

- `stack_control.sh status --json` emits a single JSON document covering compose state, sandbox inventory, and the platform-health payload.
- Intended for use by the external heartbeat (Phase 5) and by future CI smoke tests.

## Testing considerations

- **BATS smoke tests.** `tests/stack_control/` with fake `/proc` fixtures and golden output.
- **Fault injection.** Unit-test the evaluator by pointing it at fixture files that simulate WARN/CRIT conditions.
- **Non-Linux hosts.** The dispatcher's `applicable()` guard on `platform_checks_common.sh` should be `test -d /proc`. On Darwin `/proc` is absent; the section prints `unavailable — non-Linux host` and exits clean.

## Open questions

1. **Where should the small state file for rate-of-change counters live?** Options: `/tmp/ii-agent-platform-state.json` (lost on reboot, acceptable); `${XDG_STATE_HOME}/ii-agent/...` (survives reboot). Leaning toward `/tmp` — rate windows of < 60 s are all we care about; a reboot resets state cleanly.
2. **Colour output.** `stack_control.sh` currently does not use colour. Either keep it plain and prefix verdicts with `[WATCH]` / `[WARN]` labels, or introduce a minimal `tput setaf` helper. Decision: plain text + labels; respect `NO_COLOR` env var if colour is added later.
3. **Should `status` exit non-zero on CRIT?** Current behaviour: always 0. Proposal: introduce `--strict` flag that exits 2 on WARN+ and 3 on CRIT, usable from CI and heartbeat scripts. Default stays 0 for human operators.

## Dependency graph

```
Phase 6.a (common checks) ──► ships with Phase 1 code already merged
Phase 6.b (WSL + Ubuntu)  ──► independent; can ship any time
Phase 6.c (backend)       ──► requires Phase 2 host_monitor endpoint
Phase 6.d (JSON)          ──► requires 6.a, nice-to-have; defer until heartbeat needs it
```

Recommended shipping order: **6.a → 6.b → 6.c → 6.d**. 6.a + 6.b together already deliver ~80 % of the value and are gated only on shell work.
