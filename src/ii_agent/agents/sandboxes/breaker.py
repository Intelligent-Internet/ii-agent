"""Per-sandbox circuit breaker for reconnect/restart failures.

Tracks consecutive failures per sandbox UUID within a sliding window. When
the threshold is exceeded, ``should_fail_fast()`` returns True so callers
can skip further attempts until the breaker resets or the underlying row
is marked DELETED by the cleanup loop.

This is an in-process, best-effort signal — it exists to stop runaway
restart loops that otherwise saturate the Docker daemon and starve the
asyncio event loop. It is NOT a durability/correctness primitive.
"""

from __future__ import annotations

import threading
import time
from typing import Dict, Tuple

from ii_agent.core.config.settings import get_settings
from ii_agent.core.logger import logger

# sandbox_id -> (first_failure_ts, consecutive_failures)
_state: Dict[str, Tuple[float, int]] = {}
_lock = threading.Lock()


def record_failure(sandbox_id: str) -> int:
    """Record a failure and return the current consecutive-failure count.

    If the oldest failure fell outside the configured window, the counter
    resets before incrementing.
    """
    try:
        window = float(get_settings().sandbox.sandbox_failure_window_seconds)
    except Exception:
        window = 300.0
    now = time.monotonic()
    with _lock:
        first_ts, count = _state.get(sandbox_id, (now, 0))
        if now - first_ts > window:
            first_ts = now
            count = 0
        count += 1
        _state[sandbox_id] = (first_ts, count)
        return count


def record_success(sandbox_id: str) -> None:
    """Clear the failure count for a sandbox on a successful operation."""
    with _lock:
        _state.pop(sandbox_id, None)


def should_fail_fast(sandbox_id: str) -> bool:
    """Return True when the breaker is open for this sandbox."""
    try:
        settings = get_settings().sandbox
        threshold = int(settings.max_sandbox_restart_failures)
        window = float(settings.sandbox_failure_window_seconds)
    except Exception:
        threshold = 3
        window = 300.0
    now = time.monotonic()
    with _lock:
        entry = _state.get(sandbox_id)
        if entry is None:
            return False
        first_ts, count = entry
        if now - first_ts > window:
            _state.pop(sandbox_id, None)
            return False
        if count >= threshold:
            logger.warning(
                f"Sandbox circuit breaker OPEN for {sandbox_id} "
                f"({count} failures within {window:.0f}s) — failing fast"
            )
            return True
        return False


def reset(sandbox_id: str | None = None) -> None:
    """Reset breaker state for one sandbox or all (for tests / admin)."""
    with _lock:
        if sandbox_id is None:
            _state.clear()
        else:
            _state.pop(sandbox_id, None)
