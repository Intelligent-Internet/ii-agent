"""Tests for orphan cleanup of Docker sandboxes."""

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ii_agent.agents.sandboxes.orphan_cleanup import (
    _cancel_active_runs_for_session,
    _cleanup_docker_zombies,
    _cleanup_orphans,
    _soft_delete_expired_sessions,
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

        with (
            patch(
                "ii_agent.agents.sandboxes.orphan_cleanup._soft_delete_expired_sessions",
                new_callable=AsyncMock,
                return_value=0,
            ),
            patch(
                "ii_agent.agents.sandboxes.orphan_cleanup._cleanup_orphans",
                new_callable=AsyncMock,
                return_value=0,
            ) as mock_cleanup,
            patch(
                "ii_agent.agents.sandboxes.orphan_cleanup._pause_stale_sandboxes",
                new_callable=AsyncMock,
                return_value=0,
            ),
            patch(
                "ii_agent.agents.sandboxes.orphan_cleanup._cleanup_docker_zombies",
                new_callable=AsyncMock,
                return_value=0,
            ),
        ):
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
                "ii_agent.agents.sandboxes.orphan_cleanup._soft_delete_expired_sessions",
                new_callable=AsyncMock,
                return_value=0,
            ),
            patch(
                "ii_agent.agents.sandboxes.orphan_cleanup._cleanup_orphans",
                side_effect=failing_cleanup,
            ),
            patch(
                "ii_agent.agents.sandboxes.orphan_cleanup._pause_stale_sandboxes",
                new_callable=AsyncMock,
                return_value=0,
            ),
            patch(
                "ii_agent.agents.sandboxes.orphan_cleanup._cleanup_docker_zombies",
                new_callable=AsyncMock,
                return_value=0,
            ),
            patch(
                "ii_agent.agents.sandboxes.orphan_cleanup.asyncio.sleep",
                new_callable=AsyncMock,
            ),
        ):
            await run_orphan_cleanup_loop(cfg)


# ---------------------------------------------------------------------------
# _cleanup_docker_zombies tests
# ---------------------------------------------------------------------------

_MODULE = "ii_agent.agents.sandboxes.orphan_cleanup"


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
    """Returns 0 when Docker client is unavailable."""

    @pytest.mark.asyncio
    async def test_returns_zero_on_client_error(self):
        with patch(f"{_MODULE}.DockerSandbox") as mock_cls:
            mock_cls._get_docker_client.side_effect = RuntimeError("no docker")
            result = await _cleanup_docker_zombies()
        assert result == 0


class TestCleanupDockerZombiesNoContainers:
    """Returns 0 when no sandbox containers exist in Docker."""

    @pytest.mark.asyncio
    async def test_returns_zero_when_empty(self):
        with patch(f"{_MODULE}.DockerSandbox") as mock_cls:
            mock_cls._get_docker_client.return_value.containers.list.return_value = []
            result = await _cleanup_docker_zombies()
        assert result == 0


class TestCleanupDockerZombiesSkipsTracked:
    """Containers with active DB records are left alone."""

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
    """Containers within the grace period are skipped."""

    @pytest.mark.asyncio
    async def test_skips_recently_created_container(self):
        # Created 1 minute ago — within the 5-minute grace period
        recent_time = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        container = _make_docker_container(
            container_id="recent-id-123456",
            created=recent_time,
        )

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.__iter__ = lambda self: iter([])  # No active DB records
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


class TestCleanupDockerZombiesReapsOrphan:
    """Removes containers not tracked in DB and past grace period."""

    @pytest.mark.asyncio
    async def test_removes_zombie_container(self):
        old_time = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        sandbox_id = "deadbeef-1111-2222-3333-444444444444"
        container = _make_docker_container(
            container_id="zombie-id-123456",
            sandbox_id=sandbox_id,
            created=old_time,
        )

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.__iter__ = lambda self: iter([])  # No active DB records
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
    """Container already gone (NotFound) counts as reaped."""

    @pytest.mark.asyncio
    async def test_counts_not_found_as_reaped(self):
        from docker.errors import NotFound as DockerNotFound

        old_time = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        container = _make_docker_container(
            container_id="gone-id-123456",
            created=old_time,
        )
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
    """APIError on remove skips that container but continues."""

    @pytest.mark.asyncio
    async def test_continues_on_api_error(self):
        from docker.errors import APIError as DockerAPIError

        old_time = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        container_err = _make_docker_container(
            container_id="err-id-1234567890",
            name="ii-sandbox-err",
            created=old_time,
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

        # container_err failed, container_ok succeeded
        assert result == 1


class TestCleanupDockerZombiesDBFailure:
    """Returns 0 when the DB query fails."""

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


# ---------------------------------------------------------------------------
# _soft_delete_expired_sessions tests
# ---------------------------------------------------------------------------


def _make_session_record(
    *,
    session_id=None,
    is_deleted=False,
    delete_after=None,
):
    """Create a mock Session record for expiration tests."""
    record = MagicMock()
    record.id = session_id or uuid.uuid4()
    record.is_deleted = is_deleted
    record.delete_after = delete_after
    return record


class TestSoftDeleteExpiredSessions:
    """Tests for timed session deletion via delete_after."""

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
    """Tests for _cancel_active_runs_for_session."""

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

        # Should not raise
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
            # Should not raise
            await _cancel_active_runs_for_session(mock_db, session_id)
