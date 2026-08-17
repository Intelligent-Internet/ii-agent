"""Unit tests for RunTaskService."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import IntegrityError

from ii_agent.tasks.exceptions import TaskConflictException
from ii_agent.tasks.schemas import RunTaskResponse, TaskLogResponse
from ii_agent.tasks.service import RunTaskService
from ii_agent.tasks.types import RunStatus, TaskType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SESSION_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
TASK_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")
_NOW = datetime.now(timezone.utc)


def _make_task(
    task_id: uuid.UUID = TASK_ID,
    session_id: uuid.UUID = SESSION_ID,
    status: RunStatus = RunStatus.RUNNING,
    task_type: TaskType = TaskType.AGENT_RUN,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=task_id,
        session_id=session_id,
        task_type=task_type,
        status=status,
        error_message=None,
        data=None,
        version=0,
        created_at=_NOW,
        updated_at=_NOW,
    )


def _make_log(
    task_id: uuid.UUID = TASK_ID,
    status: RunStatus = RunStatus.RUNNING,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=1,
        task_id=task_id,
        status=status,
        data=None,
        created_at=_NOW,
    )


def _make_service() -> tuple[RunTaskService, MagicMock, MagicMock, MagicMock]:
    task_repo = MagicMock()
    log_repo = MagicMock()
    cache = MagicMock()
    cache.get = AsyncMock(return_value=None)
    cache.set = AsyncMock()
    cache.evict = AsyncMock()

    config = MagicMock()
    svc = RunTaskService(
        task_repo=task_repo,
        log_repo=log_repo,
        cache=cache,
        config=config,
    )
    return svc, task_repo, log_repo, cache


# ---------------------------------------------------------------------------
# claim_task
# ---------------------------------------------------------------------------


class TestClaimTask:
    @pytest.mark.asyncio
    async def test_creates_task_and_log(self):
        svc, task_repo, log_repo, _ = _make_service()
        task = _make_task()
        task_repo.save = AsyncMock(return_value=task)
        log_repo.save = AsyncMock(return_value=_make_log())

        result = await svc.claim_task(
            None,
            session_id=SESSION_ID,
            task_type=TaskType.AGENT_RUN,
        )

        task_repo.save.assert_called_once()
        log_repo.save.assert_called_once()
        assert isinstance(result, RunTaskResponse)
        assert result.id == TASK_ID

    @pytest.mark.asyncio
    async def test_raises_conflict_on_integrity_error(self):
        svc, task_repo, log_repo, _ = _make_service()
        task_repo.save = AsyncMock(side_effect=IntegrityError(None, None, None))
        db = AsyncMock()
        db.rollback = AsyncMock()

        with pytest.raises(TaskConflictException):
            await svc.claim_task(
                db,
                session_id=SESSION_ID,
                task_type=TaskType.AGENT_RUN,
            )

        db.rollback.assert_called_once()

    @pytest.mark.asyncio
    async def test_passes_custom_status(self):
        svc, task_repo, log_repo, _ = _make_service()
        saved_task = _make_task(status=RunStatus.PENDING)
        task_repo.save = AsyncMock(return_value=saved_task)
        log_repo.save = AsyncMock()

        result = await svc.claim_task(
            None,
            session_id=SESSION_ID,
            task_type=TaskType.CHAT_RUN,
            status=RunStatus.PENDING,
        )
        assert result.status == RunStatus.PENDING


# ---------------------------------------------------------------------------
# get_task_by_id
# ---------------------------------------------------------------------------


class TestGetTaskById:
    @pytest.mark.asyncio
    async def test_returns_cached_result_without_db(self):
        svc, task_repo, _, cache = _make_service()
        cached = RunTaskResponse(
            id=TASK_ID,
            session_id=SESSION_ID,
            task_type=TaskType.AGENT_RUN,
            status=RunStatus.RUNNING,
            created_at=_NOW,
            updated_at=_NOW,
        )
        cache.get = AsyncMock(return_value=cached)

        result = await svc.get_task_by_id(None, task_id=TASK_ID)

        task_repo.get_by_id.assert_not_called()
        assert result is cached

    @pytest.mark.asyncio
    async def test_returns_none_when_task_not_found(self):
        svc, task_repo, _, _ = _make_service()
        task_repo.get_by_id = AsyncMock(return_value=None)

        result = await svc.get_task_by_id(None, task_id=TASK_ID)
        assert result is None

    @pytest.mark.asyncio
    async def test_populates_cache_on_db_hit(self):
        svc, task_repo, _, cache = _make_service()
        task = _make_task()
        task_repo.get_by_id = AsyncMock(return_value=task)

        result = await svc.get_task_by_id(None, task_id=TASK_ID)

        cache.set.assert_called_once()
        assert isinstance(result, RunTaskResponse)
        assert result.id == TASK_ID


# ---------------------------------------------------------------------------
# find_active_by_session / get_last_by_session_id
# ---------------------------------------------------------------------------


class TestFindBySession:
    @pytest.mark.asyncio
    async def test_find_active_returns_none_when_not_found(self):
        svc, task_repo, _, _ = _make_service()
        task_repo.find_active_by_session = AsyncMock(return_value=None)
        result = await svc.find_active_by_session(None, SESSION_ID)
        assert result is None

    @pytest.mark.asyncio
    async def test_find_active_returns_response(self):
        svc, task_repo, _, _ = _make_service()
        task_repo.find_active_by_session = AsyncMock(return_value=_make_task())
        result = await svc.find_active_by_session(None, SESSION_ID)
        assert isinstance(result, RunTaskResponse)

    @pytest.mark.asyncio
    async def test_get_last_returns_none_when_not_found(self):
        svc, task_repo, _, _ = _make_service()
        task_repo.find_last_by_session = AsyncMock(return_value=None)
        result = await svc.get_last_by_session_id(None, SESSION_ID)
        assert result is None

    @pytest.mark.asyncio
    async def test_get_tasks_returns_list(self):
        svc, task_repo, _, _ = _make_service()
        task_repo.list_by_session = AsyncMock(return_value=[_make_task()])
        result = await svc.get_tasks_by_session(None, SESSION_ID)
        assert isinstance(result, list)
        assert len(result) == 1


# ---------------------------------------------------------------------------
# transition_status
# ---------------------------------------------------------------------------


class TestTransitionStatus:
    @pytest.mark.asyncio
    async def test_returns_none_when_task_not_found(self):
        svc, task_repo, _, _ = _make_service()
        task_repo.get_by_id = AsyncMock(return_value=None)

        result = await svc.transition_status(None, task_id=TASK_ID, to_status=RunStatus.COMPLETED)
        assert result is None

    @pytest.mark.asyncio
    async def test_updates_status_and_logs(self):
        svc, task_repo, log_repo, cache = _make_service()
        task = _make_task()
        task_repo.get_by_id = AsyncMock(return_value=task)
        task_repo.update = AsyncMock(return_value=task)
        log_repo.save = AsyncMock()

        result = await svc.transition_status(None, task_id=TASK_ID, to_status=RunStatus.COMPLETED)

        task_repo.update.assert_called_once()
        log_repo.save.assert_called_once()
        cache.evict.assert_called_once()
        assert isinstance(result, RunTaskResponse)

    @pytest.mark.asyncio
    async def test_sets_error_message_when_provided(self):
        svc, task_repo, log_repo, cache = _make_service()
        task = _make_task()
        task_repo.get_by_id = AsyncMock(return_value=task)
        task_repo.update = AsyncMock(return_value=task)
        log_repo.save = AsyncMock()

        await svc.transition_status(
            None,
            task_id=TASK_ID,
            to_status=RunStatus.FAILED,
            error_message="something went wrong",
        )
        assert task.error_message == "something went wrong"


# ---------------------------------------------------------------------------
# get_logs
# ---------------------------------------------------------------------------


class TestGetLogs:
    @pytest.mark.asyncio
    async def test_returns_list_of_log_responses(self):
        svc, _, log_repo, _ = _make_service()
        log_repo.list_by_task = AsyncMock(return_value=[_make_log()])

        result = await svc.get_logs(None, TASK_ID)
        assert isinstance(result, list)
        assert len(result) == 1
        assert isinstance(result[0], TaskLogResponse)

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_logs(self):
        svc, _, log_repo, _ = _make_service()
        log_repo.list_by_task = AsyncMock(return_value=[])

        result = await svc.get_logs(None, TASK_ID)
        assert result == []
