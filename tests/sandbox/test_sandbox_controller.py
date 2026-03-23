"""Tests for SandboxController.connect() fallback logic.

When a sandbox is marked 'running' in the DB but the container is gone,
_connect_sandbox raises SandboxNotInitializedError and connect() falls
back to _resume_sandbox.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from ii_sandbox_server.models.exceptions import (
    SandboxNotFoundException,
    SandboxNotInitializedError,
)
from ii_sandbox_server.lifecycle.sandbox_controller import SandboxController


@pytest.fixture
def controller():
    """Create a SandboxController with mocked dependencies."""
    mock_config = MagicMock()
    mock_config.provider_type = "docker"
    mock_config.redis_url = "redis://localhost"
    mock_config.redis_tls_ca_path = None
    mock_config.queue_name = "test"
    mock_config.max_retries = 3

    with patch("ii_sandbox_server.lifecycle.sandbox_controller.SandboxFactory"):
        with patch("ii_sandbox_server.lifecycle.sandbox_controller.SandboxQueueScheduler"):
            ctrl = SandboxController(mock_config)

    ctrl._ensure_consumer_started = AsyncMock()
    return ctrl


class TestSandboxControllerConnectFallback:
    """Tests for connect() method's SandboxNotInitializedError fallback."""

    @pytest.mark.asyncio
    @patch("ii_sandbox_server.lifecycle.sandbox_controller.Sandboxes")
    async def test_running_sandbox_connects_normally(self, mock_sandboxes, controller):
        sandbox_data = MagicMock()
        sandbox_data.status = "running"
        mock_sandboxes.get_sandbox_by_id = AsyncMock(return_value=sandbox_data)

        mock_sandbox = MagicMock()
        controller._connect_sandbox = AsyncMock(return_value=mock_sandbox)

        result = await controller.connect("sb-1")

        controller._connect_sandbox.assert_awaited_once_with("sb-1")
        assert result == mock_sandbox

    @pytest.mark.asyncio
    @patch("ii_sandbox_server.lifecycle.sandbox_controller.Sandboxes")
    async def test_running_sandbox_fallback_to_resume_on_not_initialized(self, mock_sandboxes, controller):
        sandbox_data = MagicMock()
        sandbox_data.status = "running"
        mock_sandboxes.get_sandbox_by_id = AsyncMock(return_value=sandbox_data)

        controller._connect_sandbox = AsyncMock(
            side_effect=SandboxNotInitializedError("container gone")
        )
        mock_resumed = MagicMock()
        controller._resume_sandbox = AsyncMock(return_value=mock_resumed)

        result = await controller.connect("sb-1")

        controller._connect_sandbox.assert_awaited_once_with("sb-1")
        controller._resume_sandbox.assert_awaited_once_with("sb-1")
        assert result == mock_resumed

    @pytest.mark.asyncio
    @patch("ii_sandbox_server.lifecycle.sandbox_controller.Sandboxes")
    async def test_paused_sandbox_goes_to_resume(self, mock_sandboxes, controller):
        sandbox_data = MagicMock()
        sandbox_data.status = "paused"
        mock_sandboxes.get_sandbox_by_id = AsyncMock(return_value=sandbox_data)

        mock_sandbox = MagicMock()
        controller._resume_sandbox = AsyncMock(return_value=mock_sandbox)

        result = await controller.connect("sb-2")

        controller._resume_sandbox.assert_awaited_once_with("sb-2")
        assert result == mock_sandbox

    @pytest.mark.asyncio
    @patch("ii_sandbox_server.lifecycle.sandbox_controller.Sandboxes")
    async def test_unknown_status_raises_not_initialized(self, mock_sandboxes, controller):
        sandbox_data = MagicMock()
        sandbox_data.status = "terminated"
        mock_sandboxes.get_sandbox_by_id = AsyncMock(return_value=sandbox_data)

        with pytest.raises(SandboxNotInitializedError):
            await controller.connect("sb-3")

    @pytest.mark.asyncio
    @patch("ii_sandbox_server.lifecycle.sandbox_controller.Sandboxes")
    async def test_missing_sandbox_raises_not_found(self, mock_sandboxes, controller):
        mock_sandboxes.get_sandbox_by_id = AsyncMock(return_value=None)

        with pytest.raises(SandboxNotFoundException):
            await controller.connect("sb-missing")
