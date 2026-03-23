"""Tests for AwakeSandboxHandler and SandboxStatusHandler changes.

Tests the new behavior where:
- After waking, sandbox status and vscode_url are returned in the event
- Port is only exposed when status == 'running'
- Exceptions during port exposure are caught and logged

Handler imports are deferred to test time to avoid triggering the full
server import chain at collection time (which causes module identity
issues with ii_tool.logger in the broader test suite).
"""

import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

from ii_agent.core.event import EventType, RealtimeEvent


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
    return stream


@pytest.fixture
def AwakeSandboxHandler():
    from ii_agent.server.socket.command.awake_sandbox_handler import AwakeSandboxHandler
    return AwakeSandboxHandler


@pytest.fixture
def SandboxStatusHandler():
    from ii_agent.server.socket.command.sandbox_status_handler import SandboxStatusHandler
    return SandboxStatusHandler


class TestAwakeSandboxHandler:
    """Tests for AwakeSandboxHandler.handle()."""

    @pytest.mark.asyncio
    @patch("ii_agent.server.socket.command.awake_sandbox_handler.config")
    @patch("ii_agent.server.socket.command.awake_sandbox_handler.sandbox_service")
    async def test_running_sandbox_exposes_port(self, mock_service, mock_config, event_stream, session_info, AwakeSandboxHandler):
        mock_config.vscode_port = 9000
        mock_service.wake_up_sandbox_by_session = AsyncMock()

        mock_sandbox = MagicMock()
        type(mock_sandbox).status = PropertyMock(return_value=AsyncMock(return_value="running")())
        mock_sandbox.expose_port = AsyncMock(return_value="http://localhost:30001")
        mock_service.get_sandbox_by_session_id = AsyncMock(return_value=mock_sandbox)

        handler = AwakeSandboxHandler(event_stream)
        await handler.handle({}, session_info)

        mock_service.wake_up_sandbox_by_session.assert_awaited_once_with(session_info.id)
        mock_sandbox.expose_port.assert_awaited_once_with(9000, external=True)

        event_stream.publish.assert_awaited_once()
        event = event_stream.publish.call_args[0][0]
        assert event.type == EventType.SANDBOX_STATUS
        assert event.content["status"] == "running"
        assert event.content["vscode_url"] == "http://localhost:30001"

    @pytest.mark.asyncio
    @patch("ii_agent.server.socket.command.awake_sandbox_handler.config")
    @patch("ii_agent.server.socket.command.awake_sandbox_handler.sandbox_service")
    async def test_paused_sandbox_no_port_exposure(self, mock_service, mock_config, event_stream, session_info, AwakeSandboxHandler):
        mock_config.vscode_port = 9000
        mock_service.wake_up_sandbox_by_session = AsyncMock()

        mock_sandbox = MagicMock()
        type(mock_sandbox).status = PropertyMock(return_value=AsyncMock(return_value="paused")())
        mock_sandbox.expose_port = AsyncMock()
        mock_service.get_sandbox_by_session_id = AsyncMock(return_value=mock_sandbox)

        handler = AwakeSandboxHandler(event_stream)
        await handler.handle({}, session_info)

        mock_sandbox.expose_port.assert_not_awaited()

        event = event_stream.publish.call_args[0][0]
        assert event.content["status"] == "paused"
        assert event.content["vscode_url"] is None

    @pytest.mark.asyncio
    @patch("ii_agent.server.socket.command.awake_sandbox_handler.config")
    @patch("ii_agent.server.socket.command.awake_sandbox_handler.sandbox_service")
    async def test_no_sandbox_returns_not_initialized(self, mock_service, mock_config, event_stream, session_info, AwakeSandboxHandler):
        mock_service.wake_up_sandbox_by_session = AsyncMock()
        mock_service.get_sandbox_by_session_id = AsyncMock(return_value=None)

        handler = AwakeSandboxHandler(event_stream)
        await handler.handle({}, session_info)

        event = event_stream.publish.call_args[0][0]
        assert event.content["status"] == "not initialized"
        assert event.content["vscode_url"] is None

    @pytest.mark.asyncio
    @patch("ii_agent.server.socket.command.awake_sandbox_handler.config")
    @patch("ii_agent.server.socket.command.awake_sandbox_handler.sandbox_service")
    async def test_port_exposure_failure_is_caught(self, mock_service, mock_config, event_stream, session_info, AwakeSandboxHandler):
        mock_config.vscode_port = 9000
        mock_service.wake_up_sandbox_by_session = AsyncMock()

        mock_sandbox = MagicMock()
        type(mock_sandbox).status = PropertyMock(return_value=AsyncMock(return_value="running")())
        mock_sandbox.expose_port = AsyncMock(side_effect=RuntimeError("port failed"))
        mock_service.get_sandbox_by_session_id = AsyncMock(return_value=mock_sandbox)

        handler = AwakeSandboxHandler(event_stream)
        await handler.handle({}, session_info)

        # Should still emit the event with None vscode_url
        event = event_stream.publish.call_args[0][0]
        assert event.content["status"] == "running"
        assert event.content["vscode_url"] is None


class TestSandboxStatusHandler:
    """Tests for SandboxStatusHandler.handle()."""

    @pytest.mark.asyncio
    @patch("ii_agent.server.socket.command.sandbox_status_handler.config")
    @patch("ii_agent.server.socket.command.sandbox_status_handler.sandbox_service")
    async def test_running_sandbox_exposes_port(self, mock_service, mock_config, event_stream, session_info, SandboxStatusHandler):
        mock_config.vscode_port = 9000

        mock_sandbox = MagicMock()
        type(mock_sandbox).status = PropertyMock(return_value=AsyncMock(return_value="running")())
        mock_sandbox.expose_port = AsyncMock(return_value="http://localhost:30002")
        mock_service.get_sandbox_by_session_id = AsyncMock(return_value=mock_sandbox)

        handler = SandboxStatusHandler(event_stream)
        await handler.handle({}, session_info)

        mock_sandbox.expose_port.assert_awaited_once_with(9000, external=True)
        event = event_stream.publish.call_args[0][0]
        assert event.content["status"] == "running"
        assert event.content["vscode_url"] == "http://localhost:30002"

    @pytest.mark.asyncio
    @patch("ii_agent.server.socket.command.sandbox_status_handler.config")
    @patch("ii_agent.server.socket.command.sandbox_status_handler.sandbox_service")
    async def test_paused_sandbox_no_port_exposure(self, mock_service, mock_config, event_stream, session_info, SandboxStatusHandler):
        mock_config.vscode_port = 9000

        mock_sandbox = MagicMock()
        type(mock_sandbox).status = PropertyMock(return_value=AsyncMock(return_value="paused")())
        mock_sandbox.expose_port = AsyncMock()
        mock_service.get_sandbox_by_session_id = AsyncMock(return_value=mock_sandbox)

        handler = SandboxStatusHandler(event_stream)
        await handler.handle({}, session_info)

        mock_sandbox.expose_port.assert_not_awaited()
        event = event_stream.publish.call_args[0][0]
        assert event.content["status"] == "paused"
        assert event.content["vscode_url"] is None

    @pytest.mark.asyncio
    @patch("ii_agent.server.socket.command.sandbox_status_handler.config")
    @patch("ii_agent.server.socket.command.sandbox_status_handler.sandbox_service")
    async def test_no_sandbox_returns_not_initialized(self, mock_service, mock_config, event_stream, session_info, SandboxStatusHandler):
        mock_service.get_sandbox_by_session_id = AsyncMock(return_value=None)

        handler = SandboxStatusHandler(event_stream)
        await handler.handle({}, session_info)

        event = event_stream.publish.call_args[0][0]
        assert event.content["status"] == "not initialized"
        assert event.content["vscode_url"] is None

    @pytest.mark.asyncio
    @patch("ii_agent.server.socket.command.sandbox_status_handler.config")
    @patch("ii_agent.server.socket.command.sandbox_status_handler.sandbox_service")
    async def test_port_exposure_failure_is_caught(self, mock_service, mock_config, event_stream, session_info, SandboxStatusHandler):
        mock_config.vscode_port = 9000

        mock_sandbox = MagicMock()
        type(mock_sandbox).status = PropertyMock(return_value=AsyncMock(return_value="running")())
        mock_sandbox.expose_port = AsyncMock(side_effect=ConnectionError("no container"))
        mock_service.get_sandbox_by_session_id = AsyncMock(return_value=mock_sandbox)

        handler = SandboxStatusHandler(event_stream)
        await handler.handle({}, session_info)

        event = event_stream.publish.call_args[0][0]
        assert event.content["status"] == "running"
        assert event.content["vscode_url"] is None
