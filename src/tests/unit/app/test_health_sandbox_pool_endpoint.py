"""Tests for the /health/sandbox-pool endpoint.

Phase 6.e surfaced the pre-warmed sandbox pool snapshot via
``GET /health/sandbox-pool``. The endpoint is consumed by
``scripts/local/lib/platform_checks_pool.sh`` and must:

- Return a stable JSON shape with all snapshot keys present.
- Set ``available=True`` when the container exposes a pool manager.
- Degrade gracefully (``available=False`` + reason) when the container
  is unwired, the pool manager is absent, or any unexpected error
  occurs — the endpoint must NEVER raise to the HTTP layer.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


def _make_snapshot(
    *,
    enabled: bool = True,
    configured: int = 2,
    ready: int = 2,
    initializing: int = 0,
    initializing_age_max_seconds: int | None = None,
    stuck_initializing: int = 0,
    claimed: int = 0,
    retiring: int = 0,
    stuck_threshold_seconds: int = 600,
) -> dict:
    return {
        "enabled": enabled,
        "configured": configured,
        "ready": ready,
        "initializing": initializing,
        "initializing_age_max_seconds": initializing_age_max_seconds,
        "stuck_initializing": stuck_initializing,
        "claimed": claimed,
        "retiring": retiring,
        "stuck_threshold_seconds": stuck_threshold_seconds,
    }


@pytest.mark.asyncio
async def test_health_sandbox_pool_returns_snapshot_when_wired():
    """Happy path: pool manager present, snapshot fields surface verbatim."""
    from ii_agent.app.health import health_sandbox_pool

    snap = _make_snapshot(ready=2, initializing=0)
    pool_mgr = MagicMock()
    pool_mgr.snapshot = AsyncMock(return_value=snap)
    container = MagicMock(sandbox_pool_manager=pool_mgr)

    with patch("ii_agent.core.container.get_app_container", return_value=container):
        result = await health_sandbox_pool()

    assert result["available"] is True
    assert result["enabled"] is True
    assert result["configured"] == 2
    assert result["ready"] == 2
    assert result["initializing"] == 0
    assert result["claimed"] == 0
    assert result["retiring"] == 0
    assert result["stuck_initializing"] == 0
    assert result["stuck_threshold_seconds"] == 600
    pool_mgr.snapshot.assert_awaited_once()


@pytest.mark.asyncio
async def test_health_sandbox_pool_surfaces_stuck_rows():
    """A stuck row bumps the snapshot counter without changing availability."""
    from ii_agent.app.health import health_sandbox_pool

    snap = _make_snapshot(
        ready=0,
        initializing=2,
        initializing_age_max_seconds=11 * 3600,
        stuck_initializing=2,
    )
    pool_mgr = MagicMock()
    pool_mgr.snapshot = AsyncMock(return_value=snap)
    container = MagicMock(sandbox_pool_manager=pool_mgr)

    with patch("ii_agent.core.container.get_app_container", return_value=container):
        result = await health_sandbox_pool()

    assert result["available"] is True
    assert result["stuck_initializing"] == 2
    assert result["initializing_age_max_seconds"] == 11 * 3600
    assert result["ready"] == 0


@pytest.mark.asyncio
async def test_health_sandbox_pool_disabled_pool_still_available():
    """A disabled pool is still ``available`` — just enabled=False."""
    from ii_agent.app.health import health_sandbox_pool

    snap = _make_snapshot(enabled=False, configured=0, ready=0)
    pool_mgr = MagicMock()
    pool_mgr.snapshot = AsyncMock(return_value=snap)
    container = MagicMock(sandbox_pool_manager=pool_mgr)

    with patch("ii_agent.core.container.get_app_container", return_value=container):
        result = await health_sandbox_pool()

    assert result["available"] is True
    assert result["enabled"] is False
    assert result["configured"] == 0


@pytest.mark.asyncio
async def test_health_sandbox_pool_unwired_container_returns_reason():
    """``sandbox_pool_manager`` attribute missing -> available=False with reason."""
    from ii_agent.app.health import health_sandbox_pool

    container = MagicMock(spec=[])  # no attributes at all

    with patch("ii_agent.core.container.get_app_container", return_value=container):
        result = await health_sandbox_pool()

    assert result["available"] is False
    assert result["reason"] is not None
    assert "pool manager" in result["reason"].lower()
    # Stable shape preserved.
    for key in (
        "enabled",
        "configured",
        "ready",
        "initializing",
        "claimed",
        "retiring",
        "stuck_initializing",
    ):
        assert key in result


@pytest.mark.asyncio
async def test_health_sandbox_pool_get_app_container_raises_runtime_error():
    """Pre-lifespan calls (``RuntimeError``) degrade to available=False."""
    from ii_agent.app.health import health_sandbox_pool

    with patch(
        "ii_agent.core.container.get_app_container",
        side_effect=RuntimeError("ApplicationContainer is not initialized"),
    ):
        result = await health_sandbox_pool()

    assert result["available"] is False
    assert "not initialized" in result["reason"].lower()


@pytest.mark.asyncio
async def test_health_sandbox_pool_snapshot_raises_is_swallowed():
    """A snapshot failure is logged + reported, never propagated."""
    from ii_agent.app.health import health_sandbox_pool

    pool_mgr = MagicMock()
    pool_mgr.snapshot = AsyncMock(side_effect=ValueError("db blew up"))
    container = MagicMock(sandbox_pool_manager=pool_mgr)

    with patch("ii_agent.core.container.get_app_container", return_value=container):
        result = await health_sandbox_pool()

    assert result["available"] is False
    assert "ValueError" in result["reason"]
    assert "db blew up" in result["reason"]


@pytest.mark.asyncio
async def test_health_sandbox_pool_returns_stable_shape_on_failure():
    """All standard keys are present on failure paths so consumers can render."""
    from ii_agent.app.health import health_sandbox_pool

    pool_mgr = MagicMock()
    pool_mgr.snapshot = AsyncMock(side_effect=Exception("boom"))
    container = MagicMock(sandbox_pool_manager=pool_mgr)

    with patch("ii_agent.core.container.get_app_container", return_value=container):
        result = await health_sandbox_pool()

    expected_keys = {
        "available",
        "reason",
        "enabled",
        "configured",
        "ready",
        "initializing",
        "initializing_age_max_seconds",
        "stuck_initializing",
        "claimed",
        "retiring",
        "stuck_threshold_seconds",
    }
    assert expected_keys.issubset(result.keys())
    # Defaults applied so platform_checks_pool.sh can parse without nulls.
    assert result["configured"] == 0
    assert result["ready"] == 0
    assert result["enabled"] is False
