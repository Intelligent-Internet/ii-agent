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

    In multi-worker deployments a Redis advisory lock (``sandbox:cleanup:lock``,
    5-minute TTL) prevents concurrent sweeps from racing on container removal.
    When Redis is unavailable the sweep proceeds with a warning.
    """
    cfg = config or get_settings()
    interval = cfg.sandbox.orphan_cleanup_interval_seconds

    while True:
        try:
            # Acquire advisory lock if Redis is available
            _lock_held = False
            _redis = None
            try:
                from ii_agent.core.redis.client import get_redis_client

                _redis = get_redis_client()
                _lock_held = bool(
                    await _redis.set(
                        "sandbox:cleanup:lock",
                        "1",
                        nx=True,
                        ex=300,  # 5-minute TTL
                    )
                )
                if not _lock_held:
                    logger.debug("Orphan cleanup: another worker holds the lock, skipping sweep")
                    await asyncio.sleep(interval)
                    continue
            except Exception as exc:
                logger.warning(
                    "Orphan cleanup: Redis advisory lock unavailable (%s); "
                    "proceeding without lock (safe in single-worker deployments)",
                    exc,
                )

            try:
                # R5: Run cleanup BEFORE sleeping so the first sweep is immediate
                expired = await _soft_delete_expired_sessions()
                cleaned = await _cleanup_orphans(cfg)
                paused = await _pause_stale_sandboxes(cfg)
                zombies = await _cleanup_docker_zombies()
                volumes = await _cleanup_orphaned_volumes()
                timed_out = await _kill_timed_out_sandboxes()
                if (
                    cleaned > 0
                    or paused > 0
                    or zombies > 0
                    or expired > 0
                    or volumes > 0
                    or timed_out > 0
                ):
                    logger.info(
                        f"Orphan cleanup sweep: expired={expired} sessions, removed={cleaned} orphaned, "
                        f"paused={paused} stale, reaped={zombies} docker zombies, "
                        f"volumes={volumes} orphaned, timed_out={timed_out} killed"
                    )
                else:
                    logger.debug("Orphan cleanup sweep completed: nothing to clean")
            finally:
                # Release advisory lock
                if _lock_held and _redis is not None:
                    try:
                        await _redis.delete("sandbox:cleanup:lock")
                    except Exception:
                        pass  # TTL will expire

            await asyncio.sleep(interval)
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
                    f"Auto-deleted expired session {session.id} (delete_after={session.delete_after})"
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
                logger.info(f"Cancelled active run {task.id} for expired session {session_id}")
            except Exception:
                logger.warning(
                    f"Failed to cancel run {task.id} for expired session {session_id}",
                    exc_info=True,
                )
    except Exception:
        logger.warning(
            f"Failed to query active runs for expired session {session_id}", exc_info=True
        )


async def _cleanup_orphans(cfg: Settings) -> int:
    """Single sweep: find and remove orphaned Docker sandboxes.

    R1: Only marks a sandbox record as DELETED when the Docker container is
    confirmed removed.  If container removal fails or times out, the record
    is left in its current state for retry on the next sweep.

    R2: Each sandbox is processed in its own DB session so a failure on one
    sandbox does not roll back progress on others.
    """
    now = datetime.now(timezone.utc)
    cleaned = 0

    # Phase 1: Identify candidates in a read-only query
    candidates: list[tuple] = []
    async with get_db_session_local() as db:
        result = await db.execute(
            select(AgentSandbox).where(
                AgentSandbox.provider == SandboxProviderType.DOCKER,
                AgentSandbox.status != SandboxStatus.DELETED,
            )
        )
        sandboxes = result.scalars().all()

        if not sandboxes:
            return 0

        session_ids = {s.session_id for s in sandboxes}
        session_result = await db.execute(
            select(Session.id, Session.is_deleted).where(Session.id.in_(session_ids))
        )
        session_map = {row.id: row.is_deleted for row in session_result}

        for sandbox in sandboxes:
            try:
                if sandbox.created_at and (now - sandbox.created_at) < _GRACE_PERIOD:
                    continue

                session_deleted = session_map.get(sandbox.session_id)
                if session_deleted is None:
                    pass  # Session row doesn't exist — treat as orphaned
                elif not session_deleted:
                    continue  # Session exists and is not deleted — keep sandbox

                candidates.append((sandbox.id, sandbox.session_id, sandbox.provider_sandbox_id))
            except Exception as e:
                logger.warning(f"Error evaluating sandbox {getattr(sandbox, 'id', '?')}: {e}")
                continue

    # Phase 2: Process each candidate in its own DB session (R2)
    for sandbox_id, session_id, provider_sandbox_id in candidates:
        try:
            container_removed = False

            if provider_sandbox_id:
                try:
                    docker_sandbox = DockerSandbox(
                        sandbox_id=str(sandbox_id),
                        session_id=str(session_id),
                        provider_sandbox_id=provider_sandbox_id,
                    )
                    client = DockerSandbox._get_docker_client()
                    try:
                        docker_sandbox._container = await asyncio.wait_for(
                            asyncio.to_thread(
                                client.containers.get,
                                provider_sandbox_id,
                            ),
                            timeout=10,
                        )
                    except asyncio.TimeoutError:
                        # R1: Cannot confirm container state — skip and retry next sweep
                        logger.warning(
                            f"Timeout getting container {provider_sandbox_id} for sandbox "
                            f"{sandbox_id} — deferring to next sweep"
                        )
                        continue
                    except NotFound:
                        # Container already gone — safe to mark DELETED
                        docker_sandbox._container = None
                        container_removed = True
                    except Exception as e:
                        logger.warning(
                            f"Error getting container {provider_sandbox_id}: {e} — deferring"
                        )
                        continue

                    if not container_removed:
                        try:
                            await asyncio.wait_for(docker_sandbox.kill(), timeout=30)
                            container_removed = True
                        except asyncio.TimeoutError:
                            logger.warning(
                                f"Timeout killing orphan container {provider_sandbox_id} — deferring"
                            )
                            continue
                        except Exception as e:
                            logger.warning(
                                f"Failed to kill orphan container {provider_sandbox_id}: {e} — deferring"
                            )
                            continue
                except Exception as e:
                    logger.warning(f"Error processing sandbox {sandbox_id}: {e}")
                    continue
            else:
                # No container to remove — safe to mark DELETED
                container_removed = True

            # R1: Only mark DELETED if container was confirmed removed
            if container_removed:
                async with get_db_session_local() as db:
                    result = await db.execute(
                        select(AgentSandbox).where(AgentSandbox.id == sandbox_id)
                    )
                    record = result.scalar_one_or_none()
                    if record and record.status != SandboxStatus.DELETED:
                        record.status = SandboxStatus.DELETED
                        await db.commit()
                        cleaned += 1
                        logger.info(
                            f"Cleaned up orphan sandbox {sandbox_id} (session {session_id} deleted)"
                        )

        except Exception as e:
            logger.warning(f"Error processing sandbox {sandbox_id}: {e}")
            continue

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
                            f"Paused stale sandbox {sandbox.id} (session {sandbox.session_id}, idle {(now - updated_at).total_seconds() if updated_at else 0:.0f}s)"
                        )
                    except asyncio.TimeoutError:
                        logger.warning(f"Timeout pausing stale sandbox {sandbox.id} — skipping")
                    except Exception as e:
                        logger.warning(f"Failed to pause stale sandbox {sandbox.id}: {e}")
            except Exception as e:
                logger.warning(f"Error processing sandbox {sandbox.id} for stale pause: {e}")
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
            timeout=120,
        )
    except asyncio.TimeoutError:
        logger.warning("Timeout listing Docker containers for zombie sweep (120s)")
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
                f"Reaped Docker zombie container {container_name} (sandbox_id={sandbox_id or 'unknown'}, no active DB record)"
            )
            reaped += 1
        except asyncio.TimeoutError:
            logger.warning(f"Timeout removing zombie container {container_name} — skipping")
            continue
        except NotFound:
            reaped += 1  # Already gone
        except APIError as e:
            logger.warning(f"Failed to remove zombie container {container_name}: {e}")
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


async def _cleanup_orphaned_volumes() -> int:
    """R9: Remove Docker volumes with no matching active sandbox record.

    Catches volumes orphaned by failed container removals or the P0-A bug
    where DB records were marked DELETED but containers (and volumes) persisted.
    """
    removed = 0

    try:
        client = DockerSandbox._get_docker_client()
    except Exception:
        logger.debug("Docker client unavailable, skipping volume cleanup")
        return 0

    try:
        volumes = await asyncio.wait_for(
            asyncio.to_thread(
                client.volumes.list,
                filters={"name": "ii-sandbox-workspace-"},
            ),
            timeout=30,
        )
    except asyncio.TimeoutError:
        logger.warning("Timeout listing Docker volumes for orphan cleanup")
        return 0
    except Exception:
        logger.debug("Failed to list Docker volumes for orphan cleanup")
        return 0

    if not volumes:
        return 0

    # Build set of sandbox IDs that have active (non-deleted) DB records
    active_sandbox_ids: set[str] = set()
    try:
        async with get_db_session_local() as db:
            result = await db.execute(
                select(AgentSandbox.id).where(
                    AgentSandbox.provider == SandboxProviderType.DOCKER,
                    AgentSandbox.status != SandboxStatus.DELETED,
                )
            )
            active_sandbox_ids = {str(row[0]) for row in result}
    except Exception:
        logger.warning("Failed to query DB for active sandbox IDs, skipping volume cleanup")
        return 0

    # Also check that no container references this volume
    try:
        containers = await asyncio.wait_for(
            asyncio.to_thread(
                client.containers.list,
                all=True,
                filters={"label": "ii-agent.sandbox=true"},
            ),
            timeout=120,
        )
        container_sandbox_ids = {c.labels.get("ii-agent.sandbox-id", "") for c in containers}
    except Exception:
        # If we can't list containers, don't risk removing volumes that are in use
        logger.debug("Cannot list containers, skipping volume cleanup")
        return 0

    prefix = "ii-sandbox-workspace-"
    for volume in volumes:
        vol_name = volume.name
        if not vol_name.startswith(prefix):
            continue

        sandbox_id = vol_name[len(prefix) :]
        if not sandbox_id:
            continue

        # Keep volumes for active DB records or existing containers
        if sandbox_id in active_sandbox_ids or sandbox_id in container_sandbox_ids:
            continue

        try:
            await asyncio.wait_for(
                asyncio.to_thread(volume.remove, force=True),
                timeout=15,
            )
            removed += 1
            logger.info(f"Removed orphaned volume {vol_name}")
        except Exception as e:
            logger.debug(f"Failed to remove orphaned volume {vol_name}: {e}")

    return removed


async def _kill_timed_out_sandboxes() -> int:
    """R6: Kill sandboxes that have exceeded their timeout_at deadline.

    This replaces the in-memory asyncio.Task timeout with a persistent
    database-driven check.  The ``timeout_at`` column is set when a sandbox
    is created and survives backend restarts.
    """
    now = datetime.now(timezone.utc)
    killed = 0

    async with get_db_session_local() as db:
        result = await db.execute(
            select(AgentSandbox).where(
                AgentSandbox.provider == SandboxProviderType.DOCKER,
                AgentSandbox.status.in_([SandboxStatus.RUNNING, SandboxStatus.PAUSED]),
                AgentSandbox.timeout_at.isnot(None),
                AgentSandbox.timeout_at <= now,
            )
        )
        timed_out = result.scalars().all()

    for sandbox in timed_out:
        try:
            if sandbox.provider_sandbox_id:
                try:
                    docker_sandbox = DockerSandbox(
                        sandbox_id=str(sandbox.id),
                        session_id=str(sandbox.session_id),
                        provider_sandbox_id=sandbox.provider_sandbox_id,
                    )
                    client = DockerSandbox._get_docker_client()
                    try:
                        docker_sandbox._container = await asyncio.wait_for(
                            asyncio.to_thread(
                                client.containers.get,
                                sandbox.provider_sandbox_id,
                            ),
                            timeout=10,
                        )
                    except NotFound:
                        docker_sandbox._container = None
                    except (asyncio.TimeoutError, Exception):
                        logger.warning(
                            f"Timeout getting timed-out container {sandbox.provider_sandbox_id}"
                        )
                        continue

                    if docker_sandbox._container:
                        try:
                            # Pause instead of kill — preserves sandbox for reconnection
                            await asyncio.wait_for(
                                asyncio.to_thread(docker_sandbox._container.stop, timeout=10),
                                timeout=20,
                            )
                        except (asyncio.TimeoutError, Exception) as e:
                            logger.warning(
                                f"Failed to stop timed-out container {sandbox.provider_sandbox_id}: {e}"
                            )
                            continue
                except Exception as e:
                    logger.warning(
                        f"Failed to connect to timed-out container {sandbox.provider_sandbox_id}: {e}"
                    )
                    continue

                async with get_db_session_local() as db:
                    result = await db.execute(
                        select(AgentSandbox).where(AgentSandbox.id == sandbox.id)
                    )
                    record = result.scalar_one_or_none()
                    if record and record.status not in (
                        SandboxStatus.DELETED,
                        SandboxStatus.PAUSED,
                    ):
                        record.status = SandboxStatus.PAUSED
                        record.timeout_at = None
                        await db.commit()
                        killed += 1
                        logger.info(
                            f"Paused timed-out sandbox {sandbox.id} "
                            f"(timeout_at={sandbox.timeout_at})"
                        )
            else:
                # No container — just clear the timeout
                async with get_db_session_local() as db:
                    result = await db.execute(
                        select(AgentSandbox).where(AgentSandbox.id == sandbox.id)
                    )
                    record = result.scalar_one_or_none()
                    if record:
                        record.timeout_at = None
                        await db.commit()

        except Exception as e:
            logger.warning(f"Error processing timed-out sandbox {sandbox.id}: {e}")
            continue

    return killed


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
