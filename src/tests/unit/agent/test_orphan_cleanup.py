"""Tests for orphan cleanup of Docker sandboxes."""

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ii_agent.agents.sandboxes.orphan_cleanup import (
    _cleanup_orphans,
    start_orphan_cleanup,
    stop_orphan_cleanup,
)
from ii_agent.agents.sandboxes.types import SandboxStatus


def _make_sandbox_record(
    *,
    sandbox_id=None,
    session_id=None,
    provider="docker",
    status="running",
    provider_sandbox_id="container-abc",
    created_at=None,
):
    """Create a mock AgentSandbox record."""
    record = MagicMock()
    record.id = sandbox_id or uuid.uuid4()
    record.session_id = session_id or uuid.uuid4()
    record.provider = provider
    record.status = status
    record.provider_sandbox_id = provider_sandbox_id
    record.created_at = created_at or (datetime.now(timezone.utc) - timedelta(hours=1))
    return record


class TestCleanupOrphansSkipsGracePeriod:
    """Sandboxes within grace period should not be cleaned up."""

    @pytest.mark.asyncio
    async def test_skips_recent_sandbox(self):
        recent = _make_sandbox_record(
            created_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        )
        session_row = MagicMock()
        session_row.id = recent.session_id
        session_row.is_deleted = True  # Session deleted, but sandbox is too new

        mock_db = AsyncMock()
        sandbox_result = MagicMock()
        sandbox_result.scalars.return_value.all.return_value = [recent]
        session_result = MagicMock()
        session_result.__iter__ = lambda self: iter([session_row])
        mock_db.execute = AsyncMock(side_effect=[sandbox_result, session_result])

        cfg = MagicMock()
        cfg.sandbox.orphan_cleanup_interval_seconds = 60

        with patch("ii_agent.agents.sandboxes.orphan_cleanup.get_db_session_local") as mock_get_db:
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
        session_row.is_deleted = False  # Session is active

        mock_db = AsyncMock()
        sandbox_result = MagicMock()
        sandbox_result.scalars.return_value.all.return_value = [sandbox]
        session_result = MagicMock()
        session_result.__iter__ = lambda self: iter([session_row])
        mock_db.execute = AsyncMock(side_effect=[sandbox_result, session_result])

        cfg = MagicMock()

        with patch("ii_agent.agents.sandboxes.orphan_cleanup.get_db_session_local") as mock_get_db:
            mock_get_db.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_get_db.return_value.__aexit__ = AsyncMock(return_value=False)

            cleaned = await _cleanup_orphans(cfg)

        assert cleaned == 0


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
        # Should not raise
        stop_orphan_cleanup()


class TestCleanupOrphansDeletedSession:
    """Sandboxes whose sessions are deleted should be cleaned up."""

    @pytest.mark.asyncio
    async def test_cleans_up_orphan_with_deleted_session(self):
        sandbox = _make_sandbox_record(
            provider_sandbox_id="container-orphan",
        )
        session_row = MagicMock()
        session_row.id = sandbox.session_id
        session_row.is_deleted = True

        mock_db = AsyncMock()
        sandbox_result = MagicMock()
        sandbox_result.scalars.return_value.all.return_value = [sandbox]
        session_result = MagicMock()
        session_result.__iter__ = lambda self: iter([session_row])
        mock_db.execute = AsyncMock(side_effect=[sandbox_result, session_result])

        cfg = MagicMock()

        with (
            patch("ii_agent.agents.sandboxes.orphan_cleanup.get_db_session_local") as mock_get_db,
            patch("ii_agent.agents.sandboxes.orphan_cleanup.DockerSandbox") as mock_docker_cls,
        ):
            mock_get_db.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_get_db.return_value.__aexit__ = AsyncMock(return_value=False)

            mock_docker_instance = MagicMock()
            mock_docker_instance.kill = AsyncMock()
            mock_docker_cls.return_value = mock_docker_instance
            mock_docker_cls._get_docker_client.return_value.containers.get.return_value = (
                MagicMock()
            )

            cleaned = await _cleanup_orphans(cfg)

        assert cleaned == 1
        assert sandbox.status == SandboxStatus.DELETED

    @pytest.mark.asyncio
    async def test_cleans_up_when_session_missing(self):
        """Sandbox should be cleaned up if its session row doesn't exist."""
        sandbox = _make_sandbox_record(
            provider_sandbox_id="container-no-session",
        )

        mock_db = AsyncMock()
        sandbox_result = MagicMock()
        sandbox_result.scalars.return_value.all.return_value = [sandbox]
        # Empty session result — session row doesn't exist
        session_result = MagicMock()
        session_result.__iter__ = lambda self: iter([])
        mock_db.execute = AsyncMock(side_effect=[sandbox_result, session_result])

        cfg = MagicMock()

        with (
            patch("ii_agent.agents.sandboxes.orphan_cleanup.get_db_session_local") as mock_get_db,
            patch("ii_agent.agents.sandboxes.orphan_cleanup.DockerSandbox") as mock_docker_cls,
        ):
            mock_get_db.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_get_db.return_value.__aexit__ = AsyncMock(return_value=False)

            mock_docker_instance = MagicMock()
            mock_docker_instance.kill = AsyncMock()
            mock_docker_cls.return_value = mock_docker_instance
            mock_docker_cls._get_docker_client.return_value.containers.get.return_value = (
                MagicMock()
            )

            cleaned = await _cleanup_orphans(cfg)

        assert cleaned == 1


class TestStartOrphanCleanupEnabled:
    """Tests for start_orphan_cleanup when conditions are met."""

    def test_start_creates_task_when_enabled(self):
        import ii_agent.agents.sandboxes.orphan_cleanup as cleanup_mod

        # Reset global
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
            # Cancel the task so it doesn't keep running
            result.cancel()
        finally:
            loop.run_until_complete(asyncio.sleep(0))
            loop.close()
            cleanup_mod._cleanup_task = original_task

    def test_start_returns_existing_task_when_running(self):
        import ii_agent.agents.sandboxes.orphan_cleanup as cleanup_mod

        original_task = cleanup_mod._cleanup_task

        # Simulate an already-running task
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


class TestCleanupOrphansNoSandboxes:
    """Test that cleanup returns 0 when no sandboxes exist."""

    @pytest.mark.asyncio
    async def test_returns_zero_when_empty(self):
        mock_db = AsyncMock()
        sandbox_result = MagicMock()
        sandbox_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=sandbox_result)

        cfg = MagicMock()

        with patch("ii_agent.agents.sandboxes.orphan_cleanup.get_db_session_local") as mock_get_db:
            mock_get_db.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_get_db.return_value.__aexit__ = AsyncMock(return_value=False)

            cleaned = await _cleanup_orphans(cfg)

        assert cleaned == 0


class TestCleanupOrphansKillFailure:
    """Test cleanup when container kill fails."""

    @pytest.mark.asyncio
    async def test_continues_on_kill_failure(self):
        sandbox = _make_sandbox_record(
            provider_sandbox_id="container-kill-fail",
        )
        session_row = MagicMock()
        session_row.id = sandbox.session_id
        session_row.is_deleted = True

        mock_db = AsyncMock()
        sandbox_result = MagicMock()
        sandbox_result.scalars.return_value.all.return_value = [sandbox]
        session_result = MagicMock()
        session_result.__iter__ = lambda self: iter([session_row])
        mock_db.execute = AsyncMock(side_effect=[sandbox_result, session_result])

        cfg = MagicMock()

        with (
            patch("ii_agent.agents.sandboxes.orphan_cleanup.get_db_session_local") as mock_get_db,
            patch("ii_agent.agents.sandboxes.orphan_cleanup.DockerSandbox") as mock_docker_cls,
        ):
            mock_get_db.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_get_db.return_value.__aexit__ = AsyncMock(return_value=False)

            mock_docker_instance = MagicMock()
            mock_docker_instance.kill = AsyncMock(side_effect=Exception("kill failed"))
            mock_docker_cls.return_value = mock_docker_instance
            mock_docker_cls._get_docker_client.return_value.containers.get.return_value = (
                MagicMock()
            )

            cleaned = await _cleanup_orphans(cfg)

        # Should still mark as deleted despite kill failure
        assert cleaned == 1
        assert sandbox.status == SandboxStatus.DELETED


class TestCleanupOrphansSandboxProcessingError:
    """Test cleanup when per-sandbox processing raises an unexpected error."""

    @pytest.mark.asyncio
    async def test_continues_on_per_sandbox_error(self):
        """Cleanup continues processing remaining sandboxes on per-record error."""
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

        mock_db = AsyncMock()
        sandbox_result = MagicMock()
        sandbox_result.scalars.return_value.all.return_value = [sandbox1, sandbox2]
        session_result = MagicMock()
        session_result.__iter__ = lambda self: iter([session_row1, session_row2])
        mock_db.execute = AsyncMock(side_effect=[sandbox_result, session_result])

        cfg = MagicMock()

        with (
            patch("ii_agent.agents.sandboxes.orphan_cleanup.get_db_session_local") as mock_get_db,
            patch("ii_agent.agents.sandboxes.orphan_cleanup.DockerSandbox") as mock_docker_cls,
        ):
            mock_get_db.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_get_db.return_value.__aexit__ = AsyncMock(return_value=False)

            mock_docker_instance = MagicMock()
            mock_docker_instance.kill = AsyncMock()
            mock_docker_cls.return_value = mock_docker_instance
            mock_docker_cls._get_docker_client.return_value.containers.get.return_value = (
                MagicMock()
            )

            cleaned = await _cleanup_orphans(cfg)

        # sandbox1 errored, sandbox2 succeeded
        assert cleaned == 1


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

        # Restore
        cleanup_mod._cleanup_task = original_task


class TestRunOrphanCleanupLoop:
    """Tests for run_orphan_cleanup_loop."""

    @pytest.mark.asyncio
    async def test_loop_runs_and_can_be_cancelled(self):
        from ii_agent.agents.sandboxes.orphan_cleanup import run_orphan_cleanup_loop

        cfg = MagicMock()
        cfg.sandbox.orphan_cleanup_interval_seconds = 0.01

        with patch(
            "ii_agent.agents.sandboxes.orphan_cleanup._cleanup_orphans",
            new_callable=AsyncMock,
            return_value=0,
        ) as mock_cleanup:
            task = asyncio.create_task(run_orphan_cleanup_loop(cfg))
            await asyncio.sleep(0.05)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

            assert mock_cleanup.call_count >= 1

    @pytest.mark.asyncio
    async def test_loop_handles_exception_and_continues(self):
        from ii_agent.agents.sandboxes.orphan_cleanup import run_orphan_cleanup_loop

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

        with (
            patch(
                "ii_agent.agents.sandboxes.orphan_cleanup._cleanup_orphans",
                side_effect=failing_cleanup,
            ),
            patch(
                "ii_agent.agents.sandboxes.orphan_cleanup.asyncio.sleep",
                new_callable=AsyncMock,
            ),
        ):
            await run_orphan_cleanup_loop(cfg)
