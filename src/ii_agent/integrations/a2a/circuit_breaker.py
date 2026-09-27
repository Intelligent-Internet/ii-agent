"""Circuit breaker for A2A adapter connectivity.

Implements a three-state circuit breaker (closed → open → half-open)
that short-circuits calls to the A2A adapter when it is repeatedly unavailable,
giving it time to recover before retrying.

States
------
``CLOSED``
    Normal operation.  All calls pass through.  Failure counter incremented
    on each error.  When ``failure_threshold`` is reached the circuit opens.

``OPEN``
    Short-circuit mode.  Calls raise :class:`CircuitBreakerOpenError`
    immediately without hitting the network.  After ``cooldown_seconds``
    the circuit transitions to HALF_OPEN.

``HALF_OPEN``
    Probe mode.  The *next* call is allowed through.  If it succeeds the
    circuit closes (counter reset).  If it fails the circuit opens again
    and the cooldown restarts.

Rate-limit awareness
--------------------
When an exception is classified as a rate-limit (HTTP 429 / 503), the breaker
opens **immediately** with a separate, longer cooldown
(``rate_limit_cooldown_seconds``) because quota exhaustion is systemic and
won't resolve in seconds.  This mirrors the pipeline_core circuit breaker
design to keep cross-project behaviour consistent.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Exception classification helpers
# ------------------------------------------------------------------


def is_rate_limit(exc: BaseException) -> bool:
    """Return ``True`` if *exc* indicates a rate-limit or service overload.

    Handles raw ``httpx.HTTPStatusError`` (from :class:`IIAgentA2AClient`)
    and wrapped A2A SDK errors (``A2AClientHTTPError``) when the SDK is
    installed.
    """
    try:
        import httpx

        if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in (429, 503):
            return True
    except ImportError:  # pragma: no cover
        pass
    try:
        from a2a.client.errors import A2AClientHTTPError  # type: ignore[import-untyped]

        if isinstance(exc, A2AClientHTTPError) and exc.status_code in (429, 503):
            return True
    except ImportError:  # pragma: no cover
        pass
    return False


def is_non_retriable(exc: BaseException) -> bool:
    """Return ``True`` for errors that indicate a bad request, not a backend failure.

    These should **not** count toward the circuit breaker failure threshold
    because they wouldn't be fixed by retrying or switching backends.
    """
    return isinstance(exc, (ValueError, json.JSONDecodeError))


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreakerOpenError(Exception):
    """Raised when a call is short-circuited by an open circuit breaker."""

    def __init__(self, remaining_seconds: float) -> None:
        self.remaining_seconds = remaining_seconds
        super().__init__(f"Circuit breaker is open; retry in {remaining_seconds:.1f}s")


class CircuitBreaker:
    """Async-safe circuit breaker with rate-limit awareness.

    Parameters
    ----------
    failure_threshold:
        Number of consecutive failures before the circuit opens.
    cooldown_seconds:
        Seconds the circuit stays open before transitioning to HALF_OPEN.
    rate_limit_cooldown_seconds:
        Longer cooldown applied when the failure is a rate-limit (429/503).
        Defaults to 5× the base cooldown.
    name:
        Optional label used in log messages.
    """

    def __init__(
        self,
        *,
        failure_threshold: int = 5,
        cooldown_seconds: float = 60.0,
        rate_limit_cooldown_seconds: float | None = None,
        name: str = "a2a",
    ) -> None:
        if failure_threshold < 1:
            raise ValueError("failure_threshold must be >= 1")
        if cooldown_seconds <= 0:
            raise ValueError("cooldown_seconds must be > 0")

        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self.rate_limit_cooldown_seconds = (
            rate_limit_cooldown_seconds
            if rate_limit_cooldown_seconds is not None
            else cooldown_seconds * 5
        )
        self.name = name

        self._state: CircuitState = CircuitState.CLOSED
        self._failure_count: int = 0
        self._fallback_count: int = 0
        self._opened_at: Optional[float] = None
        self._active_cooldown: float = cooldown_seconds
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    @property
    def state(self) -> CircuitState:
        return self._state

    @property
    def failure_count(self) -> int:
        return self._failure_count

    @property
    def fallback_count(self) -> int:
        """Cumulative count of requests that would have used the fallback path."""
        return self._fallback_count

    @property
    def is_closed(self) -> bool:
        return self._state == CircuitState.CLOSED

    @property
    def is_open(self) -> bool:
        return self._state == CircuitState.OPEN

    @property
    def is_half_open(self) -> bool:
        return self._state == CircuitState.HALF_OPEN

    def remaining_cooldown(self) -> float:
        """Seconds until the circuit transitions to HALF_OPEN (0 if already there or CLOSED)."""
        if self._state != CircuitState.OPEN or self._opened_at is None:
            return 0.0
        elapsed = time.monotonic() - self._opened_at
        return max(0.0, self._active_cooldown - elapsed)

    def record_fallback(self) -> None:
        """Increment the fallback counter (called by the inner-loop strategy)."""
        self._fallback_count += 1

    async def check(self) -> None:
        """Raise :class:`CircuitBreakerOpenError` when the circuit is open.

        Must be called *before* every protected operation.  Thread/task-safe.
        """
        async with self._lock:
            if self._state == CircuitState.CLOSED:
                return

            if self._state == CircuitState.OPEN:
                remaining = self.remaining_cooldown()
                if remaining > 0:
                    raise CircuitBreakerOpenError(remaining)
                # Cooldown elapsed → transition to HALF_OPEN
                self._state = CircuitState.HALF_OPEN
                return  # Allow the probe call through

            # HALF_OPEN — already letting one probe through (do not raise)

    async def record_success(self) -> None:
        """Record a successful call; closes the circuit and resets the counter."""
        async with self._lock:
            if self._state != CircuitState.CLOSED:
                logger.warning(
                    "Circuit breaker '%s' %s -> CLOSED (recovered; %d requests used fallback)",
                    self.name,
                    self._state.value,
                    self._fallback_count,
                )
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._opened_at = None
            self._active_cooldown = self.cooldown_seconds

    async def record_failure(self, exc: BaseException | None = None) -> None:
        """Record a failed call.

        Parameters
        ----------
        exc:
            The exception that caused the failure.  When provided, the breaker
            uses it to detect rate-limits (longer cooldown) and non-retriable
            errors (skipped entirely).

        Behaviour by state:

        - In CLOSED: increments counter; opens when threshold reached.
          A rate-limit opens **immediately** regardless of failure count.
        - In HALF_OPEN: immediately re-opens and restarts cooldown.
        - In OPEN: no-op (already open).
        """
        # Non-retriable errors (bad prompt / JSON) should never trip the breaker.
        if exc is not None and is_non_retriable(exc):
            return

        async with self._lock:
            if self._state == CircuitState.OPEN:
                return

            rate_limited = exc is not None and is_rate_limit(exc)

            if rate_limited:
                # Immediate open with longer cooldown — quota exhaustion is systemic.
                self._state = CircuitState.OPEN
                self._opened_at = time.monotonic()
                self._active_cooldown = self.rate_limit_cooldown_seconds
                self._failure_count = 0
                logger.warning(
                    "Circuit breaker '%s' -> OPEN (rate limit detected, cooldown=%ds)",
                    self.name,
                    int(self._active_cooldown),
                )
                return

            self._failure_count += 1

            if (
                self._state == CircuitState.HALF_OPEN
                or self._failure_count >= self.failure_threshold
            ):
                self._state = CircuitState.OPEN
                self._opened_at = time.monotonic()
                self._active_cooldown = self.cooldown_seconds
                logger.warning(
                    "Circuit breaker '%s' -> OPEN (failures=%d, cooldown=%ds)",
                    self.name,
                    self._failure_count,
                    int(self._active_cooldown),
                )

    def reset(self) -> None:
        """Forcibly reset the circuit to CLOSED (for testing / admin use)."""
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._fallback_count = 0
        self._opened_at = None
        self._active_cooldown = self.cooldown_seconds
