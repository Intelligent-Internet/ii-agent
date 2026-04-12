"""Background orphan cleanup for Docker sandboxes.

Periodically checks for sandboxes whose sessions have been deleted
and removes the containers, ports, and volumes.

Only active when ``settings.sandbox.local_mode`` and
``settings.sandbox.orphan_cleanup_enabled`` are both ``True``.
"""

from __future__ import annotations

import asyncio
import threading
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select

from ii_agent.agents.sandboxes.docker import DockerSandbox
from ii_agent.agents.sandboxes.models import AgentSandbox
from ii_agent.agents.sandboxes.types import SandboxProviderType, SandboxStatus
from ii_agent.core.config.settings import Settings, get_settings
from ii_agent.core.db import get_db_session_local
from ii_agent.core.logger import logger
from ii_agent.sessions.models import Session


# Grace period before a sandbox can be considered orphaned
_GRACE_PERIOD = timedelta(minutes=5)

_cleanup_task: Optional[asyncio.Task] = None
_cleanup_task_lock = threading.Lock()


async def run_orphan_cleanup_loop(config: Optional[Settings] = None) -> None:
    """Continuous loop that removes orphaned Docker sandboxes.

    A sandbox is orphaned when its linked session has been soft-deleted by
    the user *and* the sandbox was created more than 5 minutes ago (to
    avoid racing with sandbox initialization).

    Also pauses running sandboxes whose sessions have been idle longer than
    the configured ``stale_sandbox_pause_seconds``.  Paused containers
    retain their filesystem state and can be resumed without data loss by
    ``reconnect_or_create()`` on the next session access.
    """
    cfg = config or get_settings()
    interval = cfg.sandbox.orphan_cleanup_interval_seconds

    while True:
        try:
            await asyncio.sleep(interval)
            cleaned = await _cleanup_orphans(cfg)
            paused = await _pause_stale_sandboxes(cfg)
            if cleaned > 0 or paused > 0:
                logger.info(
                    "Orphan cleanup sweep: removed=%d orphaned, paused=%d stale",
                    cleaned,
                    paused,
                )
        except asyncio.CancelledError:
            logger.info("Orphan cleanup task cancelled")
            break
        except Exception:
            logger.exception("Error in orphan cleanup loop")
            await asyncio.sleep(60)


async def _cleanup_orphans(cfg: Settings) -> int:
    """Single sweep: find and remove orphaned Docker sandboxes."""
    now = datetime.now(timezone.utc)
    cleaned = 0

    async with get_db_session_local() as db:
        # Fetch all Docker sandboxes that are not already marked deleted
        result = await db.execute(
            select(AgentSandbox).where(
                AgentSandbox.provider == SandboxProviderType.DOCKER,
                AgentSandbox.status != SandboxStatus.DELETED,
            )
        )
        sandboxes = result.scalars().all()

        if not sandboxes:
            return 0

        # Pre-fetch session IDs to batch-check deletion status
        session_ids = {s.session_id for s in sandboxes}
        session_result = await db.execute(
            select(Session.id, Session.is_deleted).where(Session.id.in_(session_ids))
        )
        session_map = {row.id: row.is_deleted for row in session_result}

        for sandbox in sandboxes:
            try:
                # Skip recently created sandboxes
                if sandbox.created_at and (now - sandbox.created_at) < _GRACE_PERIOD:
                    continue

                # Only clean up if the session has been deleted (or is missing)
                session_deleted = session_map.get(sandbox.session_id)
                if session_deleted is None:
                    # Session row doesn't exist — treat as orphaned
                    pass
                elif not session_deleted:
                    # Session exists and is not deleted — keep sandbox
                    continue

                logger.info(
                    f"Cleaning up orphan sandbox {sandbox.id} "
                    f"(session {sandbox.session_id} deleted)"
                )

                # Kill the Docker container and release resources
                if sandbox.provider_sandbox_id:
                    try:
                        docker_sandbox = DockerSandbox(
                            sandbox_id=str(sandbox.id),
                            session_id=str(sandbox.session_id),
                            provider_sandbox_id=sandbox.provider_sandbox_id,
                        )
                        # Attach to the container for cleanup
                        client = DockerSandbox._get_docker_client()
                        try:
                            docker_sandbox._container = client.containers.get(
                                sandbox.provider_sandbox_id
                            )
                        except Exception:
                            docker_sandbox._container = None

                        await docker_sandbox.kill()
                    except Exception as e:
                        logger.warning(
                            f"Failed to kill orphan container {sandbox.provider_sandbox_id}: {e}"
                        )

                # Mark as deleted in DB
                sandbox.status = SandboxStatus.DELETED
                await db.flush()
                cleaned += 1

            except Exception as e:
                logger.warning(f"Error processing sandbox {sandbox.id}: {e}")
                continue

        await db.commit()

    return cleaned


async def _pause_stale_sandboxes(cfg: Settings) -> int:
    """Pause running Docker sandboxes whose sessions are idle but not deleted.

    A sandbox is considered stale when its session's ``updated_at`` is older
    than ``stale_sandbox_pause_seconds``.  Pausing (``docker stop``) keeps
    the container and its filesystem intact so ``reconnect_or_create()`` can
    restart it on the next session access without data loss.
    """
    stale_threshold = timedelta(seconds=cfg.sandbox.stale_sandbox_pause_seconds)
    now = datetime.now(timezone.utc)
    paused = 0

    async with get_db_session_local() as db:
        # Fetch RUNNING Docker sandboxes only
        result = await db.execute(
            select(AgentSandbox).where(
                AgentSandbox.provider == SandboxProviderType.DOCKER,
                AgentSandbox.status == SandboxStatus.RUNNING,
            )
        )
        sandboxes = result.scalars().all()

        if not sandboxes:
            return 0

        # Batch-fetch session activity timestamps
        session_ids = {s.session_id for s in sandboxes}
        session_result = await db.execute(
            select(Session.id, Session.is_deleted, Session.updated_at).where(
                Session.id.in_(session_ids)
            )
        )
        session_map = {row.id: (row.is_deleted, row.updated_at) for row in session_result}

        for sandbox in sandboxes:
            try:
                session_info = session_map.get(sandbox.session_id)
                if session_info is None:
                    continue  # Missing session handled by _cleanup_orphans
                is_deleted, updated_at = session_info
                if is_deleted:
                    continue  # Deleted sessions handled by _cleanup_orphans

                if updated_at and (now - updated_at) < stale_threshold:
                    continue  # Session still active

                # Session is stale — pause the sandbox
                if sandbox.provider_sandbox_id:
                    try:
                        docker_sandbox = DockerSandbox(
                            sandbox_id=str(sandbox.id),
                            session_id=str(sandbox.session_id),
                            provider_sandbox_id=sandbox.provider_sandbox_id,
                        )
                        client = DockerSandbox._get_docker_client()
                        try:
                            docker_sandbox._container = client.containers.get(
                                sandbox.provider_sandbox_id
                            )
                        except Exception:
                            docker_sandbox._container = None

                        if docker_sandbox._container is not None:
                            await docker_sandbox.pause()
                            sandbox.status = SandboxStatus.PAUSED
                            await db.flush()
                            paused += 1
                            logger.info(
                                "Paused stale sandbox %s (session %s, idle %.0fs)",
                                sandbox.id,
                                sandbox.session_id,
                                (now - updated_at).total_seconds() if updated_at else 0,
                            )
                    except Exception as e:
                        logger.warning(
                            "Failed to pause stale sandbox %s: %s",
                            sandbox.id,
                            e,
                        )
            except Exception as e:
                logger.warning("Error processing sandbox %s for stale pause: %s", sandbox.id, e)
                continue

        await db.commit()

    return paused


def start_orphan_cleanup(config: Optional[Settings] = None) -> Optional[asyncio.Task]:
    """Start the background cleanup task if configured.

    Call this from the app lifespan when local Docker mode is active.
    Returns the task handle (or ``None`` if cleanup is disabled).
    """
    global _cleanup_task

    cfg = config or get_settings()

    if not cfg.sandbox.local_mode or not cfg.sandbox.orphan_cleanup_enabled:
        return None

    with _cleanup_task_lock:
        if _cleanup_task is not None and not _cleanup_task.done():
            logger.debug("Orphan cleanup task already running")
            return _cleanup_task

        _cleanup_task = asyncio.create_task(run_orphan_cleanup_loop(cfg))
        logger.info(
            f"Orphan cleanup started (interval={cfg.sandbox.orphan_cleanup_interval_seconds}s)"
        )
        return _cleanup_task


def stop_orphan_cleanup() -> None:
    """Cancel the background cleanup task."""
    global _cleanup_task
    if _cleanup_task is not None and not _cleanup_task.done():
        _cleanup_task.cancel()
        _cleanup_task = None
