"""Tests for the /health/host endpoint.

Phase 6.c surfaced the integrated host-monitor's ring buffer state via
``GET /health/host``. The endpoint is consumed by
``scripts/local/lib/platform_checks_backend.sh`` and must:

- Return a stable JSON shape even before the first sample lands.
- Surface the current :class:`HostHealthState` and ring-buffer warmth.
- Mirror the latest :class:`HostMetrics` sample fields when present.
- Never raise, regardless of monitor state.
"""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest

from ii_agent.agents.sandboxes import host_monitor as hm
from ii_agent.agents.sandboxes import orphan_cleanup as oc

pytestmark = pytest.mark.unit


def _fake_sample(
    *,
    captured_at: float | None = None,
    order7: int = 50,
    mem_avail_kb: int = 18_000_000,
    p99_s: float = 0.123,
    timeouts: int = 7,
    compact_fail: int = 4,
) -> hm.HostMetrics:
    return hm.HostMetrics(
        captured_at=captured_at if captured_at is not None else time.time(),
        buddy_normal={o: (100 if o < 4 else (order7 if o == 7 else 5)) for o in range(11)},
        unmovable_order4plus=2,
        mem_available_kb=mem_avail_kb,
        mem_total_kb=24_000_000,
        vmstat_compact_fail=compact_fail,
        vmstat_compact_success=42,
        vmstat_allocstall_normal=1,
        docker_call_p99_s=p99_s,
        docker_call_timeout_total=timeouts,
    )


@pytest.fixture(autouse=True)
def _reset_state():
    hm._reset_host_state_for_tests()
    oc._reset_host_monitor_for_tests()
    yield
    hm._reset_host_state_for_tests()
    oc._reset_host_monitor_for_tests()


@pytest.mark.asyncio
async def test_health_host_initial_bootstrap_shape():
    """Before the first sweep: state=BOOTSTRAP, all sample fields null,
    buffer warm=False, never raises."""
    from ii_agent.app.health import health_host

    result = await health_host()

    assert result["state"] == "BOOTSTRAP"
    assert result["state_code"] == 0
    assert result["captured_at"] is None
    assert result["buddyinfo"] == {"zone": "Normal", "orders": {}}
    assert result["p99_docker_call_ms"] is None
    assert result["docker_call_timeout_total"] is None
    assert result["meminfo"] == {"available_mb": None, "total_mb": None}
    assert result["vmstat"]["compact_fail"] is None
    assert result["baseline_window_samples"] == 0
    assert result["baseline_window_capacity"] == 0
    assert result["baseline_warm"] is False


@pytest.mark.asyncio
async def test_health_host_emits_high_orders_only():
    """Only orders 4..10 surface — the operator-relevant high orders."""
    from ii_agent.app.health import health_host

    sample = _fake_sample(order7=12)
    hm.set_host_state(hm.HostHealthState.OK, sample)

    result = await health_host()

    orders = result["buddyinfo"]["orders"]
    assert set(orders.keys()) == {"4", "5", "6", "7", "8", "9", "10"}
    assert orders["7"] == 12
    # Order 0..3 must NOT leak through.
    assert "0" not in orders
    assert "3" not in orders


@pytest.mark.asyncio
async def test_health_host_renders_warn_state_with_sample():
    """A WARN state populates every sample-derived field."""
    from ii_agent.app.health import health_host

    captured = 1_700_000_000.0  # fixed for ISO-format determinism
    sample = _fake_sample(
        captured_at=captured,
        order7=1,
        mem_avail_kb=900_000,
        p99_s=4.250,
        timeouts=3,
        compact_fail=11,
    )
    hm.set_host_state(hm.HostHealthState.WARN, sample)

    result = await health_host()

    assert result["state"] == "WARN"
    assert result["state_code"] == int(hm.HostHealthState.WARN)
    assert result["captured_at"] is not None
    assert result["captured_at"].endswith("+00:00")
    assert result["p99_docker_call_ms"] == 4250.0
    assert result["docker_call_timeout_total"] == 3
    assert result["meminfo"]["available_mb"] == 900_000 // 1024
    assert result["meminfo"]["total_mb"] == 24_000_000 // 1024
    assert result["vmstat"]["compact_fail"] == 11
    assert result["vmstat"]["compact_success"] == 42
    assert result["vmstat"]["allocstall_normal"] == 1
    assert result["buddyinfo"]["orders"]["7"] == 1


@pytest.mark.asyncio
async def test_health_host_renders_crit_state():
    """CRIT state surfaces the highest severity code."""
    from ii_agent.app.health import health_host

    sample = _fake_sample(order7=0, mem_avail_kb=200_000, p99_s=9.0)
    hm.set_host_state(hm.HostHealthState.CRIT, sample)

    result = await health_host()

    assert result["state"] == "CRIT"
    assert result["state_code"] == int(hm.HostHealthState.CRIT)
    assert result["state_code"] > int(hm.HostHealthState.WARN)


@pytest.mark.asyncio
async def test_health_host_reports_buffer_warmth():
    """Buffer counts + warm flag come from the orphan-cleanup buffer."""
    from ii_agent.app.health import health_host

    buf = hm.HostMetricsBuffer(capacity=100, bootstrap_fraction=0.25)
    for _ in range(40):  # > 25% threshold => warm
        buf.append(_fake_sample())
    sample = _fake_sample()
    hm.set_host_state(hm.HostHealthState.OK, sample)

    with patch.object(oc, "get_host_monitor_buffer_snapshot", return_value=buf):
        result = await health_host()

    assert result["baseline_window_samples"] == 40
    assert result["baseline_window_capacity"] == 100
    assert result["baseline_warm"] is True


@pytest.mark.asyncio
async def test_health_host_reports_buffer_cold_when_under_threshold():
    """Below bootstrap fraction the buffer reports warm=False."""
    from ii_agent.app.health import health_host

    buf = hm.HostMetricsBuffer(capacity=100, bootstrap_fraction=0.25)
    for _ in range(5):  # below 25% threshold
        buf.append(_fake_sample())
    sample = _fake_sample()
    hm.set_host_state(hm.HostHealthState.BOOTSTRAP, sample)

    with patch.object(oc, "get_host_monitor_buffer_snapshot", return_value=buf):
        result = await health_host()

    assert result["baseline_window_samples"] == 5
    assert result["baseline_warm"] is False


@pytest.mark.asyncio
async def test_health_host_p99_rounds_to_one_decimal_ms():
    """p99 is rendered in ms with one-decimal precision."""
    from ii_agent.app.health import health_host

    # 12.3456 s -> 12345.6 ms
    sample = _fake_sample(p99_s=12.3456)
    hm.set_host_state(hm.HostHealthState.WARN, sample)

    result = await health_host()

    assert result["p99_docker_call_ms"] == 12345.6
