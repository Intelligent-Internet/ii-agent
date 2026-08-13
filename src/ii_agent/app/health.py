"""Health-check routes."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from ii_agent.core.config.settings import get_settings
from ii_agent.core.db import get_db_session_local
from ii_agent.core.redis.client import get_redis_client

health_router = APIRouter()

logger = logging.getLogger(__name__)

# Simple cache for Docker availability check (avoid hitting the daemon on every request)
_docker_cache: dict[str, Any] = {"available": None, "ts": 0.0}
_DOCKER_CACHE_TTL = 30.0  # seconds


def _check_docker_available() -> bool:
    """Return True if Docker daemon is reachable. Cached for 30s."""
    now = time.monotonic()
    if now - _docker_cache["ts"] < _DOCKER_CACHE_TTL and _docker_cache["available"] is not None:
        return _docker_cache["available"]
    try:
        import docker

        client = docker.from_env()
        client.ping()
        _docker_cache.update(available=True, ts=now)
        return True
    except Exception:
        _docker_cache.update(available=False, ts=now)
        return False


@health_router.get("/health")
async def health_check():
    settings = get_settings()
    response: dict[str, Any] = {"status": "ok"}

    # Only expose internal configuration details in local mode
    if settings.sandbox.local_mode:
        response.update(
            {
                "agent_inner_loop_mode": settings.agent.inner_loop_mode,
                "chat_inner_loop_mode": settings.agent.chat_inner_loop_mode,
                "a2a_backend": settings.agent.a2a_backend,
                "a2a_fallback_to_native": settings.agent.a2a_fallback_to_native,
                "sandbox_provider": settings.sandbox.provider,
            }
        )

        # Docker availability (cached 30s)
        if settings.sandbox.provider == "docker":
            response["docker_available"] = _check_docker_available()

            # Port pool status
            try:
                from ii_agent.agents.sandboxes.port_manager import PortPoolManager

                pm = PortPoolManager.get_instance()
                stats = pm.get_stats()
                response["port_pool_free"] = stats.get("free")
            except Exception:
                response["port_pool_free"] = None

    return response


# ── Liveness vs readiness contract ─────────────────────────────────────────
# /health        — liveness. 200 as long as the process is alive. Wired into
#                  Docker HEALTHCHECK. Must NOT probe DB: a transient PG
#                  recovery would otherwise cause Docker to restart the
#                  backend, which is the wrong action when PG (not the
#                  backend) is the problem.
# /health/ready  — readiness. Probes critical deps (DB, Redis) with tight
#                  timeouts. Returns 503 + Retry-After while any dep is
#                  unavailable (e.g. PG is in recovery mode). NOT wired into
#                  Docker HEALTHCHECK — readiness is for load balancers, the
#                  frontend bootstrap, the E2E harness, and stack_control.sh
#                  status. See docs/runtime-docs/postgres-recovery-mode-
#                  failures.md (Liveness vs readiness section).


@health_router.get("/health/ready")
async def health_ready() -> JSONResponse:
    """Readiness probe.

    Returns 200 when DB and Redis are both reachable, 503 otherwise.
    Each dep has its own short timeout so a slow dep cannot block the
    probe past the typical scrape interval.
    """
    checks: dict[str, str] = {}
    overall_ok = True

    # ── DB probe (2s timeout) ──
    # SELECT 1 is the canonical asyncpg liveness check. asyncpg raises
    # CannotConnectNowError (SQLSTATE 57P03) while PG is in recovery —
    # that surfaces here as the "db" check failing, no special handling
    # needed (the broad except catches it).
    try:
        # NOTE: get_db_session_local() returns an async session context
        # manager directly (not a factory) — see billing/service.py et al.
        async with get_db_session_local() as db:
            await asyncio.wait_for(db.execute(text("SELECT 1")), timeout=2.0)
        checks["db"] = "ok"
    except asyncio.TimeoutError:
        checks["db"] = "timeout"
        overall_ok = False
    except Exception as exc:
        checks["db"] = f"unavailable: {type(exc).__name__}"
        overall_ok = False

    # ── Redis probe (1s timeout) ──
    try:
        redis_client = get_redis_client()
        await asyncio.wait_for(redis_client.ping(), timeout=1.0)
        checks["redis"] = "ok"
    except asyncio.TimeoutError:
        checks["redis"] = "timeout"
        overall_ok = False
    except Exception as exc:
        checks["redis"] = f"unavailable: {type(exc).__name__}"
        overall_ok = False

    payload = {"ready": overall_ok, "checks": checks}
    if overall_ok:
        return JSONResponse(status_code=200, content=payload)
    # Retry-After: 5s aligns with asyncpg's typical PG-recovery window
    # backoff and gives clients (frontend, E2E harness) a sane retry hint.
    return JSONResponse(
        status_code=503,
        content=payload,
        headers={"Retry-After": "5"},
    )


@health_router.get("/health/host")
async def health_host():
    """Phase-2 host-monitor snapshot for external consumers.

    Returns the latest sample from :mod:`ii_agent.agents.sandboxes.host_monitor`
    plus buffer-warmth metadata. Used by
    ``scripts/local/lib/platform_checks_backend.sh`` to cross-check the
    shell-side ``/proc`` read against the backend's percentile baseline.

    Never raises: if the monitor is disabled or the buffer has not yet
    been constructed, we report ``state=BOOTSTRAP`` with nulls so the
    consumer can still display a consistent response shape.
    """
    from datetime import datetime, timezone

    from ii_agent.agents.sandboxes.host_monitor import (
        HostHealthState,
        get_host_state,
        get_host_state_snapshot,
    )
    from ii_agent.agents.sandboxes.orphan_cleanup import (
        get_host_monitor_buffer_snapshot,
    )

    state: HostHealthState = get_host_state()
    sample = get_host_state_snapshot()
    buffer = get_host_monitor_buffer_snapshot()

    payload: dict[str, Any] = {
        "state": state.name,
        "state_code": int(state),
        "captured_at": None,
        "buddyinfo": {"zone": "Normal", "orders": {}},
        "p99_docker_call_ms": None,
        "docker_call_timeout_total": None,
        "meminfo": {"available_mb": None, "total_mb": None},
        "vmstat": {
            "compact_fail": None,
            "compact_success": None,
            "allocstall_normal": None,
        },
        "baseline_window_samples": 0,
        "baseline_window_capacity": 0,
        "baseline_warm": False,
    }

    if sample is not None:
        payload["captured_at"] = datetime.fromtimestamp(
            sample.captured_at, tz=timezone.utc
        ).isoformat()
        # Emit orders 4..10 (the fragmentation-relevant high orders);
        # order 0..3 are always plentiful and just noise for operators.
        payload["buddyinfo"]["orders"] = {
            str(o): int(sample.buddy_normal.get(o, 0)) for o in range(4, 11)
        }
        payload["p99_docker_call_ms"] = round(sample.docker_call_p99_s * 1000.0, 1)
        payload["docker_call_timeout_total"] = int(sample.docker_call_timeout_total)
        payload["meminfo"] = {
            "available_mb": sample.mem_available_kb // 1024,
            "total_mb": sample.mem_total_kb // 1024,
        }
        payload["vmstat"] = {
            "compact_fail": int(sample.vmstat_compact_fail),
            "compact_success": int(sample.vmstat_compact_success),
            "allocstall_normal": int(sample.vmstat_allocstall_normal),
        }

    if buffer is not None:
        payload["baseline_window_samples"] = len(buffer)
        payload["baseline_window_capacity"] = int(buffer.capacity)
        payload["baseline_warm"] = bool(buffer.is_warm())

    return payload


@health_router.get("/health/sandbox-pool")
async def health_sandbox_pool():
    """Pre-warmed sandbox pool occupancy snapshot.

    Used by ``scripts/local/lib/platform_checks_pool.sh`` to surface
    pool readiness in ``stack_control.sh status`` output. Mirrors the
    shape of :meth:`SandboxPoolManager.snapshot` plus a top-level
    ``available`` flag so the consumer can distinguish "pool disabled"
    from "pool enabled but degraded".

    Never raises: if the container is not yet wired or the pool
    manager is unavailable, returns ``available=False`` with a reason
    string and zeros so the consumer can render a stable shape.
    """
    payload: dict[str, Any] = {
        "available": False,
        "reason": None,
        "enabled": False,
        "configured": 0,
        "ready": 0,
        "initializing": 0,
        "initializing_age_max_seconds": None,
        "stuck_initializing": 0,
        "claimed": 0,
        "retiring": 0,
        "stuck_threshold_seconds": 0,
    }
    try:
        from ii_agent.core.container import get_app_container

        container = get_app_container()
        pool_mgr = getattr(container, "sandbox_pool_manager", None)
        if pool_mgr is None:
            payload["reason"] = "pool manager not wired"
            return payload
        snap = await pool_mgr.snapshot()
        payload.update(snap)
        payload["available"] = True
        return payload
    except RuntimeError as exc:
        payload["reason"] = str(exc)
        return payload
    except Exception as exc:
        logger.exception("health/sandbox-pool failed")
        payload["reason"] = f"{type(exc).__name__}: {exc}"
        return payload
