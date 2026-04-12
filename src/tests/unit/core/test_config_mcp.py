"""Tests for ii_agent.core.config.mcp — MCPSettings helpers."""

from __future__ import annotations


class TestMCPSettings:
    def test_has_oauth_credentials_true(self):
        from ii_agent.core.config.mcp import MCPSettings

        settings = MCPSettings()
        settings.oauth_client_id = "client-id"
        settings.oauth_client_secret = "client-secret"
        assert settings.has_oauth_credentials() is True

    def test_has_oauth_credentials_false_when_empty(self):
        from ii_agent.core.config.mcp import MCPSettings

        settings = MCPSettings()
        settings.oauth_client_id = ""
        settings.oauth_client_secret = ""
        assert settings.has_oauth_credentials() is False

    def test_has_external_oauth_true(self):
        from ii_agent.core.config.mcp import MCPSettings

        settings = MCPSettings()
        settings.ii_client_id = "external-client-id"
        assert settings.has_external_oauth() is True

    def test_has_external_oauth_false_when_empty(self):
        from ii_agent.core.config.mcp import MCPSettings

        settings = MCPSettings()
        settings.ii_client_id = ""
        assert settings.has_external_oauth() is False
