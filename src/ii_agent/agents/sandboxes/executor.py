"""Dedicated thread pool executor for Docker API calls.

Docker-py is synchronous; running its calls on the default asyncio executor
means a slow Docker daemon can starve unrelated database I/O. This module
exposes a bounded ThreadPoolExecutor used exclusively for Docker blocking
calls, plus a helper that wraps ``asyncio.to_thread`` with an explicit
timeout.

Usage::

    from ii_agent.agents.sandboxes.executor import docker_call

    container = await docker_call(client.containers.get, provider_sandbox_id)

The executor is lazily created on first use and shared process-wide.
"""

from __future__ import annotations

import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Optional, TypeVar

from ii_agent.core.config.settings import get_settings
from ii_agent.core.logger import logger

_T = TypeVar("_T")

_executor: Optional[ThreadPoolExecutor] = None
_executor_lock = threading.Lock()


def get_docker_executor() -> ThreadPoolExecutor:
    """Return the process-wide dedicated Docker executor, creating it lazily."""
    global _executor
    if _executor is not None:
        return _executor
    with _executor_lock:
        if _executor is None:
            try:
                max_workers = int(get_settings().sandbox.docker_executor_max_workers)
            except Exception:
                max_workers = 8
            _executor = ThreadPoolExecutor(
                max_workers=max_workers,
                thread_name_prefix="docker-api",
            )
            logger.info(f"Docker executor initialized (max_workers={max_workers})")
    return _executor


async def docker_call(
    func: Callable[..., _T],
    /,
    *args: Any,
    timeout: Optional[float] = None,
    **kwargs: Any,
) -> _T:
    """Run a blocking Docker call on the dedicated executor with a timeout.

    Mirrors the ``asyncio.to_thread`` signature but (1) uses a bounded pool
    dedicated to Docker so it cannot starve DB I/O, and (2) applies an
    explicit timeout sourced from settings when not provided by the caller.

    Every call's wall-clock duration is recorded into the process-wide
    :class:`~ii_agent.agents.sandboxes.host_monitor.DockerCallStats`
    rolling window so the host monitor can derive a p99 signal and a
    timeout counter. Recording is best-effort; any failure is
    suppressed because the Docker call's result (or exception) is the
    primary contract.
    """
    loop = asyncio.get_running_loop()
    executor = get_docker_executor()

    if timeout is None:
        try:
            timeout = float(get_settings().sandbox.docker_call_timeout_seconds)
        except Exception:
            timeout = 8.0

    # Import lazily to avoid a circular import chain between
    # host_monitor <-> executor at module import time.
    from ii_agent.agents.sandboxes.host_monitor import get_docker_call_stats

    try:
        window = int(get_settings().sandbox.host_monitor_docker_latency_window)
    except Exception:
        window = 60
    stats = get_docker_call_stats(window)

    def _invoke() -> _T:
        return func(*args, **kwargs)

    fut = loop.run_in_executor(executor, _invoke)
    start = loop.time()
    try:
        result = await asyncio.wait_for(fut, timeout=timeout)
    except asyncio.TimeoutError:
        duration = loop.time() - start
        try:
            stats.record(duration, timed_out=True)
        except Exception:
            pass
        raise
    duration = loop.time() - start
    try:
        stats.record(duration, timed_out=False)
    except Exception:
        pass
    return result


def shutdown_docker_executor() -> None:
    """Shut down the Docker executor. Call during app shutdown."""
    global _executor
    with _executor_lock:
        if _executor is not None:
            _executor.shutdown(wait=False, cancel_futures=True)
            _executor = None
