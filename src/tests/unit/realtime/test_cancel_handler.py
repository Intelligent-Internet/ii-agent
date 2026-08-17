"""Unit tests for realtime/handlers/cancel.py."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from ii_agent.realtime.handlers.cancel import CancelHandler
from ii_agent.realtime.schemas import CancelContent
from ii_agent.sessions.schemas import SessionInfo
from ii_agent.sessions.types import SessionState
from ii_agent.tasks.types import RunStatus

pytestmark = pytest.mark.unit

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SESSION_ID = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")
USER_ID = uuid.UUID("bbbbbbbb-0000-0000-0000-000000000002")
TASK_ID = uuid.UUID("cccccccc-0000-0000-0000-000000000003")


def _session() -> SessionInfo:
    return SessionInfo(
        id=SESSION_ID,
        user_id=USER_ID,
        status=SessionState.ACTIVE,
        workspace_dir="/workspace",
        is_public=False,
        created_at="2025-01-01T00:00:00Z",
    )


def _make_task(status: RunStatus, task_id: uuid.UUID = TASK_ID):
    return SimpleNamespace(id=task_id, status=status)


def _cancel_content() -> CancelContent:
    return CancelContent()


def _build_handler(
    run_task_service: AsyncMock | None = None,
) -> tuple[CancelHandler, AsyncMock, AsyncMock]:
    """Build a CancelHandler with mocked pubsub and container."""
    mock_pubsub = AsyncMock()
    mock_container = SimpleNamespace(
        run_task_service=run_task_service or AsyncMock(),
    )
    handler = CancelHandler(pubsub=mock_pubsub, container=mock_container)
    return handler, mock_pubsub, mock_container.run_task_service


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCancelHandlerNoTask:
    @pytest.mark.asyncio
    async def test_sends_error_when_no_task_found(self):
        svc = AsyncMock()
        svc.get_last_by_session_id.return_value = None
        handler, pubsub, _ = _build_handler(svc)

        with patch("ii_agent.realtime.handlers.cancel.get_db_session_local") as mock_db:
            mock_db.return_value.__aenter__ = AsyncMock(return_value=AsyncMock())
            mock_db.return_value.__aexit__ = AsyncMock(return_value=False)
            await handler.handle(_cancel_content(), _session())

        # Should have published an error event
        pubsub.publish.assert_awaited_once()
        event = pubsub.publish.call_args[0][0]
        assert event.name == "system.error"


class TestCancelHandlerRunning:
    @pytest.mark.asyncio
    async def test_transitions_to_aborting_and_signals_cancel(self):
        svc = AsyncMock()
        svc.get_last_by_session_id.return_value = _make_task(RunStatus.RUNNING)
        svc.transition_status.return_value = None
        handler, pubsub, _ = _build_handler(svc)

        mock_db = AsyncMock()

        with (
            patch("ii_agent.realtime.handlers.cancel.get_db_session_local") as db_ctx,
            patch("ii_agent.realtime.handlers.cancel.cancel") as mock_cancel,
        ):
            db_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            db_ctx.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_cancel.cancel_run = AsyncMock(return_value=True)

            await handler.handle(_cancel_content(), _session())

        svc.transition_status.assert_awaited_once()
        call_kwargs = svc.transition_status.call_args
        assert call_kwargs.kwargs["to_status"] == RunStatus.ABORTING
        mock_cancel.cancel_run.assert_awaited_once_with(str(TASK_ID))


class TestCancelHandlerOrphanedRun:
    @pytest.mark.asyncio
    async def test_force_cancels_when_run_not_in_cancel_manager(self):
        """When cancel_run returns False (agent gone), force-cancel the task."""
        svc = AsyncMock()
        svc.get_last_by_session_id.return_value = _make_task(RunStatus.RUNNING)
        svc.transition_status.return_value = None
        handler, pubsub, _ = _build_handler(svc)

        mock_db = AsyncMock()
        call_count = {"db_ctx": 0}

        async def _aenter(self_):
            call_count["db_ctx"] += 1
            return mock_db

        with (
            patch("ii_agent.realtime.handlers.cancel.get_db_session_local") as db_ctx,
            patch("ii_agent.realtime.handlers.cancel.cancel") as mock_cancel,
        ):
            db_ctx.return_value.__aenter__ = _aenter
            db_ctx.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_cancel.cancel_run = AsyncMock(return_value=False)

            await handler.handle(_cancel_content(), _session())

        # Should have called transition_status twice: once for ABORTING, once for CANCELLED
        assert svc.transition_status.await_count == 2
        second_call = svc.transition_status.await_args_list[1]
        assert second_call.kwargs["to_status"] == RunStatus.CANCELLED

        # Should have sent an interrupted event
        assert pubsub.publish.await_count >= 1


class TestCancelHandlerAlreadyAborting:
    @pytest.mark.asyncio
    async def test_resignals_if_agent_still_active(self):
        svc = AsyncMock()
        svc.get_last_by_session_id.return_value = _make_task(RunStatus.ABORTING)
        handler, pubsub, _ = _build_handler(svc)

        with (
            patch("ii_agent.realtime.handlers.cancel.get_db_session_local") as db_ctx,
            patch("ii_agent.realtime.handlers.cancel.cancel") as mock_cancel,
        ):
            db_ctx.return_value.__aenter__ = AsyncMock(return_value=AsyncMock())
            db_ctx.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_cancel.get_active_runs = AsyncMock(return_value={str(TASK_ID)})
            mock_cancel.cancel_run = AsyncMock(return_value=True)

            await handler.handle(_cancel_content(), _session())

        mock_cancel.cancel_run.assert_awaited_once_with(str(TASK_ID))

    @pytest.mark.asyncio
    async def test_force_cancels_if_agent_gone_during_aborting(self):
        svc = AsyncMock()
        svc.get_last_by_session_id.return_value = _make_task(RunStatus.ABORTING)
        svc.transition_status.return_value = None
        handler, pubsub, _ = _build_handler(svc)

        mock_db = AsyncMock()

        with (
            patch("ii_agent.realtime.handlers.cancel.get_db_session_local") as db_ctx,
            patch("ii_agent.realtime.handlers.cancel.cancel") as mock_cancel,
        ):
            db_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            db_ctx.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_cancel.get_active_runs = AsyncMock(return_value=set())

            await handler.handle(_cancel_content(), _session())

        svc.transition_status.assert_awaited_once()
        assert svc.transition_status.call_args.kwargs["to_status"] == RunStatus.CANCELLED


class TestCancelHandlerIdempotent:
    @pytest.mark.asyncio
    async def test_no_action_for_completed_task(self):
        svc = AsyncMock()
        svc.get_last_by_session_id.return_value = _make_task(RunStatus.COMPLETED)
        handler, pubsub, _ = _build_handler(svc)

        with patch("ii_agent.realtime.handlers.cancel.get_db_session_local") as db_ctx:
            db_ctx.return_value.__aenter__ = AsyncMock(return_value=AsyncMock())
            db_ctx.return_value.__aexit__ = AsyncMock(return_value=False)
            await handler.handle(_cancel_content(), _session())

        svc.transition_status.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_action_for_cancelled_task(self):
        svc = AsyncMock()
        svc.get_last_by_session_id.return_value = _make_task(RunStatus.CANCELLED)
        handler, pubsub, _ = _build_handler(svc)

        with patch("ii_agent.realtime.handlers.cancel.get_db_session_local") as db_ctx:
            db_ctx.return_value.__aenter__ = AsyncMock(return_value=AsyncMock())
            db_ctx.return_value.__aexit__ = AsyncMock(return_value=False)
            await handler.handle(_cancel_content(), _session())

        svc.transition_status.assert_not_awaited()
