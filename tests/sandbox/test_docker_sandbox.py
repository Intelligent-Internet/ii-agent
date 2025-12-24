"""Unit tests for the DockerSandbox class.

This module contains tests for the Docker-based local sandbox provider,
including path validation, command sanitization, and container operations.
"""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from pathlib import PurePosixPath

from ii_sandbox_server.sandboxes.docker import (
    DockerSandbox,
    ALLOWED_WORKSPACE_BASES,
    DANGEROUS_PATTERNS,
)


class TestDockerSandboxPathValidation:
    """Tests for path validation in DockerSandbox."""

    def test_validate_path_normal_relative(self):
        """Test validation of normal relative paths."""
        result = DockerSandbox._validate_path("file.txt")
        assert result == "file.txt"

    def test_validate_path_nested_relative(self):
        """Test validation of nested relative paths."""
        result = DockerSandbox._validate_path("dir/subdir/file.txt")
        assert result == "dir/subdir/file.txt"

    def test_validate_path_absolute_in_workspace(self):
        """Test validation of absolute paths in allowed directories."""
        result = DockerSandbox._validate_path("/workspace/project/file.py")
        assert result == "/workspace/project/file.py"

    def test_validate_path_absolute_in_tmp(self):
        """Test validation of absolute paths in /tmp."""
        result = DockerSandbox._validate_path("/tmp/scratch/output.txt")
        assert result == "/tmp/scratch/output.txt"

    def test_validate_path_absolute_in_home(self):
        """Test validation of absolute paths in /home."""
        result = DockerSandbox._validate_path("/home/user/.config")
        assert result == "/home/user/.config"

    def test_validate_path_rejects_empty(self):
        """Test that empty paths are rejected."""
        with pytest.raises(ValueError, match="Path cannot be empty"):
            DockerSandbox._validate_path("")

    def test_validate_path_rejects_path_traversal(self):
        """Test that path traversal attempts are rejected."""
        with pytest.raises(ValueError, match="Invalid path"):
            DockerSandbox._validate_path("../../../etc/passwd")

    def test_validate_path_rejects_hidden_traversal(self):
        """Test that hidden path traversal is rejected."""
        with pytest.raises(ValueError, match="Invalid path"):
            DockerSandbox._validate_path("/workspace/project/../../etc/shadow")

    def test_validate_path_rejects_disallowed_absolute(self):
        """Test that absolute paths outside allowed dirs are rejected."""
        with pytest.raises(ValueError, match="Path must be within allowed directories"):
            DockerSandbox._validate_path("/etc/passwd")

    def test_validate_path_rejects_sys_proc(self):
        """Test that /sys and /proc are rejected."""
        with pytest.raises(ValueError, match="Path must be within allowed directories"):
            DockerSandbox._validate_path("/sys/kernel/config")

        with pytest.raises(ValueError, match="Path must be within allowed directories"):
            DockerSandbox._validate_path("/proc/self/environ")

    def test_validate_path_disallow_absolute_flag(self):
        """Test that allow_absolute=False rejects absolute paths."""
        with pytest.raises(ValueError, match="Absolute paths not allowed"):
            DockerSandbox._validate_path("/workspace/file.txt", allow_absolute=False)


class TestDockerSandboxCommandSanitization:
    """Tests for command sanitization in DockerSandbox."""

    def test_sanitize_command_normal(self):
        """Test that normal commands pass through."""
        result = DockerSandbox._sanitize_command("echo hello")
        assert result == "echo hello"

    def test_sanitize_command_with_args(self):
        """Test commands with arguments pass in non-strict mode."""
        result = DockerSandbox._sanitize_command("ls -la /workspace")
        assert result == "ls -la /workspace"

    def test_sanitize_command_rejects_empty(self):
        """Test that empty commands are rejected."""
        with pytest.raises(ValueError, match="Command cannot be empty"):
            DockerSandbox._sanitize_command("")

    def test_sanitize_command_strict_rejects_semicolon(self):
        """Test that strict mode rejects semicolons."""
        with pytest.raises(ValueError, match="dangerous characters"):
            DockerSandbox._sanitize_command("echo hello; rm -rf /", strict=True)

    def test_sanitize_command_strict_rejects_pipe(self):
        """Test that strict mode rejects pipes."""
        with pytest.raises(ValueError, match="dangerous characters"):
            DockerSandbox._sanitize_command("cat file | grep pattern", strict=True)

    def test_sanitize_command_strict_rejects_backticks(self):
        """Test that strict mode rejects backticks."""
        with pytest.raises(ValueError, match="dangerous characters"):
            DockerSandbox._sanitize_command("echo `whoami`", strict=True)

    def test_sanitize_command_strict_rejects_dollar(self):
        """Test that strict mode rejects $ substitution."""
        with pytest.raises(ValueError, match="dangerous characters"):
            DockerSandbox._sanitize_command("echo $PATH", strict=True)

    def test_sanitize_command_strict_rejects_sensitive_paths(self):
        """Test that strict mode rejects sensitive path references."""
        with pytest.raises(ValueError, match="dangerous characters"):
            DockerSandbox._sanitize_command("cat /etc/passwd", strict=True)

    def test_sanitize_command_nonstrict_allows_shell_chars(self):
        """Test that non-strict mode allows shell characters."""
        # These should pass in non-strict mode (default)
        result = DockerSandbox._sanitize_command("echo hello && echo world")
        assert "hello" in result

        result = DockerSandbox._sanitize_command("ls | head")
        assert "ls" in result


class TestDangerousPatternsRegex:
    """Tests for the DANGEROUS_PATTERNS regex."""

    def test_detects_semicolon(self):
        """Test that semicolons are detected."""
        assert DANGEROUS_PATTERNS.search("cmd1; cmd2")

    def test_detects_ampersand(self):
        """Test that ampersands are detected."""
        assert DANGEROUS_PATTERNS.search("cmd1 && cmd2")
        assert DANGEROUS_PATTERNS.search("cmd &")

    def test_detects_pipe(self):
        """Test that pipes are detected."""
        assert DANGEROUS_PATTERNS.search("cmd1 | cmd2")

    def test_detects_backtick(self):
        """Test that backticks are detected."""
        assert DANGEROUS_PATTERNS.search("`whoami`")

    def test_detects_dollar(self):
        """Test that $ is detected."""
        assert DANGEROUS_PATTERNS.search("$HOME")
        assert DANGEROUS_PATTERNS.search("$(whoami)")

    def test_detects_path_traversal(self):
        """Test that .. is detected."""
        assert DANGEROUS_PATTERNS.search("../secret")

    def test_detects_etc(self):
        """Test that /etc/ is detected."""
        assert DANGEROUS_PATTERNS.search("/etc/passwd")

    def test_detects_proc(self):
        """Test that /proc/ is detected."""
        assert DANGEROUS_PATTERNS.search("/proc/self/environ")

    def test_detects_sys(self):
        """Test that /sys/ is detected."""
        assert DANGEROUS_PATTERNS.search("/sys/kernel")

    def test_detects_dev(self):
        """Test that /dev/ is detected."""
        assert DANGEROUS_PATTERNS.search("/dev/null")

    def test_safe_commands_pass(self):
        """Test that safe commands are not flagged."""
        assert DANGEROUS_PATTERNS.search("echo hello") is None
        assert DANGEROUS_PATTERNS.search("ls -la") is None
        assert DANGEROUS_PATTERNS.search("python script.py") is None
        assert DANGEROUS_PATTERNS.search("cat file.txt") is None


class TestAllowedWorkspaceBases:
    """Tests for ALLOWED_WORKSPACE_BASES constant."""

    def test_workspace_in_allowed(self):
        """Test that /workspace is allowed."""
        assert "/workspace" in ALLOWED_WORKSPACE_BASES

    def test_tmp_in_allowed(self):
        """Test that /tmp is allowed."""
        assert "/tmp" in ALLOWED_WORKSPACE_BASES

    def test_home_in_allowed(self):
        """Test that /home is allowed."""
        assert "/home" in ALLOWED_WORKSPACE_BASES


class TestDockerSandboxMocked:
    """Tests for DockerSandbox with mocked Docker client."""

    def test_get_docker_client_singleton(self):
        """Test that Docker client is created as singleton."""
        # Reset singleton
        DockerSandbox._docker_client = None

        with patch("ii_sandbox_server.sandboxes.docker.docker") as mock_docker:
            mock_client = MagicMock()
            mock_docker.from_env.return_value = mock_client

            # First call creates client
            client1 = DockerSandbox._get_docker_client()

            # Second call returns same client
            client2 = DockerSandbox._get_docker_client()

            assert client1 is client2
            mock_docker.from_env.assert_called_once()

        # Clean up
        DockerSandbox._docker_client = None

    def test_find_available_ports(self):
        """Test that _find_available_ports returns correct number of ports."""
        ports = DockerSandbox._find_available_ports(3)

        assert len(ports) == 3
        assert all(isinstance(p, int) for p in ports)
        assert all(p > 0 for p in ports)
        # Ports should be unique
        assert len(set(ports)) == 3

    def test_sandbox_id_property(self):
        """Test sandbox_id property."""
        mock_container = MagicMock()
        mock_container.status = "running"

        sandbox = DockerSandbox(
            container=mock_container,
            sandbox_id="test-sandbox-123",
            queue=None,
            port_mappings={6060: 8080, 9000: 9001, 3000: 3001},
        )

        assert sandbox.sandbox_id == "test-sandbox-123"

    def test_get_mcp_url(self):
        """Test get_mcp_url returns correct URL."""
        mock_container = MagicMock()
        mock_container.status = "running"

        sandbox = DockerSandbox(
            container=mock_container,
            sandbox_id="test-123",
            queue=None,
            port_mappings={6060: 8080, 9000: 9001, 3000: 3001},
        )

        url = sandbox.get_mcp_url()

        assert url == "http://localhost:8080"

    def test_get_code_server_url(self):
        """Test get_code_server_url returns correct URL."""
        mock_container = MagicMock()
        mock_container.status = "running"

        sandbox = DockerSandbox(
            container=mock_container,
            sandbox_id="test-123",
            queue=None,
            port_mappings={6060: 8080, 9000: 9001, 3000: 3001},
        )

        url = sandbox.get_code_server_url()

        assert url == "http://localhost:9001"


class TestDockerSandboxGetSandboxImage:
    """Tests for _get_sandbox_image class method."""

    def test_uses_config_docker_image(self):
        """Test that config.docker_image takes priority."""
        mock_config = MagicMock()
        mock_config.docker_image = "custom-image:v1"

        image = DockerSandbox._get_sandbox_image(mock_config)

        assert image == "custom-image:v1"

    def test_uses_env_var_if_no_config(self):
        """Test that SANDBOX_DOCKER_IMAGE env var is used if no config."""
        mock_config = MagicMock()
        mock_config.docker_image = None

        with patch.dict("os.environ", {"SANDBOX_DOCKER_IMAGE": "env-image:latest"}):
            image = DockerSandbox._get_sandbox_image(mock_config)

        assert image == "env-image:latest"

    def test_uses_default_if_nothing_set(self):
        """Test that default image is used when nothing is configured."""
        mock_config = MagicMock()
        mock_config.docker_image = None

        with patch.dict("os.environ", {}, clear=True):
            # Remove env var if it exists
            import os
            os.environ.pop("SANDBOX_DOCKER_IMAGE", None)

            image = DockerSandbox._get_sandbox_image(mock_config)

        assert image == "ii-agent-sandbox:latest"


class TestDockerSandboxPortRegistration:
    """Tests for port registration when reconnecting to containers."""

    def setup_method(self):
        """Reset port manager singleton before each test."""
        from ii_sandbox_server.sandboxes.port_manager import PortPoolManager
        PortPoolManager.reset_instance()

    def teardown_method(self):
        """Clean up port manager after each test."""
        from ii_sandbox_server.sandboxes.port_manager import PortPoolManager
        PortPoolManager.reset_instance()

    def test_register_existing_ports_adds_to_pool(self):
        """Test that _register_existing_ports adds ports to the manager."""
        from ii_sandbox_server.sandboxes.port_manager import PortPoolManager

        port_manager = PortPoolManager.get_instance()
        port_mappings = {6060: 30100, 9000: 30101, 3000: 30102}

        DockerSandbox._register_existing_ports(
            port_manager,
            sandbox_id="reconnect-test-123",
            port_mappings=port_mappings,
            container_id="container-abc123",
        )

        # Verify ports are now tracked
        port_set = port_manager.get_sandbox_ports("reconnect-test-123")
        assert port_set is not None
        assert port_set.container_id == "container-abc123"
        assert len(port_set.allocations) == 3
        assert port_set.get_host_port(6060) == 30100
        assert port_set.get_host_port(9000) == 30101
        assert port_set.get_host_port(3000) == 30102

    def test_register_existing_ports_marks_allocated(self):
        """Test that registered ports are marked as allocated."""
        from ii_sandbox_server.sandboxes.port_manager import PortPoolManager

        port_manager = PortPoolManager.get_instance()
        port_mappings = {6060: 30200, 9000: 30201}

        DockerSandbox._register_existing_ports(
            port_manager,
            sandbox_id="alloc-test-456",
            port_mappings=port_mappings,
            container_id="container-xyz",
        )

        # Verify these ports are in the allocated set
        assert 30200 in port_manager._allocated_ports
        assert 30201 in port_manager._allocated_ports

        # Stats should reflect the allocations
        stats = port_manager.get_stats()
        assert stats["allocated"] == 2
        assert stats["sandboxes"] == 1

    def test_register_existing_ports_skips_if_already_registered(self):
        """Test that re-registration is a no-op for same sandbox."""
        from ii_sandbox_server.sandboxes.port_manager import PortPoolManager

        port_manager = PortPoolManager.get_instance()
        port_mappings = {6060: 30300}

        # Register once
        DockerSandbox._register_existing_ports(
            port_manager,
            sandbox_id="skip-test-789",
            port_mappings=port_mappings,
            container_id="container-first",
        )

        # Try to register again with different data
        DockerSandbox._register_existing_ports(
            port_manager,
            sandbox_id="skip-test-789",
            port_mappings={6060: 30999, 9000: 30998},  # Different ports
            container_id="container-second",
        )

        # Should still have original registration
        port_set = port_manager.get_sandbox_ports("skip-test-789")
        assert port_set.container_id == "container-first"
        assert len(port_set.allocations) == 1
        assert port_set.get_host_port(6060) == 30300

    def test_register_existing_ports_prevents_conflicts(self):
        """Test that registered ports prevent allocation conflicts."""
        from ii_sandbox_server.sandboxes.port_manager import PortPoolManager

        # Use a small port range to make conflict detection easier
        PortPoolManager.reset_instance()
        port_manager = PortPoolManager(port_range_start=40000, port_range_end=40004)

        # Simulate reconnecting to a container using ports 40000-40002
        reconnect_ports = {6060: 40000, 9000: 40001, 3000: 40002}
        DockerSandbox._register_existing_ports(
            port_manager,
            sandbox_id="existing-sandbox",
            port_mappings=reconnect_ports,
            container_id="existing-container",
        )

        # Now allocate ports for a new sandbox - should get 40003, 40004
        new_port_set = port_manager.allocate_ports(
            sandbox_id="new-sandbox",
            container_ports=[8080, 8081],
        )

        # New sandbox should NOT get any of the registered ports
        new_host_ports = [a.host_port for a in new_port_set.allocations.values()]
        assert 40000 not in new_host_ports
        assert 40001 not in new_host_ports
        assert 40002 not in new_host_ports

        # Should get the remaining available ports
        assert set(new_host_ports) == {40003, 40004}

    def test_register_assigns_service_names(self):
        """Test that MCP and code server ports get service names."""
        from ii_sandbox_server.sandboxes.port_manager import PortPoolManager

        port_manager = PortPoolManager.get_instance()
        port_mappings = {6060: 30400, 9000: 30401, 3000: 30402}

        DockerSandbox._register_existing_ports(
            port_manager,
            sandbox_id="service-name-test",
            port_mappings=port_mappings,
            container_id="container-svc",
        )

        port_set = port_manager.get_sandbox_ports("service-name-test")
        assert port_set.allocations[6060].service_name == "mcp_server"
        assert port_set.allocations[9000].service_name == "code_server"
        assert port_set.allocations[3000].service_name is None


class TestDockerSandboxVolumeCleanup:
    """Tests for volume cleanup when deleting sandboxes."""

    def test_cleanup_sandbox_volume_success(self):
        """Test successful volume removal."""
        mock_client = MagicMock()
        mock_volume = MagicMock()
        mock_client.volumes.get.return_value = mock_volume

        result = DockerSandbox._cleanup_sandbox_volume(mock_client, "test-sandbox-123")

        assert result is True
        mock_client.volumes.get.assert_called_once_with("ii-sandbox-workspace-test-sandbox-123")
        mock_volume.remove.assert_called_once_with(force=True)

    def test_cleanup_sandbox_volume_not_found(self):
        """Test cleanup when volume doesn't exist."""
        from docker.errors import NotFound

        mock_client = MagicMock()
        mock_client.volumes.get.side_effect = NotFound("Volume not found")

        result = DockerSandbox._cleanup_sandbox_volume(mock_client, "nonexistent-sandbox")

        assert result is False

    def test_cleanup_sandbox_volume_api_error(self):
        """Test cleanup when API error occurs."""
        from docker.errors import APIError

        mock_client = MagicMock()
        mock_volume = MagicMock()
        mock_client.volumes.get.return_value = mock_volume
        mock_volume.remove.side_effect = APIError("Volume in use")

        result = DockerSandbox._cleanup_sandbox_volume(mock_client, "busy-sandbox")

        assert result is False

    def test_cleanup_sandbox_volume_none_sandbox_id(self):
        """Test cleanup with None sandbox_id."""
        mock_client = MagicMock()

        result = DockerSandbox._cleanup_sandbox_volume(mock_client, None)

        assert result is False
        mock_client.volumes.get.assert_not_called()

    def test_cleanup_sandbox_volume_constructs_correct_name(self):
        """Test that volume name is constructed correctly."""
        mock_client = MagicMock()
        mock_volume = MagicMock()
        mock_client.volumes.get.return_value = mock_volume

        DockerSandbox._cleanup_sandbox_volume(mock_client, "my-special-sandbox-456")

        mock_client.volumes.get.assert_called_once_with(
            "ii-sandbox-workspace-my-special-sandbox-456"
        )
