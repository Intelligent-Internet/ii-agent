"""Handler for sandbox_status command.

Extracted from ``server.socket.command.sandbox_status_handler``.

Hot-path hardening:
- Per-session TTL cache so repeated frontend polls don't trigger a Docker
  restart per poll.
- asyncio timeout around the inner ``get_sandbox_for_session`` so a slow
  Docker daemon cannot block the Socket.IO event loop.
- Circuit breaker integration: after N consecutive failures the handler
  returns ERROR fast and records a failure so the orphan cleanup loop
  reaps the broken row.
"""

import asyncio
import time
from dataclasses import dataclass
from typing import Dict, Optional

from ii_agent.agents.sandboxes import SandboxStatus
from ii_agent.agents.sandboxes import breaker as _breaker
from ii_agent.core.config.settings import get_settings
from ii_agent.core.container import ApplicationContainer
from ii_agent.core.db import get_db_session_local
from ii_agent.core.logger import logger
from ii_agent.realtime.events.app_events import SandboxStatusChangedEvent
from ii_agent.realtime.handlers.base import (
    BaseCommandHandler,
    CommandType,
)
from ii_agent.realtime.pubsub import AsyncIOPubSub
from ii_agent.realtime.schemas import SandboxStatusContent
from ii_agent.sessions.schemas import SessionInfo


@dataclass(slots=True)
class _CachedStatus:
    """Cached sandbox_status result with an expiry timestamp."""

    expires_at: float
    status: str
    vscode_url: Optional[str]
    vnc_url: Optional[str]
    is_error: bool


# Module-level cache: session_id -> _CachedStatus. Safe because all access
# happens on the asyncio event loop (no threading).
_cache: Dict[str, _CachedStatus] = {}


def _cache_get(session_id: str) -> Optional[_CachedStatus]:
    entry = _cache.get(session_id)
    if entry is None:
        return None
    if entry.expires_at <= time.monotonic():
        _cache.pop(session_id, None)
        return None
    return entry


def _cache_set(
    session_id: str,
    status: str,
    vscode_url: Optional[str],
    vnc_url: Optional[str],
    ttl_seconds: float,
    *,
    is_error: bool,
) -> None:
    if ttl_seconds <= 0:
        return
    _cache[session_id] = _CachedStatus(
        expires_at=time.monotonic() + ttl_seconds,
        status=status,
        vscode_url=vscode_url,
        vnc_url=vnc_url,
        is_error=is_error,
    )


class SandboxStatusHandler(BaseCommandHandler[SandboxStatusContent]):
    """Handler for sandbox status command."""

    _content_type = SandboxStatusContent

    def __init__(self, pubsub: AsyncIOPubSub, container: ApplicationContainer) -> None:
        super().__init__(pubsub=pubsub, container=container)

    def get_command_type(self) -> CommandType:
        return CommandType.SANDBOX_STATUS

    async def handle(self, content: SandboxStatusContent, session_info: SessionInfo) -> None:
        """Handle get sandbox status request."""
        session_key = str(session_info.id)
        settings = get_settings().sandbox
        cache_ttl = float(settings.sandbox_status_cache_seconds)
        docker_timeout = float(settings.docker_call_timeout_seconds)

        cached = _cache_get(session_key)
        if cached is not None:
            await self._emit(
                session_info,
                cached.status,
                cached.vscode_url,
                cached.vnc_url,
            )
            return

        status = SandboxStatus.NOT_INITIALIZED.value
        vscode_url = None
        vnc_url = None
        sandbox_service = self._container.sandbox_service
        sandbox_uuid: Optional[str] = None
        is_error = False

        async def _resolve() -> None:
            nonlocal status, vscode_url, vnc_url, sandbox_uuid
            async with get_db_session_local() as db:
                sandbox = await sandbox_service.get_sandbox_for_session(db, session_info.id)
                if sandbox:
                    sandbox_uuid = getattr(sandbox, "sandbox_id", None)
                    sandbox_info = await sandbox.get_info()
                    status = sandbox_info.status.value
                    vscode_url = sandbox_info.vscode_url
                    vnc_url = sandbox_info.vnc_url

        try:
            await asyncio.wait_for(_resolve(), timeout=docker_timeout)
            if sandbox_uuid:
                _breaker.record_success(sandbox_uuid)
        except asyncio.TimeoutError:
            logger.warning(
                f"sandbox_status timed out after {docker_timeout}s for session {session_info.id}"
            )
            status = SandboxStatus.ERROR.value
            is_error = True
        except Exception as e:
            logger.error(f"Failed to get sandbox status for session {session_info.id}: {e}")
            status = SandboxStatus.ERROR.value
            is_error = True
            if sandbox_uuid:
                count = _breaker.record_failure(sandbox_uuid)
                logger.debug(f"sandbox_status failure count for {sandbox_uuid}: {count}")

        # Error responses are cached for half the TTL so a transient error
        # still surfaces a refreshed status within a reasonable window but
        # repeated polls don't retrigger the slow Docker path.
        _cache_set(
            session_key,
            status,
            vscode_url,
            vnc_url,
            cache_ttl / 2 if is_error else cache_ttl,
            is_error=is_error,
        )

        await self._emit(session_info, status, vscode_url, vnc_url)

    async def _emit(
        self,
        session_info: SessionInfo,
        status: str,
        vscode_url: Optional[str],
        vnc_url: Optional[str],
    ) -> None:
        valid_statuses = {"starting", "ready", "paused", "terminated", "error"}
        event_status = status if status in valid_statuses else "starting"
        # Integrated host monitor backpressure: frontend can surface a
        # warning banner when the kernel is fragmented or dockerd is
        # slow. Imported lazily so the handler module has no circular
        # import concern with the agents package.
        from ii_agent.agents.sandboxes.host_monitor import (
            HostHealthState,
            get_host_state,
        )

        host_state = get_host_state()
        degraded = host_state.is_degraded()
        host_state_name = host_state.name if host_state != HostHealthState.OK else None

        await self.send_event(
            SandboxStatusChangedEvent(
                session_id=session_info.id,
                content={
                    "status": status,
                    "vscode_url": vscode_url,
                    "vnc_url": vnc_url,
                    "degraded": degraded,
                    "host_state": host_state_name,
                },
                status=event_status,
                vscode_url=vscode_url,
                vnc_url=vnc_url,
                degraded=degraded,
                host_state=host_state_name,
            )
        )
