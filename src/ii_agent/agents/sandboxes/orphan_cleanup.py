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
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.agents.sandboxes.docker import DockerSandbox, _cleanup_sandbox_volume
from ii_agent.agents.sandboxes.executor import docker_call
from ii_agent.agents.sandboxes.host_monitor import (
    HostHealthState,
    HostMetricsBuffer,
    HostMonitorConfig,
    capacity_from_retention,
    evaluate as evaluate_host_state,
    get_host_state_snapshot,
    sample_host_metrics,
    set_host_state,
)
from ii_agent.agents.sandboxes.models import AgentSandbox
from ii_agent.agents.sandboxes.port_manager import PortPoolManager
from ii_agent.agents.sandboxes.types import PoolState, SandboxProviderType, SandboxStatus
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


def _is_pg_unavailable(exc: BaseException) -> bool:
    """Return True if ``exc`` is (wraps) asyncpg's CannotConnectNowError.

    PG emits SQLSTATE 57P03 during startup/recovery/shutdown. Walking
    ``__cause__``/``__context__`` lets us catch SQLAlchemy wrappers too.
    Kept in sync with ``core.middleware.exception_handler._is_db_unavailable``.
    """
    try:
        from asyncpg.exceptions import CannotConnectNowError  # type: ignore
    except ImportError:  # pragma: no cover
        return False
    seen: set[int] = set()
    cur: BaseException | None = exc
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        if isinstance(cur, CannotConnectNowError):
            return True
        cur = cur.__cause__ or cur.__context__
    return False


# ── Host monitor state (per-process) ──────────────────────────────────────
#
# Held at module level so both the orphan-cleanup loop and optional
# shutdown persistence helpers can reach the same buffer. Constructed
# lazily on first sweep (once settings are known) and re-built if
# retention/interval settings change between sweeps.
_HOST_MONITOR_BUFFER: Optional[HostMetricsBuffer] = None
_HOST_MONITOR_BUFFER_CAPACITY: Optional[int] = None
_HOST_MONITOR_LAST_SAMPLE = None  # type: Optional["HostMetrics"]  # noqa: F821


def _get_host_monitor_buffer(cfg: Settings) -> HostMetricsBuffer:
    """Return the shared host-metrics buffer, (re)building on capacity change."""
    global _HOST_MONITOR_BUFFER, _HOST_MONITOR_BUFFER_CAPACITY
    target_capacity = capacity_from_retention(
        cfg.sandbox.baseline_capture_retention_hours,
        cfg.sandbox.baseline_capture_interval_seconds,
    )
    if _HOST_MONITOR_BUFFER is None or _HOST_MONITOR_BUFFER_CAPACITY != target_capacity:
        _HOST_MONITOR_BUFFER = HostMetricsBuffer(
            capacity=target_capacity,
            bootstrap_fraction=cfg.sandbox.host_monitor_bootstrap_fraction,
        )
        _HOST_MONITOR_BUFFER_CAPACITY = target_capacity
    return _HOST_MONITOR_BUFFER


def _reset_host_monitor_for_tests() -> None:
    """Tests only: clear the shared buffer so each test starts fresh."""
    global _HOST_MONITOR_BUFFER, _HOST_MONITOR_BUFFER_CAPACITY, _HOST_MONITOR_LAST_SAMPLE
    _HOST_MONITOR_BUFFER = None
    _HOST_MONITOR_BUFFER_CAPACITY = None
    _HOST_MONITOR_LAST_SAMPLE = None


def get_host_monitor_buffer_snapshot() -> Optional[HostMetricsBuffer]:
    """Read-only accessor for the shared host-metrics buffer.

    Returns ``None`` before the first sweep has constructed it.
    Intended for ``/health/host``-style read-only consumers; callers
    must not mutate the returned object.
    """
    return _HOST_MONITOR_BUFFER


async def _run_host_monitor_phase(cfg: Settings) -> None:
    """Phase 0 of the cleanup sweep: sample /proc, evaluate, publish state.

    Failures are caught and logged at WARNING; a dead monitor must
    never kill the cleanup sweep. Before the ring buffer is warm, only
    hardcoded CRIT/WARN floors apply (see
    :func:`~ii_agent.agents.sandboxes.host_monitor.evaluate`).
    """
    global _HOST_MONITOR_LAST_SAMPLE

    if not cfg.sandbox.host_monitor_enabled:
        return

    try:
        sample = await sample_host_metrics(
            proc_root=cfg.sandbox.host_monitor_proc_root,
            docker_window=cfg.sandbox.host_monitor_docker_latency_window,
        )
    except FileNotFoundError:
        # /proc unreadable (e.g. running on non-Linux in tests). Silent
        # skip rather than spamming warnings.
        logger.debug("host_monitor: /proc not present; skipping sample")
        return
    except Exception as exc:
        logger.warning(f"host_monitor: sample failed ({exc}); will retry next sweep")
        return

    buffer = _get_host_monitor_buffer(cfg)
    if cfg.sandbox.baseline_capture_enabled:
        buffer.append(sample)

    monitor_cfg = HostMonitorConfig(
        order7_warn_floor=cfg.sandbox.host_monitor_order7_warn_floor,
        order7_crit_floor=cfg.sandbox.host_monitor_order7_crit_floor,
        mem_available_warn_mb=cfg.sandbox.host_monitor_mem_available_warn_mb,
        mem_available_crit_mb=cfg.sandbox.host_monitor_mem_available_crit_mb,
        docker_p99_watch_s=cfg.sandbox.host_monitor_docker_p99_watch_s,
        docker_p99_warn_s=cfg.sandbox.host_monitor_docker_p99_warn_s,
        docker_call_timeout_s=cfg.sandbox.docker_call_timeout_seconds,
    )

    prev_sample = _HOST_MONITOR_LAST_SAMPLE
    prev_state_snapshot = get_host_state_snapshot()
    # Use the previous in-memory state via the holder (set below) so
    # evaluate() can see counter deltas and hysteresis context.
    from ii_agent.agents.sandboxes.host_monitor import get_host_state as _get_host_state

    prev_state = _get_host_state()

    state = evaluate_host_state(
        sample,
        buffer,
        prev_state,
        monitor_cfg,
        prev_sample=prev_sample,
    )
    set_host_state(state, sample)
    _HOST_MONITOR_LAST_SAMPLE = sample

    # Log level scales with severity, and transitions are always
    # reported so operators see state changes in real time.
    if state != prev_state:
        msg = (
            f"host_monitor: state {prev_state.name} -> {state.name} "
            f"order7={sample.order7_free()} "
            f"mem_avail_mb={sample.mem_available_mb()} "
            f"docker_p99_s={sample.docker_call_p99_s:.2f}"
        )
        if state == HostHealthState.CRIT:
            logger.error(msg)
        elif state == HostHealthState.WARN:
            logger.warning(msg)
        else:
            logger.info(msg)
    elif state >= HostHealthState.WATCH:
        # Periodic status so degradation is visible in logs even
        # without a transition.
        logger.info(
            f"host_monitor: state={state.name} "
            f"order7={sample.order7_free()} "
            f"mem_avail_mb={sample.mem_available_mb()} "
            f"docker_p99_s={sample.docker_call_p99_s:.2f} "
            f"baseline_warm={buffer.is_warm()}"
        )

    # Touch ``prev_state_snapshot`` to silence unused-variable lint;
    # retained here because a future evaluator revision may use it for
    # additional hysteresis logic.
    _ = prev_state_snapshot


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
                    f"Orphan cleanup: Redis advisory lock unavailable ({exc}); "
                    "proceeding without lock (safe in single-worker deployments)"
                )

            try:
                # R5: Run cleanup BEFORE sleeping so the first sweep is immediate
                _sweep_started = asyncio.get_running_loop().time()
                # Phase 0: host health sample + evaluation. Must run
                # first so downstream phases (and out-of-sweep
                # consumers) see the freshest state.
                await _run_host_monitor_phase(cfg)
                expired = await _soft_delete_expired_sessions()
                pool_retired = await _retire_pool_sandboxes()
                pool_deduped = await _dedupe_pool_slots()
                pool_validated = await _validate_pool_slots()
                pool_reaped = await _reap_pool_stuck_init()
                health_marked = await _health_check_sandbox_rows()
                ttl_expired = await _expire_old_paused_sandboxes(cfg)
                cleaned = await _cleanup_orphans(cfg)
                paused = await _pause_stale_sandboxes(cfg)
                zombies = await _cleanup_docker_zombies()
                volumes = await _cleanup_orphaned_volumes()
                timed_out = await _kill_timed_out_sandboxes()
                purged = await _purge_stale_deleted_rows(cfg)
                await _ensure_pool_full()
                _sweep_elapsed = asyncio.get_running_loop().time() - _sweep_started
                if _sweep_elapsed > 5.0:
                    logger.warning(
                        f"Orphan cleanup sweep took {_sweep_elapsed:.1f}s "
                        f"(expected <5s) — Docker or DB may be slow"
                    )
                if (
                    cleaned > 0
                    or paused > 0
                    or zombies > 0
                    or expired > 0
                    or volumes > 0
                    or timed_out > 0
                    or pool_retired > 0
                    or pool_deduped > 0
                    or pool_validated > 0
                    or pool_reaped > 0
                    or health_marked > 0
                    or ttl_expired > 0
                    or purged > 0
                ):
                    logger.info(
                        f"Orphan cleanup sweep: expired={expired} sessions, removed={cleaned} orphaned, "
                        f"paused={paused} stale, reaped={zombies} docker zombies, "
                        f"volumes={volumes} orphaned, timed_out={timed_out} killed, "
                        f"pool_retired={pool_retired} pool_deduped={pool_deduped}, "
                        f"pool_validated={pool_validated}, pool_reaped={pool_reaped}, "
                        f"health_marked={health_marked}, ttl_expired={ttl_expired}, "
                        f"purged={purged}, elapsed={_sweep_elapsed:.1f}s"
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
        except Exception as loop_exc:
            # Transient PG unavailability (crash-recovery, restart,
            # failover) is expected and self-healing — downgrade the
            # log from ERROR+traceback to WARNING and back off.  See
            # docs/runtime-docs/postgres-recovery-mode-failures.md.
            if _is_pg_unavailable(loop_exc):
                logger.warning(
                    "Orphan cleanup sweep skipped: database in recovery ({}); retrying in 60s",
                    type(loop_exc).__name__,
                )
            else:
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
                # session_deleted is:
                #   False -> session row exists and is_deleted=False (alive)
                #   True  -> session row exists and is_deleted=True  (soft-deleted)
                #   None  -> session row missing (legacy / crashed / never-linked)
                session_deleted = session_map.get(sandbox.session_id)

                # AVAILABLE pool slots have no owning session by design — they
                # are warm spares managed by the pool retirement/dedupe phases,
                # never by orphan cleanup.
                if sandbox.pool_state == PoolState.AVAILABLE:
                    continue

                # All other rows (CLAIMED, RETIRING, non-pool) are reapable
                # only when their owning session is no longer alive. Previously
                # CLAIMED rows were skipped unconditionally, leaking sandboxes
                # whose sessions had been soft-deleted.
                if session_deleted is False:
                    continue

                if sandbox.created_at and (now - sandbox.created_at) < _GRACE_PERIOD:
                    continue

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
                # Skip pool-managed rows: they intentionally have no session
                # activity (AVAILABLE) or follow their own retirement schedule
                # (RETIRING). Stale-pause logic does not apply.
                if sandbox.pool_state is not None:
                    continue

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


async def _health_check_sandbox_rows() -> int:
    """Reconcile non-deleted sandbox rows against Docker reality.

    For every row in status PAUSED or RUNNING we inspect the underlying
    Docker container. If the container is missing, or its referenced
    bridge network no longer exists (common after host/Docker reboot),
    the row is marked DELETED so future session activity creates a fresh
    sandbox instead of triggering doomed restart loops.

    Pool rows in AVAILABLE state are also validated here so a standby slot
    backed by a dead container is recycled promptly. CLAIMED rows follow
    the normal session lifecycle.

    This closes the primary failure mode observed in production: paused
    rows whose networks are destroyed on reboot live forever and every
    frontend poll produces "Cannot restart sandbox ...: network X not
    found" errors that block the asyncio event loop.
    """
    try:
        client = DockerSandbox._get_docker_client()
    except Exception:
        logger.debug("Docker client unavailable, skipping health-check phase")
        return 0

    # Phase 1: read candidate rows
    async with get_db_session_local() as db:
        result = await db.execute(
            select(AgentSandbox).where(
                AgentSandbox.provider == SandboxProviderType.DOCKER,
                AgentSandbox.status.in_([SandboxStatus.RUNNING, SandboxStatus.PAUSED]),
                AgentSandbox.provider_sandbox_id.isnot(None),
            )
        )
        rows = result.scalars().all()

    if not rows:
        return 0

    marked = 0
    for row in rows:
        provider_sandbox_id = row.provider_sandbox_id
        sandbox_id = row.id
        if not provider_sandbox_id:
            continue

        container = None
        try:
            container = await docker_call(client.containers.get, provider_sandbox_id, timeout=10)
        except asyncio.TimeoutError:
            logger.debug(f"Health check: Docker timeout for sandbox {sandbox_id} — deferring")
            continue
        except NotFound:
            # Container has vanished — mark row deleted.
            logger.info(
                f"Health check: container for sandbox {sandbox_id} not found in Docker — marking deleted"
            )
        except APIError as exc:
            logger.debug(
                f"Health check: Docker APIError for sandbox {sandbox_id}: {exc} — deferring"
            )
            continue
        except Exception as exc:
            logger.debug(
                f"Health check: unexpected error for sandbox {sandbox_id}: {exc} — deferring"
            )
            continue

        network_missing = False
        if container is not None:
            try:
                await docker_call(container.reload, timeout=10)
            except Exception:
                # Reload failed — treat as transient, retry next sweep.
                continue

            # Detect the "bridge network destroyed on reboot" case. We
            # look at the *referenced* network IDs on the container; any
            # missing one is unrecoverable without container recreation.
            try:
                networks = container.attrs.get("NetworkSettings", {}).get("Networks", {}) or {}
                for net_name, net_info in networks.items():
                    net_id = net_info.get("NetworkID") if isinstance(net_info, dict) else None
                    if not net_id:
                        continue
                    try:
                        await docker_call(client.networks.get, net_id, timeout=5)
                    except NotFound:
                        logger.info(
                            f"Health check: network {net_name} ({net_id[:12]}) referenced by "
                            f"sandbox {sandbox_id} no longer exists — marking deleted"
                        )
                        network_missing = True
                        break
                    except Exception:
                        # Transient; skip this row this sweep.
                        network_missing = False
                        container = None
                        break
            except Exception:
                continue

            if not network_missing and container is not None:
                # Container exists and references live networks. Healthy.
                continue

        # Either container was NotFound, or its network is gone. Mark deleted.
        try:
            async with get_db_session_local() as db:
                result = await db.execute(select(AgentSandbox).where(AgentSandbox.id == sandbox_id))
                record = result.scalar_one_or_none()
                if record and record.status != SandboxStatus.DELETED:
                    record.status = SandboxStatus.DELETED
                    record.pool_state = None
                    record.pool_slot = None
                    await db.commit()
                    marked += 1
        except Exception:
            logger.warning(
                f"Health check: failed to mark sandbox {sandbox_id} deleted",
                exc_info=True,
            )

        # Best-effort: if the container object still exists but its
        # network is gone, remove it so a stale stopped container does
        # not linger forever.
        if network_missing and container is not None:
            try:
                await docker_call(container.remove, force=True, timeout=15)
            except Exception:
                pass

    return marked


async def _expire_old_paused_sandboxes(cfg: Settings) -> int:
    """Mark paused session-attached sandboxes older than the TTL as DELETED.

    Paused sandboxes otherwise live forever until their session is deleted,
    accumulating unrecoverable rows (e.g. after host reboots) that spam
    restart errors on every frontend poll.

    Only session-attached rows (``pool_state IS NULL``) are subject to
    this TTL — pool-managed rows have their own ``retire_at`` schedule.
    """
    ttl_seconds = cfg.sandbox.max_paused_age_seconds
    if ttl_seconds <= 0:
        return 0

    cutoff = datetime.now(timezone.utc) - timedelta(seconds=ttl_seconds)
    marked = 0

    async with get_db_session_local() as db:
        result = await db.execute(
            select(AgentSandbox).where(
                AgentSandbox.provider == SandboxProviderType.DOCKER,
                AgentSandbox.status == SandboxStatus.PAUSED,
                AgentSandbox.pool_state.is_(None),
                AgentSandbox.updated_at < cutoff,
            )
        )
        rows = result.scalars().all()
        for row in rows:
            row.status = SandboxStatus.DELETED
            marked += 1
            logger.info(
                f"Expired paused sandbox {row.id} (updated_at={row.updated_at}, ttl={ttl_seconds}s)"
            )
        if marked:
            await db.commit()

    return marked


async def _purge_stale_deleted_rows(cfg: Settings) -> int:
    """Hard-delete rows with ``status='deleted'`` older than the purge TTL.

    Keeps the ``agent_sandboxes`` table compact so index scans remain fast.
    """
    ttl_seconds = cfg.sandbox.stale_deleted_purge_age_seconds
    if ttl_seconds <= 0:
        return 0

    cutoff = datetime.now(timezone.utc) - timedelta(seconds=ttl_seconds)
    purged = 0

    try:
        async with get_db_session_local() as db:
            result = await db.execute(
                select(AgentSandbox.id).where(
                    AgentSandbox.status == SandboxStatus.DELETED,
                    AgentSandbox.updated_at < cutoff,
                )
            )
            ids = [row[0] for row in result]
            if not ids:
                return 0
            # Delete in a single statement
            from sqlalchemy import delete as _delete

            await db.execute(_delete(AgentSandbox).where(AgentSandbox.id.in_(ids)))
            await db.commit()
            purged = len(ids)
            logger.info(f"Purged {purged} stale deleted sandbox rows (older than {ttl_seconds}s)")
    except Exception:
        logger.exception("Failed to purge stale deleted sandbox rows")

    return purged


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
                # AVAILABLE pool slots manage their own lifetime via
                # retire_at — never let the per-session timeout_at check
                # kill an unclaimed pre-warmed slot. CLAIMED slots have
                # been handed to a session and follow the normal session
                # timeout rules. RETIRING rows are handled by the orphan
                # path (session_id IS NULL). NOTE: SQL ``!=`` does not
                # match NULL, so we OR explicitly to include normal
                # (non-pool) session sandboxes.
                or_(
                    AgentSandbox.pool_state.is_(None),
                    AgentSandbox.pool_state != PoolState.AVAILABLE,
                ),
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


# ── Pre-warmed pool integration ─────────────────────────────────────────


def _get_pool_manager():
    """Return the SandboxPoolManager from the global app container.

    Returns ``None`` when the container is not yet initialized (e.g. early
    test startup) or the pool is disabled.
    """
    try:
        from ii_agent.core.container import get_app_container

        container = get_app_container()
    except Exception:
        return None
    pool_mgr = getattr(container, "sandbox_pool_manager", None)
    if pool_mgr is None or not getattr(pool_mgr, "enabled", False):
        return None
    return pool_mgr


async def _retire_pool_sandboxes() -> int:
    """Mark AVAILABLE pool rows past their ``retire_at`` deadline as RETIRING.

    The actual container kill happens in ``_cleanup_orphans`` (RETIRING rows
    have ``session_id=NULL`` and fall through the orphan candidate check).
    """
    pool_mgr = _get_pool_manager()
    if pool_mgr is None:
        return 0
    try:
        return await pool_mgr.mark_due_for_retirement()
    except Exception:
        logger.exception("Sandbox pool: mark_due_for_retirement failed")
        return 0


async def _dedupe_pool_slots() -> int:
    """Drop duplicate AVAILABLE pool rows per slot (keep newest).

    Defends against rollback races where a claim scheduled a replenish but
    the caller's transaction never committed, leaving stale AVAILABLE rows.
    """
    pool_mgr = _get_pool_manager()
    if pool_mgr is None:
        return 0
    try:
        return await pool_mgr.dedupe_available_slots()
    except Exception:
        logger.exception("Sandbox pool: dedupe_available_slots failed")
        return 0


async def _validate_pool_slots() -> int:
    """Retire AVAILABLE pool rows whose containers are missing or dead."""
    pool_mgr = _get_pool_manager()
    if pool_mgr is None:
        return 0
    try:
        return await pool_mgr.validate_available_slots()
    except Exception:
        logger.exception("Sandbox pool: validate_available_slots failed")
        return 0


async def _reap_pool_stuck_init() -> int:
    """Reap AVAILABLE+INITIALIZING pool rows wedged past the stuck threshold.

    Runs unconditionally (does not skip on host WARN/CRIT) because the
    reap is a pure DB UPDATE — no container creation or memory pressure.
    Without this, stuck rows accumulate indefinitely whenever the host
    monitor stays elevated, blocking ``ensure_full`` from recreating the
    slot.
    """
    pool_mgr = _get_pool_manager()
    if pool_mgr is None:
        return 0
    try:
        return await pool_mgr.reap_stuck_initializing()
    except Exception:
        logger.exception("Sandbox pool: reap_stuck_initializing failed")
        return 0


async def _ensure_pool_full() -> None:
    """Re-fill any missing pool slots after retirements/claims.

    Fire-and-forget: the actual container creates run as background tasks.
    """
    pool_mgr = _get_pool_manager()
    if pool_mgr is None:
        return
    try:
        await pool_mgr.ensure_full()
    except Exception:
        logger.exception("Sandbox pool: ensure_full failed")


async def run_once_reconciliation(config: Optional[Settings] = None) -> None:
    """Run a single reconciliation sweep (health-check + TTL + orphans).

    Intended to be called during application startup, after Redis and DB
    are available but BEFORE the WebSocket server starts accepting
    connections. Reconciles DB rows against Docker reality so stale rows
    left behind by a host reboot don't generate a flood of failing
    restart attempts at first user interaction.

    Safe to call multiple times; individual phases tolerate empty state.
    """
    cfg = config or get_settings()
    if not cfg.sandbox.local_mode:
        return
    try:
        started = asyncio.get_running_loop().time()
        await _health_check_sandbox_rows()
        await _expire_old_paused_sandboxes(cfg)
        await _cleanup_orphans(cfg)
        await _cleanup_docker_zombies()
        await _cleanup_orphaned_volumes()
        await _purge_stale_deleted_rows(cfg)
        elapsed = asyncio.get_running_loop().time() - started
        logger.info(f"Startup sandbox reconciliation completed in {elapsed:.1f}s")
    except Exception:
        logger.exception("Startup sandbox reconciliation failed (non-fatal)")


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
