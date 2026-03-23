"""Tests for SocketIOManager._handshake() status emission.

Covers the bug where a client reconnecting to a session with no running task
would not receive a STATUS_UPDATE(READY) event, leaving the UI stuck in a
"running" state from a previous task.
"""

import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from ii_agent.core.event import AgentStatus, EventType


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


def _make_sio_manager():
    """Build a SocketIOManager with a mocked sio server."""
    from ii_agent.server.socket.socketio import SocketIOManager

    sio = MagicMock()
    sio.emit = AsyncMock()
    mgr = SocketIOManager(sio)
    return mgr


class TestHandshakeStatusEmission:
    """Tests for _handshake correctly emitting status to connecting clients."""

    @pytest.mark.asyncio
    @patch("ii_agent.server.socket.socketio.get_db_session_local")
    @patch("ii_agent.server.socket.socketio.config")
    async def test_no_running_task_emits_ready(
        self, mock_config, mock_get_db, session_info
    ):
        """When there is no running task, handshake should emit READY to the sid."""
        mock_config.workspace_path = "/workspace"
        mgr = _make_sio_manager()
        sid = "socket-123"

        # Mock DB: no running task
        mock_db = MagicMock()
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_get_db.return_value = mock_ctx

        with patch(
            "ii_agent.server.socket.socketio.AgentRunTask.find_last_by_session_id_and_status",
            new_callable=AsyncMock,
            return_value=None,
        ):
            await mgr._handshake(sid, session_info)

        # Should have emitted two events: connection_established + status_update
        calls = mgr.sio.emit.await_args_list
        assert len(calls) == 2

        # First: connection_established to the sid
        first_call = calls[0]
        assert first_call.args[0] == "chat_event"
        assert first_call.args[1]["type"] == EventType.CONNECTION_ESTABLISHED

        # Second: status_update READY to the sid (not the room)
        second_call = calls[1]
        assert second_call.args[0] == "chat_event"
        assert second_call.args[1]["type"] == EventType.STATUS_UPDATE
        assert second_call.args[1]["content"]["status"] == AgentStatus.READY
        assert second_call.kwargs.get("room") == str(sid)

    @pytest.mark.asyncio
    @patch("ii_agent.server.socket.socketio.get_db_session_local")
    @patch("ii_agent.server.socket.socketio.config")
    async def test_running_task_emits_running(
        self, mock_config, mock_get_db, session_info
    ):
        """When there IS a running task, handshake should emit RUNNING to the session room."""
        mock_config.workspace_path = "/workspace"
        mgr = _make_sio_manager()
        sid = "socket-456"

        running_task = MagicMock()
        running_task.id = uuid.uuid4()

        mock_db = MagicMock()
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_get_db.return_value = mock_ctx

        with patch(
            "ii_agent.server.socket.socketio.AgentRunTask.find_last_by_session_id_and_status",
            new_callable=AsyncMock,
            return_value=running_task,
        ):
            await mgr._handshake(sid, session_info)

        calls = mgr.sio.emit.await_args_list
        assert len(calls) == 2

        # Second event: status_update RUNNING to the session room
        second_call = calls[1]
        assert second_call.args[1]["type"] == EventType.STATUS_UPDATE
        assert second_call.args[1]["content"]["status"] == AgentStatus.RUNNING
        assert second_call.kwargs.get("room") == str(session_info.id)

    @pytest.mark.asyncio
    @patch("ii_agent.server.socket.socketio.get_db_session_local")
    @patch("ii_agent.server.socket.socketio.config")
    async def test_connection_established_always_sent(
        self, mock_config, mock_get_db, session_info
    ):
        """CONNECTION_ESTABLISHED event must always be sent, regardless of task state."""
        mock_config.workspace_path = "/workspace"
        mgr = _make_sio_manager()
        sid = "socket-789"

        mock_db = MagicMock()
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_get_db.return_value = mock_ctx

        with patch(
            "ii_agent.server.socket.socketio.AgentRunTask.find_last_by_session_id_and_status",
            new_callable=AsyncMock,
            return_value=None,
        ):
            await mgr._handshake(sid, session_info)

        first_call = mgr.sio.emit.await_args_list[0]
        content = first_call.args[1]
        assert content["type"] == EventType.CONNECTION_ESTABLISHED
        assert "workspace_path" in content["content"]
