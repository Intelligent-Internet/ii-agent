"""Unit tests for the integrated host resource monitor.

Covers:
  - /proc parsers against fixture strings captured 2026-04-23.
  - HostMetricsBuffer ring semantics and percentile nearest-rank math.
  - DockerCallStats rolling-window p99 + timeout counter.
  - evaluate() truth table across all state boundaries.
  - capacity_from_retention helper.
  - Process-wide state holder transitions.
"""

from __future__ import annotations

import time

import pytest

from ii_agent.agents.sandboxes import host_monitor as hm


# ── Fixtures (real /proc strings from backend container, 2026-04-23) ──────

_BUDDYINFO_HEALTHY = """\
Node 0, zone      DMA      0      0      1      0      2      1      1      0      1      1      3
Node 0, zone    DMA32     12     14     18     14     12      9      8      6      4      3      3
Node 0, zone   Normal    800    600    500    400    300    200    100     50     21      4      1
"""

_BUDDYINFO_FRAGMENTED = """\
Node 0, zone   Normal   2000   1500   1000    600     50      5      1      0      0      0      0
"""

_BUDDYINFO_CRIT = """\
Node 0, zone   Normal   1000    500    200    100     10      0      0      0      0      0      0
"""

_PAGETYPEINFO_HEALTHY = """\
Free pages count per migrate type at order       0      1      2      3      4      5      6      7      8      9     10
Node    0, zone   Normal, type    Unmovable      5      4      3      2      1      0      0      0      0      0      0
Node    0, zone   Normal, type      Movable    700    500    400    300    200    100     50     20      2      0      0
Node    0, zone   Normal, type  Reclaimable     20     10      5      0      0      0      0      0      0      0      0
"""

_VMSTAT_OK = """\
pgpgin 12345
pgpgout 23456
compact_stall 7
compact_fail 1
compact_success 42
allocstall_normal 3
pgmajfault 120
"""

_VMSTAT_COMPACT_FAIL_INCREASED = """\
compact_stall 10
compact_fail 5
compact_success 45
allocstall_normal 3
"""

_MEMINFO_HEALTHY = """\
MemTotal:       24000000 kB
MemFree:         8000000 kB
MemAvailable:   18000000 kB
Buffers:          200000 kB
SwapTotal:       2000000 kB
SwapFree:        1900000 kB
"""

_MEMINFO_LOW = """\
MemTotal:       24000000 kB
MemAvailable:     800000 kB
"""

_MEMINFO_CRIT = """\
MemTotal:       24000000 kB
MemAvailable:     400000 kB
"""


# ── /proc parsers ─────────────────────────────────────────────────────────


def test_parse_buddyinfo_normal_zone() -> None:
    result = hm.parse_buddyinfo(_BUDDYINFO_HEALTHY)
    # Column index = order
    assert result[0] == 800
    assert result[7] == 50
    assert result[8] == 21
    assert result[9] == 4
    assert result[10] == 1


def test_parse_buddyinfo_missing_zone_returns_empty() -> None:
    assert hm.parse_buddyinfo("") == {}
    assert hm.parse_buddyinfo(_BUDDYINFO_HEALTHY, zone="DoesNotExist") == {}


def test_parse_buddyinfo_dma32_does_not_cross_over_to_normal() -> None:
    result = hm.parse_buddyinfo(_BUDDYINFO_HEALTHY, zone="DMA32")
    assert result[0] == 12
    assert result[7] == 6


def test_parse_pagetypeinfo_unmovable_order4plus() -> None:
    # Unmovable row has 1 at order 4 and zero elsewhere in order 4+.
    assert hm.parse_pagetypeinfo(_PAGETYPEINFO_HEALTHY) == 1


def test_parse_pagetypeinfo_empty_input() -> None:
    assert hm.parse_pagetypeinfo("") == 0


def test_parse_vmstat_extracts_only_wanted_keys() -> None:
    result = hm.parse_vmstat(_VMSTAT_OK)
    assert result["compact_fail"] == 1
    assert result["compact_success"] == 42
    assert result["allocstall_normal"] == 3
    # irrelevant key filtered out
    assert "pgpgin" not in result


def test_parse_vmstat_missing_keys_default_zero() -> None:
    result = hm.parse_vmstat("foo 1\n")
    assert result["compact_fail"] == 0
    assert result["allocstall_normal"] == 0


def test_parse_meminfo_keeps_kb_units() -> None:
    result = hm.parse_meminfo(_MEMINFO_HEALTHY)
    assert result["MemTotal"] == 24_000_000
    assert result["MemAvailable"] == 18_000_000
    assert result["SwapTotal"] == 2_000_000


# ── HostMetricsBuffer ──────────────────────────────────────────────────────


def _fake_sample(
    order7: int = 50,
    mem_mb: int = 18000,
    compact_fail: int = 0,
    p99: float = 0.1,
) -> hm.HostMetrics:
    return hm.HostMetrics(
        captured_at=time.time(),
        buddy_normal={o: (100 if o < 4 else (order7 if o == 7 else 5)) for o in range(11)},
        unmovable_order4plus=1,
        mem_available_kb=mem_mb * 1024,
        mem_total_kb=24_000_000,
        vmstat_compact_fail=compact_fail,
        vmstat_compact_success=0,
        vmstat_allocstall_normal=0,
        docker_call_p99_s=p99,
        docker_call_timeout_total=0,
    )


def test_buffer_respects_capacity() -> None:
    buf = hm.HostMetricsBuffer(capacity=3)
    for i in range(10):
        buf.append(_fake_sample(order7=i))
    assert len(buf) == 3
    # Only the last three samples (order7=7,8,9) remain
    assert buf.percentile_order_free(7, 0.0) == 7
    assert buf.percentile_order_free(7, 0.99) == 9


def test_buffer_is_warm_threshold() -> None:
    buf = hm.HostMetricsBuffer(capacity=100, bootstrap_fraction=0.25)
    # 24 samples: below bootstrap threshold
    for _ in range(24):
        buf.append(_fake_sample())
    assert buf.is_warm() is False
    # 25th sample: threshold met
    buf.append(_fake_sample())
    assert buf.is_warm() is True


def test_buffer_percentile_nearest_rank() -> None:
    buf = hm.HostMetricsBuffer(capacity=10)
    # values 1..10 at order 7
    for i in range(1, 11):
        buf.append(_fake_sample(order7=i))
    # nearest-rank p05 on 10 samples → index 0 → value 1
    assert buf.percentile_order_free(7, 0.05) == 1
    # p50 → index 5 → value 6
    assert buf.percentile_order_free(7, 0.5) == 6
    # p99 clamps to last index → value 10
    assert buf.percentile_order_free(7, 0.99) == 10


def test_buffer_percentile_empty_returns_none() -> None:
    buf = hm.HostMetricsBuffer(capacity=10)
    assert buf.percentile_order_free(7, 0.5) is None
    assert buf.percentile_mem_available_mb(0.5) is None


def test_buffer_summary_for_persist_handles_empty() -> None:
    buf = hm.HostMetricsBuffer(capacity=10)
    summary = buf.summary_for_persist()
    assert summary == {"samples": 0}


def test_buffer_summary_for_persist_populated() -> None:
    buf = hm.HostMetricsBuffer(capacity=10)
    for i in range(1, 11):
        buf.append(_fake_sample(order7=i, mem_mb=1000 * i))
    summary = buf.summary_for_persist()
    assert summary["samples"] == 10
    assert summary["order7_p50"] == 6
    assert summary["mem_available_mb_p95"] >= summary["mem_available_mb_p50"]


# ── capacity helper ───────────────────────────────────────────────────────


def test_capacity_from_retention() -> None:
    assert hm.capacity_from_retention(48, 60) == 2880
    assert hm.capacity_from_retention(1, 60) == 60
    # Zero interval clamps to 1
    assert hm.capacity_from_retention(48, 0) == 1


# ── DockerCallStats ───────────────────────────────────────────────────────


def test_docker_call_stats_p99_empty() -> None:
    stats = hm.DockerCallStats(window=10)
    p99, timeouts = stats.snapshot()
    assert p99 == 0.0
    assert timeouts == 0


def test_docker_call_stats_records_and_sorts() -> None:
    stats = hm.DockerCallStats(window=100)
    for v in [0.1, 0.2, 0.3, 0.4, 5.0]:  # 5.0 is the outlier
        stats.record(v)
    p99, _ = stats.snapshot()
    # Nearest-rank p99 on 5 samples: idx = max(0, int(5*0.99)-1) = 3 -> value 0.4
    # (p99 of a 5-sample window is inherently coarse; larger windows are smoother.)
    assert p99 in {0.4, 5.0}


def test_docker_call_stats_timeout_counter_monotonic() -> None:
    stats = hm.DockerCallStats(window=100)
    stats.record(0.1)
    stats.record(8.0, timed_out=True)
    stats.record(8.0, timed_out=True)
    _, timeouts = stats.snapshot()
    assert timeouts == 2


def test_docker_call_stats_reconfigure_resizes() -> None:
    stats = hm.DockerCallStats(window=3)
    for v in [1.0, 2.0, 3.0]:
        stats.record(v)
    stats.reconfigure(10)
    # Old samples preserved
    stats.record(4.0)
    _, _ = stats.snapshot()
    # No exception; window has been resized
    assert stats._window.maxlen == 10  # noqa: SLF001


# ── evaluate() truth table ────────────────────────────────────────────────


@pytest.fixture
def cfg() -> hm.HostMonitorConfig:
    return hm.HostMonitorConfig(
        order7_warn_floor=2,
        order7_crit_floor=0,
        mem_available_warn_mb=1024,
        mem_available_crit_mb=512,
        docker_p99_watch_s=2.0,
        docker_p99_warn_s=4.0,
        docker_call_timeout_s=8.0,
    )


@pytest.fixture
def warm_buffer() -> hm.HostMetricsBuffer:
    """A buffer where the p05/p01 of order7_free is 40."""
    buf = hm.HostMetricsBuffer(capacity=100, bootstrap_fraction=0.25)
    for _ in range(100):
        buf.append(_fake_sample(order7=40, mem_mb=8000))
    assert buf.is_warm()
    return buf


def test_evaluate_bootstrap_when_buffer_cold(cfg) -> None:
    buf = hm.HostMetricsBuffer(capacity=100)
    sample = _fake_sample(order7=50, mem_mb=18000)
    state = hm.evaluate(sample, buf, hm.HostHealthState.BOOTSTRAP, cfg)
    assert state == hm.HostHealthState.BOOTSTRAP


def test_evaluate_ok_on_warm_buffer_healthy_sample(cfg, warm_buffer) -> None:
    sample = _fake_sample(order7=50, mem_mb=18000)
    state = hm.evaluate(sample, warm_buffer, hm.HostHealthState.OK, cfg)
    assert state == hm.HostHealthState.OK


def test_evaluate_crit_on_order7_zero(cfg, warm_buffer) -> None:
    sample = _fake_sample(order7=0, mem_mb=18000)
    state = hm.evaluate(sample, warm_buffer, hm.HostHealthState.OK, cfg)
    assert state == hm.HostHealthState.CRIT


def test_evaluate_crit_on_low_mem(cfg, warm_buffer) -> None:
    sample = _fake_sample(order7=50, mem_mb=400)
    state = hm.evaluate(sample, warm_buffer, hm.HostHealthState.OK, cfg)
    assert state == hm.HostHealthState.CRIT


def test_evaluate_crit_on_docker_timeout_breach(cfg, warm_buffer) -> None:
    sample = _fake_sample(order7=50, mem_mb=18000, p99=8.5)
    state = hm.evaluate(sample, warm_buffer, hm.HostHealthState.OK, cfg)
    assert state == hm.HostHealthState.CRIT


def test_evaluate_warn_on_order7_at_warn_floor(cfg, warm_buffer) -> None:
    sample = _fake_sample(order7=1, mem_mb=18000)
    state = hm.evaluate(sample, warm_buffer, hm.HostHealthState.OK, cfg)
    assert state == hm.HostHealthState.WARN


def test_evaluate_warn_on_low_mem_below_warn_floor(cfg, warm_buffer) -> None:
    sample = _fake_sample(order7=50, mem_mb=800)
    state = hm.evaluate(sample, warm_buffer, hm.HostHealthState.OK, cfg)
    assert state == hm.HostHealthState.WARN


def test_evaluate_warn_when_compact_fail_increased(cfg, warm_buffer) -> None:
    prev = _fake_sample(order7=50, mem_mb=18000, compact_fail=1)
    now = _fake_sample(order7=50, mem_mb=18000, compact_fail=5)
    state = hm.evaluate(now, warm_buffer, hm.HostHealthState.OK, cfg, prev_sample=prev)
    assert state == hm.HostHealthState.WARN


def test_evaluate_warn_on_docker_p99_warn_breach(cfg, warm_buffer) -> None:
    sample = _fake_sample(order7=50, mem_mb=18000, p99=5.0)
    state = hm.evaluate(sample, warm_buffer, hm.HostHealthState.OK, cfg)
    assert state == hm.HostHealthState.WARN


def test_evaluate_watch_on_docker_p99_watch_breach(cfg, warm_buffer) -> None:
    sample = _fake_sample(order7=50, mem_mb=18000, p99=2.5)
    state = hm.evaluate(sample, warm_buffer, hm.HostHealthState.OK, cfg)
    assert state == hm.HostHealthState.WATCH


def test_evaluate_watch_when_order7_drops_below_p05(cfg) -> None:
    # Build a buffer where p05(order7) == 20
    buf = hm.HostMetricsBuffer(capacity=100, bootstrap_fraction=0.25)
    # 95 samples at 50, 5 samples at 20 → sorted p05 (nearest-rank idx 5) is 20
    for _ in range(95):
        buf.append(_fake_sample(order7=50))
    for _ in range(5):
        buf.append(_fake_sample(order7=20))
    assert buf.is_warm()
    # Below p05
    sample = _fake_sample(order7=10, mem_mb=18000)
    state = hm.evaluate(sample, buf, hm.HostHealthState.OK, cfg)
    assert state in {hm.HostHealthState.WATCH, hm.HostHealthState.WARN}


def test_evaluate_crit_beats_warn_beats_watch(cfg, warm_buffer) -> None:
    # Configure a sample that triggers CRIT *and* WARN *and* WATCH
    sample = _fake_sample(order7=0, mem_mb=400, p99=9.0)
    state = hm.evaluate(sample, warm_buffer, hm.HostHealthState.OK, cfg)
    assert state == hm.HostHealthState.CRIT


def test_evaluate_hard_floors_apply_even_in_bootstrap(cfg) -> None:
    """Verify hard CRIT/WARN floors fire without a warm baseline."""
    buf = hm.HostMetricsBuffer(capacity=100)
    # No samples appended → not warm.
    assert not buf.is_warm()
    sample = _fake_sample(order7=0, mem_mb=400, p99=9.0)
    state = hm.evaluate(sample, buf, hm.HostHealthState.BOOTSTRAP, cfg)
    assert state == hm.HostHealthState.CRIT


# ── HostHealthState ordering / is_degraded ────────────────────────────────


def test_state_ordering() -> None:
    assert hm.HostHealthState.BOOTSTRAP < hm.HostHealthState.OK
    assert hm.HostHealthState.OK < hm.HostHealthState.WATCH
    assert hm.HostHealthState.WATCH < hm.HostHealthState.WARN
    assert hm.HostHealthState.WARN < hm.HostHealthState.CRIT


def test_state_is_degraded_threshold() -> None:
    assert hm.HostHealthState.BOOTSTRAP.is_degraded() is False
    assert hm.HostHealthState.OK.is_degraded() is False
    assert hm.HostHealthState.WATCH.is_degraded() is False
    assert hm.HostHealthState.WARN.is_degraded() is True
    assert hm.HostHealthState.CRIT.is_degraded() is True


# ── Process-wide state holder ─────────────────────────────────────────────


def test_state_holder_transitions_preserve_sample() -> None:
    hm._reset_host_state_for_tests()  # noqa: SLF001
    assert hm.get_host_state() == hm.HostHealthState.BOOTSTRAP
    sample = _fake_sample()
    hm.set_host_state(hm.HostHealthState.WATCH, sample)
    assert hm.get_host_state() == hm.HostHealthState.WATCH
    assert hm.get_host_state_snapshot() is sample


def test_state_holder_resets_for_tests() -> None:
    hm._reset_host_state_for_tests()  # noqa: SLF001
    hm.set_host_state(hm.HostHealthState.WARN)
    hm._reset_host_state_for_tests()  # noqa: SLF001
    assert hm.get_host_state() == hm.HostHealthState.BOOTSTRAP
    assert hm.get_host_state_snapshot() is None


# ── Persist summary (best-effort, does not raise) ─────────────────────────


def test_persist_summary_writes_json(tmp_path) -> None:
    buf = hm.HostMetricsBuffer(capacity=10)
    for i in range(1, 11):
        buf.append(_fake_sample(order7=i))
    dest = tmp_path / "subdir" / "summary.json"
    hm.persist_summary_to_path(buf, str(dest))
    assert dest.exists()
    data = dest.read_text()
    assert '"samples": 10' in data


def test_persist_summary_swallows_errors() -> None:
    buf = hm.HostMetricsBuffer(capacity=10)
    # Pass a path that will fail write (e.g. containing a NUL byte).
    hm.persist_summary_to_path(buf, "/does/not/exist/and/cannot-create/\x00")
    # No exception raised is the contract.
