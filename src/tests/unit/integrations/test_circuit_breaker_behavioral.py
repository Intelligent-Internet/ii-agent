"""Tests for circuit breaker behavioral gaps observed in production logs.

Covers:
- P4: HALF_OPEN probe failure increments failure count
- P4: Failure count survives across HALF_OPEN cycles (5→6→7→...→12 pattern)
- P4: Independent circuit breaker instances are isolated
"""

from __future__ import annotations

import time as time_module

import pytest

from ii_agent.integrations.a2a.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerOpenError,
    CircuitState,
)

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# HALF_OPEN probe failure increments count
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_half_open_probe_failure_increments_failure_count(monkeypatch):
    """When a HALF_OPEN probe fails, the failure count should increment,
    not reset. This matches the production pattern where failures went
    5→6→7→8→... across HALF_OPEN cycles."""
    cb = CircuitBreaker(failure_threshold=5, cooldown_seconds=60)

    # Drive to OPEN with 5 failures
    for _ in range(5):
        await cb.record_failure()
    assert cb.state == CircuitState.OPEN
    assert cb.failure_count == 5

    # Advance time past cooldown to get to HALF_OPEN
    original = time_module.monotonic
    t = original() + 61
    monkeypatch.setattr(time_module, "monotonic", lambda: t)

    await cb.check()  # → HALF_OPEN
    assert cb.state == CircuitState.HALF_OPEN

    # Probe fails → should re-OPEN with count=6
    await cb.record_failure()
    assert cb.state == CircuitState.OPEN
    assert cb.failure_count == 6


@pytest.mark.asyncio
async def test_failure_count_survives_across_multiple_half_open_cycles(monkeypatch):
    """Simulate the production pattern: failures accumulate 5→6→7→8
    across multiple HALF_OPEN → OPEN cycles without ever resetting."""
    cb = CircuitBreaker(failure_threshold=5, cooldown_seconds=0.01)

    # Initial 5 failures → OPEN
    for _ in range(5):
        await cb.record_failure()
    assert cb.failure_count == 5
    assert cb.state == CircuitState.OPEN

    original = time_module.monotonic
    base_time = original()

    for expected_count in range(6, 13):  # 6, 7, 8, 9, 10, 11, 12
        # Advance past cooldown
        base_time += 1.0
        monkeypatch.setattr(time_module, "monotonic", lambda bt=base_time: bt)

        await cb.check()  # → HALF_OPEN
        assert cb.state == CircuitState.HALF_OPEN

        await cb.record_failure()  # probe fails → re-OPEN
        assert cb.state == CircuitState.OPEN
        assert cb.failure_count == expected_count


# ---------------------------------------------------------------------------
# Independent circuit breaker instances
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_separate_instances_are_independent():
    """The chat circuit breaker (a2a-chat) and agent circuit breaker
    are independent instances. Failing one should not affect the other."""
    cb_chat = CircuitBreaker(name="a2a-chat", failure_threshold=3, cooldown_seconds=60)
    cb_agent = CircuitBreaker(name="a2a-agent", failure_threshold=3, cooldown_seconds=60)

    # Fail the chat breaker to OPEN
    for _ in range(3):
        await cb_chat.record_failure()
    assert cb_chat.state == CircuitState.OPEN

    # Agent breaker should still be CLOSED
    assert cb_agent.state == CircuitState.CLOSED
    await cb_agent.check()  # should not raise


@pytest.mark.asyncio
async def test_fresh_instance_always_starts_closed():
    """Each new CircuitBreaker instance starts CLOSED with zero failures.
    This explains why agent inner loop always shows failure=1/5:
    each sandbox gets a fresh instance."""
    for _ in range(5):
        cb = CircuitBreaker(failure_threshold=5, cooldown_seconds=60)
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0
        assert cb.fallback_count == 0

        # Record one failure (simulating per-session agent pattern)
        await cb.record_failure()
        assert cb.failure_count == 1
        assert cb.state == CircuitState.CLOSED  # threshold=5, only 1


# ---------------------------------------------------------------------------
# HALF_OPEN success resets count
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_half_open_success_resets_failure_count_to_zero(monkeypatch):
    """When a HALF_OPEN probe succeeds, the failure count resets to 0
    and the circuit closes. This is the recovery path."""
    cb = CircuitBreaker(failure_threshold=5, cooldown_seconds=60)

    # Drive to failure count = 8 (like production pattern)
    for _ in range(5):
        await cb.record_failure()
    assert cb.failure_count == 5

    original = time_module.monotonic
    base_time = original()

    # Two more HALF_OPEN cycles with failure
    for _ in range(3):
        base_time += 61
        monkeypatch.setattr(time_module, "monotonic", lambda bt=base_time: bt)
        await cb.check()
        await cb.record_failure()

    assert cb.failure_count == 8
    assert cb.state == CircuitState.OPEN

    # Now succeed on HALF_OPEN
    base_time += 61
    monkeypatch.setattr(time_module, "monotonic", lambda bt=base_time: bt)
    await cb.check()  # → HALF_OPEN
    await cb.record_success()

    assert cb.state == CircuitState.CLOSED
    assert cb.failure_count == 0
