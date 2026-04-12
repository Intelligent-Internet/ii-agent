"""Tests for ii_agent.chat.messages.history_service."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from ii_agent.chat.messages.history_service import (
    ChatMessageHistoryService,
    _normalize_content,
)


# ---------------------------------------------------------------------------
# _normalize_content (pure function)
# ---------------------------------------------------------------------------


class TestNormalizeContent:
    def test_none_returns_empty(self):
        assert _normalize_content(None) == []

    def test_empty_list_returns_empty(self):
        assert _normalize_content([]) == []

    def test_list_returned_as_is(self):
        parts = [{"type": "text", "text": "hello"}]
        assert _normalize_content(parts) == parts

    def test_dict_with_parts_key_returns_parts(self):
        parts = [{"type": "text", "text": "hi"}]
        assert _normalize_content({"parts": parts}) == parts

    def test_dict_without_parts_returns_empty(self):
        """A dict without 'parts' key falls through to the default []."""
        d = {"type": "text", "text": "bare"}
        result = _normalize_content(d)
        assert result == []

    def test_string_returns_empty(self):
        """Unknown types (str) fall through to the default []."""
        result = _normalize_content("hello")
        assert result == []

    def test_empty_dict_without_parts_returns_empty(self):
        result = _normalize_content({})
        assert result == []


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _make_service(
    chat_msgs=None, has_more=False, file_uploads=None
) -> ChatMessageHistoryService:
    """Build a ChatMessageHistoryService with mocked repos."""
    chat_repo = AsyncMock()
    chat_repo.get_history = AsyncMock(return_value=(chat_msgs or [], has_more))

    file_repo = AsyncMock()
    file_repo.get_by_ids = AsyncMock(return_value=file_uploads or [])

    return ChatMessageHistoryService(chat_repo=chat_repo, file_repo=file_repo)


def _make_message(
    role="user",
    content=None,
    file_ids=None,
    usage=None,
    tokens=None,
    model=None,
    finish_reason=None,
    message_metadata=None,
    provider_metadata=None,
) -> MagicMock:
    msg = MagicMock()
    msg.id = uuid.uuid4()
    msg.role = role
    msg.content = content if content is not None else [{"type": "text", "text": "hello"}]
    msg.file_ids = file_ids or []
    msg.usage = usage
    msg.tokens = tokens
    msg.model = model
    msg.finish_reason = finish_reason
    msg.message_metadata = message_metadata
    msg.provider_metadata = provider_metadata
    msg.created_at = datetime(2024, 1, 1, tzinfo=timezone.utc)
    return msg


# ---------------------------------------------------------------------------
# get_message_history
# ---------------------------------------------------------------------------


class TestGetMessageHistory:
    @pytest.mark.asyncio
    async def test_delegates_to_repo(self):
        svc = _make_service(chat_msgs=[], has_more=False)
        db = AsyncMock()
        session_id = uuid.uuid4()

        msgs, more = await svc.get_message_history(db, session_id=session_id, limit=10)

        svc._repo.get_history.assert_awaited_once_with(db, session_id, 10, None)
        assert msgs == []
        assert more is False

    @pytest.mark.asyncio
    async def test_passes_before_cursor(self):
        svc = _make_service()
        db = AsyncMock()
        session_id = uuid.uuid4()

        await svc.get_message_history(db, session_id=session_id, limit=5, before="cursor-123")

        svc._repo.get_history.assert_awaited_once_with(db, session_id, 5, "cursor-123")


# ---------------------------------------------------------------------------
# build_message_history_response
# ---------------------------------------------------------------------------


class TestBuildMessageHistoryResponse:
    @pytest.mark.asyncio
    async def test_empty_messages(self):
        svc = _make_service(chat_msgs=[], has_more=False)
        db = AsyncMock()
        session_id = uuid.uuid4()

        result = await svc.build_message_history_response(db, session_id=session_id)

        assert result.messages == []
        assert result.has_more is False
        assert result.total_count == 0

    @pytest.mark.asyncio
    async def test_single_message_no_files(self):
        msg = _make_message(role="user", content=[{"type": "text", "text": "hi"}])
        svc = _make_service(chat_msgs=[msg])
        db = AsyncMock()
        session_id = uuid.uuid4()

        result = await svc.build_message_history_response(db, session_id=session_id)

        assert result.total_count == 1
        assert result.messages[0].role == "user"
        assert result.messages[0].content == [{"type": "text", "text": "hi"}]

    @pytest.mark.asyncio
    async def test_has_more_propagated(self):
        msg = _make_message()
        svc = _make_service(chat_msgs=[msg], has_more=True)
        db = AsyncMock()
        session_id = uuid.uuid4()

        result = await svc.build_message_history_response(db, session_id=session_id)

        assert result.has_more is True

    @pytest.mark.asyncio
    async def test_message_with_file_ids_resolved(self):
        file_id = uuid.uuid4()
        msg = _make_message(file_ids=[file_id])

        file_upload = MagicMock()
        file_upload.id = file_id
        file_upload.file_name = "test.txt"
        file_upload.file_size = 100
        file_upload.content_type = "text/plain"
        file_upload.created_at = datetime(2024, 1, 1, tzinfo=timezone.utc)

        svc = _make_service(chat_msgs=[msg], file_uploads=[file_upload])
        db = AsyncMock()
        session_id = uuid.uuid4()

        result = await svc.build_message_history_response(db, session_id=session_id)

        assert len(result.messages[0].files) == 1
        assert result.messages[0].files[0].file_name == "test.txt"
        assert result.messages[0].files[0].id == file_id

    @pytest.mark.asyncio
    async def test_message_with_unknown_file_id_not_included(self):
        """File IDs that have no corresponding upload are silently dropped."""
        file_id = uuid.uuid4()
        msg = _make_message(file_ids=[file_id])
        # file_repo returns empty list (file not found)
        svc = _make_service(chat_msgs=[msg], file_uploads=[])
        db = AsyncMock()
        session_id = uuid.uuid4()

        result = await svc.build_message_history_response(db, session_id=session_id)

        assert result.messages[0].files == []

    @pytest.mark.asyncio
    async def test_message_usage_and_tokens(self):
        msg = _make_message(tokens=500, model="claude-3-5-sonnet")
        svc = _make_service(chat_msgs=[msg])
        db = AsyncMock()
        session_id = uuid.uuid4()

        result = await svc.build_message_history_response(db, session_id=session_id)

        r = result.messages[0]
        assert r.tokens == 500
        assert r.model == "claude-3-5-sonnet"

    @pytest.mark.asyncio
    async def test_old_format_content_normalized(self):
        """Old content format {parts: [...]} is normalized to list."""
        parts = [{"type": "text", "text": "old format"}]
        msg = _make_message(content={"parts": parts})
        svc = _make_service(chat_msgs=[msg])
        db = AsyncMock()
        session_id = uuid.uuid4()

        result = await svc.build_message_history_response(db, session_id=session_id)

        assert result.messages[0].content == parts

    @pytest.mark.asyncio
    async def test_multiple_messages_all_included(self):
        msgs = [_make_message(role="user"), _make_message(role="assistant")]
        svc = _make_service(chat_msgs=msgs)
        db = AsyncMock()
        session_id = uuid.uuid4()

        result = await svc.build_message_history_response(db, session_id=session_id)

        assert result.total_count == 2
        roles = [m.role for m in result.messages]
        assert "user" in roles
        assert "assistant" in roles

    @pytest.mark.asyncio
    async def test_file_repo_not_called_when_no_file_ids(self):
        """If no messages have file_ids, file_repo.get_by_ids is not called."""
        msg = _make_message(file_ids=[])
        svc = _make_service(chat_msgs=[msg])
        db = AsyncMock()
        session_id = uuid.uuid4()

        await svc.build_message_history_response(db, session_id=session_id)

        svc._file_repo.get_by_ids.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_file_repo_called_once_for_all_messages(self):
        """All file IDs across messages are fetched in a single query."""
        file_id_1 = uuid.uuid4()
        file_id_2 = uuid.uuid4()
        msgs = [
            _make_message(file_ids=[file_id_1]),
            _make_message(file_ids=[file_id_2]),
        ]
        svc = _make_service(chat_msgs=msgs, file_uploads=[])
        db = AsyncMock()
        session_id = uuid.uuid4()

        await svc.build_message_history_response(db, session_id=session_id)

        svc._file_repo.get_by_ids.assert_awaited_once()
        called_ids = set(svc._file_repo.get_by_ids.call_args[0][1])
        assert file_id_1 in called_ids
        assert file_id_2 in called_ids
