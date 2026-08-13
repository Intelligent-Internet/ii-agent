"""Tests for CircuitBreaker — targeting line/branch coverage gaps."""

from __future__ import annotations

import json

import pytest

from ii_agent.integrations.a2a.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerOpenError,
    CircuitState,
    is_non_retriable,
    is_rate_limit,
)

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Constructor validation
# ---------------------------------------------------------------------------


def test_invalid_failure_threshold_raises():
    with pytest.raises(ValueError):
        CircuitBreaker(failure_threshold=0)


def test_invalid_cooldown_raises():
    with pytest.raises(ValueError):
        CircuitBreaker(cooldown_seconds=0)

    with pytest.raises(ValueError):
        CircuitBreaker(cooldown_seconds=-1)


# ---------------------------------------------------------------------------
# CLOSED → OPEN transition
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_closed_does_not_raise():
    cb = CircuitBreaker(failure_threshold=3, cooldown_seconds=60)
    await cb.check()  # must not raise


@pytest.mark.asyncio
async def test_failures_open_circuit():
    cb = CircuitBreaker(failure_threshold=2, cooldown_seconds=60)
    await cb.record_failure()
    assert cb.state == CircuitState.CLOSED
    await cb.record_failure()
    assert cb.state == CircuitState.OPEN


@pytest.mark.asyncio
async def test_open_circuit_check_raises():
    cb = CircuitBreaker(failure_threshold=1, cooldown_seconds=60)
    await cb.record_failure()
    assert cb.is_open

    with pytest.raises(CircuitBreakerOpenError) as exc_info:
        await cb.check()
    assert exc_info.value.remaining_seconds > 0


@pytest.mark.asyncio
async def test_failure_in_open_state_is_noop():
    """Recording a failure while OPEN should not change anything."""
    cb = CircuitBreaker(failure_threshold=1, cooldown_seconds=60)
    await cb.record_failure()  # → OPEN
    count_before = cb.failure_count
    await cb.record_failure()
    assert cb.state == CircuitState.OPEN
    assert cb.failure_count == count_before  # unchanged


# ---------------------------------------------------------------------------
# OPEN → HALF_OPEN after cooldown
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_transitions_to_half_open_after_cooldown(monkeypatch):
    """After the cooldown elapses, check() transitions from OPEN to HALF_OPEN."""
    import time

    cb = CircuitBreaker(failure_threshold=1, cooldown_seconds=0.01)
    await cb.record_failure()
    assert cb.state == CircuitState.OPEN

    # Advance monotonic time past the cooldown.
    original_monotonic = time.monotonic
    future_time = original_monotonic() + 1.0
    monkeypatch.setattr(time, "monotonic", lambda: future_time)

    await cb.check()  # should NOT raise, and should transition to HALF_OPEN
    assert cb.state == CircuitState.HALF_OPEN


# ---------------------------------------------------------------------------
# HALF_OPEN transitions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_half_open_success_closes_circuit(monkeypatch):
    import time

    cb = CircuitBreaker(failure_threshold=1, cooldown_seconds=0.01)
    await cb.record_failure()

    original_monotonic = time.monotonic
    future_time = original_monotonic() + 1.0
    monkeypatch.setattr(time, "monotonic", lambda: future_time)

    await cb.check()  # → HALF_OPEN
    await cb.record_success()
    assert cb.state == CircuitState.CLOSED
    assert cb.failure_count == 0


@pytest.mark.asyncio
async def test_half_open_failure_reopens_circuit(monkeypatch):
    import time

    cb = CircuitBreaker(failure_threshold=1, cooldown_seconds=0.01)
    await cb.record_failure()

    original_monotonic = time.monotonic
    future_time = original_monotonic() + 1.0
    monkeypatch.setattr(time, "monotonic", lambda: future_time)

    await cb.check()  # → HALF_OPEN
    await cb.record_failure()  # immediately re-opens
    assert cb.state == CircuitState.OPEN


# ---------------------------------------------------------------------------
# record_success in closed state
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_record_success_in_closed_state():
    cb = CircuitBreaker(failure_threshold=3, cooldown_seconds=60)
    await cb.record_failure()
    assert cb.failure_count == 1
    await cb.record_success()
    assert cb.state == CircuitState.CLOSED
    assert cb.failure_count == 0


# ---------------------------------------------------------------------------
# remaining_cooldown
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_remaining_cooldown_is_zero_when_closed():
    cb = CircuitBreaker(failure_threshold=1, cooldown_seconds=60)
    assert cb.remaining_cooldown() == 0.0


@pytest.mark.asyncio
async def test_remaining_cooldown_positive_when_open():
    cb = CircuitBreaker(failure_threshold=1, cooldown_seconds=60)
    await cb.record_failure()
    remaining = cb.remaining_cooldown()
    assert 0 < remaining <= 60.0


# ---------------------------------------------------------------------------
# reset
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reset_returns_to_closed():
    cb = CircuitBreaker(failure_threshold=1, cooldown_seconds=60)
    await cb.record_failure()
    assert cb.is_open
    cb.reset()
    assert cb.is_closed
    assert cb.failure_count == 0


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------


def test_properties_initial_state():
    cb = CircuitBreaker()
    assert cb.is_closed
    assert not cb.is_open
    assert not cb.is_half_open
    assert cb.state == CircuitState.CLOSED
    assert cb.failure_count == 0
    assert cb.fallback_count == 0


# ---------------------------------------------------------------------------
# P0: Rate-limit detection and longer cooldown
# ---------------------------------------------------------------------------


def test_is_rate_limit_with_httpx_429():
    import httpx

    request = httpx.Request("POST", "http://example.com/message:stream")
    response = httpx.Response(429, request=request)
    exc = httpx.HTTPStatusError("rate limit", request=request, response=response)
    assert is_rate_limit(exc) is True


def test_is_rate_limit_with_httpx_503():
    import httpx

    request = httpx.Request("POST", "http://example.com/message:stream")
    response = httpx.Response(503, request=request)
    exc = httpx.HTTPStatusError("overloaded", request=request, response=response)
    assert is_rate_limit(exc) is True


def test_is_rate_limit_with_httpx_500_is_false():
    import httpx

    request = httpx.Request("POST", "http://example.com/message:stream")
    response = httpx.Response(500, request=request)
    exc = httpx.HTTPStatusError("server error", request=request, response=response)
    assert is_rate_limit(exc) is False


def test_is_rate_limit_generic_exception_is_false():
    assert is_rate_limit(RuntimeError("some error")) is False


@pytest.mark.asyncio
async def test_rate_limit_opens_immediately_with_longer_cooldown():
    """A rate-limit error should open the circuit immediately, ignoring failure_threshold."""
    import httpx

    cb = CircuitBreaker(
        failure_threshold=10,
        cooldown_seconds=60,
        rate_limit_cooldown_seconds=300,
    )
    request = httpx.Request("POST", "http://example.com/")
    response = httpx.Response(429, request=request)
    rate_limit_exc = httpx.HTTPStatusError("rate limit", request=request, response=response)

    await cb.record_failure(rate_limit_exc)
    assert cb.state == CircuitState.OPEN
    # Cooldown should use the longer rate_limit_cooldown_seconds
    remaining = cb.remaining_cooldown()
    assert remaining > 60  # Must be the longer cooldown, not the base 60s


@pytest.mark.asyncio
async def test_rate_limit_cooldown_defaults_to_5x_base():
    cb = CircuitBreaker(cooldown_seconds=60)
    assert cb.rate_limit_cooldown_seconds == 300.0


# ---------------------------------------------------------------------------
# P1: Non-retriable error filtering
# ---------------------------------------------------------------------------


def test_is_non_retriable_value_error():
    assert is_non_retriable(ValueError("bad prompt")) is True


def test_is_non_retriable_json_decode_error():
    exc = json.JSONDecodeError("msg", "doc", 0)
    assert is_non_retriable(exc) is True


def test_is_non_retriable_runtime_error_is_false():
    assert is_non_retriable(RuntimeError("transient")) is False


@pytest.mark.asyncio
async def test_non_retriable_does_not_increment_failure_count():
    cb = CircuitBreaker(failure_threshold=2, cooldown_seconds=60)
    await cb.record_failure(ValueError("bad prompt"))
    assert cb.failure_count == 0
    assert cb.state == CircuitState.CLOSED  # unchanged


@pytest.mark.asyncio
async def test_non_retriable_does_not_open_circuit():
    """Even many non-retriable failures should never open the circuit."""
    cb = CircuitBreaker(failure_threshold=1, cooldown_seconds=60)
    for _ in range(5):
        await cb.record_failure(ValueError("bad prompt"))
    assert cb.state == CircuitState.CLOSED


# ---------------------------------------------------------------------------
# P2: Fallback cost counter
# ---------------------------------------------------------------------------


def test_fallback_count_starts_at_zero():
    cb = CircuitBreaker()
    assert cb.fallback_count == 0


def test_record_fallback_increments():
    cb = CircuitBreaker()
    cb.record_fallback()
    cb.record_fallback()
    cb.record_fallback()
    assert cb.fallback_count == 3


def test_reset_clears_fallback_count():
    cb = CircuitBreaker()
    cb.record_fallback()
    cb.record_fallback()
    cb.reset()
    assert cb.fallback_count == 0


# ---------------------------------------------------------------------------
# record_failure backward compatibility (no exc argument)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_record_failure_without_exc_still_works():
    """Calling record_failure() without an exception should behave as before."""
    cb = CircuitBreaker(failure_threshold=2, cooldown_seconds=60)
    await cb.record_failure()
    assert cb.failure_count == 1
    await cb.record_failure()
    assert cb.state == CircuitState.OPEN
