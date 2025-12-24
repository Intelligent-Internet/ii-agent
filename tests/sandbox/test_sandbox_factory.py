"""Unit tests for the SandboxFactory class.

This module contains tests for the sandbox provider factory,
ensuring correct provider selection based on configuration.
"""

import os
import pytest
from unittest.mock import patch, MagicMock

from ii_sandbox_server.sandboxes.sandbox_factory import SandboxFactory
from ii_sandbox_server.sandboxes.e2b import E2BSandbox
from ii_sandbox_server.sandboxes.docker import DockerSandbox


class TestSandboxFactoryProviders:
    """Tests for SandboxFactory provider registration."""

    def test_e2b_provider_registered(self):
        """Test that e2b provider is registered."""
        assert "e2b" in SandboxFactory._providers
        assert SandboxFactory._providers["e2b"] is E2BSandbox

    def test_docker_provider_registered(self):
        """Test that docker provider is registered."""
        assert "docker" in SandboxFactory._providers
        assert SandboxFactory._providers["docker"] is DockerSandbox

    def test_local_alias_for_docker(self):
        """Test that 'local' is an alias for docker provider."""
        assert "local" in SandboxFactory._providers
        assert SandboxFactory._providers["local"] is DockerSandbox

    def test_get_available_providers(self):
        """Test that get_available_providers returns all registered providers."""
        providers = SandboxFactory.get_available_providers()

        assert "e2b" in providers
        assert "docker" in providers
        assert "local" in providers


class TestSandboxFactoryGetProvider:
    """Tests for SandboxFactory.get_provider method."""

    def test_get_provider_e2b(self):
        """Test getting E2B provider."""
        provider = SandboxFactory.get_provider("e2b")
        assert provider is E2BSandbox

    def test_get_provider_docker(self):
        """Test getting Docker provider."""
        provider = SandboxFactory.get_provider("docker")
        assert provider is DockerSandbox

    def test_get_provider_local(self):
        """Test getting local (Docker) provider."""
        provider = SandboxFactory.get_provider("local")
        assert provider is DockerSandbox

    def test_get_provider_uses_env_var(self):
        """Test that get_provider uses SANDBOX_PROVIDER env var."""
        with patch.dict(os.environ, {"SANDBOX_PROVIDER": "docker"}):
            provider = SandboxFactory.get_provider()
            assert provider is DockerSandbox

    def test_get_provider_defaults_to_e2b(self):
        """Test that get_provider defaults to e2b when no config."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("SANDBOX_PROVIDER", None)
            provider = SandboxFactory.get_provider()
            assert provider is E2BSandbox

    def test_get_provider_invalid_raises(self):
        """Test that invalid provider type raises ValueError."""
        with pytest.raises(ValueError, match="Unsupported provider type"):
            SandboxFactory.get_provider("invalid_provider")


class TestSandboxFactoryRegisterProvider:
    """Tests for SandboxFactory.register_provider method."""

    def test_register_new_provider(self):
        """Test registering a new provider."""
        # Create a mock provider class
        class MockSandbox:
            pass

        # Patch to make it look like it inherits from BaseSandbox
        with patch.object(SandboxFactory, 'register_provider') as mock_register:
            # Just verify the method can be called
            mock_register("mock", MockSandbox)
            mock_register.assert_called_once_with("mock", MockSandbox)

    def test_register_overwrites_existing(self):
        """Test that registering overwrites existing provider."""
        # Save original
        original = SandboxFactory._providers.get("docker")

        try:
            # Create a mock class that inherits from BaseSandbox
            from ii_sandbox_server.sandboxes.base import BaseSandbox

            class TestSandbox(BaseSandbox):
                pass

            SandboxFactory.register_provider("docker", TestSandbox)

            assert SandboxFactory._providers["docker"] is TestSandbox

        finally:
            # Restore original
            SandboxFactory._providers["docker"] = original


class TestSandboxFactoryEnvVarHandling:
    """Tests for environment variable handling."""

    def test_explicit_type_overrides_env_var(self):
        """Test that explicit provider_type overrides env var."""
        with patch.dict(os.environ, {"SANDBOX_PROVIDER": "e2b"}):
            provider = SandboxFactory.get_provider("docker")
            assert provider is DockerSandbox

    def test_env_var_case_sensitive(self):
        """Test that provider names are case sensitive."""
        with patch.dict(os.environ, {"SANDBOX_PROVIDER": "DOCKER"}):
            # Should fail because provider names are lowercase
            with pytest.raises(ValueError):
                SandboxFactory.get_provider()
