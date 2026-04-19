"""Health-check routes."""

from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import APIRouter

from ii_agent.core.config.settings import get_settings

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
