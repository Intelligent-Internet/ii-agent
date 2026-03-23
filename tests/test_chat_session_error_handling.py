"""Tests for ChatSessionContext.arun() error handling.

Covers the bug where an exception during agent execution would emit an ERROR
event but not a STATUS_UPDATE(READY) event, leaving the frontend stuck in a
"running" state.

Handler imports are deferred to test time to avoid triggering the full
server import chain at collection time (which causes circular imports).
"""

import uuid
import pytest
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

from ii_agent.core.event import AgentStatus, EventType, RealtimeEvent
from ii_tool.tools.base import ToolResult


@pytest.fixture
def session_info():
    from ii_agent.server.models.sessions import SessionInfo

    return SessionInfo(
        id=uuid.uuid4(),
        user_id="user-1",
        status="active",
        workspace_dir="/tmp/ws",
        is_public=False,
        created_at="2025-01-01T00:00:00Z",
    )


@pytest.fixture
def event_stream():
    stream = MagicMock()
    stream.publish = AsyncMock()
    stream.register_hook = MagicMock()
    return stream


@pytest.fixture
def query_content():
    """Minimal QueryContentInternal-like object."""
    obj = MagicMock()
    obj.text = "do something"
    obj.file_upload_paths = []
    obj.resume = False
    obj.images_data = None
    return obj


def _make_chat_session(event_stream, session_info, *, agent_side_effect=None):
    """Build a ChatSessionContext with mocked internals.

    ``agent_side_effect`` is assigned to agent_controller.run_agent_async.
    """
    from ii_agent.server.socket.chat_session import ChatSessionContext

    agent_controller = MagicMock()
    agent_controller.run_agent_async = AsyncMock(side_effect=agent_side_effect)
    agent_controller.state = MagicMock()
    agent_controller.state.save_to_session = MagicMock()

    # Build the dataclass bypassing __post_init__ hooks by mocking dependencies
    chat_session = ChatSessionContext.__new__(ChatSessionContext)
    chat_session.workspace_manager = MagicMock()
    chat_session.file_store = MagicMock()
    chat_session.config = MagicMock()
    chat_session.config.custom_domain = None
    chat_session.session_info = session_info
    chat_session.llm_config = MagicMock()
    chat_session.agent_controller = agent_controller
    chat_session.event_stream = event_stream
    chat_session.first_message = True
    chat_session.sandbox = None
    chat_session.session_metadata = None
    chat_session.vscode_url = None

    return chat_session


class TestChatSessionRunErrorHandling:
    """Tests for ChatSessionContext.arun() exception path."""

    @pytest.mark.asyncio
    async def test_error_emits_status_update_ready(self, event_stream, session_info, query_content):
        """When arun() catches an exception, it must emit both ERROR and STATUS_UPDATE(READY)."""
        chat_session = _make_chat_session(
            event_stream,
            session_info,
            agent_side_effect=RuntimeError("API 400 error"),
        )

        result = await chat_session.arun(query_content)

        # Result must be an error
        assert result.is_error is True

        # Must have published at least 2 events
        calls = event_stream.publish.await_args_list
        assert len(calls) >= 2

        # First event: ERROR
        error_event = calls[0][0][0]
        assert error_event.type == EventType.ERROR
        assert "API 400 error" in error_event.content["message"]

        # Second event: STATUS_UPDATE with READY
        status_event = calls[1][0][0]
        assert status_event.type == EventType.STATUS_UPDATE
        assert status_event.content["status"] == AgentStatus.READY

    @pytest.mark.asyncio
    async def test_error_emits_correct_session_id(self, event_stream, session_info, query_content):
        """Both error events must carry the correct session_id."""
        chat_session = _make_chat_session(
            event_stream,
            session_info,
            agent_side_effect=ValueError("bad value"),
        )

        await chat_session.arun(query_content)

        for call in event_stream.publish.await_args_list:
            event = call[0][0]
            assert event.session_id == session_info.id

    @pytest.mark.asyncio
    async def test_state_saved_even_on_error(self, event_stream, session_info, query_content):
        """The finally clause must call save_to_session even after an error."""
        chat_session = _make_chat_session(
            event_stream,
            session_info,
            agent_side_effect=RuntimeError("boom"),
        )

        await chat_session.arun(query_content)

        chat_session.agent_controller.state.save_to_session.assert_called_once_with(
            str(session_info.id), chat_session.file_store
        )

    @pytest.mark.asyncio
    async def test_success_does_not_emit_error(self, event_stream, session_info, query_content):
        """A successful run should NOT publish an error or an extra READY event."""
        chat_session = _make_chat_session(event_stream, session_info)
        chat_session.agent_controller.run_agent_async.return_value = ToolResult(
            llm_content="all good"
        )

        result = await chat_session.arun(query_content)

        assert result.is_error is not True
        # event_stream.publish should NOT have been called for ERROR
        for call in event_stream.publish.await_args_list:
            event = call[0][0]
            assert event.type != EventType.ERROR

    @pytest.mark.asyncio
    async def test_unknown_error_type_formats_message(self, event_stream, session_info, query_content):
        """Exception with empty str() should fall back to type name."""

        class SilentError(Exception):
            def __str__(self):
                return ""

        chat_session = _make_chat_session(
            event_stream,
            session_info,
            agent_side_effect=SilentError(),
        )

        await chat_session.arun(query_content)

        error_event = event_stream.publish.await_args_list[0][0][0]
        assert "SilentError" in error_event.content["message"]
