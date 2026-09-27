"""Tests for the /health/ready readiness endpoint.

The 2026-04-25 PG-recovery incident motivated a Kubernetes-style
readiness probe distinct from the liveness ``/health`` endpoint. The
contract is:

- Returns 200 + ``{"ready": true, "checks": {...}}`` when DB and Redis
  are both reachable.
- Returns 503 + ``Retry-After: 5`` + per-check failure detail when any
  dep is unreachable, with a tight per-dep timeout so a slow dep cannot
  block the probe past the typical scrape interval.
- Never raises — every failure mode is captured into ``checks`` and
  surfaces as 503.

Regression note: the first cut of this endpoint called
``get_db_session_local()`` as if it returned a factory
(``factory()`` → another call) when it actually returns the session
context manager directly. That bug rendered ``checks["db"]`` as
``"unavailable: TypeError"`` for every probe. These tests guard the
correct call shape and the 200/503 split.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.unit

_MODULE = "ii_agent.app.health"


def _db_cm_ok():
    """Mimic ``get_db_session_local()``'s `async with ... as db` shape."""

    @asynccontextmanager
    async def _cm():
        db = MagicMock()
        db.execute = AsyncMock(return_value=None)
        yield db

    return _cm()


def _db_cm_raises(exc: Exception):
    @asynccontextmanager
    async def _cm():
        db = MagicMock()
        db.execute = AsyncMock(side_effect=exc)
        yield db

    return _cm()


def _redis_ok():
    client = MagicMock()
    client.ping = AsyncMock(return_value=True)
    return client


def _redis_raises(exc: Exception):
    client = MagicMock()
    client.ping = AsyncMock(side_effect=exc)
    return client


@pytest.mark.asyncio
async def test_ready_returns_200_when_db_and_redis_ok():
    from ii_agent.app.health import health_ready

    with (
        patch(f"{_MODULE}.get_db_session_local", return_value=_db_cm_ok()),
        patch(f"{_MODULE}.get_redis_client", return_value=_redis_ok()),
    ):
        resp = await health_ready()

    assert resp.status_code == 200
    import json

    body = json.loads(resp.body)
    assert body == {"ready": True, "checks": {"db": "ok", "redis": "ok"}}


@pytest.mark.asyncio
async def test_ready_returns_503_with_retry_after_when_db_down():
    from ii_agent.app.health import health_ready

    with (
        patch(
            f"{_MODULE}.get_db_session_local",
            return_value=_db_cm_raises(ConnectionError("PG in recovery")),
        ),
        patch(f"{_MODULE}.get_redis_client", return_value=_redis_ok()),
    ):
        resp = await health_ready()

    assert resp.status_code == 503
    assert resp.headers["Retry-After"] == "5"
    import json

    body = json.loads(resp.body)
    assert body["ready"] is False
    assert body["checks"]["db"].startswith("unavailable:")
    assert body["checks"]["redis"] == "ok"


@pytest.mark.asyncio
async def test_ready_returns_503_when_redis_down():
    from ii_agent.app.health import health_ready

    with (
        patch(f"{_MODULE}.get_db_session_local", return_value=_db_cm_ok()),
        patch(
            f"{_MODULE}.get_redis_client",
            return_value=_redis_raises(RuntimeError("redis offline")),
        ),
    ):
        resp = await health_ready()

    assert resp.status_code == 503
    assert resp.headers["Retry-After"] == "5"
    import json

    body = json.loads(resp.body)
    assert body["checks"]["db"] == "ok"
    assert body["checks"]["redis"].startswith("unavailable:")


@pytest.mark.asyncio
async def test_ready_db_timeout_reported_as_timeout():
    """A slow DB must be reported as 'timeout', not blocked indefinitely."""
    from ii_agent.app.health import health_ready

    @asynccontextmanager
    async def _slow_cm():
        db = MagicMock()

        async def _slow_execute(*_args, **_kwargs):
            await asyncio.sleep(10.0)  # well past the 2s probe timeout

        db.execute = _slow_execute
        yield db

    with (
        patch(f"{_MODULE}.get_db_session_local", return_value=_slow_cm()),
        patch(f"{_MODULE}.get_redis_client", return_value=_redis_ok()),
    ):
        # The whole probe must finish well under the slow-execute delay.
        resp = await asyncio.wait_for(health_ready(), timeout=5.0)

    assert resp.status_code == 503
    import json

    body = json.loads(resp.body)
    assert body["checks"]["db"] == "timeout"


@pytest.mark.asyncio
async def test_ready_does_not_call_session_factory_twice():
    """Regression: ``get_db_session_local()`` returns the session context
    manager directly, NOT a factory that must be called again. Calling
    it twice would surface as 'unavailable: TypeError'.
    """
    from ii_agent.app.health import health_ready

    cm = _db_cm_ok()
    factory = MagicMock(return_value=cm)
    with (
        patch(f"{_MODULE}.get_db_session_local", factory),
        patch(f"{_MODULE}.get_redis_client", return_value=_redis_ok()),
    ):
        resp = await health_ready()

    assert resp.status_code == 200, resp.body
    assert factory.call_count == 1, "get_db_session_local must be called exactly once per probe"
