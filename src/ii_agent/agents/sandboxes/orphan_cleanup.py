"""Background orphan cleanup for Docker sandboxes.

Periodically checks for sandboxes whose sessions have been deleted
and removes the containers, ports, and volumes.

Also sweeps Docker directly for exited containers that have no
matching active DB record (e.g. from crashes or bulk DB deletes).

Only active when ``settings.sandbox.local_mode`` and
``settings.sandbox.orphan_cleanup_enabled`` are both ``True``.
"""

from __future__ import annotations

import asyncio
import threading
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import docker
from docker.errors import APIError, NotFound
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.agents.sandboxes.docker import DockerSandbox, _cleanup_sandbox_volume
from ii_agent.agents.sandboxes.models import AgentSandbox
from ii_agent.agents.sandboxes.port_manager import PortPoolManager
from ii_agent.agents.sandboxes.types import SandboxProviderType, SandboxStatus
from ii_agent.core.config.settings import Settings, get_settings
from ii_agent.core.db import get_db_session_local
from ii_agent.core.logger import logger
from ii_agent.sessions.models import Session
from ii_agent.tasks.models import RunTask
from ii_agent.tasks.types import RunStatus


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
            expired = await _soft_delete_expired_sessions()
            cleaned = await _cleanup_orphans(cfg)
            paused = await _pause_stale_sandboxes(cfg)
            zombies = await _cleanup_docker_zombies()
            if cleaned > 0 or paused > 0 or zombies > 0 or expired > 0:
                logger.info(
                    "Orphan cleanup sweep: expired=%d sessions, removed=%d orphaned, "
                    "paused=%d stale, reaped=%d docker zombies",
                    expired,
                    cleaned,
                    paused,
                    zombies,
                )
        except asyncio.CancelledError:
            logger.info("Orphan cleanup task cancelled")
            break
        except Exception:
            logger.exception("Error in orphan cleanup loop")
            await asyncio.sleep(60)


async def _soft_delete_expired_sessions() -> int:
    """Soft-delete sessions whose ``delete_after`` timestamp has passed.

    This enables timed deletion: callers set ``delete_after`` to a future
    timestamp and the session is automatically soft-deleted once that time
    arrives.  The subsequent orphan cleanup sweep will then remove any
    associated sandbox containers.

    Also cancels any active agent runs on the expired sessions via Redis
    and transitions their run tasks to CANCELLED status.
    """
    now = datetime.now(timezone.utc)
    deleted = 0

    try:
        async with get_db_session_local() as db:
            result = await db.execute(
                select(Session).where(
                    Session.is_deleted.is_(False),
                    Session.delete_after.isnot(None),
                    Session.delete_after <= now,
                )
            )
            sessions = result.scalars().all()

            for session in sessions:
                # Cancel any active runs before marking deleted
                await _cancel_active_runs_for_session(db, session.id)

                session.is_deleted = True
                deleted += 1
                logger.info(
                    "Auto-deleted expired session %s (delete_after=%s)",
                    session.id,
                    session.delete_after,
                )

            if deleted:
                await db.commit()
    except Exception:
        logger.exception("Error in expired session cleanup")

    return deleted


async def _cancel_active_runs_for_session(db: AsyncSession, session_id: "uuid.UUID") -> None:
    """Cancel active runs for a session being auto-deleted.

    Sends a Redis cancellation signal and transitions run tasks to CANCELLED.
    Best-effort: failures are logged but do not prevent session deletion.
    """
    try:
        active_values = [s.value for s in RunStatus.active_states()]
        result = await db.execute(
            select(RunTask).where(
                RunTask.session_id == session_id,
                RunTask.status.in_(active_values),
            )
        )
        active_tasks = result.scalars().all()

        for task in active_tasks:
            try:
                from ii_agent.core.redis.cancel import cancel_run

                await cancel_run(str(task.id))
                task.status = RunStatus.CANCELLED.value
                task.error_message = "Session auto-deleted (timed deletion)"
                logger.info(
                    "Cancelled active run %s for expired session %s",
                    task.id,
                    session_id,
                )
            except Exception:
                logger.warning(
                    "Failed to cancel run %s for expired session %s",
                    task.id,
                    session_id,
                    exc_info=True,
                )
    except Exception:
        logger.warning(
            "Failed to query active runs for expired session %s",
            session_id,
            exc_info=True,
        )


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
                            docker_sandbox._container = await asyncio.wait_for(
                                asyncio.to_thread(
                                    client.containers.get,
                                    sandbox.provider_sandbox_id,
                                ),
                                timeout=10,
                            )
                        except (asyncio.TimeoutError, Exception):
                            docker_sandbox._container = None

                        await asyncio.wait_for(docker_sandbox.kill(), timeout=30)
                    except asyncio.TimeoutError:
                        logger.warning(
                            "Timeout killing orphan container %s — skipping",
                            sandbox.provider_sandbox_id,
                        )
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
                        client = DockerSandbox._get_docker_client()
                        container = await asyncio.wait_for(
                            asyncio.to_thread(client.containers.get, sandbox.provider_sandbox_id),
                            timeout=10,
                        )
                        await asyncio.wait_for(
                            asyncio.to_thread(container.stop, timeout=10),
                            timeout=20,
                        )
                        sandbox.status = SandboxStatus.PAUSED
                        await db.flush()
                        paused += 1
                        logger.info(
                            "Paused stale sandbox %s (session %s, idle %.0fs)",
                            sandbox.id,
                            sandbox.session_id,
                            (now - updated_at).total_seconds() if updated_at else 0,
                        )
                    except asyncio.TimeoutError:
                        logger.warning(
                            "Timeout pausing stale sandbox %s — skipping",
                            sandbox.id,
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


async def _cleanup_docker_zombies() -> int:
    """Sweep Docker directly for sandbox containers not tracked in the DB.

    This catches containers that were orphaned because:
    - Their DB records were bulk-deleted (e.g. mass session cleanup)
    - The DB record was never written (crash during creation)
    - ``init_sandbox()`` replaced a dead container without removing the old one

    Only exited containers older than the grace period are removed.
    Running containers with no DB record are stopped and removed too, since
    they cannot be reconnected to any session.
    """
    reaped = 0
    now = datetime.now(timezone.utc)

    try:
        client = DockerSandbox._get_docker_client()
    except Exception:
        logger.debug("Docker client unavailable, skipping zombie sweep")
        return 0

    # Find all ii-sandbox containers (any status) via label
    try:
        containers = await asyncio.wait_for(
            asyncio.to_thread(
                client.containers.list,
                all=True,
                filters={"label": "ii-agent.sandbox=true"},
            ),
            timeout=15,
        )
    except asyncio.TimeoutError:
        logger.debug("Timeout listing Docker containers for zombie sweep")
        return 0
    except Exception:
        logger.debug("Failed to list Docker containers for zombie sweep")
        return 0

    if not containers:
        return 0

    # Collect the full container IDs present in Docker
    container_map: dict[str, docker.models.containers.Container] = {}
    for c in containers:
        container_map[c.id] = c

    # Query DB for all non-deleted sandbox provider_sandbox_ids
    active_ids: set[str] = set()
    try:
        async with get_db_session_local() as db:
            result = await db.execute(
                select(AgentSandbox.provider_sandbox_id).where(
                    AgentSandbox.provider == SandboxProviderType.DOCKER,
                    AgentSandbox.status != SandboxStatus.DELETED,
                    AgentSandbox.provider_sandbox_id.isnot(None),
                )
            )
            active_ids = {row[0] for row in result}
    except Exception:
        logger.warning("Failed to query DB for active sandbox IDs, skipping zombie sweep")
        return 0

    port_manager = PortPoolManager.get_instance()

    for container_id, container in container_map.items():
        if container_id in active_ids:
            continue  # Tracked in DB — leave it alone

        # Check grace period using the container's creation time
        try:
            created_str = container.attrs.get("Created", "")
            if created_str:
                # Docker returns ISO format with nanoseconds, parse safely
                created_at = datetime.fromisoformat(
                    created_str.replace("Z", "+00:00").split(".")[0] + "+00:00"
                )
                if (now - created_at) < _GRACE_PERIOD:
                    continue  # Too new — might still be initializing
        except Exception:
            pass  # If we can't parse, proceed with cleanup

        # Extract sandbox_id from label for volume + port cleanup
        sandbox_id = container.labels.get("ii-agent.sandbox-id", "")
        container_name = container.name or container.short_id

        try:
            await asyncio.wait_for(
                asyncio.to_thread(container.remove, force=True),
                timeout=15,
            )
            logger.info(
                "Reaped Docker zombie container %s (sandbox_id=%s, no active DB record)",
                container_name,
                sandbox_id or "unknown",
            )
            reaped += 1
        except asyncio.TimeoutError:
            logger.warning("Timeout removing zombie container %s — skipping", container_name)
            continue
        except NotFound:
            reaped += 1  # Already gone
        except APIError as e:
            logger.warning("Failed to remove zombie container %s: %s", container_name, e)
            continue

        # Clean up associated volume and ports
        if sandbox_id:
            try:
                _cleanup_sandbox_volume(client, sandbox_id)
            except Exception:
                pass
            try:
                port_manager.release_ports(sandbox_id)
            except Exception:
                pass

    return reaped


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
