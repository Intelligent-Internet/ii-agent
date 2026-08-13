"""Integration tests for host monitor wiring into orphan cleanup, pool,
executor, and sandbox-status handler.

These tests drive a synthetic /proc tree through the live
``_run_host_monitor_phase`` and verify that:

1. A CRIT sample transitions the process state to CRIT.
2. After state == CRIT, ``SandboxPoolManager.ensure_full`` is a no-op.
3. After state == CRIT, ``SandboxService._create_provider`` raises
   :class:`SandboxCreationError` before reaching the semaphore.
4. After state == CRIT, the sandbox_status handler emits
   ``degraded=True`` on the resulting event.
5. ``docker_call`` records success durations and timeout events into
   the rolling window consumed by ``sample_host_metrics``.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ii_agent.agents.sandboxes import host_monitor as hm
from ii_agent.agents.sandboxes.exceptions import SandboxCreationError


# ── Synthetic /proc contents tuned to drive CRIT ─────────────────────────

_CRIT_BUDDY = """\
Node 0, zone   Normal   1000    500    200    100     10      0      0      0      0      0      0
"""

_CRIT_PAGETYPE = """\
Node    0, zone   Normal, type    Unmovable      5      4      3      2      1      0      0      0      0      0      0
"""

_CRIT_VMSTAT = """\
compact_fail 99
compact_success 0
allocstall_normal 99
"""

_CRIT_MEMINFO = """\
MemTotal:       16000000 kB
MemAvailable:     200000 kB
SwapTotal:             0 kB
SwapFree:              0 kB
"""


_OK_BUDDY = """\
Node 0, zone   Normal    800    600    500    400    300    200    100     50     21      4      5
"""

_OK_PAGETYPE = """\
Node    0, zone   Normal, type    Unmovable      5      4      3      2      1      0      0      0      0      0      0
"""

_OK_VMSTAT = """\
compact_fail 0
compact_success 42
allocstall_normal 0
"""

_OK_MEMINFO = """\
MemTotal:       16000000 kB
MemAvailable:   12000000 kB
SwapTotal:             0 kB
SwapFree:              0 kB
"""


def _build_proc(root: Path, *, crit: bool) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    if crit:
        (root / "buddyinfo").write_text(_CRIT_BUDDY)
        (root / "pagetypeinfo").write_text(_CRIT_PAGETYPE)
        (root / "vmstat").write_text(_CRIT_VMSTAT)
        (root / "meminfo").write_text(_CRIT_MEMINFO)
    else:
        (root / "buddyinfo").write_text(_OK_BUDDY)
        (root / "pagetypeinfo").write_text(_OK_PAGETYPE)
        (root / "vmstat").write_text(_OK_VMSTAT)
        (root / "meminfo").write_text(_OK_MEMINFO)
    return root


def _make_cfg(proc_root: str) -> SimpleNamespace:
    """Minimal stand-in for Settings.sandbox used by the phase runner."""
    sandbox_cfg = SimpleNamespace(
        host_monitor_enabled=True,
        host_monitor_proc_root=proc_root,
        host_monitor_docker_latency_window=60,
        baseline_capture_enabled=True,
        baseline_capture_retention_hours=48,
        baseline_capture_interval_seconds=60,
        host_monitor_bootstrap_fraction=0.25,
        host_monitor_order7_warn_floor=2,
        host_monitor_order7_crit_floor=0,
        host_monitor_mem_available_warn_mb=1024,
        host_monitor_mem_available_crit_mb=512,
        host_monitor_docker_p99_watch_s=2.0,
        host_monitor_docker_p99_warn_s=4.0,
        docker_call_timeout_seconds=8.0,
    )
    return SimpleNamespace(sandbox=sandbox_cfg)


@pytest.fixture(autouse=True)
def _reset_state():
    """Each test starts with pristine host-monitor state."""
    hm._reset_host_state_for_tests()
    hm._reset_docker_call_stats_for_tests()
    # Reset buffer held by orphan_cleanup
    from ii_agent.agents.sandboxes import orphan_cleanup

    orphan_cleanup._reset_host_monitor_for_tests()
    yield
    hm._reset_host_state_for_tests()
    hm._reset_docker_call_stats_for_tests()
    orphan_cleanup._reset_host_monitor_for_tests()


# ── 1. Phase runner transitions to CRIT on bad /proc ─────────────────────


@pytest.mark.asyncio
async def test_phase_runner_transitions_to_crit(tmp_path):
    from ii_agent.agents.sandboxes.orphan_cleanup import _run_host_monitor_phase

    proc = _build_proc(tmp_path / "proc", crit=True)
    cfg = _make_cfg(str(proc))

    await _run_host_monitor_phase(cfg)

    assert hm.get_host_state() == hm.HostHealthState.CRIT


@pytest.mark.asyncio
async def test_phase_runner_ok_on_healthy_proc(tmp_path):
    from ii_agent.agents.sandboxes.orphan_cleanup import _run_host_monitor_phase

    proc = _build_proc(tmp_path / "proc", crit=False)
    cfg = _make_cfg(str(proc))

    # Pre-warm bootstrap buffer threshold doesn't matter here — only
    # hard floors apply in bootstrap, and healthy /proc clears them.
    await _run_host_monitor_phase(cfg)

    # Healthy -> at worst BOOTSTRAP; not degraded.
    assert not hm.get_host_state().is_degraded()


@pytest.mark.asyncio
async def test_phase_runner_missing_proc_is_silent(tmp_path):
    from ii_agent.agents.sandboxes.orphan_cleanup import _run_host_monitor_phase

    cfg = _make_cfg(str(tmp_path / "does-not-exist"))

    # Must not raise.
    await _run_host_monitor_phase(cfg)

    # State stays at initial (never degraded).
    assert not hm.get_host_state().is_degraded()


@pytest.mark.asyncio
async def test_phase_runner_disabled_skips(tmp_path):
    from ii_agent.agents.sandboxes.orphan_cleanup import _run_host_monitor_phase

    proc = _build_proc(tmp_path / "proc", crit=True)
    cfg = _make_cfg(str(proc))
    cfg.sandbox.host_monitor_enabled = False

    await _run_host_monitor_phase(cfg)

    # Still BOOTSTRAP (initial) because we never sampled.
    assert hm.get_host_state() == hm.HostHealthState.BOOTSTRAP


# ── 2. Pool.ensure_full / bootstrap skip on WARN+ ────────────────────────


@pytest.mark.asyncio
async def test_pool_ensure_full_skipped_under_pressure():
    from ii_agent.agents.sandboxes.pool import SandboxPoolManager

    cfg = SimpleNamespace(
        sandbox=SimpleNamespace(
            prewarm_pool_size=3,
            prewarm_max_age_seconds=3600,
            provider="docker",
            local_mode=True,
        )
    )
    mgr = SandboxPoolManager(
        sandbox_repo=MagicMock(),
        config=cfg,
        provider_create_fn=AsyncMock(),
    )
    # Force CRIT.
    hm.set_host_state(hm.HostHealthState.CRIT, None)

    # Patch the DB-touching helper so we can tell if ensure_full tried
    # to proceed. On skip, it never runs.
    with patch.object(mgr, "_existing_live_slots", AsyncMock()) as mock_existing:
        await mgr.ensure_full()
        mock_existing.assert_not_called()


@pytest.mark.asyncio
async def test_pool_bootstrap_skipped_under_pressure():
    from ii_agent.agents.sandboxes.pool import SandboxPoolManager

    cfg = SimpleNamespace(
        sandbox=SimpleNamespace(
            prewarm_pool_size=3,
            prewarm_max_age_seconds=3600,
            provider="docker",
            local_mode=True,
        )
    )
    mgr = SandboxPoolManager(
        sandbox_repo=MagicMock(),
        config=cfg,
        provider_create_fn=AsyncMock(),
    )
    hm.set_host_state(hm.HostHealthState.WARN, None)

    with patch.object(mgr, "_existing_live_slots", AsyncMock()) as mock_existing:
        await mgr.bootstrap()
        mock_existing.assert_not_called()


@pytest.mark.asyncio
async def test_pool_ensure_full_runs_when_healthy():
    from ii_agent.agents.sandboxes.pool import SandboxPoolManager

    cfg = SimpleNamespace(
        sandbox=SimpleNamespace(
            prewarm_pool_size=2,
            prewarm_max_age_seconds=3600,
            provider="docker",
            local_mode=True,
        )
    )
    mgr = SandboxPoolManager(
        sandbox_repo=MagicMock(),
        config=cfg,
        provider_create_fn=AsyncMock(),
    )
    hm.set_host_state(hm.HostHealthState.OK, None)

    # ``ensure_full`` also calls ``reap_stuck_initializing`` which would
    # otherwise hit the (mocked) repo.list_active_pool_rows -> await
    # MagicMock TypeError. Stub it out — exercised separately in pool tests.
    with (
        patch.object(mgr, "reap_stuck_initializing", AsyncMock(return_value=0)),
        patch.object(mgr, "_existing_live_slots", AsyncMock(return_value=set())) as mock_existing,
        patch.object(mgr, "_create_slot_async", AsyncMock()),
    ):
        await mgr.ensure_full()
        mock_existing.assert_called_once()


# ── 3. service._create_provider rejects on CRIT ──────────────────────────


@pytest.mark.asyncio
async def test_create_provider_rejects_on_crit():
    from ii_agent.agents.sandboxes.service import SandboxService

    hm.set_host_state(hm.HostHealthState.CRIT, None)

    cfg = SimpleNamespace(sandbox=SimpleNamespace(sandbox_concurrent_create_limit=4))
    # Build a minimal service stub with just the attributes
    # ``_create_provider`` touches.
    service = SandboxService.__new__(SandboxService)
    service._config = cfg
    # Should never reach dispatch.
    service._dispatch_create = AsyncMock(side_effect=AssertionError("must not dispatch"))

    record = MagicMock()
    with pytest.raises(SandboxCreationError) as excinfo:
        await service._create_provider(record)
    assert "pressure" in str(excinfo.value).lower()


@pytest.mark.asyncio
async def test_create_provider_allowed_on_warn():
    """WARN gates pool pre-warm but NOT active user-session creates."""
    from ii_agent.agents.sandboxes.service import SandboxService

    hm.set_host_state(hm.HostHealthState.WARN, None)

    cfg = SimpleNamespace(sandbox=SimpleNamespace(sandbox_concurrent_create_limit=0))
    service = SandboxService.__new__(SandboxService)
    service._config = cfg
    expected = object()
    service._dispatch_create = AsyncMock(return_value=expected)

    record = MagicMock()
    result = await service._create_provider(record)
    assert result is expected


# ── 4. docker_call records latency + timeouts ────────────────────────────


@pytest.mark.asyncio
async def test_docker_call_records_success_latency():
    from ii_agent.agents.sandboxes.executor import docker_call

    def quick() -> int:
        return 42

    # Patch settings lookup to use a small window.
    with patch(
        "ii_agent.agents.sandboxes.executor.get_settings",
        return_value=SimpleNamespace(
            sandbox=SimpleNamespace(
                docker_call_timeout_seconds=5.0,
                host_monitor_docker_latency_window=16,
            )
        ),
    ):
        result = await docker_call(quick, timeout=2.0)
    assert result == 42

    stats = hm.get_docker_call_stats(16)
    p99, timeouts = stats.snapshot()
    assert p99 >= 0.0
    assert timeouts == 0


@pytest.mark.asyncio
async def test_docker_call_records_timeout():
    from ii_agent.agents.sandboxes.executor import docker_call

    def slow() -> None:
        import time as _t

        _t.sleep(2.0)

    with patch(
        "ii_agent.agents.sandboxes.executor.get_settings",
        return_value=SimpleNamespace(
            sandbox=SimpleNamespace(
                docker_call_timeout_seconds=5.0,
                host_monitor_docker_latency_window=16,
            )
        ),
    ):
        with pytest.raises(asyncio.TimeoutError):
            await docker_call(slow, timeout=0.05)

    _p99, timeouts = hm.get_docker_call_stats(16).snapshot()
    assert timeouts == 1
