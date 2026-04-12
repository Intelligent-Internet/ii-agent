"""Unit tests for SandboxSettings configuration."""

import pytest

from ii_agent.core.config.sandbox import SandboxSettings


class TestSandboxSettingsDefaults:
    """Tests for default field values."""

    def test_default_provider(self):
        settings = SandboxSettings()
        assert settings.provider == "e2b"

    def test_default_port_fields(self):
        settings = SandboxSettings()
        assert settings.mcp_server_port == 6060
        assert settings.code_server_port == 9000
        assert settings.novnc_port == 6080

    def test_default_local_mode_disabled(self):
        settings = SandboxSettings()
        assert settings.local_mode is False

    def test_default_orphan_cleanup_enabled(self):
        settings = SandboxSettings()
        assert settings.orphan_cleanup_enabled is True

    def test_default_docker_network(self):
        settings = SandboxSettings()
        assert settings.docker_network == "ii-agent-local_ii-network"

    def test_default_port_range(self):
        settings = SandboxSettings()
        assert settings.port_range_start == 30000
        assert settings.port_range_end == 30999


class TestSandboxSettingsValidation:
    """Tests for validate_for_provider method."""

    def test_e2b_without_api_key_raises(self):
        settings = SandboxSettings(provider="e2b", e2b_api_key=None)
        with pytest.raises(ValueError, match="E2B API key is required"):
            settings.validate_for_provider()

    def test_e2b_with_api_key_passes(self):
        settings = SandboxSettings(provider="e2b", e2b_api_key="test-key")
        settings.validate_for_provider()  # Should not raise

    def test_docker_without_api_key_passes(self):
        settings = SandboxSettings(provider="docker", e2b_api_key=None)
        settings.validate_for_provider()  # Should not raise

    def test_local_without_api_key_passes(self):
        settings = SandboxSettings(provider="local", e2b_api_key=None)
        settings.validate_for_provider()  # Should not raise


class TestSandboxSettingsCustomValues:
    """Tests for overriding default values."""

    def test_custom_port_fields(self):
        settings = SandboxSettings(
            mcp_server_port=7070,
            code_server_port=8000,
            novnc_port=7080,
        )
        assert settings.mcp_server_port == 7070
        assert settings.code_server_port == 8000
        assert settings.novnc_port == 7080

    def test_docker_provider(self):
        settings = SandboxSettings(provider="docker")
        assert settings.provider == "docker"

    def test_local_mode_enabled(self):
        settings = SandboxSettings(local_mode=True)
        assert settings.local_mode is True
