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
    from ii_agent.core.config.settings import get_settings

    pubsub = AsyncIOPubSub()

    pubsub.subscribe(SioCallbackHandler(sio))
    pubsub.subscribe(DatabaseCallbackHandler(container.event_repo))
    pubsub.subscribe(
        CreditUsageHandler(
            credit_service=container.credit_service,
            pubsub=pubsub,
            billing_enabled=get_settings().credits.billing_enabled,
            agent_settings=get_settings().agent,
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

        # 0. Observability: raise slow-callback threshold so blocking I/O
        #    is visible in logs. Default 0.5s; 0 disables.
        try:
            import asyncio as _asyncio_obs
            from ii_agent.core.config.settings import get_settings as _gsettings

            _slow = float(_gsettings().sandbox.event_loop_slow_callback_seconds)
            if _slow > 0:
                _asyncio_obs.get_event_loop().slow_callback_duration = _slow
        except Exception:
            pass

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

        # 4a. ORM defence-in-depth: register before_insert guard on Session
        #     so direct ORM inserts cannot bypass NotPurgingDep when the
        #     owning user has is_purging=true (I3/I8/I14, Adversarial v3.9 #5).
        try:
            from ii_agent.sessions.purge.orm_guards import register_purge_guards

            register_purge_guards()
        except Exception as exc:
            logger.error("Failed to register ORM purge guards: %s", exc)
            raise

        # 4a-bis. I17 deployment-config gate: verify the grace-purge cleanup
        #     loop will bind to the primary DB engine, not a read replica.
        #     A replica-bound sweep would silently miss the GDPR Art. 17
        #     deadline. Fail-loud on any suspect engine attribute.
        try:
            from ii_agent.sessions.purge.check_runner import (
                assert_cleanup_uses_primary_db,
            )

            assert_cleanup_uses_primary_db()
        except AssertionError as exc:
            logger.error("I17 deployment-config check FAILED: %s", exc)
            raise

        # 4c. Register session-purge phase-(b) provider cleanup hooks.
        #     Each hook is opt-in via SESSIONS_*_PROVIDER_CLEANUP_ENABLED so
        #     the registration ships dark; satisfies pre-flip gate #4.
        try:
            from ii_agent.sessions.purge.hooks_openai import maybe_register_openai_hook

            if maybe_register_openai_hook():
                logger.info("Session-purge phase-(b): OpenAI hook active")
        except Exception as exc:
            # A hook-registration failure must not crash startup; phase (b)
            # is degraded (more leaks) but the rest of the system is up.
            logger.error("Failed to register session-purge cleanup hooks: %s", exc)

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
        # Audit item #7: surface MCP-configure failures into the agent UI.
        container.sandbox_service.set_pubsub(pubsub)
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

        # 8b. A2A inner-loop startup validation
        try:
            from ii_agent.core.config.settings import get_settings as _get_a2a_settings

            _a2a_cfg = _get_a2a_settings().agent
            _a2a_modes = (_a2a_cfg.inner_loop_mode, _a2a_cfg.chat_inner_loop_mode)
            if "a2a" in _a2a_modes:
                # Check that optional extras are installed
                from ii_agent.integrations.a2a import require_a2a_extras

                require_a2a_extras()

                # Warn about the active backend and required credentials
                _backend = _a2a_cfg.a2a_backend
                _cred_map = {
                    "copilot": "GITHUB_TOKEN / GH_TOKEN (or 'gh auth login')",
                    "claude-code": "ANTHROPIC_API_KEY",
                    "codex": "OPENAI_API_KEY",
                }
                logger.info(
                    "A2A inner-loop enabled: backend=%s, fallback=%s, timeout=%ss. "
                    "Required credentials: %s",
                    _backend,
                    _a2a_cfg.a2a_fallback_to_native,
                    _a2a_cfg.a2a_timeout_seconds,
                    _cred_map.get(_backend, "unknown"),
                )

                # Validate per-mode A2A configuration.
                #
                # Agent A2A: per-session adapter URL via sandbox.expose_port()
                # works in BOTH local Docker and cloud E2B (every sandbox
                # ships the adapter via docker/sandbox/start-services.sh).
                # AGENT_A2A_AGENT_URL is only needed if the operator wants
                # to override that with an external adapter.
                #
                # Chat A2A: chat sessions do NOT own sandboxes; the chat
                # A2A loop is a stateless protocol bridge to a single
                # adapter URL.  AGENT_A2A_AGENT_URL is REQUIRED.  The
                # local Docker stack ships an `a2a-adapter` sidecar
                # (docker/docker-compose.local.yaml) that auto-populates
                # the URL.  See docs/design-docs/chat-a2a-adapter-sidecar.md.
                if _a2a_cfg.chat_inner_loop_mode == "a2a" and not _a2a_cfg.a2a_agent_url:
                    _msg = (
                        "AGENT_CHAT_INNER_LOOP_MODE=a2a but "
                        "AGENT_A2A_AGENT_URL is not set. Chat A2A is "
                        "sandbox-independent by design and requires an "
                        "explicit adapter URL. Without it, every chat "
                        "request will silently fall back to the native "
                        "LLM and incur direct provider charges (10x+ "
                        "the Copilot subscription cost). The local "
                        "Docker stack ships an a2a-adapter sidecar at "
                        "http://a2a-adapter:18100 — set this URL or "
                        "deploy your own adapter. See "
                        "docs/design-docs/chat-a2a-adapter-sidecar.md."
                    )
                    if _a2a_cfg.a2a_chat_strict:
                        logger.error(_msg)
                        raise RuntimeError(_msg)
                    logger.error(_msg)
                elif _a2a_cfg.chat_inner_loop_mode == "a2a" and _a2a_cfg.a2a_agent_url:
                    logger.info(
                        "AGENT_CHAT_INNER_LOOP_MODE=a2a, adapter URL: %s",
                        _a2a_cfg.a2a_agent_url,
                    )
        except RuntimeError as exc:
            # require_a2a_extras raises RuntimeError when packages are missing
            logger.error("A2A startup validation failed: %s", exc)
            raise
        except Exception as exc:
            logger.warning("A2A startup validation skipped: %s", exc)

        # 9. Docker sandbox: scan existing containers to reclaim ports
        try:
            from ii_agent.core.config.settings import get_settings as _get_settings

            _settings = _get_settings()
            if _settings.sandbox.local_mode:
                from ii_agent.agents.sandboxes.docker import DockerSandbox
                from ii_agent.agents.sandboxes.port_manager import PortPoolManager

                # 9a. Docker socket permission diagnostic
                _sock_path = DockerSandbox._resolve_docker_socket()
                if _sock_path:
                    if not os.access(_sock_path, os.R_OK | os.W_OK):
                        logger.error(
                            "Docker socket at %s exists but is not accessible. "
                            "Add your user to the 'docker' group: "
                            "sudo usermod -aG docker $USER && newgrp docker",
                            _sock_path,
                        )

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
                from ii_agent.agents.sandboxes.orphan_cleanup import (
                    run_once_reconciliation,
                    start_orphan_cleanup,
                )

                # 10a. Startup reconciliation sweep: mark stale rows DELETED
                #      before the WebSocket server starts accepting pings so
                #      frontends don't trigger a flood of doomed restart
                #      attempts on sandboxes whose networks/containers are
                #      gone (e.g. after host reboot).
                try:
                    await run_once_reconciliation(_settings)
                except Exception:
                    logger.exception("Startup sandbox reconciliation failed (non-fatal)")

                start_orphan_cleanup(_settings)

                # 11. Pre-warmed sandbox pool: bootstrap all N slots in parallel.
                #     No-op if SANDBOX_PREWARM_POOL_SIZE=0 (default).
                try:
                    pool_mgr = getattr(container, "sandbox_pool_manager", None)
                    if pool_mgr is not None and pool_mgr.enabled:
                        logger.info(
                            "Bootstrapping pre-warmed sandbox pool (size=%d, max_age=%ds)",
                            pool_mgr.pool_size,
                            pool_mgr.max_age_seconds,
                        )
                        # Fire-and-forget: bootstrap can take ~110s per slot.
                        # We must not block startup.
                        import asyncio as _asyncio_pool

                        _asyncio_pool.create_task(pool_mgr.bootstrap())
                except Exception as exc:
                    logger.warning("Sandbox pool bootstrap skipped: %s", exc)
        except Exception as exc:
            logger.warning("Docker sandbox initialization skipped: %s", exc)

        yield

        # ── Shutdown (clean-shutdown contract) ─────────────────────────
        # Order matters. The compose-level `stop_grace_period: 30s` and
        # gunicorn `--graceful-timeout 25` give us a strict budget. We
        # must reach `shutdown_engine()` (asyncpg pool dispose) before
        # the SIGKILL deadline, otherwise PG sees N child backends die
        # mid-transaction in the same millisecond and enters recovery
        # for 5+ minutes. See:
        #   docs/runtime-docs/postgres-recovery-mode-failures.md
        # Order:
        #   1. Stop accepting *new* work (sio, orphan-cleanup, scheduler).
        #   2. Stop publishing events (pubsub).
        #   3. Best-effort drain of in-flight sandbox turns, *bounded*.
        #   4. Dispose Redis + DB pools (clean FIN to PG, not RST).
        import asyncio

        # 1. Stop new traffic / background loops.
        try:
            from ii_agent.agents.sandboxes.orphan_cleanup import (
                stop_orphan_cleanup,
            )

            stop_orphan_cleanup()
        except Exception:
            pass
        try:
            from ii_agent.agents.sandboxes.executor import (
                shutdown_docker_executor,
            )

            shutdown_docker_executor()
        except Exception:
            pass
        shutdown_scheduler()
        await container.workspace_explorer_service.shutdown()
        await sio_manager.shutdown()

        # 2. Stop event publishing.
        await pubsub.stop()
        logger.info("PubSub stopped")

        # 3. Bounded sandbox drain. Capped at 10s via wait_for so it
        #    cannot consume the entire grace period (historic bug:
        #    asyncio.sleep(10) blocked DB dispose every shutdown).
        if _settings.sandbox.local_mode:

            async def _drain_sandboxes() -> None:
                from ii_agent.agents.sandboxes.docker import DockerSandbox

                running = DockerSandbox.list_sandboxes()
                active = [s for s in running if s["status"] == "running"]
                if active:
                    logger.info(
                        "Graceful shutdown: %d sandbox(es) still running, "
                        "waiting up to 10s for in-flight turns to complete",
                        len(active),
                    )
                    await asyncio.sleep(10)

            try:
                await asyncio.wait_for(_drain_sandboxes(), timeout=10.5)
            except asyncio.TimeoutError:
                logger.warning("Sandbox drain hit 10s deadline; proceeding")
            except Exception as exc:
                logger.debug("Sandbox drain skipped: %s", exc)

        # 4. Tear down infra last so any straggler query above succeeds.
        await shutdown_redis_client()
        await shutdown_engine()
        set_app_container(None)
        logger.info("Database engine disposed")

    return lifespan
