"""Tests for SocketIOManager._extract_client_host().

Validates hostname extraction from ASGI environ dict used by Socket.IO,
covering X-Forwarded-Host, Host header, port stripping, and fallbacks.
"""

import pytest


def _make_manager():
    """Create a SocketIOManager with minimal mocked dependencies."""
    from unittest.mock import MagicMock, AsyncMock

    # SocketIOManager expects a socketio.AsyncServer and CommandFactory
    mock_sio = MagicMock()
    mock_sio.on = MagicMock()
    mock_sio.save_session = AsyncMock()

    from ii_agent.server.socket.socketio import SocketIOManager
    manager = SocketIOManager.__new__(SocketIOManager)
    manager.sio = mock_sio
    return manager


class TestExtractClientHost:
    """Tests for _extract_client_host."""

    def test_host_header_without_port(self):
        manager = _make_manager()
        env = {"HTTP_HOST": "192.168.2.2"}
        assert manager._extract_client_host(env) == "192.168.2.2"

    def test_host_header_with_port(self):
        manager = _make_manager()
        env = {"HTTP_HOST": "192.168.2.2:8000"}
        assert manager._extract_client_host(env) == "192.168.2.2"

    def test_x_forwarded_host_takes_precedence(self):
        manager = _make_manager()
        env = {
            "HTTP_X_FORWARDED_HOST": "myproxy.example.com:443",
            "HTTP_HOST": "backend:8000",
        }
        assert manager._extract_client_host(env) == "myproxy.example.com"

    def test_localhost_returned_when_empty(self):
        manager = _make_manager()
        assert manager._extract_client_host({}) == "localhost"

    def test_localhost_returned_when_host_is_empty_string(self):
        manager = _make_manager()
        env = {"HTTP_HOST": ""}
        assert manager._extract_client_host(env) == "localhost"

    def test_plain_localhost(self):
        manager = _make_manager()
        env = {"HTTP_HOST": "localhost"}
        assert manager._extract_client_host(env) == "localhost"

    def test_localhost_with_port(self):
        manager = _make_manager()
        env = {"HTTP_HOST": "localhost:8000"}
        assert manager._extract_client_host(env) == "localhost"
