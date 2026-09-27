"""Integrated host resource monitor.

Samples ``/proc/buddyinfo``, ``/proc/pagetypeinfo``, ``/proc/vmstat``,
``/proc/meminfo`` plus in-process docker-call latency, maintains a
sliding-window baseline, and evaluates a 5-state health signal
(BOOTSTRAP / OK / WATCH / WARN / CRIT) used to gate pool warming and
new sandbox creation.

Design: ``docs/runtime-docs/host-resource-monitoring.md``. Verified
2026-04-23 that ``/proc/buddyinfo``, ``/proc/pagetypeinfo``,
``/proc/vmstat``, and ``/proc/meminfo`` reflect host kernel state from
inside ``ii-agent-local-backend-1``. ``/proc/sys/vm/compact_memory`` is
read-only inside the container; compaction is kernel-managed via
``vm.compaction_proactiveness`` (Phase 4), not triggered by this
module.

Public API:

- :class:`HostHealthState` — enum of monitor verdicts.
- :class:`HostMetrics` — one-sample snapshot (immutable).
- :class:`HostMetricsBuffer` — bounded ring buffer, computes percentiles.
- :func:`sample_host_metrics` — async I/O reader.
- :func:`evaluate` — deterministic state transition function.

The module is intentionally import-light (only stdlib + the project's
loguru logger) so parser/evaluator logic is unit-testable without
spinning up DB / Docker / Redis.
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path
from typing import Deque, Mapping, Optional

from ii_agent.core.logger import logger


# Number of orders we track on /proc/buddyinfo. The kernel exposes 11
# columns (order 0..10) on x86_64. We store all of them but only
# order 4+ matter for contiguous-allocation health.
_BUDDYINFO_ORDER_COUNT = 11


class HostHealthState(IntEnum):
    """Monitor verdicts, ordered by severity.

    ``>=`` comparisons are used throughout the code (e.g.
    ``if state >= HostHealthState.WARN: ...``) so numeric ordering
    matters: BOOTSTRAP is treated as "unknown / optimistic" and sits
    below OK for gating purposes.
    """

    BOOTSTRAP = 0
    OK = 1
    WATCH = 2
    WARN = 3
    CRIT = 4

    def is_degraded(self) -> bool:
        """True when any consumer should apply backpressure."""
        return self >= HostHealthState.WARN


@dataclass(frozen=True)
class HostMetrics:
    """Single-sample snapshot of host resource indicators."""

    captured_at: float  # unix timestamp (seconds)
    # /proc/buddyinfo Normal zone: order -> free blocks
    buddy_normal: Mapping[int, int]
    # /proc/pagetypeinfo summed high-order (>=4) unmovable blocks
    unmovable_order4plus: int
    # /proc/meminfo
    mem_available_kb: int
    mem_total_kb: int
    # /proc/vmstat counters (absolute; deltas computed by evaluate())
    vmstat_compact_fail: int
    vmstat_compact_success: int
    vmstat_allocstall_normal: int
    # In-process docker-call telemetry
    docker_call_p99_s: float
    docker_call_timeout_total: int

    def order7_free(self) -> int:
        return int(self.buddy_normal.get(7, 0))

    def order_free(self, order: int) -> int:
        return int(self.buddy_normal.get(order, 0))

    def mem_available_mb(self) -> int:
        return self.mem_available_kb // 1024


# ── /proc parsers ─────────────────────────────────────────────────────────
#
# The parsers take text so tests can feed fixture strings; the
# file-reading happens in sample_host_metrics().


def parse_buddyinfo(text: str, zone: str = "Normal") -> dict[int, int]:
    """Parse ``/proc/buddyinfo``; return order -> free-block count for ``zone``.

    Example line::

        Node 0, zone   Normal      1      0      0      2     12     49  ...

    Returns an empty dict if the requested zone isn't present.
    """
    result: dict[int, int] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        # Split on whitespace; look for "zone <name>" marker.
        parts = line.split()
        if "zone" not in parts:
            continue
        try:
            zone_idx = parts.index("zone")
        except ValueError:
            continue
        if zone_idx + 1 >= len(parts):
            continue
        zone_name = parts[zone_idx + 1]
        if zone_name != zone:
            continue
        counts = parts[zone_idx + 2 :]
        for order, raw_count in enumerate(counts[:_BUDDYINFO_ORDER_COUNT]):
            try:
                result[order] = int(raw_count)
            except ValueError:
                continue
        # First matching Normal zone wins (there is only one on single-node
        # WSL/NUMA systems; multi-node hosts would sum, but we don't
        # encounter them in our deployment).
        return result
    return result


def parse_pagetypeinfo(text: str, zone: str = "Normal") -> int:
    """Sum high-order (>=4) Unmovable blocks on the given zone.

    ``/proc/pagetypeinfo`` format::

        Node    0, zone   Normal, type    Unmovable      0      0   ...  9 10

    We specifically want *Unmovable* because those blocks cannot be
    compacted; a large count at order >=4 is a durable-fragmentation
    signal.
    """
    total = 0
    for raw in text.splitlines():
        line = raw.strip()
        if not line.startswith("Node"):
            continue
        if f"zone {zone}" not in line and f"zone  {zone}" not in line:
            # Compose with flexible whitespace; also covers " zone   Normal,".
            if f"zone {zone}," not in line.replace("  ", " ") and zone not in line:
                continue
        if "type" not in line:
            continue
        parts = line.split()
        try:
            type_idx = parts.index("type")
        except ValueError:
            continue
        if type_idx + 1 >= len(parts):
            continue
        migrate_type = parts[type_idx + 1]
        if migrate_type != "Unmovable":
            continue
        counts = parts[type_idx + 2 :]
        for order, raw_count in enumerate(counts[:_BUDDYINFO_ORDER_COUNT]):
            if order < 4:
                continue
            try:
                total += int(raw_count)
            except ValueError:
                continue
    return total


def parse_vmstat(text: str) -> dict[str, int]:
    """Parse ``/proc/vmstat`` into a plain dict.

    Only the keys we care about are returned; absent keys default to 0.
    """
    wanted = {
        "compact_fail",
        "compact_success",
        "compact_stall",
        "allocstall_normal",
        "pgmajfault",
    }
    result = {k: 0 for k in wanted}
    for raw in text.splitlines():
        parts = raw.strip().split()
        if len(parts) != 2:
            continue
        key, value = parts
        if key not in wanted:
            continue
        try:
            result[key] = int(value)
        except ValueError:
            continue
    return result


def parse_meminfo(text: str) -> dict[str, int]:
    """Parse ``/proc/meminfo`` values (in kB) for the keys we use."""
    wanted = {"MemAvailable", "MemTotal", "SwapTotal", "SwapFree"}
    result = {k: 0 for k in wanted}
    for raw in text.splitlines():
        if ":" not in raw:
            continue
        key, rest = raw.split(":", 1)
        key = key.strip()
        if key not in wanted:
            continue
        tokens = rest.strip().split()
        if not tokens:
            continue
        try:
            result[key] = int(tokens[0])
        except ValueError:
            continue
    return result


# ── Docker-call latency tracker ───────────────────────────────────────────


class DockerCallStats:
    """Thread-safe rolling window for docker_call durations.

    Uses a bounded :class:`collections.deque`; inserts are O(1) and
    atomic per CPython's deque C implementation so concurrent
    appends from ThreadPoolExecutor threads (via
    :func:`~ii_agent.agents.sandboxes.executor.docker_call`) are safe
    without additional locking. The `snapshot` method returns p99
    plus a timeout counter; it sorts a copy of the window, which is
    O(n log n) but only called at monitor sample time (1/min) so cost
    is trivial.

    A single process-wide instance is held below. The :func:`docker_call`
    wrapper records into it on every call.
    """

    def __init__(self, window: int = 60) -> None:
        self._window: Deque[float] = deque(maxlen=window)
        self._timeout_total = 0

    def reconfigure(self, window: int) -> None:
        """Resize the window on settings change."""
        if window <= 0:
            return
        if self._window.maxlen != window:
            snapshot = list(self._window)[-window:]
            self._window = deque(snapshot, maxlen=window)

    def record(self, duration_s: float, timed_out: bool = False) -> None:
        self._window.append(float(duration_s))
        if timed_out:
            self._timeout_total += 1

    def snapshot(self) -> tuple[float, int]:
        """Return (p99_seconds, timeout_total). p99 is 0.0 when empty."""
        if not self._window:
            return 0.0, self._timeout_total
        sorted_vals = sorted(self._window)
        p99_idx = max(0, int(len(sorted_vals) * 0.99) - 1)
        return sorted_vals[p99_idx], self._timeout_total


_docker_call_stats: Optional[DockerCallStats] = None


def get_docker_call_stats(window: int = 60) -> DockerCallStats:
    """Return the process-wide DockerCallStats singleton, creating it lazily."""
    global _docker_call_stats
    if _docker_call_stats is None:
        _docker_call_stats = DockerCallStats(window=window)
    else:
        _docker_call_stats.reconfigure(window)
    return _docker_call_stats


def _reset_docker_call_stats_for_tests() -> None:
    """Tests only: drop the cached stats singleton."""
    global _docker_call_stats
    _docker_call_stats = None


# ── Sampler ───────────────────────────────────────────────────────────────


async def sample_host_metrics(
    proc_root: str = "/proc",
    docker_window: int = 60,
) -> HostMetrics:
    """Read one sample from ``/proc`` and the in-process docker stats.

    I/O is offloaded to a thread so a slow filesystem (unlikely for
    /proc, but cheap insurance) can't block the event loop.
    """
    proc = Path(proc_root)

    def _read_all() -> tuple[str, str, str, str]:
        return (
            (proc / "buddyinfo").read_text(errors="replace"),
            (proc / "pagetypeinfo").read_text(errors="replace"),
            (proc / "vmstat").read_text(errors="replace"),
            (proc / "meminfo").read_text(errors="replace"),
        )

    buddy_txt, pagetype_txt, vmstat_txt, meminfo_txt = await asyncio.to_thread(_read_all)

    buddy = parse_buddyinfo(buddy_txt)
    unmovable_order4plus = parse_pagetypeinfo(pagetype_txt)
    vm = parse_vmstat(vmstat_txt)
    mem = parse_meminfo(meminfo_txt)
    p99, timeout_total = get_docker_call_stats(docker_window).snapshot()

    return HostMetrics(
        captured_at=time.time(),
        buddy_normal=buddy,
        unmovable_order4plus=unmovable_order4plus,
        mem_available_kb=mem.get("MemAvailable", 0),
        mem_total_kb=mem.get("MemTotal", 0),
        vmstat_compact_fail=vm.get("compact_fail", 0),
        vmstat_compact_success=vm.get("compact_success", 0),
        vmstat_allocstall_normal=vm.get("allocstall_normal", 0),
        docker_call_p99_s=p99,
        docker_call_timeout_total=timeout_total,
    )


# ── Ring buffer + percentiles ─────────────────────────────────────────────


@dataclass
class HostMetricsBuffer:
    """Bounded ring buffer of :class:`HostMetrics` for percentile queries.

    Capacity is expressed in *samples*, which callers compute from
    retention_hours / interval_seconds. The buffer also records the
    time span it covers so callers can decide whether percentile
    thresholds should engage.
    """

    capacity: int
    # Bootstrap gate: percentile-based pressure thresholds only engage
    # once the buffer is at least ``bootstrap_fraction * capacity`` full.
    # With the default 1-hour retention at 60s sampling (capacity=60),
    # 0.25 means ~15 minutes of data before percentile checks fire. The
    # design doc (docs/runtime-docs/host-resource-monitoring.md) discusses
    # a longer baseline; we deliberately bias toward earlier engagement
    # because (a) hardcoded floors still cover the cold-start window and
    # (b) operators care more about catching real fragmentation early
    # than about avoiding an occasional false WARN during the first
    # 15 minutes after a backend restart.
    bootstrap_fraction: float = 0.25
    _samples: Deque[HostMetrics] = field(default_factory=deque)

    def __post_init__(self) -> None:
        self._samples = deque(maxlen=max(1, int(self.capacity)))

    def append(self, sample: HostMetrics) -> None:
        self._samples.append(sample)

    def __len__(self) -> int:
        return len(self._samples)

    def is_warm(self) -> bool:
        """True once the buffer holds at least ``bootstrap_fraction * capacity`` samples."""
        required = max(1, int(self.capacity * self.bootstrap_fraction))
        return len(self._samples) >= required

    def percentile_order_free(self, order: int, q: float) -> Optional[int]:
        """Return the q-percentile free-block count at ``order`` across the window.

        Returns None when the buffer is empty. ``q`` is a fraction in
        [0, 1]. Uses nearest-rank percentile (floor semantics) which is
        adequate for monitoring and avoids interpolation edge cases on
        small windows.
        """
        if not self._samples:
            return None
        vals = sorted(s.order_free(order) for s in self._samples)
        idx = max(0, min(len(vals) - 1, int(len(vals) * q)))
        return vals[idx]

    def percentile_mem_available_mb(self, q: float) -> Optional[int]:
        if not self._samples:
            return None
        vals = sorted(s.mem_available_mb() for s in self._samples)
        idx = max(0, min(len(vals) - 1, int(len(vals) * q)))
        return vals[idx]

    def summary_for_persist(self) -> dict:
        """Compact JSON-ready snapshot for optional shutdown dump."""
        if not self._samples:
            return {"samples": 0}
        return {
            "samples": len(self._samples),
            "capacity": self.capacity,
            "order7_p05": self.percentile_order_free(7, 0.05),
            "order7_p50": self.percentile_order_free(7, 0.50),
            "order7_p95": self.percentile_order_free(7, 0.95),
            "mem_available_mb_p05": self.percentile_mem_available_mb(0.05),
            "mem_available_mb_p50": self.percentile_mem_available_mb(0.50),
            "mem_available_mb_p95": self.percentile_mem_available_mb(0.95),
        }


# ── Evaluator ─────────────────────────────────────────────────────────────


@dataclass
class HostMonitorConfig:
    """Subset of SandboxSettings that the evaluator cares about.

    Keeps evaluate() independent of the full Settings object so it
    remains pure and easy to unit-test.
    """

    order7_warn_floor: int = 2
    order7_crit_floor: int = 0
    mem_available_warn_mb: int = 1024
    mem_available_crit_mb: int = 512
    docker_p99_watch_s: float = 2.0
    docker_p99_warn_s: float = 4.0
    docker_call_timeout_s: float = 8.0


def evaluate(
    latest: HostMetrics,
    buffer: HostMetricsBuffer,
    prev_state: HostHealthState,
    cfg: HostMonitorConfig,
    prev_sample: Optional[HostMetrics] = None,
) -> HostHealthState:
    """Decide the current health state from the latest sample + baseline.

    Logic (highest severity wins):

    1. **Hard CRIT floors** always apply regardless of bootstrap status:
       - ``order7_free <= order7_crit_floor``
       - ``mem_available_mb <= mem_available_crit_mb``
       - ``docker_call_p99_s >= docker_call_timeout_s``
    2. **Hard WARN floors** (absolute numbers):
       - ``order7_free <= order7_warn_floor``
       - ``mem_available_mb <= mem_available_warn_mb``
       - ``docker_call_p99_s >= docker_p99_warn_s``
       - ``compact_fail`` counter advanced since the previous sample.
    3. **Docker WATCH**: ``docker_call_p99_s >= docker_p99_watch_s``.
    4. **Percentile-derived floors** (only when the buffer is warm):
       - order7_free < p05(order7) for WATCH
       - order7_free < p01(order7) for WARN
       - mem_available_mb < p05(mem) for WATCH

    ``prev_sample``, when provided, allows the evaluator to detect
    counter deltas (``compact_fail``) between adjacent sweeps. Callers
    that have no prior sample yet can pass None.
    """
    mem_mb = latest.mem_available_mb()
    order7 = latest.order7_free()

    # 1. Hard CRIT floors ------------------------------------------------
    if order7 <= cfg.order7_crit_floor:
        return HostHealthState.CRIT
    if mem_mb <= cfg.mem_available_crit_mb:
        return HostHealthState.CRIT
    if latest.docker_call_p99_s >= cfg.docker_call_timeout_s:
        return HostHealthState.CRIT

    # 2. Hard WARN floors ------------------------------------------------
    warn_triggered = False
    if order7 <= cfg.order7_warn_floor:
        warn_triggered = True
    if mem_mb <= cfg.mem_available_warn_mb:
        warn_triggered = True
    if latest.docker_call_p99_s >= cfg.docker_p99_warn_s:
        warn_triggered = True
    if prev_sample is not None:
        if latest.vmstat_compact_fail > prev_sample.vmstat_compact_fail:
            warn_triggered = True

    # Percentile-derived WARN (only if baseline is warm)
    if buffer.is_warm():
        p01_order7 = buffer.percentile_order_free(7, 0.01)
        if p01_order7 is not None and order7 < p01_order7:
            warn_triggered = True

    if warn_triggered:
        return HostHealthState.WARN

    # 3. Docker WATCH ----------------------------------------------------
    watch_triggered = False
    if latest.docker_call_p99_s >= cfg.docker_p99_watch_s:
        watch_triggered = True

    # Percentile-derived WATCH
    if buffer.is_warm():
        p05_order7 = buffer.percentile_order_free(7, 0.05)
        if p05_order7 is not None and order7 < p05_order7:
            watch_triggered = True
        p05_mem = buffer.percentile_mem_available_mb(0.05)
        if p05_mem is not None and mem_mb < p05_mem:
            watch_triggered = True

    if watch_triggered:
        return HostHealthState.WATCH

    # 4. Bootstrap or OK -------------------------------------------------
    if not buffer.is_warm():
        # Percentile logic not engaged yet; if no hard floors fired we
        # report BOOTSTRAP so consumers know state is provisional.
        # Treated as non-degraded by is_degraded() but signals to
        # observability that the baseline is still warming.
        return HostHealthState.BOOTSTRAP

    return HostHealthState.OK


# ── Process-wide current-state holder ─────────────────────────────────────
#
# Consumers (pool manager, SandboxService.create_sandbox,
# sandbox_status handler) read this to apply backpressure. Written by
# the orphan-cleanup loop on every sample.


class _HostStateHolder:
    """Thin atomic holder for the latest evaluated state."""

    def __init__(self) -> None:
        self._state: HostHealthState = HostHealthState.BOOTSTRAP
        self._last_transition_at: float = time.time()
        self._last_sample: Optional[HostMetrics] = None

    def get(self) -> HostHealthState:
        return self._state

    def get_snapshot(self) -> Optional[HostMetrics]:
        return self._last_sample

    def set(self, state: HostHealthState, sample: Optional[HostMetrics] = None) -> None:
        if state != self._state:
            self._last_transition_at = time.time()
        self._state = state
        if sample is not None:
            self._last_sample = sample

    def seconds_in_current_state(self) -> float:
        return max(0.0, time.time() - self._last_transition_at)


_host_state = _HostStateHolder()


def get_host_state() -> HostHealthState:
    """Return the currently-reported host health state (process-wide)."""
    return _host_state.get()


def get_host_state_snapshot() -> Optional[HostMetrics]:
    """Return the most recent :class:`HostMetrics`, or None before first sample."""
    return _host_state.get_snapshot()


def set_host_state(state: HostHealthState, sample: Optional[HostMetrics] = None) -> None:
    """Update the current state; called by the orphan-cleanup phase."""
    _host_state.set(state, sample)


def _reset_host_state_for_tests() -> None:
    """Tests only: reset the holder to BOOTSTRAP."""
    global _host_state
    _host_state = _HostStateHolder()


# ── Helpers ───────────────────────────────────────────────────────────────


def capacity_from_retention(retention_hours: int, interval_seconds: int) -> int:
    """Convert retention window + sampling interval into buffer capacity (samples)."""
    if interval_seconds <= 0:
        return 1
    return max(1, (retention_hours * 3600) // interval_seconds)


def persist_summary_to_path(buffer: HostMetricsBuffer, path: str) -> None:
    """Write ``buffer.summary_for_persist()`` to ``path`` as JSON.

    Never raises; failures are logged at WARNING. Callers invoke this
    only at orderly shutdown so best-effort semantics are appropriate.
    """
    import json

    try:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(buffer.summary_for_persist(), indent=2))
    except Exception as exc:  # pragma: no cover - best-effort
        logger.warning(f"host_monitor: failed to persist summary to {path}: {exc}")


__all__ = [
    "HostHealthState",
    "HostMetrics",
    "HostMetricsBuffer",
    "HostMonitorConfig",
    "DockerCallStats",
    "capacity_from_retention",
    "evaluate",
    "get_docker_call_stats",
    "get_host_state",
    "get_host_state_snapshot",
    "parse_buddyinfo",
    "parse_meminfo",
    "parse_pagetypeinfo",
    "parse_vmstat",
    "persist_summary_to_path",
    "sample_host_metrics",
    "set_host_state",
]
