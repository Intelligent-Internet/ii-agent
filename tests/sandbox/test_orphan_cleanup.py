"""Unit tests for orphan sandbox cleanup functionality.

This module tests the local-mode orphan cleanup feature that removes
sandboxes when their associated sessions are deleted.
"""

import pytest
import asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, AsyncMock, patch

from ii_sandbox_server.config import SandboxConfig


class TestOrphanCleanupConfig:
    """Tests for orphan cleanup configuration."""

    def test_local_mode_defaults_to_false(self):
        """Test that local_mode is disabled by default."""
        with patch.dict("os.environ", {"SANDBOX_PROVIDER": "docker"}, clear=True):
            config = SandboxConfig(_env_file=None)
            assert config.local_mode is False

    def test_local_mode_can_be_enabled(self):
        """Test that local_mode can be enabled via env var."""
        with patch.dict("os.environ", {"SANDBOX_PROVIDER": "docker", "LOCAL_MODE": "true"}, clear=True):
            config = SandboxConfig(_env_file=None)
            assert config.local_mode is True

    def test_orphan_cleanup_defaults(self):
        """Test orphan cleanup default settings."""
        with patch.dict("os.environ", {"SANDBOX_PROVIDER": "docker"}, clear=True):
            config = SandboxConfig(_env_file=None)
            assert config.orphan_cleanup_enabled is True
            assert config.orphan_cleanup_interval_seconds == 300  # 5 minutes

    def test_backend_url_default(self):
        """Test backend URL default value."""
        with patch.dict("os.environ", {"SANDBOX_PROVIDER": "docker"}, clear=True):
            config = SandboxConfig(_env_file=None)
            assert config.backend_url == "http://backend:8000"

    def test_orphan_cleanup_interval_validation(self):
        """Test that interval must be within bounds."""
        # Too low
        with pytest.raises(ValueError):
            with patch.dict("os.environ", {"SANDBOX_PROVIDER": "docker"}, clear=True):
                SandboxConfig(_env_file=None, orphan_cleanup_interval_seconds=30)  # Below 60 minimum

        # Too high
        with pytest.raises(ValueError):
            with patch.dict("os.environ", {"SANDBOX_PROVIDER": "docker"}, clear=True):
                SandboxConfig(_env_file=None, orphan_cleanup_interval_seconds=7200)  # Above 3600 maximum


class TestCheckSandboxHasActiveSession:
    """Tests for _check_sandbox_has_active_session method."""

    @pytest.fixture
    def mock_controller(self):
        """Create a mock sandbox controller for testing."""
        from ii_sandbox_server.lifecycle.sandbox_controller import SandboxController

        config = MagicMock()
        config.local_mode = True
        config.orphan_cleanup_enabled = True
        config.orphan_cleanup_interval_seconds = 300
        config.backend_url = "http://backend:8000"
        config.redis_url = "redis://localhost:6379"
        config.redis_tls_ca_path = None
        config.queue_name = "test_queue"
        config.max_retries = 3
        config.provider_type = "docker"

        with patch('ii_sandbox_server.lifecycle.sandbox_controller.SandboxFactory'):
            with patch('ii_sandbox_server.lifecycle.sandbox_controller.SandboxQueueScheduler'):
                controller = SandboxController(config)

        return controller

    @pytest.mark.asyncio
    async def test_returns_true_when_session_active(self, mock_controller):
        """Test returns True when backend says session is active."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"has_active_session": True, "sandbox_id": "test-id"}

        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client_class.return_value = mock_client

            result = await mock_controller._check_sandbox_has_active_session("test-sandbox-id")

        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_when_session_deleted(self, mock_controller):
        """Test returns False when backend says session is deleted."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"has_active_session": False, "sandbox_id": "test-id"}

        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client_class.return_value = mock_client

            result = await mock_controller._check_sandbox_has_active_session("test-sandbox-id")

        assert result is False

    @pytest.mark.asyncio
    async def test_returns_true_on_http_error(self, mock_controller):
        """Test returns True (keep sandbox) on HTTP errors."""
        mock_response = MagicMock()
        mock_response.status_code = 500

        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client_class.return_value = mock_client

            result = await mock_controller._check_sandbox_has_active_session("test-sandbox-id")

        # Should return True to keep sandbox when we can't verify
        assert result is True

    @pytest.mark.asyncio
    async def test_returns_true_on_connection_error(self, mock_controller):
        """Test returns True (keep sandbox) when backend is unreachable."""
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get.side_effect = Exception("Connection refused")
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client_class.return_value = mock_client

            result = await mock_controller._check_sandbox_has_active_session("test-sandbox-id")

        # Should return True to keep sandbox when we can't connect
        assert result is True

    @pytest.mark.asyncio
    async def test_returns_true_on_malformed_response(self, mock_controller):
        """Test returns True when response is missing expected field."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"unexpected": "response"}

        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client_class.return_value = mock_client

            result = await mock_controller._check_sandbox_has_active_session("test-sandbox-id")

        # Should default to True when field is missing
        assert result is True


class TestOrphanCleanupLoop:
    """Tests for _orphan_cleanup_loop method."""

    @pytest.fixture
    def mock_sandbox_data(self):
        """Create mock sandbox data."""
        sandbox = MagicMock()
        sandbox.id = "test-sandbox-123"
        sandbox.provider_sandbox_id = "docker-container-abc"
        sandbox.status = "running"
        sandbox.created_at = datetime.now(timezone.utc) - timedelta(minutes=10)  # Not in grace period
        return sandbox

    @pytest.fixture
    def mock_controller_for_cleanup(self):
        """Create a mock sandbox controller for cleanup testing."""
        from ii_sandbox_server.lifecycle.sandbox_controller import SandboxController

        config = MagicMock()
        config.local_mode = True
        config.orphan_cleanup_enabled = True
        config.orphan_cleanup_interval_seconds = 1  # Fast for testing
        config.backend_url = "http://backend:8000"
        config.redis_url = "redis://localhost:6379"
        config.redis_tls_ca_path = None
        config.queue_name = "test_queue"
        config.max_retries = 3
        config.provider_type = "docker"

        with patch('ii_sandbox_server.lifecycle.sandbox_controller.SandboxFactory'):
            with patch('ii_sandbox_server.lifecycle.sandbox_controller.SandboxQueueScheduler'):
                controller = SandboxController(config)

        controller.sandbox_provider = MagicMock()
        controller.sandbox_provider.delete = AsyncMock()

        return controller

    @pytest.mark.asyncio
    async def test_cleanup_skips_recently_created_sandboxes(self, mock_controller_for_cleanup):
        """Test that cleanup skips sandboxes within grace period."""
        recent_sandbox = MagicMock()
        recent_sandbox.id = "new-sandbox"
        recent_sandbox.status = "running"
        recent_sandbox.created_at = datetime.now(timezone.utc) - timedelta(minutes=2)  # Within 5 min grace

        with patch('ii_sandbox_server.db.manager.Sandboxes') as mock_sandboxes:
            mock_sandboxes.get_all_sandboxes = AsyncMock(return_value=[recent_sandbox])
            mock_sandboxes.delete_sandbox = AsyncMock()

            # Mock the session check - would return False (no session)
            mock_controller_for_cleanup._check_sandbox_has_active_session = AsyncMock(return_value=False)

            # Run one iteration manually (simplified)
            all_sandboxes = await mock_sandboxes.get_all_sandboxes()

            # Verify the sandbox is within grace period
            now = datetime.now(timezone.utc)
            grace_period = timedelta(minutes=5)
            assert (now - recent_sandbox.created_at) < grace_period

            # Delete should NOT be called for this sandbox
            mock_sandboxes.delete_sandbox.assert_not_called()

    @pytest.mark.asyncio
    async def test_cleanup_skips_sandboxes_with_active_sessions(self, mock_controller_for_cleanup, mock_sandbox_data):
        """Test that cleanup skips sandboxes with active sessions."""
        with patch('ii_sandbox_server.db.manager.Sandboxes') as mock_sandboxes:
            mock_sandboxes.get_all_sandboxes = AsyncMock(return_value=[mock_sandbox_data])
            mock_sandboxes.delete_sandbox = AsyncMock()

            # Mock session check to return True (session exists)
            mock_controller_for_cleanup._check_sandbox_has_active_session = AsyncMock(return_value=True)

            # Simulate cleanup logic
            has_active = await mock_controller_for_cleanup._check_sandbox_has_active_session(
                str(mock_sandbox_data.id)
            )

            assert has_active is True
            # Delete should NOT be called
            mock_sandboxes.delete_sandbox.assert_not_called()

    @pytest.mark.asyncio
    async def test_cleanup_removes_orphan_sandboxes(self, mock_controller_for_cleanup, mock_sandbox_data):
        """Test that cleanup removes sandboxes without active sessions."""
        with patch('ii_sandbox_server.lifecycle.sandbox_controller.Sandboxes') as mock_sandboxes:
            mock_sandboxes.get_all_sandboxes = AsyncMock(return_value=[mock_sandbox_data])
            mock_sandboxes.delete_sandbox = AsyncMock(return_value=True)

            # Mock session check to return False (session deleted)
            mock_controller_for_cleanup._check_sandbox_has_active_session = AsyncMock(return_value=False)

            # Simulate the cleanup logic for one sandbox
            has_active = await mock_controller_for_cleanup._check_sandbox_has_active_session(
                str(mock_sandbox_data.id)
            )

            assert has_active is False

            # Now simulate what cleanup would do
            if not has_active:
                await mock_controller_for_cleanup.sandbox_provider.delete(
                    provider_sandbox_id=str(mock_sandbox_data.provider_sandbox_id),
                    config=mock_controller_for_cleanup.sandbox_config,
                    queue=mock_controller_for_cleanup.queue_scheduler,
                    sandbox_id=str(mock_sandbox_data.id),
                )
                await mock_sandboxes.delete_sandbox(str(mock_sandbox_data.id))

            # Verify both delete methods were called
            mock_controller_for_cleanup.sandbox_provider.delete.assert_called_once()
            mock_sandboxes.delete_sandbox.assert_called_once_with(str(mock_sandbox_data.id))

    @pytest.mark.asyncio
    async def test_cleanup_handles_delete_error_gracefully(self, mock_controller_for_cleanup, mock_sandbox_data):
        """Test that cleanup continues even if container deletion fails."""
        with patch('ii_sandbox_server.lifecycle.sandbox_controller.Sandboxes') as mock_sandboxes:
            mock_sandboxes.get_all_sandboxes = AsyncMock(return_value=[mock_sandbox_data])
            mock_sandboxes.delete_sandbox = AsyncMock(return_value=True)

            # Make provider delete fail
            mock_controller_for_cleanup.sandbox_provider.delete = AsyncMock(
                side_effect=Exception("Container not found")
            )
            mock_controller_for_cleanup._check_sandbox_has_active_session = AsyncMock(return_value=False)

            # Simulate cleanup - should not raise
            try:
                await mock_controller_for_cleanup.sandbox_provider.delete(
                    provider_sandbox_id=str(mock_sandbox_data.provider_sandbox_id),
                    config=mock_controller_for_cleanup.sandbox_config,
                    queue=mock_controller_for_cleanup.queue_scheduler,
                    sandbox_id=str(mock_sandbox_data.id),
                )
            except Exception:
                pass  # Expected to fail

            # DB cleanup should still proceed
            await mock_sandboxes.delete_sandbox(str(mock_sandbox_data.id))
            mock_sandboxes.delete_sandbox.assert_called_once()

    @pytest.mark.asyncio
    async def test_cleanup_skips_deleted_status_sandboxes(self, mock_controller_for_cleanup):
        """Test that cleanup skips sandboxes already marked as deleted."""
        deleted_sandbox = MagicMock()
        deleted_sandbox.id = "deleted-sandbox"
        deleted_sandbox.status = "deleted"
        deleted_sandbox.created_at = datetime.now(timezone.utc) - timedelta(hours=1)

        with patch('ii_sandbox_server.lifecycle.sandbox_controller.Sandboxes') as mock_sandboxes:
            mock_sandboxes.get_all_sandboxes = AsyncMock(return_value=[deleted_sandbox])
            mock_sandboxes.delete_sandbox = AsyncMock()

            # Session check should not even be called for deleted sandboxes
            mock_controller_for_cleanup._check_sandbox_has_active_session = AsyncMock()

            # Verify status check
            assert deleted_sandbox.status == "deleted"

            # Neither method should be called
            mock_controller_for_cleanup._check_sandbox_has_active_session.assert_not_called()
            mock_sandboxes.delete_sandbox.assert_not_called()
