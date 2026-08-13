"""Tests for ii_agent.integrations.connectors.composio.client — ComposioClient singleton."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


class TestComposioClient:
    def setup_method(self):
        from ii_agent.integrations.connectors.composio.client import ComposioClient

        ComposioClient.reset()

    def teardown_method(self):
        from ii_agent.integrations.connectors.composio.client import ComposioClient

        ComposioClient.reset()

    def test_get_client_no_key_raises(self):
        """Lines 28-33, branch [28,29],[30,31]: no key → ValueError."""
        from ii_agent.integrations.connectors.composio.client import ComposioClient

        with patch("ii_agent.integrations.connectors.composio.client.get_settings") as ms:
            ms.return_value.composio_api_key = None
            try:
                ComposioClient.get_client(api_key=None)
                assert False, "Should raise ValueError"
            except ValueError as e:
                assert "COMPOSIO_API_KEY" in str(e)

    def test_get_client_with_explicit_key(self):
        """Lines 29-36: uses explicit api_key, creates Composio instance."""
        from ii_agent.integrations.connectors.composio.client import ComposioClient

        with patch("ii_agent.integrations.connectors.composio.client.Composio") as mock_composio:
            mock_composio.return_value = MagicMock()
            result = ComposioClient.get_client(api_key="test-key-123")
            mock_composio.assert_called_once_with(api_key="test-key-123")

    def test_get_client_with_settings_key(self):
        """Lines 29-36: uses key from settings."""
        from ii_agent.integrations.connectors.composio.client import ComposioClient

        with patch("ii_agent.integrations.connectors.composio.client.get_settings") as ms:
            ms.return_value.composio_api_key = "settings-key"
            with patch("ii_agent.integrations.connectors.composio.client.Composio") as mc:
                mc.return_value = MagicMock()
                result = ComposioClient.get_client()
                mc.assert_called_once_with(api_key="settings-key")

    def test_get_client_returns_same_singleton(self):
        """Branch [28,38]: returns existing instance on second call."""
        from ii_agent.integrations.connectors.composio.client import ComposioClient

        with patch("ii_agent.integrations.connectors.composio.client.Composio") as mc:
            mc.return_value = MagicMock()
            first = ComposioClient.get_client(api_key="key1")
            second = ComposioClient.get_client(api_key="key1")
            assert mc.call_count == 1  # only created once
            assert first is second

    def test_reset_clears_singleton(self):
        """Line 43: reset() sets _instance to None."""
        from ii_agent.integrations.connectors.composio.client import ComposioClient

        with patch("ii_agent.integrations.connectors.composio.client.Composio") as mc:
            mc.return_value = MagicMock()
            ComposioClient.get_client(api_key="k")
            assert ComposioClient._instance is not None
            ComposioClient.reset()
            assert ComposioClient._instance is None
