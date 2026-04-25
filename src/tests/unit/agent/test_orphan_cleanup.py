"""Tests for orphan cleanup of Docker sandboxes."""

import asyncio
import contextlib
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ii_agent.agents.sandboxes.orphan_cleanup import (
    _cancel_active_runs_for_session,
    _cleanup_docker_zombies,
    _cleanup_orphaned_volumes,
    _cleanup_orphans,
    _is_pg_unavailable,
    _kill_timed_out_sandboxes,
    _soft_delete_expired_sessions,
    run_orphan_cleanup_loop,
    start_orphan_cleanup,
    stop_orphan_cleanup,
)
from ii_agent.agents.sandboxes.types import SandboxStatus


_MODULE = "ii_agent.agents.sandboxes.orphan_cleanup"


def _make_sandbox_record(
    *,
    sandbox_id=None,
    session_id=None,
    provider="docker",
    status="running",
    provider_sandbox_id="container-abc",
    created_at=None,
    timeout_at=None,
):
    """Create a mock AgentSandbox record."""
    record = MagicMock()
    record.id = sandbox_id or uuid.uuid4()
    record.session_id = session_id or uuid.uuid4()
    record.provider = provider
    record.status = status
    record.provider_sandbox_id = provider_sandbox_id
    record.created_at = created_at or (datetime.now(timezone.utc) - timedelta(hours=1))
    record.timeout_at = timeout_at
    return record


def _mock_db_session(sandbox_result=None, session_result=None, side_effects=None):
    """Create a mock async DB context manager."""
    mock_db = AsyncMock()
    if side_effects:
        mock_db.execute = AsyncMock(side_effect=side_effects)
    elif sandbox_result is not None:
        sb_mock = MagicMock()
        sb_mock.scalars.return_value.all.return_value = sandbox_result
        sess_mock = MagicMock()
        sess_mock.__iter__ = lambda self: iter(session_result or [])
        mock_db.execute = AsyncMock(side_effect=[sb_mock, sess_mock])
    return mock_db


def _patch_db(mock_db):
    """Patch get_db_session_local to return the given mock."""
    ctx = patch(f"{_MODULE}.get_db_session_local")
    mock_get_db = ctx.start()
    mock_get_db.return_value.__aenter__ = AsyncMock(return_value=mock_db)
    mock_get_db.return_value.__aexit__ = AsyncMock(return_value=False)
    return ctx, mock_get_db


# ───────────────────────────── _cleanup_orphans ──────────────────────────────


class TestCleanupOrphansSkipsGracePeriod:
    """Sandboxes within grace period should not be cleaned up."""

    @pytest.mark.asyncio
    async def test_skips_recent_sandbox(self):
        recent = _make_sandbox_record(
            created_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        )
        session_row = MagicMock()
        session_row.id = recent.session_id
        session_row.is_deleted = True

        mock_db = _mock_db_session([recent], [session_row])
        cfg = MagicMock()

        with patch(f"{_MODULE}.get_db_session_local") as mock_get_db:
            mock_get_db.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_get_db.return_value.__aexit__ = AsyncMock(return_value=False)

            cleaned = await _cleanup_orphans(cfg)

        assert cleaned == 0


class TestCleanupOrphansSkipsActiveSessions:
    """Sandboxes with active sessions should not be cleaned up."""

    @pytest.mark.asyncio
    async def test_keeps_sandbox_with_active_session(self):
        sandbox = _make_sandbox_record()
        session_row = MagicMock()
        session_row.id = sandbox.session_id
        session_row.is_deleted = False

        mock_db = _mock_db_session([sandbox], [session_row])
        cfg = MagicMock()

        with patch(f"{_MODULE}.get_db_session_local") as mock_get_db:
            mock_get_db.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_get_db.return_value.__aexit__ = AsyncMock(return_value=False)

            cleaned = await _cleanup_orphans(cfg)

        assert cleaned == 0


class TestCleanupOrphansDeletedSession:
    """Sandboxes whose sessions are deleted should be cleaned up."""

    @pytest.mark.asyncio
    async def test_cleans_up_orphan_with_deleted_session(self):
        sandbox = _make_sandbox_record(provider_sandbox_id="container-orphan")
        session_row = MagicMock()
        session_row.id = sandbox.session_id
        session_row.is_deleted = True

        # Phase 1: read query returns sandbox+session
        phase1_db = _mock_db_session([sandbox], [session_row])
        # Phase 2: per-sandbox DB session for marking DELETED
        phase2_db = AsyncMock()
        phase2_record = MagicMock()
        phase2_record.status = SandboxStatus.RUNNING
        phase2_result = MagicMock()
        phase2_result.scalar_one_or_none.return_value = phase2_record
        phase2_db.execute = AsyncMock(return_value=phase2_result)

        call_count = [0]

        def _get_db_ctx():
            ctx = AsyncMock()
            if call_count[0] == 0:
                ctx.__aenter__ = AsyncMock(return_value=phase1_db)
            else:
                ctx.__aenter__ = AsyncMock(return_value=phase2_db)
            ctx.__aexit__ = AsyncMock(return_value=False)
            call_count[0] += 1
            return ctx

        cfg = MagicMock()

        with (
            patch(f"{_MODULE}.get_db_session_local", side_effect=_get_db_ctx),
            patch(f"{_MODULE}.DockerSandbox") as mock_docker_cls,
        ):
            mock_docker_instance = MagicMock()
            mock_docker_instance.kill = AsyncMock()
            mock_docker_cls.return_value = mock_docker_instance
            mock_docker_cls._get_docker_client.return_value.containers.get.return_value = (
                MagicMock()
            )

            cleaned = await _cleanup_orphans(cfg)

        assert cleaned == 1
        assert phase2_record.status == SandboxStatus.DELETED

    @pytest.mark.asyncio
    async def test_cleans_up_when_session_missing(self):
        """Sandbox should be cleaned up if its session row doesn't exist."""
        sandbox = _make_sandbox_record(provider_sandbox_id="container-no-session")

        phase1_db = _mock_db_session([sandbox], [])

        phase2_db = AsyncMock()
        phase2_record = MagicMock()
        phase2_record.status = SandboxStatus.RUNNING
        phase2_result = MagicMock()
        phase2_result.scalar_one_or_none.return_value = phase2_record
        phase2_db.execute = AsyncMock(return_value=phase2_result)

        call_count = [0]

        def _get_db_ctx():
            ctx = AsyncMock()
            if call_count[0] == 0:
                ctx.__aenter__ = AsyncMock(return_value=phase1_db)
            else:
                ctx.__aenter__ = AsyncMock(return_value=phase2_db)
            ctx.__aexit__ = AsyncMock(return_value=False)
            call_count[0] += 1
            return ctx

        cfg = MagicMock()

        with (
            patch(f"{_MODULE}.get_db_session_local", side_effect=_get_db_ctx),
            patch(f"{_MODULE}.DockerSandbox") as mock_docker_cls,
        ):
            mock_docker_instance = MagicMock()
            mock_docker_instance.kill = AsyncMock()
            mock_docker_cls.return_value = mock_docker_instance
            mock_docker_cls._get_docker_client.return_value.containers.get.return_value = (
                MagicMock()
            )

            cleaned = await _cleanup_orphans(cfg)

        assert cleaned == 1


class TestCleanupOrphansPoolStateInteraction:
    """Pool-state filtering must not protect CLAIMED slots whose session is gone."""

    @pytest.mark.asyncio
    async def test_claimed_slot_with_deleted_session_is_reaped(self):
        """Regression: CLAIMED pool slots whose session was soft-deleted must be reaped.

        Previously ``_cleanup_orphans`` skipped every CLAIMED row unconditionally,
        which leaked sandboxes (and their containers) for hours after the user
        deleted the session.
        """
        from ii_agent.agents.sandboxes.types import PoolState

        sandbox = _make_sandbox_record(provider_sandbox_id="container-claimed-orphan")
        sandbox.pool_state = PoolState.CLAIMED
        session_row = MagicMock()
        session_row.id = sandbox.session_id
        session_row.is_deleted = True

        phase1_db = _mock_db_session([sandbox], [session_row])

        phase2_db = AsyncMock()
        phase2_record = MagicMock()
        phase2_record.status = SandboxStatus.RUNNING
        phase2_result = MagicMock()
        phase2_result.scalar_one_or_none.return_value = phase2_record
        phase2_db.execute = AsyncMock(return_value=phase2_result)

        call_count = [0]

        def _get_db_ctx():
            ctx = AsyncMock()
            if call_count[0] == 0:
                ctx.__aenter__ = AsyncMock(return_value=phase1_db)
            else:
                ctx.__aenter__ = AsyncMock(return_value=phase2_db)
            ctx.__aexit__ = AsyncMock(return_value=False)
            call_count[0] += 1
            return ctx

        cfg = MagicMock()

        with (
            patch(f"{_MODULE}.get_db_session_local", side_effect=_get_db_ctx),
            patch(f"{_MODULE}.DockerSandbox") as mock_docker_cls,
        ):
            mock_docker_instance = MagicMock()
            mock_docker_instance.kill = AsyncMock()
            mock_docker_cls.return_value = mock_docker_instance
            mock_docker_cls._get_docker_client.return_value.containers.get.return_value = (
                MagicMock()
            )

            cleaned = await _cleanup_orphans(cfg)

        assert cleaned == 1
        assert phase2_record.status == SandboxStatus.DELETED

    @pytest.mark.asyncio
    async def test_claimed_slot_with_live_session_is_kept(self):
        """CLAIMED pool slot whose session is alive must NOT be reaped."""
        from ii_agent.agents.sandboxes.types import PoolState

        sandbox = _make_sandbox_record(provider_sandbox_id="container-claimed-live")
        sandbox.pool_state = PoolState.CLAIMED
        session_row = MagicMock()
        session_row.id = sandbox.session_id
        session_row.is_deleted = False

        mock_db = _mock_db_session([sandbox], [session_row])
        cfg = MagicMock()

        with patch(f"{_MODULE}.get_db_session_local") as mock_get_db:
            mock_get_db.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_get_db.return_value.__aexit__ = AsyncMock(return_value=False)

            cleaned = await _cleanup_orphans(cfg)

        assert cleaned == 0

    @pytest.mark.asyncio
    async def test_available_slot_is_never_reaped(self):
        """AVAILABLE pool slots are managed by other phases — never an orphan."""
        from ii_agent.agents.sandboxes.types import PoolState

        sandbox = _make_sandbox_record(provider_sandbox_id="container-available")
        sandbox.pool_state = PoolState.AVAILABLE
        # AVAILABLE rows have no owning session → session row missing.
        mock_db = _mock_db_session([sandbox], [])
        cfg = MagicMock()

        with patch(f"{_MODULE}.get_db_session_local") as mock_get_db:
            mock_get_db.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_get_db.return_value.__aexit__ = AsyncMock(return_value=False)

            cleaned = await _cleanup_orphans(cfg)

        assert cleaned == 0


class TestCleanupOrphansR1ConditionalDelete:
    """R1: Only mark DELETED when container is confirmed removed."""

    @pytest.mark.asyncio
    async def test_defers_on_containers_get_timeout(self):
        """When containers.get() times out, sandbox must NOT be marked DELETED."""
        sandbox = _make_sandbox_record(provider_sandbox_id="container-timeout")
        session_row = MagicMock()
        session_row.id = sandbox.session_id
        session_row.is_deleted = True

        phase1_db = _mock_db_session([sandbox], [session_row])

        cfg = MagicMock()

        with (
            patch(f"{_MODULE}.get_db_session_local") as mock_get_db,
            patch(f"{_MODULE}.DockerSandbox"),
            patch(f"{_MODULE}.asyncio") as mock_asyncio,
        ):
            mock_get_db.return_value.__aenter__ = AsyncMock(return_value=phase1_db)
            mock_get_db.return_value.__aexit__ = AsyncMock(return_value=False)

            # Make containers.get() time out
            mock_asyncio.wait_for = AsyncMock(side_effect=asyncio.TimeoutError())
            mock_asyncio.to_thread = asyncio.to_thread
            mock_asyncio.TimeoutError = asyncio.TimeoutError

            cleaned = await _cleanup_orphans(cfg)

        # Must NOT be marked deleted — deferred to next sweep
        assert cleaned == 0

    @pytest.mark.asyncio
    async def test_defers_on_kill_failure(self):
        """When kill() fails, sandbox must NOT be marked DELETED."""
        sandbox = _make_sandbox_record(provider_sandbox_id="container-kill-fail")
        session_row = MagicMock()
        session_row.id = sandbox.session_id
        session_row.is_deleted = True

        phase1_db = _mock_db_session([sandbox], [session_row])

        cfg = MagicMock()

        with (
            patch(f"{_MODULE}.get_db_session_local") as mock_get_db,
            patch(f"{_MODULE}.DockerSandbox") as mock_docker_cls,
        ):
            mock_get_db.return_value.__aenter__ = AsyncMock(return_value=phase1_db)
            mock_get_db.return_value.__aexit__ = AsyncMock(return_value=False)

            mock_docker_instance = MagicMock()
            mock_docker_instance.kill = AsyncMock(side_effect=Exception("kill failed"))
            mock_docker_cls.return_value = mock_docker_instance
            mock_docker_cls._get_docker_client.return_value.containers.get.return_value = (
                MagicMock()
            )

            cleaned = await _cleanup_orphans(cfg)

        # Must NOT be marked deleted — deferred
        assert cleaned == 0

    @pytest.mark.asyncio
    async def test_marks_deleted_when_container_already_gone(self):
        """When containers.get() raises NotFound, safe to mark DELETED."""
        from docker.errors import NotFound as DockerNotFound

        sandbox = _make_sandbox_record(provider_sandbox_id="container-gone")
        session_row = MagicMock()
        session_row.id = sandbox.session_id
        session_row.is_deleted = True

        phase1_db = _mock_db_session([sandbox], [session_row])

        phase2_db = AsyncMock()
        phase2_record = MagicMock()
        phase2_record.status = SandboxStatus.RUNNING
        phase2_result = MagicMock()
        phase2_result.scalar_one_or_none.return_value = phase2_record
        phase2_db.execute = AsyncMock(return_value=phase2_result)

        call_count = [0]

        def _get_db_ctx():
            ctx = AsyncMock()
            if call_count[0] == 0:
                ctx.__aenter__ = AsyncMock(return_value=phase1_db)
            else:
                ctx.__aenter__ = AsyncMock(return_value=phase2_db)
            ctx.__aexit__ = AsyncMock(return_value=False)
            call_count[0] += 1
            return ctx

        cfg = MagicMock()

        with (
            patch(f"{_MODULE}.get_db_session_local", side_effect=_get_db_ctx),
            patch(f"{_MODULE}.DockerSandbox") as mock_docker_cls,
        ):
            mock_docker_cls.return_value = MagicMock()
            mock_docker_cls._get_docker_client.return_value.containers.get.side_effect = (
                DockerNotFound("gone")
            )

            cleaned = await _cleanup_orphans(cfg)

        assert cleaned == 1
        assert phase2_record.status == SandboxStatus.DELETED


class TestCleanupOrphansR2Isolation:
    """R2: Per-sandbox error isolation — one failure doesn't affect others."""

    @pytest.mark.asyncio
    async def test_continues_on_per_sandbox_error(self):
        """An error on sandbox1 should not prevent sandbox2 cleanup."""
        sandbox1 = _make_sandbox_record(
            sandbox_id=uuid.uuid4(),
            session_id=uuid.uuid4(),
            provider_sandbox_id="container-err",
        )
        sandbox2 = _make_sandbox_record(
            sandbox_id=uuid.uuid4(),
            session_id=uuid.uuid4(),
            provider_sandbox_id="container-ok",
        )

        # Make sandbox1 raise when accessing created_at
        type(sandbox1).created_at = property(
            lambda self: (_ for _ in ()).throw(RuntimeError("broken record"))
        )

        session_row1 = MagicMock()
        session_row1.id = sandbox1.session_id
        session_row1.is_deleted = True
        session_row2 = MagicMock()
        session_row2.id = sandbox2.session_id
        session_row2.is_deleted = True

        phase1_db = _mock_db_session([sandbox1, sandbox2], [session_row1, session_row2])

        phase2_db = AsyncMock()
        phase2_record = MagicMock()
        phase2_record.status = SandboxStatus.RUNNING
        phase2_result = MagicMock()
        phase2_result.scalar_one_or_none.return_value = phase2_record
        phase2_db.execute = AsyncMock(return_value=phase2_result)

        call_count = [0]

        def _get_db_ctx():
            ctx = AsyncMock()
            if call_count[0] == 0:
                ctx.__aenter__ = AsyncMock(return_value=phase1_db)
            else:
                ctx.__aenter__ = AsyncMock(return_value=phase2_db)
            ctx.__aexit__ = AsyncMock(return_value=False)
            call_count[0] += 1
            return ctx

        cfg = MagicMock()

        with (
            patch(f"{_MODULE}.get_db_session_local", side_effect=_get_db_ctx),
            patch(f"{_MODULE}.DockerSandbox") as mock_docker_cls,
        ):
            mock_docker_instance = MagicMock()
            mock_docker_instance.kill = AsyncMock()
            mock_docker_cls.return_value = mock_docker_instance
            mock_docker_cls._get_docker_client.return_value.containers.get.return_value = (
                MagicMock()
            )

            cleaned = await _cleanup_orphans(cfg)

        # sandbox1 errored in phase 1, sandbox2 succeeded
        assert cleaned == 1


class TestCleanupOrphansNoSandboxes:
    """Test that cleanup returns 0 when no sandboxes exist."""

    @pytest.mark.asyncio
    async def test_returns_zero_when_empty(self):
        mock_db = AsyncMock()
        sandbox_result = MagicMock()
        sandbox_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=sandbox_result)

        cfg = MagicMock()

        with patch(f"{_MODULE}.get_db_session_local") as mock_get_db:
            mock_get_db.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_get_db.return_value.__aexit__ = AsyncMock(return_value=False)

            cleaned = await _cleanup_orphans(cfg)

        assert cleaned == 0


# ───────────────────────── start/stop lifecycle ──────────────────────────────


class TestStartStopOrphanCleanup:
    """Tests for start/stop lifecycle."""

    def test_start_returns_none_when_disabled(self):
        cfg = MagicMock()
        cfg.sandbox.local_mode = False
        cfg.sandbox.orphan_cleanup_enabled = True

        result = start_orphan_cleanup(cfg)
        assert result is None

    def test_start_returns_none_when_cleanup_disabled(self):
        cfg = MagicMock()
        cfg.sandbox.local_mode = True
        cfg.sandbox.orphan_cleanup_enabled = False

        result = start_orphan_cleanup(cfg)
        assert result is None

    def test_stop_when_no_task(self):
        stop_orphan_cleanup()


class TestStartOrphanCleanupEnabled:
    """Tests for start_orphan_cleanup when conditions are met."""

    def test_start_creates_task_when_enabled(self):
        import ii_agent.agents.sandboxes.orphan_cleanup as cleanup_mod

        original_task = cleanup_mod._cleanup_task
        cleanup_mod._cleanup_task = None

        cfg = MagicMock()
        cfg.sandbox.local_mode = True
        cfg.sandbox.orphan_cleanup_enabled = True
        cfg.sandbox.orphan_cleanup_interval_seconds = 60

        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(
                asyncio.ensure_future(_start_orphan_in_loop(cfg), loop=loop)
            )
            assert result is not None
            result.cancel()
        finally:
            loop.run_until_complete(asyncio.sleep(0))
            loop.close()
            cleanup_mod._cleanup_task = original_task

    def test_start_returns_existing_task_when_running(self):
        import ii_agent.agents.sandboxes.orphan_cleanup as cleanup_mod

        original_task = cleanup_mod._cleanup_task

        mock_task = MagicMock()
        mock_task.done.return_value = False
        cleanup_mod._cleanup_task = mock_task

        cfg = MagicMock()
        cfg.sandbox.local_mode = True
        cfg.sandbox.orphan_cleanup_enabled = True

        result = start_orphan_cleanup(cfg)

        assert result is mock_task
        cleanup_mod._cleanup_task = original_task


async def _start_orphan_in_loop(cfg):
    """Helper to call start_orphan_cleanup inside an event loop."""
    return start_orphan_cleanup(cfg)


class TestStopOrphanCleanupRunningTask:
    """Test stop_orphan_cleanup cancels a running task."""

    def test_cancels_running_task(self):
        import ii_agent.agents.sandboxes.orphan_cleanup as cleanup_mod

        original_task = cleanup_mod._cleanup_task

        mock_task = MagicMock()
        mock_task.done.return_value = False
        cleanup_mod._cleanup_task = mock_task

        stop_orphan_cleanup()

        mock_task.cancel.assert_called_once()
        assert cleanup_mod._cleanup_task is None

        cleanup_mod._cleanup_task = original_task


# ───────────────────── run_orphan_cleanup_loop ───────────────────────────────


# Every phase invoked inside ``run_orphan_cleanup_loop``.  Used by the
# tests below so we never fall through to real DB / Redis / Docker calls.
_LOOP_PHASES = (
    "_run_host_monitor_phase",
    "_soft_delete_expired_sessions",
    "_retire_pool_sandboxes",
    "_dedupe_pool_slots",
    "_validate_pool_slots",
    "_reap_pool_stuck_init",
    "_health_check_sandbox_rows",
    "_expire_old_paused_sandboxes",
    "_cleanup_orphans",
    "_pause_stale_sandboxes",
    "_cleanup_docker_zombies",
    "_cleanup_orphaned_volumes",
    "_kill_timed_out_sandboxes",
    "_purge_stale_deleted_rows",
    "_ensure_pool_full",
)


def _patch_all_loop_phases(extra: dict | None = None) -> list:
    """Build patch() context managers for every phase the sweep invokes.

    Pass ``extra`` to override individual phases (e.g. inject side_effects).
    Values must be already-constructed ``patch(...)`` objects.
    """
    extra = extra or {}
    patches = []
    for name in _LOOP_PHASES:
        if name in extra:
            patches.append(extra[name])
        else:
            patches.append(patch(f"{_MODULE}.{name}", new_callable=AsyncMock, return_value=0))
    return patches


def _redis_lock_mock(acquired: bool = True):
    """Build a Redis client mock whose SET NX returns ``acquired``."""
    mock_redis = AsyncMock()
    mock_redis.set = AsyncMock(return_value=acquired)
    mock_redis.delete = AsyncMock()
    return mock_redis


class TestRunOrphanCleanupLoop:
    """Tests for run_orphan_cleanup_loop."""

    @pytest.mark.asyncio
    async def test_loop_runs_cleanup_before_sleep(self):
        """R5: Cleanup runs BEFORE sleep, not after."""
        call_order = []

        async def mock_cleanup(cfg):
            call_order.append("cleanup")
            return 0

        async def mock_sleep(seconds):
            call_order.append(f"sleep({seconds})")
            raise asyncio.CancelledError()

        cfg = MagicMock()
        cfg.sandbox.orphan_cleanup_interval_seconds = 42

        loop_patches = _patch_all_loop_phases(
            extra={
                "_cleanup_orphans": patch(f"{_MODULE}._cleanup_orphans", side_effect=mock_cleanup),
            }
        )
        with contextlib.ExitStack() as stack:
            for cm in loop_patches:
                stack.enter_context(cm)
            stack.enter_context(patch(f"{_MODULE}.asyncio.sleep", side_effect=mock_sleep))
            stack.enter_context(
                patch(
                    "ii_agent.core.redis.client.get_redis_client",
                    return_value=_redis_lock_mock(),
                )
            )
            # 5s wedge guard — see TestLoopHandlesPostgresRecovery docstring.
            await asyncio.wait_for(run_orphan_cleanup_loop(cfg), timeout=5.0)

        assert call_order == ["cleanup", "sleep(42)"]

    @pytest.mark.asyncio
    async def test_loop_handles_exception_and_continues(self):
        cfg = MagicMock()
        cfg.sandbox.orphan_cleanup_interval_seconds = 0

        call_count = 0

        async def failing_cleanup(cfg):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("db error")
            if call_count >= 3:
                raise asyncio.CancelledError()
            return 0

        loop_patches = _patch_all_loop_phases(
            extra={
                "_cleanup_orphans": patch(
                    f"{_MODULE}._cleanup_orphans", side_effect=failing_cleanup
                ),
            }
        )
        with contextlib.ExitStack() as stack:
            for cm in loop_patches:
                stack.enter_context(cm)
            stack.enter_context(patch(f"{_MODULE}.asyncio.sleep", new_callable=AsyncMock))
            stack.enter_context(
                patch(
                    "ii_agent.core.redis.client.get_redis_client",
                    return_value=_redis_lock_mock(),
                )
            )
            await asyncio.wait_for(run_orphan_cleanup_loop(cfg), timeout=5.0)

    @pytest.mark.asyncio
    async def test_loop_calls_all_phases(self):
        """Every phase invoked by the sweep must be called at least once."""
        cfg = MagicMock()
        cfg.sandbox.orphan_cleanup_interval_seconds = 0.01

        mocks: dict[str, AsyncMock] = {}
        ctx_managers = []
        for name in _LOOP_PHASES:
            mock = AsyncMock(return_value=0)
            mocks[name] = mock
            ctx_managers.append(patch(f"{_MODULE}.{name}", mock))

        with contextlib.ExitStack() as stack:
            for cm in ctx_managers:
                stack.enter_context(cm)
            stack.enter_context(
                patch(
                    "ii_agent.core.redis.client.get_redis_client",
                    return_value=_redis_lock_mock(),
                )
            )
            task = asyncio.create_task(run_orphan_cleanup_loop(cfg))
            await asyncio.sleep(0.05)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        for name, mock in mocks.items():
            assert mock.call_count >= 1, f"{name} was never invoked"

    @pytest.mark.asyncio
    async def test_loop_skips_sweep_when_lock_not_acquired(self):
        """When another worker holds the Redis advisory lock, the sweep is skipped."""
        cfg = MagicMock()
        cfg.sandbox.orphan_cleanup_interval_seconds = 0

        sleep_calls: list[float] = []

        async def mock_sleep(seconds):
            sleep_calls.append(seconds)
            if len(sleep_calls) >= 2:
                raise asyncio.CancelledError()

        # Cleanup phases — should NOT be called when lock is held by another worker.
        # Track with explicit AsyncMocks so we can assert on call counts.
        phase_mocks: dict[str, AsyncMock] = {
            name: AsyncMock(return_value=0) for name in _LOOP_PHASES
        }
        ctx_managers = [patch(f"{_MODULE}.{n}", m) for n, m in phase_mocks.items()]

        with contextlib.ExitStack() as stack:
            for cm in ctx_managers:
                stack.enter_context(cm)
            stack.enter_context(patch(f"{_MODULE}.asyncio.sleep", side_effect=mock_sleep))
            stack.enter_context(
                patch(
                    "ii_agent.core.redis.client.get_redis_client",
                    return_value=_redis_lock_mock(acquired=False),
                )
            )
            await asyncio.wait_for(run_orphan_cleanup_loop(cfg), timeout=5.0)

        # Loop should have slept (skipped the sweep) at least once
        assert len(sleep_calls) >= 1
        # No phase should have been invoked because the lock was contested
        for name, mock in phase_mocks.items():
            assert mock.call_count == 0, f"{name} ran while another worker held the lock"

    @pytest.mark.asyncio
    async def test_loop_proceeds_when_redis_unavailable(self):
        """If Redis is unavailable the sweep proceeds without the lock."""
        cfg = MagicMock()
        cfg.sandbox.orphan_cleanup_interval_seconds = 0

        async def mock_sleep(seconds):
            raise asyncio.CancelledError()

        cleanup_called = False

        async def mock_cleanup(cfg):
            nonlocal cleanup_called
            cleanup_called = True
            return 0

        loop_patches = _patch_all_loop_phases(
            extra={
                "_cleanup_orphans": patch(f"{_MODULE}._cleanup_orphans", side_effect=mock_cleanup),
            }
        )
        with contextlib.ExitStack() as stack:
            for cm in loop_patches:
                stack.enter_context(cm)
            stack.enter_context(patch(f"{_MODULE}.asyncio.sleep", side_effect=mock_sleep))
            stack.enter_context(
                patch(
                    "ii_agent.core.redis.client.get_redis_client",
                    side_effect=RuntimeError("redis down"),
                )
            )
            await asyncio.wait_for(run_orphan_cleanup_loop(cfg), timeout=5.0)

        assert cleanup_called, "Sweep must proceed when Redis lock is unavailable"

    @pytest.mark.asyncio
    async def test_loop_releases_lock_on_phase_failure(self):
        """The Redis advisory lock must be released even if a phase raises."""
        cfg = MagicMock()
        cfg.sandbox.orphan_cleanup_interval_seconds = 0

        mock_redis = _redis_lock_mock()

        # First sweep: phase raises. Second sweep: phase succeeds, then we
        # cancel via mock_sleep so the loop terminates cleanly.
        call_n = {"phase": 0}

        async def boom_then_ok(*_a, **_kw):
            call_n["phase"] += 1
            if call_n["phase"] == 1:
                raise RuntimeError("phase exploded")
            return 0

        async def mock_sleep(seconds):
            # Cancel on the second sleep call so we observe at least one
            # successful release after the failure.
            if seconds < 60:
                # interval sleep at end of successful sweep — terminate now
                raise asyncio.CancelledError()
            # else: error-path 60s sleep, return immediately to continue

        loop_patches = _patch_all_loop_phases(
            extra={
                "_cleanup_orphans": patch(f"{_MODULE}._cleanup_orphans", side_effect=boom_then_ok),
            }
        )
        with contextlib.ExitStack() as stack:
            for cm in loop_patches:
                stack.enter_context(cm)
            stack.enter_context(patch(f"{_MODULE}.asyncio.sleep", side_effect=mock_sleep))
            stack.enter_context(
                patch(
                    "ii_agent.core.redis.client.get_redis_client",
                    return_value=mock_redis,
                )
            )
            await asyncio.wait_for(run_orphan_cleanup_loop(cfg), timeout=5.0)

        # The lock must have been released at least twice: once after the
        # failing sweep (via the inner finally) and once after the
        # successful sweep that was cancelled.
        assert mock_redis.delete.await_count >= 2


class TestIsPgUnavailable:
    """Regression tests for the PG-recovery classifier used by the
    orphan-cleanup loop (and mirrored in the HTTP middleware).
    """

    def test_direct_cannot_connect_now_is_true(self):
        from asyncpg.exceptions import CannotConnectNowError

        assert _is_pg_unavailable(CannotConnectNowError("recovery"))

    def test_wrapped_via_cause_is_true(self):
        from asyncpg.exceptions import CannotConnectNowError

        try:
            raise CannotConnectNowError("x")
        except CannotConnectNowError as inner:
            try:
                raise RuntimeError("wrapper") from inner
            except RuntimeError as outer:
                assert _is_pg_unavailable(outer)

    def test_unrelated_error_is_false(self):
        assert not _is_pg_unavailable(ValueError("nope"))

    def test_none_safe(self):
        # Defence-in-depth: treat None as not-unavailable rather than crash.
        assert not _is_pg_unavailable(RuntimeError("plain"))


class TestLoopHandlesPostgresRecovery:
    """When PG is in startup-recovery the sweep must log WARNING (not
    ERROR+traceback) and continue polling.  Regression guard for the
    2026-04-25 post-WSL2-hard-kill incident — see
    docs/runtime-docs/postgres-recovery-mode-failures.md.

    Each test wraps ``run_orphan_cleanup_loop`` in ``asyncio.wait_for``
    with a 5-second ceiling.  Without this guard a misbehaving mock
    (e.g. ``CancelledError`` swallowed by an over-broad ``except``,
    or an iteration counter that never trips) wedges the test forever:
    on 2026-04-25 a single such hang consumed 25 GiB RSS and 8.5 hours
    of CPU before being killed manually.  ``wait_for`` makes any
    future regression fail fast and visibly.
    """

    @pytest.mark.asyncio
    async def test_cannot_connect_now_logs_warning_not_exception(self):
        from asyncpg.exceptions import CannotConnectNowError

        cfg = MagicMock()
        cfg.sandbox.orphan_cleanup_interval_seconds = 0

        sleep_calls: list[float] = []
        # After the error-path 60s sleep fires, raise CancelledError
        # so the outer loop's `except asyncio.CancelledError: break`
        # terminates cleanly.  (Raising it from the first sleep would
        # be caught by the `except Exception` handler instead.)
        iteration = {"n": 0}

        async def mock_sleep(seconds):
            sleep_calls.append(seconds)
            iteration["n"] += 1
            if iteration["n"] >= 2:
                raise asyncio.CancelledError()

        # First phase blows up with the recovery error; on the second
        # iteration let it succeed so the outer loop reaches its
        # normal-path ``asyncio.sleep(interval)`` and the cancel fires
        # there (outside the except handler).
        call_n = {"phase": 0}

        async def boom_then_ok(cfg_arg):
            call_n["phase"] += 1
            if call_n["phase"] == 1:
                raise CannotConnectNowError("the database system is in recovery mode")
            return None

        loop_patches = _patch_all_loop_phases(
            extra={
                "_run_host_monitor_phase": patch(
                    f"{_MODULE}._run_host_monitor_phase", side_effect=boom_then_ok
                ),
            }
        )
        with contextlib.ExitStack() as stack:
            for cm in loop_patches:
                stack.enter_context(cm)
            stack.enter_context(patch(f"{_MODULE}.asyncio.sleep", side_effect=mock_sleep))
            stack.enter_context(
                patch(
                    "ii_agent.core.redis.client.get_redis_client",
                    return_value=_redis_lock_mock(),
                )
            )
            mock_logger = stack.enter_context(patch(f"{_MODULE}.logger"))
            # 5s wait_for guard — see class docstring. The test is
            # designed to terminate via mocked CancelledError after 2
            # sleeps; if the mock chain breaks the test must fail fast.
            await asyncio.wait_for(run_orphan_cleanup_loop(cfg), timeout=5.0)

        # Must take the WARNING path, not the .exception() path.
        assert mock_logger.warning.called, "expected WARNING log for PG-recovery"
        assert not mock_logger.exception.called, (
            "ERROR+traceback must NOT fire for CannotConnectNowError"
        )
        # And the loop backed off by 60s before continuing.
        assert 60 in sleep_calls

    @pytest.mark.asyncio
    async def test_real_errors_still_use_exception(self):
        """Non-PG failures must remain loud.  Guards against over-broad
        suppression if someone later widens ``_is_pg_unavailable``.
        """
        cfg = MagicMock()
        cfg.sandbox.orphan_cleanup_interval_seconds = 0
        iteration = {"n": 0}

        async def mock_sleep(seconds):
            iteration["n"] += 1
            if iteration["n"] >= 2:
                raise asyncio.CancelledError()

        call_n = {"phase": 0}

        async def boom_then_ok(cfg_arg):
            call_n["phase"] += 1
            if call_n["phase"] == 1:
                raise ValueError("unrelated bug")
            return None

        loop_patches = _patch_all_loop_phases(
            extra={
                "_run_host_monitor_phase": patch(
                    f"{_MODULE}._run_host_monitor_phase", side_effect=boom_then_ok
                ),
            }
        )
        with contextlib.ExitStack() as stack:
            for cm in loop_patches:
                stack.enter_context(cm)
            stack.enter_context(patch(f"{_MODULE}.asyncio.sleep", side_effect=mock_sleep))
            stack.enter_context(
                patch(
                    "ii_agent.core.redis.client.get_redis_client",
                    return_value=_redis_lock_mock(),
                )
            )
            mock_logger = stack.enter_context(patch(f"{_MODULE}.logger"))
            await asyncio.wait_for(run_orphan_cleanup_loop(cfg), timeout=5.0)

        assert mock_logger.exception.called, "unrelated errors still need traceback"


# ──────────────────── _cleanup_docker_zombies ────────────────────────────────


def _make_docker_container(
    *,
    container_id="abc123deadbeef",
    name="ii-sandbox-abc123deadb",
    sandbox_id="aaaaaaaa-1111-2222-3333-444444444444",
    created="2025-01-01T00:00:00Z",
    labels=None,
):
    """Build a mock Docker container object."""
    c = MagicMock()
    c.id = container_id
    c.name = name
    c.short_id = container_id[:12]
    c.labels = labels or {
        "ii-agent.sandbox": "true",
        "ii-agent.sandbox-id": sandbox_id,
    }
    c.attrs = {"Created": created}
    c.remove = MagicMock()
    return c


class TestCleanupDockerZombiesNoClient:
    @pytest.mark.asyncio
    async def test_returns_zero_on_client_error(self):
        with patch(f"{_MODULE}.DockerSandbox") as mock_cls:
            mock_cls._get_docker_client.side_effect = RuntimeError("no docker")
            result = await _cleanup_docker_zombies()
        assert result == 0


class TestCleanupDockerZombiesNoContainers:
    @pytest.mark.asyncio
    async def test_returns_zero_when_empty(self):
        with patch(f"{_MODULE}.DockerSandbox") as mock_cls:
            mock_cls._get_docker_client.return_value.containers.list.return_value = []
            result = await _cleanup_docker_zombies()
        assert result == 0


class TestCleanupDockerZombiesSkipsTracked:
    @pytest.mark.asyncio
    async def test_skips_container_tracked_in_db(self):
        container = _make_docker_container(container_id="tracked-id-123456")

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.__iter__ = lambda self: iter([("tracked-id-123456",)])
        mock_db.execute = AsyncMock(return_value=mock_result)

        with (
            patch(f"{_MODULE}.DockerSandbox") as mock_cls,
            patch(f"{_MODULE}.get_db_session_local") as mock_get_db,
            patch(f"{_MODULE}.PortPoolManager"),
        ):
            mock_cls._get_docker_client.return_value.containers.list.return_value = [container]
            mock_get_db.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_get_db.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await _cleanup_docker_zombies()

        assert result == 0
        container.remove.assert_not_called()


class TestCleanupDockerZombiesSkipsRecent:
    @pytest.mark.asyncio
    async def test_skips_recently_created_container(self):
        recent_time = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        container = _make_docker_container(container_id="recent-id-123456", created=recent_time)

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.__iter__ = lambda self: iter([])
        mock_db.execute = AsyncMock(return_value=mock_result)

        with (
            patch(f"{_MODULE}.DockerSandbox") as mock_cls,
            patch(f"{_MODULE}.get_db_session_local") as mock_get_db,
            patch(f"{_MODULE}.PortPoolManager"),
        ):
            mock_cls._get_docker_client.return_value.containers.list.return_value = [container]
            mock_get_db.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_get_db.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await _cleanup_docker_zombies()

        assert result == 0
        container.remove.assert_not_called()


class TestCleanupDockerZombiesR4Timeout:
    """R4: Zombie sweep uses 120s timeout instead of 15s."""

    @pytest.mark.asyncio
    async def test_uses_120s_timeout_for_container_list(self):
        with (
            patch(f"{_MODULE}.DockerSandbox") as mock_cls,
            patch(f"{_MODULE}.asyncio") as mock_asyncio,
        ):
            mock_asyncio.wait_for = AsyncMock(side_effect=asyncio.TimeoutError())
            mock_asyncio.to_thread = asyncio.to_thread
            mock_asyncio.TimeoutError = asyncio.TimeoutError
            mock_cls._get_docker_client.return_value = MagicMock()

            result = await _cleanup_docker_zombies()

        assert result == 0
        # Verify the timeout value passed was 120
        call_args = mock_asyncio.wait_for.call_args
        assert call_args[1].get("timeout") == 120 or call_args.kwargs.get("timeout") == 120


class TestCleanupDockerZombiesReapsOrphan:
    @pytest.mark.asyncio
    async def test_removes_zombie_container(self):
        old_time = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        sandbox_id = "deadbeef-1111-2222-3333-444444444444"
        container = _make_docker_container(
            container_id="zombie-id-123456", sandbox_id=sandbox_id, created=old_time
        )

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.__iter__ = lambda self: iter([])
        mock_db.execute = AsyncMock(return_value=mock_result)

        mock_port_manager = MagicMock()

        with (
            patch(f"{_MODULE}.DockerSandbox") as mock_cls,
            patch(f"{_MODULE}.get_db_session_local") as mock_get_db,
            patch(f"{_MODULE}.PortPoolManager") as mock_pm,
            patch(f"{_MODULE}._cleanup_sandbox_volume") as mock_vol,
        ):
            mock_cls._get_docker_client.return_value.containers.list.return_value = [container]
            mock_get_db.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_get_db.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_pm.get_instance.return_value = mock_port_manager

            result = await _cleanup_docker_zombies()

        assert result == 1
        container.remove.assert_called_once_with(force=True)
        mock_vol.assert_called_once()
        mock_port_manager.release_ports.assert_called_once_with(sandbox_id)


class TestCleanupDockerZombiesHandlesNotFound:
    @pytest.mark.asyncio
    async def test_counts_not_found_as_reaped(self):
        from docker.errors import NotFound as DockerNotFound

        old_time = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        container = _make_docker_container(container_id="gone-id-123456", created=old_time)
        container.remove.side_effect = DockerNotFound("already removed")

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.__iter__ = lambda self: iter([])
        mock_db.execute = AsyncMock(return_value=mock_result)

        with (
            patch(f"{_MODULE}.DockerSandbox") as mock_cls,
            patch(f"{_MODULE}.get_db_session_local") as mock_get_db,
            patch(f"{_MODULE}.PortPoolManager") as mock_pm,
            patch(f"{_MODULE}._cleanup_sandbox_volume"),
        ):
            mock_cls._get_docker_client.return_value.containers.list.return_value = [container]
            mock_get_db.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_get_db.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_pm.get_instance.return_value = MagicMock()

            result = await _cleanup_docker_zombies()

        assert result == 1


class TestCleanupDockerZombiesHandlesAPIError:
    @pytest.mark.asyncio
    async def test_continues_on_api_error(self):
        from docker.errors import APIError as DockerAPIError

        old_time = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        container_err = _make_docker_container(
            container_id="err-id-1234567890", name="ii-sandbox-err", created=old_time
        )
        container_err.remove.side_effect = DockerAPIError("permission denied")

        container_ok = _make_docker_container(
            container_id="ok-id-12345678901",
            name="ii-sandbox-ok",
            sandbox_id="bbbbbbbb-1111-2222-3333-444444444444",
            created=old_time,
        )

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.__iter__ = lambda self: iter([])
        mock_db.execute = AsyncMock(return_value=mock_result)

        with (
            patch(f"{_MODULE}.DockerSandbox") as mock_cls,
            patch(f"{_MODULE}.get_db_session_local") as mock_get_db,
            patch(f"{_MODULE}.PortPoolManager") as mock_pm,
            patch(f"{_MODULE}._cleanup_sandbox_volume"),
        ):
            mock_cls._get_docker_client.return_value.containers.list.return_value = [
                container_err,
                container_ok,
            ]
            mock_get_db.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_get_db.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_pm.get_instance.return_value = MagicMock()

            result = await _cleanup_docker_zombies()

        assert result == 1


class TestCleanupDockerZombiesDBFailure:
    @pytest.mark.asyncio
    async def test_returns_zero_on_db_error(self):
        container = _make_docker_container(container_id="zombie-id-1234567")

        with (
            patch(f"{_MODULE}.DockerSandbox") as mock_cls,
            patch(f"{_MODULE}.get_db_session_local") as mock_get_db,
        ):
            mock_cls._get_docker_client.return_value.containers.list.return_value = [container]
            mock_get_db.return_value.__aenter__ = AsyncMock(side_effect=RuntimeError("db down"))
            mock_get_db.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await _cleanup_docker_zombies()

        assert result == 0
        container.remove.assert_not_called()


# ─────────────────── _soft_delete_expired_sessions ───────────────────────────


def _make_session_record(*, session_id=None, is_deleted=False, delete_after=None):
    """Create a mock Session record for expiration tests."""
    record = MagicMock()
    record.id = session_id or uuid.uuid4()
    record.is_deleted = is_deleted
    record.delete_after = delete_after
    return record


class TestSoftDeleteExpiredSessions:
    @pytest.mark.asyncio
    async def test_deletes_expired_session(self):
        expired = _make_session_record(
            delete_after=datetime.now(timezone.utc) - timedelta(hours=1),
        )

        mock_db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [expired]
        mock_db.execute = AsyncMock(return_value=result_mock)

        with (
            patch(f"{_MODULE}.get_db_session_local") as mock_get_db,
            patch(
                f"{_MODULE}._cancel_active_runs_for_session", new_callable=AsyncMock
            ) as mock_cancel,
        ):
            mock_get_db.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_get_db.return_value.__aexit__ = AsyncMock(return_value=False)

            deleted = await _soft_delete_expired_sessions()

        assert deleted == 1
        assert expired.is_deleted is True
        mock_cancel.assert_awaited_once_with(mock_db, expired.id)
        mock_db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_zero_when_none_expired(self):
        mock_db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=result_mock)

        with patch(f"{_MODULE}.get_db_session_local") as mock_get_db:
            mock_get_db.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_get_db.return_value.__aexit__ = AsyncMock(return_value=False)

            deleted = await _soft_delete_expired_sessions()

        assert deleted == 0

    @pytest.mark.asyncio
    async def test_handles_db_error_gracefully(self):
        with patch(f"{_MODULE}.get_db_session_local") as mock_get_db:
            mock_get_db.return_value.__aenter__ = AsyncMock(side_effect=RuntimeError("db down"))
            mock_get_db.return_value.__aexit__ = AsyncMock(return_value=False)

            deleted = await _soft_delete_expired_sessions()

        assert deleted == 0

    @pytest.mark.asyncio
    async def test_deletes_multiple_expired_sessions(self):
        expired1 = _make_session_record(
            delete_after=datetime.now(timezone.utc) - timedelta(hours=2),
        )
        expired2 = _make_session_record(
            delete_after=datetime.now(timezone.utc) - timedelta(minutes=5),
        )

        mock_db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [expired1, expired2]
        mock_db.execute = AsyncMock(return_value=result_mock)

        with (
            patch(f"{_MODULE}.get_db_session_local") as mock_get_db,
            patch(f"{_MODULE}._cancel_active_runs_for_session", new_callable=AsyncMock),
        ):
            mock_get_db.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_get_db.return_value.__aexit__ = AsyncMock(return_value=False)

            deleted = await _soft_delete_expired_sessions()

        assert deleted == 2
        assert expired1.is_deleted is True
        assert expired2.is_deleted is True


class TestCancelActiveRunsForSession:
    @pytest.mark.asyncio
    async def test_cancels_active_run(self):
        session_id = uuid.uuid4()
        task = MagicMock()
        task.id = uuid.uuid4()
        task.status = "running"

        mock_db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [task]
        mock_db.execute = AsyncMock(return_value=result_mock)

        with patch("ii_agent.core.redis.cancel.cancel_run", new_callable=AsyncMock) as mock_cancel:
            await _cancel_active_runs_for_session(mock_db, session_id)

        mock_cancel.assert_awaited_once_with(str(task.id))
        assert task.status == "cancelled"
        assert task.error_message == "Session auto-deleted (timed deletion)"

    @pytest.mark.asyncio
    async def test_no_active_runs(self):
        session_id = uuid.uuid4()
        mock_db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=result_mock)

        await _cancel_active_runs_for_session(mock_db, session_id)

    @pytest.mark.asyncio
    async def test_handles_cancel_failure_gracefully(self):
        session_id = uuid.uuid4()
        task = MagicMock()
        task.id = uuid.uuid4()
        task.status = "running"

        mock_db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [task]
        mock_db.execute = AsyncMock(return_value=result_mock)

        with patch(
            "ii_agent.core.redis.cancel.cancel_run",
            new_callable=AsyncMock,
            side_effect=RuntimeError("redis down"),
        ):
            await _cancel_active_runs_for_session(mock_db, session_id)


# ─────────────────── _cleanup_orphaned_volumes (R9) ─────────────────────────


class TestCleanupOrphanedVolumes:
    """Tests for R9: orphaned volume cleanup."""

    @pytest.mark.asyncio
    async def test_returns_zero_when_no_docker(self):
        with patch(f"{_MODULE}.DockerSandbox") as mock_cls:
            mock_cls._get_docker_client.side_effect = RuntimeError("no docker")
            result = await _cleanup_orphaned_volumes()
        assert result == 0

    @pytest.mark.asyncio
    async def test_returns_zero_when_no_volumes(self):
        with patch(f"{_MODULE}.DockerSandbox") as mock_cls:
            mock_cls._get_docker_client.return_value.volumes.list.return_value = []
            result = await _cleanup_orphaned_volumes()
        assert result == 0

    @pytest.mark.asyncio
    async def test_removes_orphaned_volume(self):
        sandbox_id = "deadbeef-1111-2222-3333-444444444444"
        volume = MagicMock()
        volume.name = f"ii-sandbox-workspace-{sandbox_id}"

        mock_db = AsyncMock()
        # No active sandbox records
        db_result = MagicMock()
        db_result.__iter__ = lambda self: iter([])
        mock_db.execute = AsyncMock(return_value=db_result)

        with (
            patch(f"{_MODULE}.DockerSandbox") as mock_cls,
            patch(f"{_MODULE}.get_db_session_local") as mock_get_db,
        ):
            client = mock_cls._get_docker_client.return_value
            client.volumes.list.return_value = [volume]
            # No containers referencing this volume
            client.containers.list.return_value = []
            mock_get_db.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_get_db.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await _cleanup_orphaned_volumes()

        assert result == 1
        volume.remove.assert_called_once_with(force=True)

    @pytest.mark.asyncio
    async def test_keeps_volume_with_active_record(self):
        sandbox_id = "aaaaaaaa-1111-2222-3333-444444444444"
        volume = MagicMock()
        volume.name = f"ii-sandbox-workspace-{sandbox_id}"

        mock_db = AsyncMock()
        # This sandbox has an active DB record
        db_result = MagicMock()
        db_result.__iter__ = lambda self: iter([(uuid.UUID(sandbox_id),)])
        mock_db.execute = AsyncMock(return_value=db_result)

        with (
            patch(f"{_MODULE}.DockerSandbox") as mock_cls,
            patch(f"{_MODULE}.get_db_session_local") as mock_get_db,
        ):
            client = mock_cls._get_docker_client.return_value
            client.volumes.list.return_value = [volume]
            client.containers.list.return_value = []
            mock_get_db.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_get_db.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await _cleanup_orphaned_volumes()

        assert result == 0
        volume.remove.assert_not_called()

    @pytest.mark.asyncio
    async def test_keeps_volume_with_existing_container(self):
        sandbox_id = "bbbbbbbb-1111-2222-3333-444444444444"
        volume = MagicMock()
        volume.name = f"ii-sandbox-workspace-{sandbox_id}"

        container = MagicMock()
        container.labels = {"ii-agent.sandbox-id": sandbox_id}

        mock_db = AsyncMock()
        db_result = MagicMock()
        db_result.__iter__ = lambda self: iter([])  # No active DB record
        mock_db.execute = AsyncMock(return_value=db_result)

        with (
            patch(f"{_MODULE}.DockerSandbox") as mock_cls,
            patch(f"{_MODULE}.get_db_session_local") as mock_get_db,
        ):
            client = mock_cls._get_docker_client.return_value
            client.volumes.list.return_value = [volume]
            client.containers.list.return_value = [container]  # Container exists
            mock_get_db.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_get_db.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await _cleanup_orphaned_volumes()

        assert result == 0
        volume.remove.assert_not_called()


# ─────────────────── _kill_timed_out_sandboxes (R6) ─────────────────────────


class TestKillTimedOutSandboxes:
    """Tests for R6: persistent timeout enforcement."""

    @pytest.mark.asyncio
    async def test_returns_zero_when_none_timed_out(self):
        mock_db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=result_mock)

        with patch(f"{_MODULE}.get_db_session_local") as mock_get_db:
            mock_get_db.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_get_db.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await _kill_timed_out_sandboxes()

        assert result == 0

    @pytest.mark.asyncio
    async def test_pauses_timed_out_sandbox(self):
        sandbox = _make_sandbox_record(
            provider_sandbox_id="container-timeout",
            timeout_at=datetime.now(timezone.utc) - timedelta(minutes=5),
        )

        # Phase 1 DB: returns the timed-out sandbox
        phase1_db = AsyncMock()
        phase1_result = MagicMock()
        phase1_result.scalars.return_value.all.return_value = [sandbox]
        phase1_db.execute = AsyncMock(return_value=phase1_result)

        # Phase 2 DB: for updating the record
        phase2_db = AsyncMock()
        phase2_record = MagicMock()
        phase2_record.status = SandboxStatus.RUNNING
        phase2_result = MagicMock()
        phase2_result.scalar_one_or_none.return_value = phase2_record
        phase2_db.execute = AsyncMock(return_value=phase2_result)

        call_count = [0]

        def _get_db_ctx():
            ctx = AsyncMock()
            if call_count[0] == 0:
                ctx.__aenter__ = AsyncMock(return_value=phase1_db)
            else:
                ctx.__aenter__ = AsyncMock(return_value=phase2_db)
            ctx.__aexit__ = AsyncMock(return_value=False)
            call_count[0] += 1
            return ctx

        mock_container = MagicMock()

        with (
            patch(f"{_MODULE}.get_db_session_local", side_effect=_get_db_ctx),
            patch(f"{_MODULE}.DockerSandbox") as mock_docker_cls,
        ):
            mock_docker_cls._get_docker_client.return_value.containers.get.return_value = (
                mock_container
            )

            result = await _kill_timed_out_sandboxes()

        assert result == 1
        assert phase2_record.status == SandboxStatus.PAUSED
        assert phase2_record.timeout_at is None

    @pytest.mark.asyncio
    async def test_handles_missing_container_gracefully(self):
        """When container is NotFound, still clear timeout and mark paused."""
        from docker.errors import NotFound as DockerNotFound

        sandbox = _make_sandbox_record(
            provider_sandbox_id="container-gone",
            timeout_at=datetime.now(timezone.utc) - timedelta(minutes=5),
        )

        phase1_db = AsyncMock()
        phase1_result = MagicMock()
        phase1_result.scalars.return_value.all.return_value = [sandbox]
        phase1_db.execute = AsyncMock(return_value=phase1_result)

        phase2_db = AsyncMock()
        phase2_record = MagicMock()
        phase2_record.status = SandboxStatus.RUNNING
        phase2_result = MagicMock()
        phase2_result.scalar_one_or_none.return_value = phase2_record
        phase2_db.execute = AsyncMock(return_value=phase2_result)

        call_count = [0]

        def _get_db_ctx():
            ctx = AsyncMock()
            if call_count[0] == 0:
                ctx.__aenter__ = AsyncMock(return_value=phase1_db)
            else:
                ctx.__aenter__ = AsyncMock(return_value=phase2_db)
            ctx.__aexit__ = AsyncMock(return_value=False)
            call_count[0] += 1
            return ctx

        with (
            patch(f"{_MODULE}.get_db_session_local", side_effect=_get_db_ctx),
            patch(f"{_MODULE}.DockerSandbox") as mock_docker_cls,
        ):
            mock_docker_cls._get_docker_client.return_value.containers.get.side_effect = (
                DockerNotFound("gone")
            )

            result = await _kill_timed_out_sandboxes()

        # Container gone = already stopped, should still mark paused + clear timeout
        assert result == 1
