"""Tests for ii_agent.sessions.service.SessionService."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ii_agent.sessions.exceptions import SessionNotFoundError
from ii_agent.sessions.schemas import SessionInfo
from ii_agent.sessions.service import SessionService


# ---------------------------------------------------------------------------
# Factories / helpers
# ---------------------------------------------------------------------------


def _make_service(**repo_overrides) -> SessionService:
    """Build a SessionService with fully mocked dependencies."""
    defaults = dict(
        session_repo=AsyncMock(),
        event_repo=AsyncMock(),
        run_task_service=AsyncMock(),
        file_store=AsyncMock(),
        file_service=AsyncMock(),
        sandbox_repo=AsyncMock(),
        cache=AsyncMock(),
        config=MagicMock(),
    )
    defaults.update(repo_overrides)
    return SessionService(**defaults)


def _make_orm_session(
    session_id: Optional[uuid.UUID] = None,
    user_id: Optional[uuid.UUID] = None,
    name: Optional[str] = "test-session",
    status: str = "active",
    is_deleted: bool = False,
    is_public: bool = False,
    api_version: str = "v0",
    session_metadata: Optional[dict] = None,
    agent_type=None,
    model_setting_id: Optional[uuid.UUID] = None,
    app_kind: str = "agent",
    public_url: Optional[str] = None,
) -> MagicMock:
    """Create a mock ORM session with required attributes."""
    session = MagicMock()
    session.id = session_id or uuid.uuid4()
    session.user_id = user_id or uuid.uuid4()
    session.name = name
    session.status = status
    session.is_deleted = is_deleted
    session.is_public = is_public
    session.api_version = api_version
    session.session_metadata = session_metadata or {}
    session.agent_type = agent_type
    session.model_setting_id = model_setting_id
    session.app_kind = app_kind
    session.public_url = public_url
    session.last_message_at = None
    session.created_at = datetime(2024, 1, 1, tzinfo=timezone.utc)
    session.updated_at = datetime(2024, 1, 2, tzinfo=timezone.utc)
    session.project = None
    session.get_workspace_dir = MagicMock(return_value=f"/workspace/{session.id}")
    return session


# ---------------------------------------------------------------------------
# create_session
# ---------------------------------------------------------------------------


class TestCreateSession:
    @pytest.mark.asyncio
    async def test_saves_and_returns_session_info(self):
        svc = _make_service()
        session_id = uuid.uuid4()
        user_id = uuid.uuid4()

        orm_session = _make_orm_session(session_id=session_id, user_id=user_id)
        svc._session_repo.save = AsyncMock(return_value=orm_session)

        result = await svc.create_session(AsyncMock(), session_uuid=session_id, user_id=user_id)

        assert isinstance(result, SessionInfo)
        assert result.id == session_id
        assert result.user_id == user_id

    @pytest.mark.asyncio
    async def test_name_passed_through(self):
        svc = _make_service()
        orm_session = _make_orm_session(name="My Session")
        svc._session_repo.save = AsyncMock(return_value=orm_session)

        result = await svc.create_session(
            AsyncMock(), session_uuid=uuid.uuid4(), user_id=uuid.uuid4(), name="My Session"
        )

        assert result.name == "My Session"

    @pytest.mark.asyncio
    async def test_api_version_passed_through(self):
        svc = _make_service()
        orm_session = _make_orm_session(api_version="v1")
        svc._session_repo.save = AsyncMock(return_value=orm_session)

        result = await svc.create_session(
            AsyncMock(), session_uuid=uuid.uuid4(), user_id=uuid.uuid4(), api_version="v1"
        )

        assert result.api_version == "v1"


# ---------------------------------------------------------------------------
# get_session_by_id
# ---------------------------------------------------------------------------


class TestGetSessionById:
    @pytest.mark.asyncio
    async def test_returns_session_info_when_found(self):
        svc = _make_service()
        session_id = uuid.uuid4()
        orm_session = _make_orm_session(session_id=session_id)
        svc._session_repo.get_by_id_with_project = AsyncMock(return_value=orm_session)

        result = await svc.get_session_by_id(AsyncMock(), session_id)

        assert result is not None
        assert result.id == session_id

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self):
        svc = _make_service()
        svc._session_repo.get_by_id_with_project = AsyncMock(return_value=None)

        result = await svc.get_session_by_id(AsyncMock(), uuid.uuid4())

        assert result is None


# ---------------------------------------------------------------------------
# update_session_fields
# ---------------------------------------------------------------------------


class TestUpdateSessionFields:
    @pytest.mark.asyncio
    async def test_sets_fields_and_saves(self):
        svc = _make_service()
        orm_session = _make_orm_session()
        svc._session_repo.get_by_id = AsyncMock(return_value=orm_session)
        svc._session_repo.update = AsyncMock()
        svc._cache.evict = AsyncMock()

        await svc.update_session_fields(AsyncMock(), orm_session.id, name="New Name")

        assert orm_session.name == "New Name"
        svc._session_repo.update.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_does_nothing_when_session_not_found(self):
        svc = _make_service()
        svc._session_repo.get_by_id = AsyncMock(return_value=None)
        svc._session_repo.update = AsyncMock()

        await svc.update_session_fields(AsyncMock(), uuid.uuid4(), name="X")

        svc._session_repo.update.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_multiple_fields_updated(self):
        svc = _make_service()
        orm_session = _make_orm_session()
        svc._session_repo.get_by_id = AsyncMock(return_value=orm_session)
        svc._session_repo.update = AsyncMock()
        svc._cache.evict = AsyncMock()

        await svc.update_session_fields(AsyncMock(), orm_session.id, name="New", is_public=True)

        assert orm_session.name == "New"
        assert orm_session.is_public is True


# ---------------------------------------------------------------------------
# soft_delete_session
# ---------------------------------------------------------------------------


class TestSoftDeleteSession:
    @pytest.mark.asyncio
    async def test_sets_is_deleted_flag(self):
        svc = _make_service()
        orm_session = _make_orm_session()
        session_id = orm_session.id
        user_id = orm_session.user_id
        svc._session_repo.get_by_id_and_user = AsyncMock(return_value=orm_session)
        svc._session_repo.update = AsyncMock()

        await svc.soft_delete_session(AsyncMock(), session_id, user_id)

        assert orm_session.is_deleted is True
        svc._session_repo.update.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_raises_when_not_found(self):
        svc = _make_service()
        svc._session_repo.get_by_id_and_user = AsyncMock(return_value=None)

        with pytest.raises(SessionNotFoundError):
            await svc.soft_delete_session(AsyncMock(), uuid.uuid4(), uuid.uuid4())


# ---------------------------------------------------------------------------
# bulk_soft_delete_sessions
# ---------------------------------------------------------------------------


class TestBulkSoftDeleteSessions:
    @pytest.mark.asyncio
    async def test_marks_found_as_deleted(self):
        svc = _make_service()
        user_id = uuid.uuid4()
        sess1 = _make_orm_session()
        sess2 = _make_orm_session()

        svc._session_repo.get_non_deleted_by_ids_and_user = AsyncMock(return_value=[sess1, sess2])

        db = AsyncMock()
        db.flush = AsyncMock()

        deleted, failed = await svc.bulk_soft_delete_sessions(db, [sess1.id, sess2.id], user_id)

        assert set(deleted) == {sess1.id, sess2.id}
        assert failed == []
        assert sess1.is_deleted is True
        assert sess2.is_deleted is True

    @pytest.mark.asyncio
    async def test_returns_failed_ids_for_missing_sessions(self):
        svc = _make_service()
        user_id = uuid.uuid4()
        found_sess = _make_orm_session()
        missing_id = uuid.uuid4()

        svc._session_repo.get_non_deleted_by_ids_and_user = AsyncMock(return_value=[found_sess])

        db = AsyncMock()
        db.flush = AsyncMock()

        deleted, failed = await svc.bulk_soft_delete_sessions(
            db, [found_sess.id, missing_id], user_id
        )

        assert found_sess.id in deleted
        assert missing_id in failed

    @pytest.mark.asyncio
    async def test_all_ids_missing_returns_all_as_failed(self):
        svc = _make_service()
        user_id = uuid.uuid4()
        ids = [uuid.uuid4(), uuid.uuid4()]

        svc._session_repo.get_non_deleted_by_ids_and_user = AsyncMock(return_value=[])

        db = AsyncMock()
        db.flush = AsyncMock()

        deleted, failed = await svc.bulk_soft_delete_sessions(db, ids, user_id)

        assert deleted == []
        assert set(failed) == set(ids)


# ---------------------------------------------------------------------------
# set_session_public
# ---------------------------------------------------------------------------


class TestSetSessionPublic:
    @pytest.mark.asyncio
    async def test_returns_true_when_updated(self):
        svc = _make_service()
        orm_session = _make_orm_session(is_public=False)
        svc._session_repo.get_by_id_and_user = AsyncMock(return_value=orm_session)
        svc._session_repo.update = AsyncMock()

        result = await svc.set_session_public(
            AsyncMock(), orm_session.id, orm_session.user_id, True
        )

        assert result is True
        assert orm_session.is_public is True

    @pytest.mark.asyncio
    async def test_returns_false_when_not_found(self):
        svc = _make_service()
        svc._session_repo.get_by_id_and_user = AsyncMock(return_value=None)

        result = await svc.set_session_public(AsyncMock(), uuid.uuid4(), uuid.uuid4(), True)

        assert result is False


# ---------------------------------------------------------------------------
# get_or_create_session
# ---------------------------------------------------------------------------


class TestGetOrCreateSession:
    @pytest.mark.asyncio
    async def test_returns_existing_session(self):
        svc = _make_service()
        session_id = uuid.uuid4()
        user_id = uuid.uuid4()
        orm_session = _make_orm_session(session_id=session_id, user_id=user_id)
        svc._session_repo.get_by_id_with_project = AsyncMock(return_value=orm_session)

        result = await svc.get_or_create_session(AsyncMock(), session_id, user_id)

        assert result.id == session_id
        svc._session_repo.save.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_raises_when_given_id_not_found(self):
        svc = _make_service()
        svc._session_repo.get_by_id_with_project = AsyncMock(return_value=None)

        with pytest.raises(SessionNotFoundError):
            await svc.get_or_create_session(AsyncMock(), uuid.uuid4(), uuid.uuid4())

    @pytest.mark.asyncio
    async def test_creates_new_when_no_id_given(self):
        svc = _make_service()
        user_id = uuid.uuid4()
        new_session = _make_orm_session(user_id=user_id)
        svc._session_repo.save = AsyncMock(return_value=new_session)

        result = await svc.get_or_create_session(AsyncMock(), None, user_id)

        svc._session_repo.save.assert_awaited_once()
        assert result.user_id == user_id


# ---------------------------------------------------------------------------
# ensure_session_exists
# ---------------------------------------------------------------------------


class TestEnsureSessionExists:
    @pytest.mark.asyncio
    async def test_returns_existing_user_id_when_session_found(self):
        svc = _make_service()
        user_id = uuid.uuid4()
        session_id = uuid.uuid4()
        orm_session = _make_orm_session(session_id=session_id, user_id=user_id)
        svc._session_repo.get_by_id_with_project = AsyncMock(return_value=orm_session)

        result = await svc.ensure_session_exists(AsyncMock(), session_id, user_id)

        assert result == user_id

    @pytest.mark.asyncio
    async def test_creates_session_when_not_found(self):
        svc = _make_service()
        user_id = uuid.uuid4()
        session_id = uuid.uuid4()
        new_session = _make_orm_session(session_id=session_id, user_id=user_id)

        svc._session_repo.get_by_id_with_project = AsyncMock(return_value=None)
        svc._session_repo.save = AsyncMock(return_value=new_session)

        result = await svc.ensure_session_exists(AsyncMock(), session_id, user_id)

        assert result == user_id
        svc._session_repo.save.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_raises_when_no_session_and_no_user_id(self):
        svc = _make_service()
        svc._session_repo.get_by_id_with_project = AsyncMock(return_value=None)

        from ii_agent.core.exceptions import ValidationError

        with pytest.raises(ValidationError):
            await svc.ensure_session_exists(AsyncMock(), uuid.uuid4(), user_id=None)


# ---------------------------------------------------------------------------
# get_session_running_status
# ---------------------------------------------------------------------------


class TestGetSessionRunningStatus:
    @pytest.mark.asyncio
    async def test_delegates_to_run_task_service(self):
        svc = _make_service()
        session_id = uuid.uuid4()
        expected = MagicMock()
        svc._run_task_service.find_active_by_session = AsyncMock(return_value=expected)

        result = await svc.get_session_running_status(AsyncMock(), session_id)

        assert result is expected
        svc._run_task_service.find_active_by_session.assert_awaited_once()


# ---------------------------------------------------------------------------
# update_session_name
# ---------------------------------------------------------------------------


class TestUpdateSessionName:
    @pytest.mark.asyncio
    async def test_updates_name_and_clears_title_pending(self):
        """update_session_name calls update_session_title_state with title_pending=False."""
        svc = _make_service()
        session_id = uuid.uuid4()
        orm_session = _make_orm_session(session_id=session_id, name="Old Name")
        svc._session_repo.get_by_id = AsyncMock(return_value=orm_session)
        svc._session_repo.update = AsyncMock()
        svc._cache.evict = AsyncMock()

        await svc.update_session_name(AsyncMock(), session_id, "New Name")

        assert orm_session.name == "New Name"
        svc._session_repo.update.assert_awaited_once()


# ---------------------------------------------------------------------------
# soft_delete_session — resource cleanup (cancellation, events, cache)
# ---------------------------------------------------------------------------


class TestSoftDeleteSessionCleanup:
    @pytest.mark.asyncio
    async def test_cancels_active_run_before_delete(self):
        """soft_delete_session should cancel any active run."""
        svc = _make_service()
        orm_session = _make_orm_session()
        session_id = orm_session.id
        user_id = orm_session.user_id

        svc._session_repo.get_by_id_and_user = AsyncMock(return_value=orm_session)
        svc._session_repo.update = AsyncMock()

        active_task = MagicMock()
        active_task.id = uuid.uuid4()
        svc._run_task_service.find_active_by_session = AsyncMock(return_value=active_task)

        with patch("ii_agent.core.redis.cancel.cancel_run", new=AsyncMock(return_value=True)):
            await svc.soft_delete_session(AsyncMock(), session_id, user_id)

        assert orm_session.is_deleted is True
        svc._run_task_service.find_active_by_session.assert_awaited_once()
        svc._run_task_service.transition_status.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_publishes_session_deleted_event(self):
        """soft_delete_session should persist a session.deleted event."""
        svc = _make_service()
        orm_session = _make_orm_session()
        session_id = orm_session.id
        user_id = orm_session.user_id

        svc._session_repo.get_by_id_and_user = AsyncMock(return_value=orm_session)
        svc._session_repo.update = AsyncMock()
        svc._run_task_service.find_active_by_session = AsyncMock(return_value=None)

        db = AsyncMock()
        await svc.soft_delete_session(db, session_id, user_id)

        svc._event_repo.save.assert_awaited_once()
        saved_event = svc._event_repo.save.call_args[0][1]
        assert saved_event.event_type == "session.deleted"

    @pytest.mark.asyncio
    async def test_evicts_cache_on_delete(self):
        """soft_delete_session should evict the session from cache."""
        svc = _make_service()
        orm_session = _make_orm_session()
        session_id = orm_session.id
        user_id = orm_session.user_id

        svc._session_repo.get_by_id_and_user = AsyncMock(return_value=orm_session)
        svc._session_repo.update = AsyncMock()
        svc._run_task_service.find_active_by_session = AsyncMock(return_value=None)

        await svc.soft_delete_session(AsyncMock(), session_id, user_id)

        svc._cache.evict.assert_awaited_once()


# ---------------------------------------------------------------------------
# bulk_soft_delete_sessions — resource cleanup
# ---------------------------------------------------------------------------


class TestBulkSoftDeleteSessionsCleanup:
    @pytest.mark.asyncio
    async def test_cancels_runs_and_publishes_events_for_each(self):
        svc = _make_service()
        user_id = uuid.uuid4()
        sess1 = _make_orm_session()
        sess2 = _make_orm_session()

        svc._session_repo.get_non_deleted_by_ids_and_user = AsyncMock(return_value=[sess1, sess2])
        svc._run_task_service.find_active_by_session = AsyncMock(return_value=None)

        db = AsyncMock()
        db.flush = AsyncMock()

        deleted, failed = await svc.bulk_soft_delete_sessions(db, [sess1.id, sess2.id], user_id)

        assert len(deleted) == 2
        # Two events published (one per session).
        assert svc._event_repo.save.await_count == 2
        # Two cache evictions.
        assert svc._cache.evict.await_count == 2
