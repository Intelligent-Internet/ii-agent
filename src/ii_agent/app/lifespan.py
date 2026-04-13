"""Application lifespan wiring.

Startup order:
1. Redis client (lazy singleton)
2. Database migrations
3. ServiceContainer (all domain services)
4. PubSub (singleton + callback handlers)
5. SocketIOManager (registers socket event handlers)
6. Seed data (LLM settings, built-in skills)
7. Cron scheduler

Shutdown order: reverse.
"""

from __future__ import annotations

import logging
import os
import uuid
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

import socketio
from fastapi import FastAPI
from sqlalchemy import update

from ii_agent.core.container import ApplicationContainer, set_app_container
from ii_agent.core.db import get_db_session_local
from ii_agent.core.db.base import get_engine, shutdown_engine
from ii_agent.core.redis.client import get_redis_client, shutdown_redis_client
from ii_agent.realtime.pubsub.asyncio_pubsub import AsyncIOPubSub
from ii_agent.credits.usage import CreditUsageHandler
from ii_agent.realtime.pubsub.callbacks import (
    DatabaseCallbackHandler,
    SioCallbackHandler,
)
from ii_agent.realtime.manager import SocketIOManager
from ii_agent.sessions.models import Session
from ii_agent.sessions.types import SessionState
from ii_agent.settings.llm.seeding import ensure_admin_llm_settings_seeded
from ii_agent.settings.skills.seeding import ensure_builtin_skills_synced
from ii_agent.tasks.types import RunStatus
from ii_agent.workers.cron.tasks import shutdown_scheduler, start_scheduler

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

logger = logging.getLogger(__name__)


async def _cleanup_orphaned_tasks(container: ApplicationContainer) -> None:
    """Cancel any run_tasks left in RUNNING or ABORTING from a previous process.

    After a server restart the in-memory (or Redis) cancel registry is
    empty, so these tasks will never complete on their own.  Transitioning
    them to CANCELLED and resetting their sessions to 'active' unblocks
    the frontend.
    """
    svc = container.run_task_service

    async with get_db_session_local() as db:
        running_session_ids = await svc.get_all_running_session_ids(db)

        if not running_session_ids:
            return

        logger.info(
            "Cleaning up %d sessions with orphaned running tasks",
            len(running_session_ids),
        )

        for sid_str in running_session_ids:
            session_id = uuid.UUID(sid_str) if isinstance(sid_str, str) else sid_str
            task = await svc.get_last_by_session_id(db, session_id)
            if task and task.status in [RunStatus.RUNNING, RunStatus.ABORTING]:
                await svc.transition_status(
                    db,
                    task_id=task.id,
                    to_status=RunStatus.CANCELLED,
                    error_message="Force-cancelled: orphaned after server restart",
                )
                logger.info("Cancelled orphaned task %s (session %s)", task.id, session_id)

        # Reset any sessions stuck in 'pending' state
        result = await db.execute(
            update(Session)
            .where(Session.status == SessionState.PENDING)
            .values(status=SessionState.ACTIVE)
        )
        if result.rowcount:
            logger.info("Reset %d sessions from pending to active", result.rowcount)

        await db.commit()


def _init_pubsub(
    sio: socketio.AsyncServer,
    container: ApplicationContainer,
) -> AsyncIOPubSub:
    """Create the pub/sub singleton and register callback handlers."""
    pubsub = AsyncIOPubSub()

    pubsub.subscribe(SioCallbackHandler(sio))
    pubsub.subscribe(DatabaseCallbackHandler(container.event_repo))
    pubsub.subscribe(
        CreditUsageHandler(
            credit_service=container.credit_service,
            pubsub=pubsub,
        )
    )

    return pubsub


async def _init_sio_manager(
    sio: socketio.AsyncServer,
    pubsub: AsyncIOPubSub,
    container: ApplicationContainer,
) -> SocketIOManager:
    """Create and initialize the Socket.IO manager."""
    sio_manager = SocketIOManager(sio=sio, pubsub=pubsub, container=container)
    await sio_manager.init()
    return sio_manager


def create_lifespan(sio: socketio.AsyncServer):
    """Create the FastAPI lifespan context manager.

    ``sio`` is the Socket.IO server created in ``create_app()`` — it must
    exist before the ASGI app starts, but its event handlers and pub/sub
    callbacks are wired here during startup.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # ── Startup ────────────────────────────────────────────────────

        # 1. Database engine (lazy singleton — ensures connection pool is ready)
        get_engine()
        logger.info("Database engine initialized")

        # 2. Redis (lazy singleton)
        get_redis_client()

        # 3. Database migrations
        if os.getenv("II_AGENT_SKIP_MIGRATIONS", "").lower() not in ("1", "true", "yes"):
            from ii_agent.core.db.base import run_migrations

            run_migrations()
            logger.info("Database migrations applied")

        # 4. Service container (all domain services)
        container = ApplicationContainer.init()
        set_app_container(container)
        app.state.container = container

        # 4b. Cleanup orphaned run tasks from previous server lifecycle
        try:
            await _cleanup_orphaned_tasks(container)
        except Exception as exc:
            logger.warning("Orphaned task cleanup failed: %s", exc)

        # 5. Pub/sub (callbacks: socket.io + db persistence)
        pubsub = _init_pubsub(sio, container)
        await pubsub.start()
        app.state.pubsub = pubsub
        container.plan_service.set_pubsub(pubsub)
        container.workspace_explorer_service.set_pubsub(pubsub)
        logger.info("PubSub started with %d handlers", len(pubsub._handlers))

        # 6. Socket.IO manager (registers socket event handlers)
        sio_manager = await _init_sio_manager(sio, pubsub, container)
        app.state.sio_manager = sio_manager
        logger.info("SocketIOManager initialized")

        # 7. Seed data
        try:
            await ensure_admin_llm_settings_seeded()
            await ensure_builtin_skills_synced()
        except Exception as exc:
            logger.error("Failed to run startup seeds: %s", exc)

        # 8. Cron scheduler
        start_scheduler()

        # 9. Docker sandbox: scan existing containers to reclaim ports
        try:
            from ii_agent.core.config.settings import get_settings as _get_settings

            _settings = _get_settings()
            if _settings.sandbox.local_mode:
                from ii_agent.agents.sandboxes.docker import DockerSandbox
                from ii_agent.agents.sandboxes.port_manager import PortPoolManager

                try:
                    docker_client = DockerSandbox._get_docker_client()
                    port_manager = PortPoolManager.get_instance()
                    discovered = port_manager.scan_existing_containers(docker_client)
                    logger.info("Scanned existing Docker sandbox containers: %d found", discovered)
                except Exception as exc:
                    logger.warning(
                        "Docker sandbox scan failed (Docker may not be running): %s", exc
                    )

                # 10. Orphan cleanup background task
                from ii_agent.agents.sandboxes.orphan_cleanup import start_orphan_cleanup

                start_orphan_cleanup(_settings)
        except Exception as exc:
            logger.warning("Docker sandbox initialization skipped: %s", exc)

        yield

        # ── Shutdown (reverse order) ───────────────────────────────────

        # Stop orphan cleanup first
        try:
            from ii_agent.agents.sandboxes.orphan_cleanup import stop_orphan_cleanup

            stop_orphan_cleanup()
        except Exception:
            pass

        shutdown_scheduler()
        await container.workspace_explorer_service.shutdown()
        await sio_manager.shutdown()
        await pubsub.stop()
        logger.info("PubSub stopped")
        await shutdown_redis_client()
        await shutdown_engine()
        set_app_container(None)
        logger.info("Database engine disposed")

    return lifespan
