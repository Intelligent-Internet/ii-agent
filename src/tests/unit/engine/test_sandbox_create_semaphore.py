"""Unit tests for the concurrent-create semaphore in ``SandboxService``.

The gate protects the kernel from veth/bridge allocation bursts that
drive high-order page fragmentation (observed in the 2026-04-23 WSL2
force-reboot).  Tests exercise:

- the default (limit=2) caps in-flight creates
- a custom limit of 1 fully serialises creates
- limit=0 disables the gate (unlimited concurrency)
- slow waits log at INFO above the configured threshold
- settings changes rebuild the semaphore instead of keeping the old one
"""

from __future__ import annotations

import asyncio
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from ii_agent.agents.sandboxes import service as service_module
from ii_agent.agents.sandboxes.service import (
    SandboxService,
    _get_create_semaphore,
    _reset_create_semaphore_for_tests,
)
from ii_agent.agents.sandboxes.types import SandboxProviderType


def _make_settings(*, limit: int, log_threshold_ms: int = 500):
    return SimpleNamespace(
        sandbox=SimpleNamespace(
            sandbox_concurrent_create_limit=limit,
            sandbox_create_wait_log_threshold_ms=log_threshold_ms,
        )
    )


def _make_service(settings):
    return SandboxService(
        sandbox_repo=MagicMock(),
        session_repo=MagicMock(),
        config=settings,
    )


def _make_record():
    return SimpleNamespace(
        id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        provider=SandboxProviderType.DOCKER,
    )


@pytest.fixture(autouse=True)
def _reset_semaphore():
    """Ensure every test starts with a fresh gate."""
    _reset_create_semaphore_for_tests()
    yield
    _reset_create_semaphore_for_tests()


@pytest.mark.asyncio
async def test_semaphore_caps_concurrent_creates_at_limit():
    """With limit=2, at most 2 creates run concurrently."""
    settings = _make_settings(limit=2)
    service = _make_service(settings)

    in_flight = 0
    max_in_flight = 0
    release = asyncio.Event()

    async def slow_dispatch(record, metadata=None):
        nonlocal in_flight, max_in_flight
        in_flight += 1
        max_in_flight = max(max_in_flight, in_flight)
        await release.wait()
        in_flight -= 1
        return MagicMock()

    service._dispatch_create = slow_dispatch  # type: ignore[assignment]

    tasks = [asyncio.create_task(service._create_provider(_make_record())) for _ in range(5)]
    # Let the scheduler admit as many as the gate allows.
    await asyncio.sleep(0.05)
    assert max_in_flight == 2, f"expected max 2 concurrent, got {max_in_flight}"
    release.set()
    await asyncio.gather(*tasks)
    assert max_in_flight == 2


@pytest.mark.asyncio
async def test_semaphore_limit_of_one_fully_serialises():
    """Limit=1 means strict serialisation."""
    settings = _make_settings(limit=1)
    service = _make_service(settings)

    in_flight = 0
    max_in_flight = 0

    async def dispatch(record, metadata=None):
        nonlocal in_flight, max_in_flight
        in_flight += 1
        max_in_flight = max(max_in_flight, in_flight)
        await asyncio.sleep(0.01)
        in_flight -= 1
        return MagicMock()

    service._dispatch_create = dispatch  # type: ignore[assignment]

    await asyncio.gather(*[service._create_provider(_make_record()) for _ in range(4)])
    assert max_in_flight == 1


@pytest.mark.asyncio
async def test_limit_zero_disables_gate():
    """limit=0 disables the gate; all creates run fully concurrently."""
    settings = _make_settings(limit=0)
    service = _make_service(settings)

    in_flight = 0
    max_in_flight = 0
    release = asyncio.Event()

    async def dispatch(record, metadata=None):
        nonlocal in_flight, max_in_flight
        in_flight += 1
        max_in_flight = max(max_in_flight, in_flight)
        await release.wait()
        in_flight -= 1
        return MagicMock()

    service._dispatch_create = dispatch  # type: ignore[assignment]

    tasks = [asyncio.create_task(service._create_provider(_make_record())) for _ in range(6)]
    await asyncio.sleep(0.02)
    assert max_in_flight == 6
    release.set()
    await asyncio.gather(*tasks)

    # Also verify the module-level semaphore was never built.
    assert await _get_create_semaphore(0) is None


@pytest.mark.asyncio
async def test_wait_above_threshold_logs_info(caplog):
    """A create that waits longer than the threshold emits an INFO log."""
    settings = _make_settings(limit=1, log_threshold_ms=10)
    service = _make_service(settings)

    first_running = asyncio.Event()
    first_release = asyncio.Event()

    async def dispatch(record, metadata=None):
        first_running.set()
        await first_release.wait()
        return MagicMock()

    service._dispatch_create = dispatch  # type: ignore[assignment]

    first = asyncio.create_task(service._create_provider(_make_record()))
    await first_running.wait()

    # loguru needs a stdlib sink to reach caplog; service uses loguru.
    # Easiest approach: monkeypatch the logger to stdlib and assert.
    logs: list[str] = []

    def capture(msg, *args, **kwargs):
        logs.append(str(msg).format(*args, **kwargs) if args else str(msg))

    service_module.logger = SimpleNamespace(info=capture, warning=capture)

    # Second create waits at least 30 ms before first releases.
    second = asyncio.create_task(service._create_provider(_make_record()))
    await asyncio.sleep(0.03)
    first_release.set()
    await asyncio.gather(first, second)

    assert any("waited" in line and "concurrent-create semaphore" in line for line in logs), logs


@pytest.mark.asyncio
async def test_fast_wait_below_threshold_does_not_log():
    """A create that waits below the threshold does NOT log."""
    settings = _make_settings(limit=2, log_threshold_ms=10_000)
    service = _make_service(settings)

    async def dispatch(record, metadata=None):
        return MagicMock()

    service._dispatch_create = dispatch  # type: ignore[assignment]

    logs: list[str] = []
    service_module.logger = SimpleNamespace(
        info=lambda *a, **k: logs.append("info"),
        warning=lambda *a, **k: logs.append("warning"),
    )

    await asyncio.gather(*[service._create_provider(_make_record()) for _ in range(3)])
    assert logs == []


@pytest.mark.asyncio
async def test_settings_change_rebuilds_semaphore():
    """Changing the limit between calls rebuilds the underlying semaphore."""
    sem_a = await _get_create_semaphore(2)
    sem_b = await _get_create_semaphore(2)
    sem_c = await _get_create_semaphore(4)

    assert sem_a is sem_b
    assert sem_a is not sem_c
    # New semaphore should allow 4 holders concurrently.
    assert sem_c is not None
    async with sem_c, sem_c, sem_c, sem_c:
        # Holding 4 must succeed; a 5th must block.
        fifth = asyncio.create_task(sem_c.acquire())
        await asyncio.sleep(0.01)
        assert not fifth.done()
        fifth.cancel()
        with pytest.raises(asyncio.CancelledError):
            await fifth


@pytest.mark.asyncio
async def test_dispatch_is_invoked_with_record_and_metadata():
    """Sanity: the semaphore path still forwards record + metadata."""
    settings = _make_settings(limit=2)
    service = _make_service(settings)

    calls: list[tuple] = []

    async def dispatch(record, metadata=None):
        calls.append((record, metadata))
        return MagicMock()

    service._dispatch_create = dispatch  # type: ignore[assignment]

    record = _make_record()
    meta = {"agent_kind": "deep_research"}
    await service._create_provider(record, metadata=meta)
    assert calls == [(record, meta)]
