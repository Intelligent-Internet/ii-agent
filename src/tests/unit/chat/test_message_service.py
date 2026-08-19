"""Unit tests for MessageService._db_message_to_message (pure sync converter)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Optional
from unittest.mock import AsyncMock, MagicMock

import pytest

from ii_agent.chat.messages.service import MessageService
from ii_agent.chat.types import MessageRole, TextContent


# ---------------------------------------------------------------------------
# Helper: build a fake ChatMessage ORM row
# ---------------------------------------------------------------------------


def _now_ts() -> datetime:
    return datetime.now(tz=timezone.utc)


_SENTINEL = object()


def _make_db_msg(
    *,
    id: Optional[uuid.UUID] = None,
    session_id: Optional[uuid.UUID] = None,
    role: str = "user",
    content=_SENTINEL,
    model: str = "claude-3-5-sonnet",
    is_finished: bool = True,
    tokens: Optional[int] = None,
    file_ids=None,
    tools: Optional[dict] = None,
    message_metadata: Optional[dict] = None,
    provider_metadata: Optional[dict] = None,
    finish_reason: Optional[str] = None,
    created_at: Optional[datetime] = None,
    updated_at: Optional[datetime] = None,
):
    """Return a SimpleNamespace that mimics a ChatMessage ORM row."""
    if content is _SENTINEL:
        content = [{"type": "text", "text": "hello"}]
    return SimpleNamespace(
        id=id or uuid.uuid4(),
        session_id=session_id or uuid.uuid4(),
        role=role,
        content=content,
        model=model,
        is_finished=is_finished,
        tokens=tokens,
        file_ids=file_ids,
        tools=tools,
        message_metadata=message_metadata,
        provider_metadata=provider_metadata,
        finish_reason=finish_reason,
        created_at=created_at or _now_ts(),
        updated_at=updated_at or _now_ts(),
    )


@pytest.fixture
def svc():
    return MessageService(chat_repo=MagicMock())


# ---------------------------------------------------------------------------
# _db_message_to_message
# ---------------------------------------------------------------------------


class TestDbMessageToMessage:
    def test_returns_none_for_unfinished_message(self, svc):
        db_msg = _make_db_msg(is_finished=False)
        result = svc._db_message_to_message(db_msg)
        assert result is None

    def test_basic_conversion_with_list_content(self, svc):
        msg_id = uuid.uuid4()
        session_id = uuid.uuid4()
        db_msg = _make_db_msg(
            id=msg_id,
            session_id=session_id,
            role="user",
            content=[{"type": "text", "text": "hello world"}],
        )
        result = svc._db_message_to_message(db_msg)
        assert result is not None
        assert result.id == msg_id
        assert result.session_id == session_id
        assert result.role == MessageRole.USER

    def test_dict_content_with_parts_key(self, svc):
        """Content stored as {\"parts\": [...]} should be unwrapped."""
        db_msg = _make_db_msg(content={"parts": [{"type": "text", "text": "nested content"}]})
        result = svc._db_message_to_message(db_msg)
        assert result is not None
        assert len(result.parts) == 1
        assert isinstance(result.parts[0], TextContent)
        assert result.parts[0].text == "nested content"

    def test_empty_dict_content_without_parts_key(self, svc):
        """Dict content without 'parts' key → empty parts list."""
        db_msg = _make_db_msg(content={"unexpected": "shape"})
        result = svc._db_message_to_message(db_msg)
        assert result is not None
        assert result.parts == []

    def test_none_content_becomes_empty_parts(self, svc):
        """None content handled gracefully → empty parts list."""
        db_msg = _make_db_msg(content=None)
        result = svc._db_message_to_message(db_msg)
        assert result is not None
        assert result.parts == []

    def test_preserves_model_field(self, svc):
        db_msg = _make_db_msg(model="gpt-4o", content=[])
        result = svc._db_message_to_message(db_msg)
        assert result.model == "gpt-4o"

    def test_preserves_tokens(self, svc):
        db_msg = _make_db_msg(tokens=512)
        result = svc._db_message_to_message(db_msg)
        assert result.tokens == 512

    def test_file_ids_converted_to_strings(self, svc):
        fid = uuid.uuid4()
        db_msg = _make_db_msg(file_ids=[fid])
        result = svc._db_message_to_message(db_msg)
        assert result.file_ids == [str(fid)]

    def test_none_file_ids_remains_none(self, svc):
        db_msg = _make_db_msg(file_ids=None)
        result = svc._db_message_to_message(db_msg)
        assert result.file_ids is None

    def test_preserves_tools(self, svc):
        tools = {"code_interpreter": True, "search": False}
        db_msg = _make_db_msg(tools=tools)
        result = svc._db_message_to_message(db_msg)
        assert result.tools_enabled == tools

    def test_preserves_metadata(self, svc):
        meta = {"source": "api", "version": 2}
        db_msg = _make_db_msg(message_metadata=meta)
        result = svc._db_message_to_message(db_msg)
        assert result.metadata == meta

    def test_preserves_provider_metadata(self, svc):
        pmeta = {"anthropic": {"cache_creation_input_tokens": 100}}
        db_msg = _make_db_msg(provider_metadata=pmeta)
        result = svc._db_message_to_message(db_msg)
        assert result.provider_metadata == pmeta

    def test_preserves_finish_reason(self, svc):
        db_msg = _make_db_msg(finish_reason="end_turn")
        result = svc._db_message_to_message(db_msg)
        assert result.finish_reason == "end_turn"

    def test_timestamps_converted_to_int(self, svc):
        ts = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
        db_msg = _make_db_msg(created_at=ts, updated_at=ts)
        result = svc._db_message_to_message(db_msg)
        assert isinstance(result.created_at, int)
        assert isinstance(result.updated_at, int)
        assert result.created_at == int(ts.timestamp())

    def test_assistant_role_preserved(self, svc):
        db_msg = _make_db_msg(role="assistant")
        result = svc._db_message_to_message(db_msg)
        assert result.role == MessageRole.ASSISTANT

    def test_tool_role_preserved(self, svc):
        db_msg = _make_db_msg(role="tool", content=[])
        result = svc._db_message_to_message(db_msg)
        assert result.role == MessageRole.TOOL

    def test_is_finished_true_does_not_skip(self, svc):
        db_msg = _make_db_msg(is_finished=True)
        result = svc._db_message_to_message(db_msg)
        assert result is not None

    def test_is_finished_none_does_not_skip(self, svc):
        """is_finished=None is not False, so message is NOT skipped."""
        db_msg = _make_db_msg(is_finished=None)
        result = svc._db_message_to_message(db_msg)
        assert result is not None


# ---------------------------------------------------------------------------
# list_by_session - filters out unfinished messages
# ---------------------------------------------------------------------------


class TestListBySession:
    @pytest.mark.asyncio
    async def test_filters_unfinished_messages(self):
        repo = MagicMock()
        finished = _make_db_msg(is_finished=True)
        unfinished = _make_db_msg(is_finished=False)
        repo.list_by_session = AsyncMock(return_value=[finished, unfinished])

        svc = MessageService(chat_repo=repo)
        db = MagicMock()
        results = await svc.list_by_session(db, finished.session_id)
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_returns_empty_when_all_unfinished(self):
        repo = MagicMock()
        repo.list_by_session = AsyncMock(return_value=[_make_db_msg(is_finished=False)])
        svc = MessageService(chat_repo=repo)
        db = MagicMock()
        results = await svc.list_by_session(db, uuid.uuid4())
        assert results == []

    @pytest.mark.asyncio
    async def test_returns_all_finished_messages(self):
        repo = MagicMock()
        msgs = [_make_db_msg(is_finished=True) for _ in range(3)]
        repo.list_by_session = AsyncMock(return_value=msgs)
        svc = MessageService(chat_repo=repo)
        db = MagicMock()
        results = await svc.list_by_session(db, uuid.uuid4())
        assert len(results) == 3
