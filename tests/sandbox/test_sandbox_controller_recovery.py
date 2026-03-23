"""Tests for SandboxController stale-running container recovery.

When a container has stopped (e.g., system restart) but the database still
says "running", `connect()` should catch SandboxNotInitializedError from
`_connect_sandbox` and fall back to `_resume_sandbox`.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from ii_sandbox_server.lifecycle.sandbox_controller import SandboxController
from ii_sandbox_server.models.exceptions import (
    SandboxNotInitializedError,
    SandboxNotFoundException,
)


@pytest.fixture
def controller():
    ctrl = SandboxController.__new__(SandboxController)
    ctrl._ensure_consumer_started = AsyncMock()
    ctrl._connect_sandbox = AsyncMock()
    ctrl._resume_sandbox = AsyncMock()
    return ctrl


def _make_sandbox_data(status: str):
    data = MagicMock()
    data.status = status
    return data


class TestStaleRunningRecovery:
    """Tests for connect() handling of stale 'running' status."""

    @pytest.mark.asyncio
    @patch("ii_sandbox_server.lifecycle.sandbox_controller.Sandboxes")
    async def test_running_sandbox_connects_normally(self, mock_sandboxes, controller):
        mock_sandboxes.get_sandbox_by_id = AsyncMock(return_value=_make_sandbox_data("running"))
        mock_sandbox = MagicMock()
        controller._connect_sandbox.return_value = mock_sandbox

        result = await controller.connect("sandbox-1")
        assert result is mock_sandbox
        controller._connect_sandbox.assert_awaited_once_with("sandbox-1")
        controller._resume_sandbox.assert_not_awaited()

    @pytest.mark.asyncio
    @patch("ii_sandbox_server.lifecycle.sandbox_controller.Sandboxes")
    async def test_stale_running_falls_back_to_resume(self, mock_sandboxes, controller):
        mock_sandboxes.get_sandbox_by_id = AsyncMock(return_value=_make_sandbox_data("running"))
        controller._connect_sandbox.side_effect = SandboxNotInitializedError("container gone")
        mock_sandbox = MagicMock()
        controller._resume_sandbox.return_value = mock_sandbox

        result = await controller.connect("sandbox-1")
        assert result is mock_sandbox
        controller._connect_sandbox.assert_awaited_once()
        controller._resume_sandbox.assert_awaited_once_with("sandbox-1")

    @pytest.mark.asyncio
    @patch("ii_sandbox_server.lifecycle.sandbox_controller.Sandboxes")
    async def test_paused_sandbox_resumes_directly(self, mock_sandboxes, controller):
        mock_sandboxes.get_sandbox_by_id = AsyncMock(return_value=_make_sandbox_data("paused"))
        mock_sandbox = MagicMock()
        controller._resume_sandbox.return_value = mock_sandbox

        result = await controller.connect("sandbox-1")
        assert result is mock_sandbox
        controller._connect_sandbox.assert_not_awaited()
        controller._resume_sandbox.assert_awaited_once_with("sandbox-1")

    @pytest.mark.asyncio
    @patch("ii_sandbox_server.lifecycle.sandbox_controller.Sandboxes")
    async def test_not_found_raises(self, mock_sandboxes, controller):
        mock_sandboxes.get_sandbox_by_id = AsyncMock(return_value=None)

        with pytest.raises(SandboxNotFoundException):
            await controller.connect("sandbox-missing")

    @pytest.mark.asyncio
    @patch("ii_sandbox_server.lifecycle.sandbox_controller.Sandboxes")
    async def test_unexpected_status_raises(self, mock_sandboxes, controller):
        mock_sandboxes.get_sandbox_by_id = AsyncMock(return_value=_make_sandbox_data("terminated"))

        with pytest.raises(SandboxNotInitializedError, match="not paused or running"):
            await controller.connect("sandbox-terminated")
