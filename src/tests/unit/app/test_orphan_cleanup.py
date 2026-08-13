"""Unit tests for app/lifespan.py — _cleanup_orphaned_tasks."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ii_agent.app.lifespan import _cleanup_orphaned_tasks
from ii_agent.tasks.schemas import RunTaskResponse
from ii_agent.tasks.types import RunStatus, TaskType

pytestmark = pytest.mark.unit

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SESSION_A = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")
SESSION_B = uuid.UUID("bbbbbbbb-0000-0000-0000-000000000002")
TASK_A = uuid.UUID("cccccccc-0000-0000-0000-000000000003")
TASK_B = uuid.UUID("dddddddd-0000-0000-0000-000000000004")
NOW = datetime.now(timezone.utc)


def _task_response(
    task_id: uuid.UUID,
    session_id: uuid.UUID,
    status: RunStatus,
) -> RunTaskResponse:
    return RunTaskResponse(
        id=task_id,
        session_id=session_id,
        task_type=TaskType.AGENT_RUN,
        status=status,
        created_at=NOW,
        updated_at=NOW,
    )


def _make_container(
    running_session_ids: list[str],
    tasks_by_session: dict[uuid.UUID, RunTaskResponse | None],
):
    """Build a mock container with a configured run_task_service."""
    svc = AsyncMock()
    svc.get_all_running_session_ids.return_value = running_session_ids
    svc.get_last_by_session_id.side_effect = lambda db, sid: tasks_by_session.get(sid)
    svc.transition_status.return_value = None
    container = SimpleNamespace(run_task_service=svc)
    return container, svc


def _mock_db_ctx():
    """Create a mock for get_db_session_local() context manager."""
    mock_db = AsyncMock()
    # Mock the execute result for the session reset query
    mock_result = MagicMock()
    mock_result.rowcount = 0
    mock_db.execute.return_value = mock_result
    return mock_db


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCleanupOrphanedTasksNoop:
    @pytest.mark.asyncio
    async def test_does_nothing_when_no_running_sessions(self):
        container, svc = _make_container(running_session_ids=[], tasks_by_session={})

        with patch("ii_agent.app.lifespan.get_db_session_local") as db_ctx:
            mock_db = _mock_db_ctx()
            db_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            db_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            await _cleanup_orphaned_tasks(container)

        svc.transition_status.assert_not_awaited()
        mock_db.commit.assert_not_awaited()


class TestCleanupOrphanedTasksRunning:
    @pytest.mark.asyncio
    async def test_cancels_running_task(self):
        task = _task_response(TASK_A, SESSION_A, RunStatus.RUNNING)
        container, svc = _make_container(
            running_session_ids=[str(SESSION_A)],
            tasks_by_session={SESSION_A: task},
        )

        with patch("ii_agent.app.lifespan.get_db_session_local") as db_ctx:
            mock_db = _mock_db_ctx()
            db_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            db_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            await _cleanup_orphaned_tasks(container)

        svc.transition_status.assert_awaited_once()
        call_kwargs = svc.transition_status.call_args.kwargs
        assert call_kwargs["task_id"] == TASK_A
        assert call_kwargs["to_status"] == RunStatus.CANCELLED
        assert "orphaned" in call_kwargs["error_message"]
        mock_db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_cancels_aborting_task(self):
        task = _task_response(TASK_A, SESSION_A, RunStatus.ABORTING)
        container, svc = _make_container(
            running_session_ids=[str(SESSION_A)],
            tasks_by_session={SESSION_A: task},
        )

        with patch("ii_agent.app.lifespan.get_db_session_local") as db_ctx:
            mock_db = _mock_db_ctx()
            db_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            db_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            await _cleanup_orphaned_tasks(container)

        svc.transition_status.assert_awaited_once()
        assert svc.transition_status.call_args.kwargs["to_status"] == RunStatus.CANCELLED


class TestCleanupOrphanedTasksMultiple:
    @pytest.mark.asyncio
    async def test_cancels_multiple_sessions(self):
        task_a = _task_response(TASK_A, SESSION_A, RunStatus.RUNNING)
        task_b = _task_response(TASK_B, SESSION_B, RunStatus.ABORTING)
        container, svc = _make_container(
            running_session_ids=[str(SESSION_A), str(SESSION_B)],
            tasks_by_session={SESSION_A: task_a, SESSION_B: task_b},
        )

        with patch("ii_agent.app.lifespan.get_db_session_local") as db_ctx:
            mock_db = _mock_db_ctx()
            db_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            db_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            await _cleanup_orphaned_tasks(container)

        assert svc.transition_status.await_count == 2


class TestCleanupOrphanedTasksSkipsCompleted:
    @pytest.mark.asyncio
    async def test_skips_completed_task(self):
        task = _task_response(TASK_A, SESSION_A, RunStatus.COMPLETED)
        container, svc = _make_container(
            running_session_ids=[str(SESSION_A)],
            tasks_by_session={SESSION_A: task},
        )

        with patch("ii_agent.app.lifespan.get_db_session_local") as db_ctx:
            mock_db = _mock_db_ctx()
            db_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            db_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            await _cleanup_orphaned_tasks(container)

        svc.transition_status.assert_not_awaited()


class TestCleanupOrphanedTasksNoTask:
    @pytest.mark.asyncio
    async def test_handles_session_with_no_last_task(self):
        container, svc = _make_container(
            running_session_ids=[str(SESSION_A)],
            tasks_by_session={SESSION_A: None},
        )

        with patch("ii_agent.app.lifespan.get_db_session_local") as db_ctx:
            mock_db = _mock_db_ctx()
            db_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            db_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            await _cleanup_orphaned_tasks(container)

        svc.transition_status.assert_not_awaited()


class TestCleanupOrphanedTasksSessionReset:
    @pytest.mark.asyncio
    async def test_resets_pending_sessions_to_active(self):
        container, svc = _make_container(
            running_session_ids=[str(SESSION_A)],
            tasks_by_session={SESSION_A: _task_response(TASK_A, SESSION_A, RunStatus.RUNNING)},
        )

        with patch("ii_agent.app.lifespan.get_db_session_local") as db_ctx:
            mock_db = _mock_db_ctx()
            mock_result = MagicMock()
            mock_result.rowcount = 3
            mock_db.execute.return_value = mock_result
            db_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            db_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            await _cleanup_orphaned_tasks(container)

        mock_db.execute.assert_awaited()
        mock_db.commit.assert_awaited_once()
