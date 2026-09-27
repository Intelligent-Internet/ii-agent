"""Unit tests for the DockerSandbox class.

Tests the Docker-based local sandbox provider: path validation,
container operations, port management, and file operations.
"""

import asyncio
import io
import tarfile

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from ii_agent.agents.sandboxes.docker import (
    DockerSandbox,
    ADAPTER_CONTAINER_PORT,
    ALLOWED_WORKSPACE_BASES,
    DANGEROUS_PATTERNS,
    DEFAULT_EXPOSED_PORTS,
    MCP_SERVER_PORT,
    CODE_SERVER_PORT,
    NOVNC_PORT,
    _validate_path,
    _register_existing_ports,
    _cleanup_sandbox_volume,
)
from ii_agent.agents.sandboxes.exceptions import (
    SandboxCreationError,
    SandboxNotInitializedError,
    SandboxNotFoundException,
    SandboxOperationError,
    SandboxTimeoutException,
)
from ii_agent.agents.sandboxes.types import SandboxStatus


class TestPathValidation:
    """Tests for _validate_path helper."""

    def test_normal_relative(self):
        result = _validate_path("file.txt")
        assert result == "file.txt"

    def test_nested_relative(self):
        result = _validate_path("dir/subdir/file.txt")
        assert result == "dir/subdir/file.txt"

    def test_absolute_in_workspace(self):
        result = _validate_path("/workspace/project/file.py")
        assert result == "/workspace/project/file.py"

    def test_absolute_in_tmp(self):
        result = _validate_path("/tmp/scratch/output.txt")
        assert result == "/tmp/scratch/output.txt"

    def test_absolute_in_home(self):
        result = _validate_path("/home/user/.config")
        assert result == "/home/user/.config"

    def test_rejects_empty(self):
        with pytest.raises(ValueError, match="Path cannot be empty"):
            _validate_path("")

    def test_rejects_path_traversal(self):
        with pytest.raises(ValueError, match="traversal"):
            _validate_path("../../../etc/passwd")

    def test_rejects_hidden_traversal(self):
        with pytest.raises(ValueError, match="traversal"):
            _validate_path("/workspace/project/../../etc/shadow")

    def test_rejects_disallowed_absolute(self):
        with pytest.raises(ValueError, match="allowed directories"):
            _validate_path("/etc/passwd")

    def test_rejects_sys_proc(self):
        with pytest.raises(ValueError, match="allowed directories"):
            _validate_path("/sys/kernel/config")
        with pytest.raises(ValueError, match="allowed directories"):
            _validate_path("/proc/self/environ")

    def test_disallow_absolute_flag(self):
        with pytest.raises(ValueError, match="Absolute paths not allowed"):
            _validate_path("/workspace/file.txt", allow_absolute=False)


class TestDangerousPatternsRegex:
    """Tests for the DANGEROUS_PATTERNS regex."""

    def test_detects_semicolon(self):
        assert DANGEROUS_PATTERNS.search("cmd1; cmd2")

    def test_detects_ampersand(self):
        assert DANGEROUS_PATTERNS.search("cmd1 && cmd2")

    def test_detects_pipe(self):
        assert DANGEROUS_PATTERNS.search("cmd1 | cmd2")

    def test_detects_backtick(self):
        assert DANGEROUS_PATTERNS.search("`whoami`")

    def test_detects_dollar(self):
        assert DANGEROUS_PATTERNS.search("$HOME")

    def test_detects_path_traversal(self):
        assert DANGEROUS_PATTERNS.search("../secret")

    def test_detects_sensitive_paths(self):
        assert DANGEROUS_PATTERNS.search("/etc/passwd")
        assert DANGEROUS_PATTERNS.search("/proc/self/environ")
        assert DANGEROUS_PATTERNS.search("/sys/kernel")
        assert DANGEROUS_PATTERNS.search("/dev/null")

    def test_safe_commands_pass(self):
        assert DANGEROUS_PATTERNS.search("echo hello") is None
        assert DANGEROUS_PATTERNS.search("ls -la") is None
        assert DANGEROUS_PATTERNS.search("python script.py") is None


class TestAllowedWorkspaceBases:
    """Tests for ALLOWED_WORKSPACE_BASES constant."""

    def test_workspace_in_allowed(self):
        assert "/workspace" in ALLOWED_WORKSPACE_BASES

    def test_tmp_in_allowed(self):
        assert "/tmp" in ALLOWED_WORKSPACE_BASES

    def test_home_in_allowed(self):
        assert "/home" in ALLOWED_WORKSPACE_BASES


def _make_sandbox(
    sandbox_id="test-sandbox-123",
    port_mappings=None,
    container=None,
) -> DockerSandbox:
    """Create a DockerSandbox with mocked internals for testing."""
    if container is None:
        container = MagicMock()
        container.status = "running"
        container.id = "container-abc123"

    if port_mappings is None:
        port_mappings = {6060: 8080, 9000: 9001, 3000: 3001}

    return DockerSandbox(
        sandbox_id=sandbox_id,
        session_id="session-456",
        provider_sandbox_id=container.id,
        container=container,
        port_mappings=port_mappings,
    )


class TestDockerSandboxMocked:
    """Tests for DockerSandbox with mocked Docker client."""

    def test_get_docker_client_singleton(self):
        DockerSandbox._docker_client = None

        with (
            patch("ii_agent.agents.sandboxes.docker.docker") as mock_docker,
            patch.object(DockerSandbox, "_resolve_docker_socket", return_value=None),
        ):
            mock_client = MagicMock()
            mock_docker.from_env.return_value = mock_client

            client1 = DockerSandbox._get_docker_client()
            client2 = DockerSandbox._get_docker_client()

            assert client1 is client2
            mock_docker.from_env.assert_called_once()

        DockerSandbox._docker_client = None

    def test_sandbox_id_property(self):
        sandbox = _make_sandbox()
        assert sandbox.sandbox_id == "test-sandbox-123"

    def test_get_provider_id(self):
        sandbox = _make_sandbox()
        assert sandbox.get_provider_id() == "container-abc123"


class TestDockerSandboxPortConstants:
    """Tests for port constants and DEFAULT_EXPOSED_PORTS."""

    def test_novnc_port_value(self):
        assert NOVNC_PORT == 6080

    def test_novnc_port_in_default_exposed_ports(self):
        assert NOVNC_PORT in DEFAULT_EXPOSED_PORTS

    def test_default_exposed_ports_includes_all_required(self):
        assert MCP_SERVER_PORT in DEFAULT_EXPOSED_PORTS
        assert CODE_SERVER_PORT in DEFAULT_EXPOSED_PORTS
        assert NOVNC_PORT in DEFAULT_EXPOSED_PORTS
        # Adapter port is NOT in the base set — only added when inner_loop_mode=a2a
        assert ADAPTER_CONTAINER_PORT not in DEFAULT_EXPOSED_PORTS

    def test_default_exposed_ports_count(self):
        assert len(DEFAULT_EXPOSED_PORTS) == 6

    def test_novnc_port_mapping_stored(self):
        sandbox = _make_sandbox(
            port_mappings={6060: 30000, 9000: 30001, 6080: 30002, 3000: 30003},
        )
        assert sandbox._port_mappings[NOVNC_PORT] == 30002


class TestDockerSandboxPortRegistration:
    """Tests for port registration when reconnecting to containers."""

    def setup_method(self):
        from ii_agent.agents.sandboxes.port_manager import PortPoolManager

        PortPoolManager.reset_instance()

    def teardown_method(self):
        from ii_agent.agents.sandboxes.port_manager import PortPoolManager

        PortPoolManager.reset_instance()

    def test_register_existing_ports_adds_to_pool(self):
        from ii_agent.agents.sandboxes.port_manager import PortPoolManager

        port_manager = PortPoolManager.get_instance()
        port_mappings = {6060: 30100, 9000: 30101, 3000: 30102}

        _register_existing_ports(
            port_manager,
            sandbox_id="reconnect-test-123",
            port_mappings=port_mappings,
            container_id="container-abc123",
        )

        port_set = port_manager.get_sandbox_ports("reconnect-test-123")
        assert port_set is not None
        assert port_set.container_id == "container-abc123"
        assert len(port_set.allocations) == 3
        assert port_set.get_host_port(6060) == 30100

    def test_register_existing_ports_marks_allocated(self):
        from ii_agent.agents.sandboxes.port_manager import PortPoolManager

        port_manager = PortPoolManager.get_instance()
        _register_existing_ports(
            port_manager,
            sandbox_id="alloc-test-456",
            port_mappings={6060: 30200, 9000: 30201},
            container_id="container-xyz",
        )

        assert 30200 in port_manager._allocated_ports
        assert 30201 in port_manager._allocated_ports
        stats = port_manager.get_stats()
        assert stats["allocated"] == 2

    def test_register_existing_ports_skips_if_already_registered(self):
        from ii_agent.agents.sandboxes.port_manager import PortPoolManager

        port_manager = PortPoolManager.get_instance()
        _register_existing_ports(
            port_manager,
            sandbox_id="skip-test-789",
            port_mappings={6060: 30300},
            container_id="container-first",
        )

        _register_existing_ports(
            port_manager,
            sandbox_id="skip-test-789",
            port_mappings={6060: 30999, 9000: 30998},
            container_id="container-second",
        )

        port_set = port_manager.get_sandbox_ports("skip-test-789")
        assert port_set.container_id == "container-first"
        assert len(port_set.allocations) == 1

    def test_register_existing_ports_prevents_conflicts(self):
        from ii_agent.agents.sandboxes.port_manager import PortPoolManager

        PortPoolManager.reset_instance()
        port_manager = PortPoolManager(port_range_start=40000, port_range_end=40004)

        _register_existing_ports(
            port_manager,
            sandbox_id="existing-sandbox",
            port_mappings={6060: 40000, 9000: 40001, 3000: 40002},
            container_id="existing-container",
        )

        new_port_set = port_manager.allocate_ports(
            sandbox_id="new-sandbox",
            container_ports=[8080, 8081],
        )

        new_host_ports = [a.host_port for a in new_port_set.allocations.values()]
        assert 40000 not in new_host_ports
        assert 40001 not in new_host_ports
        assert 40002 not in new_host_ports
        assert set(new_host_ports) == {40003, 40004}

    def test_register_assigns_service_names(self):
        from ii_agent.agents.sandboxes.port_manager import PortPoolManager

        port_manager = PortPoolManager.get_instance()
        _register_existing_ports(
            port_manager,
            sandbox_id="service-name-test",
            port_mappings={6060: 30400, 9000: 30401, 3000: 30402},
            container_id="container-svc",
        )

        port_set = port_manager.get_sandbox_ports("service-name-test")
        assert port_set.allocations[6060].service_name == "mcp_server"
        assert port_set.allocations[9000].service_name == "code_server"
        assert port_set.allocations[3000].service_name is None


class TestDockerSandboxVolumeCleanup:
    """Tests for volume cleanup when deleting sandboxes."""

    def test_cleanup_success(self):
        mock_client = MagicMock()
        mock_volume = MagicMock()
        mock_client.volumes.get.return_value = mock_volume

        result = _cleanup_sandbox_volume(mock_client, "test-sandbox-123")

        assert result is True
        mock_client.volumes.get.assert_called_once_with("ii-sandbox-workspace-test-sandbox-123")
        mock_volume.remove.assert_called_once_with(force=True)

    def test_cleanup_not_found(self):
        from docker.errors import NotFound

        mock_client = MagicMock()
        mock_client.volumes.get.side_effect = NotFound("not found")

        result = _cleanup_sandbox_volume(mock_client, "nonexistent")
        assert result is False

    def test_cleanup_api_error(self):
        from docker.errors import APIError

        mock_client = MagicMock()
        mock_volume = MagicMock()
        mock_client.volumes.get.return_value = mock_volume
        mock_volume.remove.side_effect = APIError("in use")

        result = _cleanup_sandbox_volume(mock_client, "busy-sandbox")
        assert result is False

    def test_cleanup_none_sandbox_id(self):
        mock_client = MagicMock()

        result = _cleanup_sandbox_volume(mock_client, None)
        assert result is False
        mock_client.volumes.get.assert_not_called()


class TestDockerSandboxExposePort:
    """Tests for expose_port method."""

    @pytest.mark.asyncio
    async def test_external_from_port_mappings(self):
        sandbox = _make_sandbox(
            port_mappings={6060: 8080, 9000: 9001},
        )
        sandbox._container.attrs = {
            "NetworkSettings": {
                "Networks": {"bridge": {"IPAddress": "172.17.0.5"}},
                "Ports": {},
            }
        }

        url = await sandbox.expose_port(6060, external=True)
        assert url == "http://localhost:8080"

    @pytest.mark.asyncio
    async def test_external_from_container_bindings(self):
        sandbox = _make_sandbox(port_mappings={})
        sandbox._container.attrs = {
            "NetworkSettings": {
                "Networks": {"bridge": {"IPAddress": "172.17.0.5"}},
                "Ports": {"5000/tcp": [{"HostPort": "32000"}]},
            }
        }

        url = await sandbox.expose_port(5000, external=True)
        assert url == "http://localhost:32000"

    @pytest.mark.asyncio
    async def test_external_raises_for_unmapped(self):
        sandbox = _make_sandbox(port_mappings={})
        sandbox._container.attrs = {
            "NetworkSettings": {
                "Networks": {"bridge": {"IPAddress": "172.17.0.5"}},
                "Ports": {},
            }
        }

        with pytest.raises(SandboxOperationError, match="not exposed"):
            await sandbox.expose_port(9999, external=True)

    @pytest.mark.asyncio
    async def test_internal_returns_docker_ip(self):
        sandbox = _make_sandbox(port_mappings={5000: 32000})
        sandbox._container.attrs = {
            "NetworkSettings": {
                "Networks": {"bridge": {"IPAddress": "172.17.0.5"}},
                "Ports": {},
            }
        }

        url = await sandbox.expose_port(5000, external=False)
        assert url == "http://172.17.0.5:5000"

    @pytest.mark.asyncio
    async def test_novnc_external(self):
        sandbox = _make_sandbox(
            port_mappings={6060: 30000, 9000: 30001, 6080: 30002},
        )
        sandbox._container.attrs = {
            "NetworkSettings": {
                "Networks": {"bridge": {"IPAddress": "172.17.0.5"}},
                "Ports": {},
            }
        }

        url = await sandbox.expose_port(NOVNC_PORT, external=True)
        assert url == "http://localhost:30002"


class TestDockerSandboxGetStatus:
    """Tests for get_status method."""

    @pytest.mark.asyncio
    async def test_running_container(self):
        sandbox = _make_sandbox()
        sandbox._container.status = "running"
        status = await sandbox.get_status()
        assert status.value == "running"

    @pytest.mark.asyncio
    async def test_no_container(self):
        sandbox = _make_sandbox()
        sandbox._container = None
        status = await sandbox.get_status()
        assert status.value == "initializing"

    @pytest.mark.asyncio
    async def test_exited_container(self):
        sandbox = _make_sandbox()
        sandbox._container.status = "exited"
        status = await sandbox.get_status()
        assert status.value == "paused"


class TestDockerSandboxKillExceptionSafety:
    """Tests for kill() method exception safety — ports must always be released."""

    def setup_method(self):
        from ii_agent.agents.sandboxes.port_manager import PortPoolManager

        PortPoolManager.reset_instance()

    def teardown_method(self):
        from ii_agent.agents.sandboxes.port_manager import PortPoolManager

        PortPoolManager.reset_instance()

    @pytest.mark.asyncio
    async def test_kill_releases_ports_on_container_remove_failure(self):
        """Ports must be released even if container.remove() raises APIError."""
        from docker.errors import APIError as DockerAPIError
        from ii_agent.agents.sandboxes.port_manager import PortPoolManager

        port_manager = PortPoolManager.get_instance()
        port_manager.allocate_ports(
            sandbox_id="kill-test-123",
            container_ports=[6060, 9000],
        )
        assert port_manager.get_stats()["allocated"] == 2

        container = MagicMock()
        container.status = "running"
        container.id = "container-fail"
        container.remove.side_effect = DockerAPIError("device busy")

        sandbox = DockerSandbox(
            sandbox_id="kill-test-123",
            session_id="session-456",
            provider_sandbox_id=container.id,
            container=container,
            port_mappings={6060: 30000, 9000: 30001},
        )

        with patch.object(DockerSandbox, "_get_docker_client") as mock_client:
            mock_volume = MagicMock()
            mock_client.return_value.volumes.get.return_value = mock_volume

            result = await sandbox.kill()

        assert result is True
        # Ports MUST be released despite container.remove failure
        assert port_manager.get_stats()["allocated"] == 0
        assert port_manager.get_sandbox_ports("kill-test-123") is None

    @pytest.mark.asyncio
    async def test_kill_succeeds_when_container_already_gone(self):
        """kill() succeeds if the container is already removed (NotFound)."""
        from docker.errors import NotFound as DockerNotFound
        from ii_agent.agents.sandboxes.port_manager import PortPoolManager

        port_manager = PortPoolManager.get_instance()
        port_manager.allocate_ports(
            sandbox_id="gone-test-456",
            container_ports=[6060],
        )

        container = MagicMock()
        container.status = "running"
        container.id = "container-gone"
        container.remove.side_effect = DockerNotFound("no such container")

        sandbox = DockerSandbox(
            sandbox_id="gone-test-456",
            session_id="session-789",
            provider_sandbox_id=container.id,
            container=container,
            port_mappings={6060: 30000},
        )

        with patch.object(DockerSandbox, "_get_docker_client") as mock_client:
            mock_client.return_value.volumes.get.side_effect = DockerNotFound("no volume")

            result = await sandbox.kill()

        assert result is True
        assert port_manager.get_stats()["allocated"] == 0


class TestEnsureContainer:
    """Tests for _ensure_container method."""

    def test_raises_when_container_is_none(self):
        sandbox = _make_sandbox()
        sandbox._container = None

        with pytest.raises(SandboxNotInitializedError):
            sandbox._ensure_container()

    def test_raises_when_container_not_running(self):
        container = MagicMock()
        container.status = "exited"
        container.id = "container-stopped"
        sandbox = _make_sandbox(container=container)

        with pytest.raises(SandboxNotInitializedError, match="not running"):
            sandbox._ensure_container()

    def test_passes_when_running(self):
        container = MagicMock()
        container.status = "running"
        container.id = "container-ok"
        sandbox = _make_sandbox(container=container)

        sandbox._ensure_container()  # Should not raise


class TestGetHost:
    """Tests for get_host method."""

    @pytest.mark.asyncio
    async def test_returns_ip_from_network(self):
        sandbox = _make_sandbox()
        sandbox._container.attrs = {
            "NetworkSettings": {
                "Networks": {"bridge": {"IPAddress": "172.17.0.5"}},
            }
        }

        host = await sandbox.get_host()
        assert host == "172.17.0.5"

    @pytest.mark.asyncio
    async def test_returns_localhost_when_no_networks(self):
        sandbox = _make_sandbox()
        sandbox._container.attrs = {
            "NetworkSettings": {"Networks": {}},
        }

        host = await sandbox.get_host()
        assert host == "localhost"

    @pytest.mark.asyncio
    async def test_returns_localhost_when_no_container(self):
        sandbox = _make_sandbox()
        sandbox._container = None

        host = await sandbox.get_host()
        assert host == "localhost"

    @pytest.mark.asyncio
    async def test_returns_first_ip_among_multiple_networks(self):
        sandbox = _make_sandbox()
        sandbox._container.attrs = {
            "NetworkSettings": {
                "Networks": {
                    "net1": {"IPAddress": ""},
                    "net2": {"IPAddress": "10.0.0.5"},
                },
            }
        }

        host = await sandbox.get_host()
        assert host == "10.0.0.5"


class TestWatchDir:
    """Tests for watch_dir method using inotifywait."""

    @pytest.mark.asyncio
    async def test_watch_dir_returns_handle(self):
        sandbox = _make_sandbox()

        # Mock the Docker API client so the background task doesn't fail hard
        mock_api = MagicMock()
        mock_api.exec_create.return_value = {"Id": "exec-123"}
        mock_api.exec_start.return_value = iter([])  # empty stream
        sandbox._container.client.api = mock_api

        on_event = MagicMock()
        on_exit = AsyncMock()
        handle = await sandbox.watch_dir("/workspace", on_event=on_event, on_exit=on_exit)

        # Should return a handle with a stop method
        assert hasattr(handle, "stop")
        assert handle._path == "/workspace"
        handle.stop()
        # Give the background task a moment to finish
        await asyncio.sleep(0.05)


class TestCreateLiveTerminal:
    """Tests for create_live_terminal — should always raise."""

    @pytest.mark.asyncio
    async def test_raises_sandbox_operation_error(self):
        sandbox = _make_sandbox()

        with pytest.raises(SandboxOperationError, match="not supported"):
            await sandbox.create_live_terminal(
                cols=80, rows=24, cwd="/workspace", on_data=MagicMock()
            )


class TestRunCommand:
    """Tests for run_command method."""

    @pytest.mark.asyncio
    async def test_success(self):
        sandbox = _make_sandbox()
        sandbox._container.exec_run.return_value = (0, b"hello world\n")

        result = await sandbox.run_command("echo hello world")

        assert result == "hello world\n"
        sandbox._container.exec_run.assert_called_once_with(
            ["/bin/sh", "-c", "echo hello world"],
            workdir="/workspace",
        )

    @pytest.mark.asyncio
    async def test_failure_raises(self):
        sandbox = _make_sandbox()
        sandbox._container.exec_run.return_value = (1, b"command not found")

        with pytest.raises(SandboxOperationError, match="Command failed"):
            await sandbox.run_command("bad_command")

    @pytest.mark.asyncio
    async def test_background(self):
        sandbox = _make_sandbox()

        result = await sandbox.run_command("sleep 100", background=True)

        assert result == ""
        sandbox._container.exec_run.assert_called_once_with(
            ["/bin/sh", "-c", "nohup sleep 100 > /dev/null 2>&1 &"],
            detach=True,
            workdir="/workspace",
        )

    @pytest.mark.asyncio
    async def test_custom_cwd(self):
        sandbox = _make_sandbox()
        sandbox._container.exec_run.return_value = (0, b"ok")

        await sandbox.run_command("ls", cwd="/tmp/work")

        sandbox._container.exec_run.assert_called_once_with(
            ["/bin/sh", "-c", "ls"],
            workdir="/tmp/work",
        )

    @pytest.mark.asyncio
    async def test_raises_when_no_container(self):
        sandbox = _make_sandbox()
        sandbox._container = None

        with pytest.raises(SandboxNotInitializedError):
            await sandbox.run_command("ls")


class TestRunPythonCode:
    """Tests for run_python_code method."""

    @pytest.mark.asyncio
    async def test_success(self):
        sandbox = _make_sandbox()
        sandbox._container.exec_run.return_value = (0, b"42\n")

        result = await sandbox.run_python_code("print(42)")
        assert result == "42\n"

    @pytest.mark.asyncio
    async def test_failure_raises(self):
        sandbox = _make_sandbox()
        sandbox._container.exec_run.return_value = (1, b"SyntaxError")

        with pytest.raises(SandboxOperationError, match="Execution failed"):
            await sandbox.run_python_code("invalid python")


class TestPause:
    """Tests for pause method."""

    @pytest.mark.asyncio
    async def test_success(self):
        from ii_agent.agents.sandboxes.types import SandboxStatus

        sandbox = _make_sandbox()

        await sandbox.pause()

        sandbox._container.stop.assert_called_once_with(timeout=10)
        assert sandbox.status == SandboxStatus.PAUSED

    @pytest.mark.asyncio
    async def test_not_found_raises(self):
        from docker.errors import NotFound as DockerNotFound

        sandbox = _make_sandbox()
        sandbox._container.stop.side_effect = DockerNotFound("gone")

        with pytest.raises(SandboxNotFoundException):
            await sandbox.pause()

    @pytest.mark.asyncio
    async def test_api_error_raises(self):
        from docker.errors import APIError as DockerAPIError

        sandbox = _make_sandbox()
        sandbox._container.stop.side_effect = DockerAPIError("timeout")

        with pytest.raises(SandboxOperationError, match="pause"):
            await sandbox.pause()

    @pytest.mark.asyncio
    async def test_raises_when_no_container(self):
        sandbox = _make_sandbox()
        sandbox._container = None

        with pytest.raises(SandboxNotInitializedError):
            await sandbox.pause()


class TestKillSuccess:
    """Tests for kill() normal operation."""

    def setup_method(self):
        from ii_agent.agents.sandboxes.port_manager import PortPoolManager

        PortPoolManager.reset_instance()

    def teardown_method(self):
        from ii_agent.agents.sandboxes.port_manager import PortPoolManager

        PortPoolManager.reset_instance()

    @pytest.mark.asyncio
    async def test_normal_kill(self):
        from ii_agent.agents.sandboxes.port_manager import PortPoolManager
        from ii_agent.agents.sandboxes.types import SandboxStatus

        port_manager = PortPoolManager.get_instance()
        port_manager.allocate_ports(
            sandbox_id="kill-normal",
            container_ports=[6060],
        )

        container = MagicMock()
        container.status = "running"
        container.id = "container-kill"

        sandbox = DockerSandbox(
            sandbox_id="kill-normal",
            session_id="session-1",
            provider_sandbox_id=container.id,
            container=container,
            port_mappings={6060: 30000},
        )

        with patch.object(DockerSandbox, "_get_docker_client") as mock_client:
            mock_volume = MagicMock()
            mock_client.return_value.volumes.get.return_value = mock_volume

            result = await sandbox.kill()

        assert result is True
        assert sandbox.status == SandboxStatus.DELETED
        container.remove.assert_called_once_with(force=True)
        mock_volume.remove.assert_called_once_with(force=True)
        assert port_manager.get_stats()["allocated"] == 0


class TestGetStatusEdgeCases:
    """Tests for get_status edge cases (NotFound, APIError)."""

    @pytest.mark.asyncio
    async def test_not_found_returns_deleted(self):
        from docker.errors import NotFound as DockerNotFound
        from ii_agent.agents.sandboxes.types import SandboxStatus

        sandbox = _make_sandbox()
        sandbox._container.reload.side_effect = DockerNotFound("gone")

        status = await sandbox.get_status()
        assert status == SandboxStatus.DELETED

    @pytest.mark.asyncio
    async def test_api_error_returns_error(self):
        from docker.errors import APIError as DockerAPIError
        from ii_agent.agents.sandboxes.types import SandboxStatus

        sandbox = _make_sandbox()
        sandbox._container.reload.side_effect = DockerAPIError("daemon unresponsive")

        status = await sandbox.get_status()
        assert status == SandboxStatus.ERROR

    @pytest.mark.asyncio
    async def test_paused_status(self):
        from ii_agent.agents.sandboxes.types import SandboxStatus

        sandbox = _make_sandbox()
        sandbox._container.status = "paused"

        status = await sandbox.get_status()
        assert status == SandboxStatus.PAUSED


class TestListSandboxes:
    """Tests for list_sandboxes class method."""

    def test_returns_sandbox_info(self):
        container = MagicMock()
        container.id = "abc123"
        container.status = "running"
        container.name = "ii-sandbox-test123"
        container.labels = {
            "ii-agent.sandbox-id": "test-sandbox-id",
            "ii-agent.created-at": "2024-01-01T00:00:00Z",
        }

        with patch.object(DockerSandbox, "_get_docker_client") as mock_get:
            mock_get.return_value.containers.list.return_value = [container]

            result = DockerSandbox.list_sandboxes()

        assert len(result) == 1
        assert result[0]["sandbox_id"] == "test-sandbox-id"
        assert result[0]["container_id"] == "abc123"
        assert result[0]["status"] == "running"

    def test_empty_when_no_containers(self):
        with patch.object(DockerSandbox, "_get_docker_client") as mock_get:
            mock_get.return_value.containers.list.return_value = []

            result = DockerSandbox.list_sandboxes()

        assert result == []


def _make_tar_bytes(filename: str, content: bytes) -> bytes:
    """Helper to create a tar archive in memory."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        info = tarfile.TarInfo(name=filename)
        info.size = len(content)
        tar.addfile(info, io.BytesIO(content))
    buf.seek(0)
    return buf.read()


class TestFileOperations:
    """Tests for file I/O methods."""

    @pytest.mark.asyncio
    async def test_read_file_success(self):
        sandbox = _make_sandbox()
        tar_data = _make_tar_bytes("file.txt", b"hello world")

        sandbox._container.get_archive.return_value = (iter([tar_data]), {})

        result = await sandbox.read_file("/workspace/file.txt")
        assert result == "hello world"

    @pytest.mark.asyncio
    async def test_read_file_not_found(self):
        from docker.errors import NotFound as DockerNotFound

        sandbox = _make_sandbox()
        sandbox._container.get_archive.side_effect = DockerNotFound("not found")

        with pytest.raises(FileNotFoundError, match="File not found"):
            await sandbox.read_file("/workspace/missing.txt")

    @pytest.mark.asyncio
    async def test_write_file_success(self):
        sandbox = _make_sandbox()

        result = await sandbox.write_file("/workspace/output.txt", "data")

        assert result.name == "output.txt"
        assert result.path == "/workspace/output.txt"
        sandbox._container.put_archive.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_file_success(self):
        sandbox = _make_sandbox()
        sandbox._container.exec_run.return_value = (0, b"")

        result = await sandbox.delete_file("/workspace/trash.txt")
        assert result is True

    @pytest.mark.asyncio
    async def test_delete_file_failure(self):
        sandbox = _make_sandbox()
        sandbox._container.exec_run.return_value = (1, b"")

        result = await sandbox.delete_file("/workspace/protected.txt")
        assert result is False

    @pytest.mark.asyncio
    async def test_create_directory(self):
        sandbox = _make_sandbox()
        sandbox._container.exec_run.return_value = (0, b"")

        result = await sandbox.create_directory("/workspace/newdir", exist_ok=True)
        assert result is True

    @pytest.mark.asyncio
    async def test_file_exists_true(self):
        sandbox = _make_sandbox()
        sandbox._container.exec_run.return_value = (0, b"")

        result = await sandbox.file_exists("/workspace/file.txt")
        assert result is True

    @pytest.mark.asyncio
    async def test_file_exists_false(self):
        sandbox = _make_sandbox()
        sandbox._container.exec_run.return_value = (1, b"")

        result = await sandbox.file_exists("/workspace/missing.txt")
        assert result is False


class TestGetInfo:
    """Tests for get_info method."""

    @pytest.mark.asyncio
    async def test_returns_info_when_running(self):
        sandbox = _make_sandbox(port_mappings={6060: 8080, 9000: 9001})
        sandbox.status = SandboxStatus.RUNNING
        sandbox._container.attrs = {
            "NetworkSettings": {
                "Networks": {"bridge": {"IPAddress": "172.17.0.5"}},
                "Ports": {},
            }
        }

        # Mock _config.vscode_port so expose_port returns a URL
        sandbox._config = MagicMock()
        sandbox._config.vscode_port = 9000
        sandbox._config.sandbox.docker_host = "localhost"

        info = await sandbox.get_info()

        assert info.id == "test-sandbox-123"
        assert info.session_id == "session-456"
        assert info.status == SandboxStatus.RUNNING
        assert info.vscode_url == "http://localhost:9001"

    @pytest.mark.asyncio
    async def test_returns_info_not_running(self):
        sandbox = _make_sandbox()
        sandbox.status = SandboxStatus.PAUSED

        info = await sandbox.get_info()

        assert info.id == "test-sandbox-123"
        assert info.vscode_url is None

    @pytest.mark.asyncio
    async def test_returns_info_expose_port_fails(self):
        sandbox = _make_sandbox(port_mappings={})
        sandbox.status = SandboxStatus.RUNNING
        sandbox._container.attrs = {
            "NetworkSettings": {"Networks": {}, "Ports": {}},
        }
        sandbox._config = MagicMock()
        sandbox._config.vscode_port = 9999
        sandbox._config.sandbox.docker_host = "localhost"

        info = await sandbox.get_info()

        # expose_port fails, but get_info catches and returns None
        assert info.vscode_url is None


class TestUploadPath:
    """Tests for upload_path property."""

    def test_returns_config_value(self):
        sandbox = _make_sandbox()
        sandbox._config = MagicMock()
        sandbox._config.workspace_upload_path = "/workspace/uploads"

        assert sandbox.upload_path == "/workspace/uploads"


class TestSetTimeout:
    """Tests for set_timeout method."""

    @pytest.mark.asyncio
    async def test_creates_timeout_task(self):
        sandbox = _make_sandbox()

        await sandbox.set_timeout(300)

        assert sandbox._timeout_task is not None
        assert not sandbox._timeout_task.done()

        # Cleanup
        sandbox._timeout_task.cancel()

    @pytest.mark.asyncio
    async def test_replaces_existing_timeout(self):
        sandbox = _make_sandbox()

        await sandbox.set_timeout(300)
        first_task = sandbox._timeout_task

        await sandbox.set_timeout(600)
        second_task = sandbox._timeout_task

        await asyncio.sleep(0)  # Let event loop process cancellation
        assert first_task.cancelled()
        assert second_task is not first_task

        # Cleanup
        second_task.cancel()

    @pytest.mark.asyncio
    async def test_uses_caller_session_when_db_passed(self):
        """Regression test for the 2026-04-24 pool-claim self-deadlock.

        When ``db`` is provided, ``set_timeout`` MUST mutate ``timeout_at``
        on the caller's session and MUST NOT open a second DB session via
        ``get_db_session_local``. Opening a second session while the caller
        holds a row-lock on the same ``agent_sandboxes`` row produces a
        self-deadlock that exhausts the asyncpg connection pool.

        See docs/design-docs/sandbox-pool-claim-self-deadlock.md.
        """
        import uuid as _uuid

        sandbox = _make_sandbox(sandbox_id=str(_uuid.uuid4()))

        record = MagicMock()
        record.timeout_at = None

        scalar_result = MagicMock()
        scalar_result.scalar_one_or_none.return_value = record

        db = MagicMock()
        db.execute = AsyncMock(return_value=scalar_result)
        db.commit = AsyncMock()

        with patch("ii_agent.core.db.get_db_session_local") as mock_get_session:
            await sandbox.set_timeout(300, db=db)

            # Critical invariant: no separate DB session was opened.
            mock_get_session.assert_not_called()

        # The caller's session was used to mutate the row.
        db.execute.assert_awaited_once()
        # Caller owns commit/rollback — set_timeout must not commit.
        db.commit.assert_not_called()
        assert record.timeout_at is not None

        # Cleanup
        if sandbox._timeout_task:
            sandbox._timeout_task.cancel()


class TestCreate:
    """Tests for DockerSandbox.create class method."""

    def setup_method(self):
        from ii_agent.agents.sandboxes.port_manager import PortPoolManager

        PortPoolManager.reset_instance()
        DockerSandbox._docker_client = None

    def teardown_method(self):
        from ii_agent.agents.sandboxes.port_manager import PortPoolManager

        PortPoolManager.reset_instance()
        DockerSandbox._docker_client = None

    @pytest.mark.asyncio
    async def test_create_success(self):
        mock_container = MagicMock()
        mock_container.id = "new-container-123"
        mock_container.status = "running"
        mock_container.attrs = {
            "NetworkSettings": {
                "Networks": {"ii-network": {"IPAddress": "172.18.0.5"}},
            }
        }

        mock_client = MagicMock()
        mock_client.containers.run.return_value = mock_container

        mock_settings = MagicMock()
        mock_settings.sandbox.docker_image = "ii-agent-sandbox:latest"
        mock_settings.sandbox.docker_network = "ii-network"
        mock_settings.sandbox.mcp_server_port = 6060
        mock_settings.sandbox.code_server_port = 9000
        mock_settings.sandbox.novnc_port = 6080
        mock_settings.sandbox.timeout_seconds = 0
        mock_settings.sandbox.max_concurrent_sandboxes = 0

        mock_httpx_response = MagicMock()
        mock_httpx_response.status_code = 200

        with (
            patch.object(DockerSandbox, "_get_docker_client", return_value=mock_client),
            patch("ii_agent.agents.sandboxes.docker.get_settings", return_value=mock_settings),
            patch("httpx.AsyncClient") as mock_httpx_cls,
        ):
            mock_httpx_client = AsyncMock()
            mock_httpx_client.get.return_value = mock_httpx_response
            mock_httpx_cls.return_value.__aenter__ = AsyncMock(return_value=mock_httpx_client)
            mock_httpx_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            sandbox = await DockerSandbox.create(
                sandbox_id="create-test-id",
                session_id="session-abc",
            )

        assert sandbox.sandbox_id == "create-test-id"
        assert sandbox.session_id == "session-abc"
        assert sandbox.status == SandboxStatus.RUNNING
        assert sandbox._container is mock_container
        mock_client.containers.run.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_image_not_found(self):
        import docker as docker_lib

        mock_client = MagicMock()
        mock_client.containers.run.side_effect = docker_lib.errors.ImageNotFound("not found")

        mock_settings = MagicMock()
        mock_settings.sandbox.docker_image = "missing-image:v1"
        mock_settings.sandbox.docker_network = "net"
        mock_settings.sandbox.mcp_server_port = 6060
        mock_settings.sandbox.code_server_port = 9000
        mock_settings.sandbox.novnc_port = 6080
        mock_settings.sandbox.max_concurrent_sandboxes = 0

        with (
            patch.object(DockerSandbox, "_get_docker_client", return_value=mock_client),
            patch("ii_agent.agents.sandboxes.docker.get_settings", return_value=mock_settings),
        ):
            with pytest.raises(SandboxCreationError, match="not found"):
                await DockerSandbox.create(
                    sandbox_id="create-fail-id",
                    session_id="session-abc",
                )

    @pytest.mark.asyncio
    async def test_create_api_error(self):
        from docker.errors import APIError as DockerAPIError

        mock_client = MagicMock()
        mock_client.containers.run.side_effect = DockerAPIError("out of memory")

        mock_settings = MagicMock()
        mock_settings.sandbox.docker_image = "img"
        mock_settings.sandbox.docker_network = "net"
        mock_settings.sandbox.mcp_server_port = 6060
        mock_settings.sandbox.code_server_port = 9000
        mock_settings.sandbox.novnc_port = 6080
        mock_settings.sandbox.max_concurrent_sandboxes = 0

        with (
            patch.object(DockerSandbox, "_get_docker_client", return_value=mock_client),
            patch("ii_agent.agents.sandboxes.docker.get_settings", return_value=mock_settings),
        ):
            with pytest.raises(SandboxCreationError, match="Failed to create"):
                await DockerSandbox.create(
                    sandbox_id="create-api-fail",
                    session_id="session-abc",
                )


class TestConnect:
    """Tests for DockerSandbox.connect class method."""

    def setup_method(self):
        from ii_agent.agents.sandboxes.port_manager import PortPoolManager

        PortPoolManager.reset_instance()
        DockerSandbox._docker_client = None

    def teardown_method(self):
        from ii_agent.agents.sandboxes.port_manager import PortPoolManager

        PortPoolManager.reset_instance()
        DockerSandbox._docker_client = None

    @pytest.mark.asyncio
    async def test_connect_success(self):
        mock_container = MagicMock()
        mock_container.id = "existing-container"
        mock_container.status = "running"
        mock_container.attrs = {
            "NetworkSettings": {
                "Ports": {
                    "6060/tcp": [{"HostPort": "30100"}],
                    "9000/tcp": [{"HostPort": "30101"}],
                }
            }
        }

        mock_client = MagicMock()
        mock_client.containers.get.return_value = mock_container

        mock_settings = MagicMock()

        with (
            patch.object(DockerSandbox, "_get_docker_client", return_value=mock_client),
            patch("ii_agent.agents.sandboxes.docker.get_settings", return_value=mock_settings),
        ):
            sandbox = await DockerSandbox.connect(
                sandbox_id="connect-test",
                session_id="session-xyz",
                provider_sandbox_id="existing-container",
            )

        assert sandbox.sandbox_id == "connect-test"
        assert sandbox._port_mappings[6060] == 30100
        assert sandbox._port_mappings[9000] == 30101
        assert sandbox.status == SandboxStatus.RUNNING

    @pytest.mark.asyncio
    async def test_connect_not_found(self):
        from docker.errors import NotFound as DockerNotFound

        mock_client = MagicMock()
        mock_client.containers.get.side_effect = DockerNotFound("gone")
        mock_client.containers.list.return_value = []

        mock_settings = MagicMock()

        with (
            patch.object(DockerSandbox, "_get_docker_client", return_value=mock_client),
            patch("ii_agent.agents.sandboxes.docker.get_settings", return_value=mock_settings),
        ):
            with pytest.raises(SandboxNotFoundException):
                await DockerSandbox.connect(
                    sandbox_id="gone-id",
                    session_id="session-xyz",
                    provider_sandbox_id="nonexistent",
                )

    @pytest.mark.asyncio
    async def test_connect_not_running(self):
        mock_container = MagicMock()
        mock_container.id = "stopped-container"
        mock_container.status = "exited"

        mock_client = MagicMock()
        mock_client.containers.get.return_value = mock_container

        mock_settings = MagicMock()

        with (
            patch.object(DockerSandbox, "_get_docker_client", return_value=mock_client),
            patch("ii_agent.agents.sandboxes.docker.get_settings", return_value=mock_settings),
        ):
            with pytest.raises(SandboxNotInitializedError, match="not running"):
                await DockerSandbox.connect(
                    sandbox_id="stopped-id",
                    session_id="session-xyz",
                    provider_sandbox_id="stopped-container",
                )


class TestDownloadFile:
    """Tests for download_file method."""

    @pytest.mark.asyncio
    async def test_download_text(self):
        sandbox = _make_sandbox()
        tar_data = _make_tar_bytes("file.txt", b"hello text")
        sandbox._container.get_archive.return_value = (iter([tar_data]), {})

        result = await sandbox.download_file("/workspace/file.txt", format="text")
        assert result == "hello text"

    @pytest.mark.asyncio
    async def test_download_bytes(self):
        sandbox = _make_sandbox()
        tar_data = _make_tar_bytes("file.bin", b"\x00\x01\x02")
        sandbox._container.get_archive.return_value = (iter([tar_data]), {})

        result = await sandbox.download_file("/workspace/file.bin", format="bytes")
        assert result == b"\x00\x01\x02"

    @pytest.mark.asyncio
    async def test_download_not_found(self):
        from docker.errors import NotFound as DockerNotFound

        sandbox = _make_sandbox()
        sandbox._container.get_archive.side_effect = DockerNotFound("missing")

        result = await sandbox.download_file("/workspace/missing.txt")
        assert result is None


class TestUploadFile:
    """Tests for upload_file method."""

    @pytest.mark.asyncio
    async def test_upload_success(self):
        sandbox = _make_sandbox()

        result = await sandbox.upload_file(b"file content", "/workspace/uploaded.txt")
        assert result is True
        sandbox._container.put_archive.assert_called_once()


class TestWriteFiles:
    """Tests for write_files method."""

    @pytest.mark.asyncio
    async def test_write_multiple_files(self):
        from ii_agent.agents.sandboxes.schemas import FileUpload

        sandbox = _make_sandbox()

        files = [
            FileUpload(path="/workspace/a.txt", content="aaa"),
            FileUpload(path="/workspace/b.txt", content="bbb"),
        ]

        results = await sandbox.write_files(files)
        assert len(results) == 2
        assert results[0].name == "a.txt"
        assert results[1].name == "b.txt"


class TestPutFileVariants:
    """Tests for _put_file with bytes and IO-like objects."""

    @pytest.mark.asyncio
    async def test_put_file_bytes(self):
        sandbox = _make_sandbox()

        await sandbox._put_file("/workspace/data.bin", b"raw bytes")
        sandbox._container.put_archive.assert_called_once()

    @pytest.mark.asyncio
    async def test_put_file_io_object(self):
        sandbox = _make_sandbox()
        file_like = io.BytesIO(b"io content")

        await sandbox._put_file("/workspace/data.txt", file_like)
        sandbox._container.put_archive.assert_called_once()

    @pytest.mark.asyncio
    async def test_put_file_string_io(self):
        sandbox = _make_sandbox()
        file_like = io.StringIO("string io content")

        await sandbox._put_file("/workspace/data.txt", file_like)
        sandbox._container.put_archive.assert_called_once()


class TestListFilesRecursive:
    """Tests for list_files_recursive method."""

    @pytest.mark.asyncio
    async def test_lists_files_and_dirs(self):
        sandbox = _make_sandbox()
        # First call: list /workspace
        # Second call: list /workspace/src (subdirectory)
        sandbox._container.exec_run.side_effect = [
            (0, b"src/\nREADME.md\n"),
            (0, b"main.py\n"),
        ]

        tree = await sandbox.list_files_recursive("/workspace", max_depth=2)

        assert tree.type == "directory"
        assert len(tree.children) == 2
        # Dirs sorted before files
        assert tree.children[0].name == "src"
        assert tree.children[0].type == "directory"
        assert tree.children[1].name == "README.md"
        assert tree.children[1].type == "file"

    @pytest.mark.asyncio
    async def test_skips_excluded_dirs(self):
        sandbox = _make_sandbox()
        sandbox._container.exec_run.return_value = (0, b"node_modules/\napp.js\n")

        tree = await sandbox.list_files_recursive("/workspace", max_depth=2)

        names = [c.name for c in tree.children]
        assert "node_modules" not in names
        assert "app.js" in names

    @pytest.mark.asyncio
    async def test_respects_max_depth(self):
        sandbox = _make_sandbox()
        sandbox._container.exec_run.return_value = (0, b"deep/\n")

        tree = await sandbox.list_files_recursive("/workspace", max_depth=0)

        # At max depth, directories are listed but not recursed into
        assert len(tree.children) == 1
        assert tree.children[0].children == []

    @pytest.mark.asyncio
    async def test_handles_ls_failure(self):
        sandbox = _make_sandbox()
        sandbox._container.exec_run.return_value = (1, b"")

        tree = await sandbox.list_files_recursive("/workspace")
        assert tree.type == "directory"
        assert tree.children == []


class TestReadFileContent:
    """Tests for read_file_content method."""

    @pytest.mark.asyncio
    async def test_reads_text_file(self):
        sandbox = _make_sandbox()
        tar_data = _make_tar_bytes("test.py", b"print('hello')")
        sandbox._container.get_archive.return_value = (iter([tar_data]), {})

        result = await sandbox.read_file_content("/workspace/test.py")
        assert result.content == "print('hello')"
        assert result.language == "python"

    @pytest.mark.asyncio
    async def test_returns_image_kind_for_images(self):
        sandbox = _make_sandbox()

        result = await sandbox.read_file_content("/workspace/photo.png")
        assert result.file_kind == "image"
        assert result.content is None

    @pytest.mark.asyncio
    async def test_returns_binary_kind_for_binary(self):
        sandbox = _make_sandbox()

        result = await sandbox.read_file_content("/workspace/data.exe")
        assert result.file_kind == "binary"

    @pytest.mark.asyncio
    async def test_raises_on_missing_file(self):
        from docker.errors import NotFound as DockerNotFound

        sandbox = _make_sandbox()
        sandbox._container.get_archive.side_effect = DockerNotFound("missing")

        with pytest.raises(SandboxOperationError, match="File not found"):
            await sandbox.read_file_content("/workspace/missing.py")


class TestWaitForReady:
    """Tests for _wait_for_ready method."""

    @pytest.mark.asyncio
    async def test_succeeds_on_healthy_response(self):
        sandbox = _make_sandbox(port_mappings={6060: 30000})
        sandbox._config = MagicMock()
        sandbox._config.sandbox.docker_network = "ii-network"
        sandbox._config.sandbox.docker_host = "localhost"
        sandbox._container.attrs = {
            "NetworkSettings": {
                "Networks": {"ii-network": {"IPAddress": "172.18.0.5"}},
            }
        }

        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch("httpx.AsyncClient") as mock_httpx_cls:
            mock_httpx_client = AsyncMock()
            mock_httpx_client.get.return_value = mock_response
            mock_httpx_cls.return_value.__aenter__ = AsyncMock(return_value=mock_httpx_client)
            mock_httpx_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            await sandbox._wait_for_ready(timeout=5)

        mock_httpx_client.get.assert_called()

    @pytest.mark.asyncio
    async def test_timeout_raises(self):
        sandbox = _make_sandbox(port_mappings={6060: 30000})
        sandbox._config = MagicMock()
        sandbox._config.sandbox.docker_network = "ii-network"
        sandbox._config.sandbox.docker_host = "localhost"
        sandbox._container.attrs = {
            "NetworkSettings": {"Networks": {}},
        }

        with patch("httpx.AsyncClient") as mock_httpx_cls:
            mock_httpx_client = AsyncMock()
            mock_httpx_client.get.side_effect = ConnectionError("refused")
            mock_httpx_cls.return_value.__aenter__ = AsyncMock(return_value=mock_httpx_client)
            mock_httpx_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            with pytest.raises(SandboxTimeoutException, match="did not become ready"):
                await sandbox._wait_for_ready(timeout=0)

    @pytest.mark.asyncio
    async def test_uses_host_port_when_no_network_ip(self):
        sandbox = _make_sandbox(port_mappings={6060: 31000})
        sandbox._config = MagicMock()
        sandbox._config.sandbox.docker_network = "ii-network"
        sandbox._config.sandbox.docker_host = "localhost"
        sandbox._config.sandbox.mcp_server_port = 6060
        sandbox._container.attrs = {
            "NetworkSettings": {"Networks": {}},
        }

        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch("httpx.AsyncClient") as mock_httpx_cls:
            mock_httpx_client = AsyncMock()
            mock_httpx_client.get.return_value = mock_response
            mock_httpx_cls.return_value.__aenter__ = AsyncMock(return_value=mock_httpx_client)
            mock_httpx_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            await sandbox._wait_for_ready(timeout=5)

        # Verify it used localhost with the host-mapped port
        call_url = mock_httpx_client.get.call_args[0][0]
        assert "localhost:31000" in call_url


class TestGetMcpClient:
    """Tests for get_mcp_client method."""

    def test_returns_client_with_mcp_path(self):
        sandbox = _make_sandbox()
        sandbox._config = MagicMock()
        sandbox._config.mcp.timeout = 30

        with patch("fastmcp.Client") as mock_client_cls:
            sandbox.get_mcp_client("http://172.18.0.5:6060")
            mock_client_cls.assert_called_once_with("http://172.18.0.5:6060/mcp/", timeout=30)


class TestExposePortInternalFallback:
    """Tests for expose_port internal mode fallback to host-mapped."""

    @pytest.mark.asyncio
    async def test_internal_falls_back_to_host_port(self):
        sandbox = _make_sandbox(port_mappings={5000: 32000})
        sandbox._container.attrs = {
            "NetworkSettings": {
                "Networks": {},  # No networks — no container IP
                "Ports": {},
            }
        }

        url = await sandbox.expose_port(5000, external=False)
        assert url == "http://localhost:32000"

    @pytest.mark.asyncio
    async def test_internal_raises_when_no_ip_no_mapping(self):
        sandbox = _make_sandbox(port_mappings={})
        sandbox._container.attrs = {
            "NetworkSettings": {
                "Networks": {},
                "Ports": {},
            }
        }

        with pytest.raises(SandboxOperationError, match="Cannot resolve"):
            await sandbox.expose_port(9999, external=False)


class TestA2AAdapterEnv:
    """Tests for DockerSandbox._a2a_adapter_env()."""

    def _cfg(self, backend: str = "copilot") -> MagicMock:
        cfg = MagicMock()
        cfg.agent.a2a_backend = backend
        cfg.agent.a2a_adapter_timeout_long_horizon = 3600
        cfg.agent.a2a_adapter_activity_timeout_long_horizon = 900
        cfg.agent.a2a_adapter_long_horizon_agent_kinds = {"deep_research"}
        return cfg

    def test_returns_backend_key(self):
        env = DockerSandbox._a2a_adapter_env(self._cfg("copilot"))
        assert env["SANDBOX_ADAPTER_BACKEND"] == "copilot"

    def test_backend_value_passthrough(self):
        env = DockerSandbox._a2a_adapter_env(self._cfg("claude-code"))
        assert env["SANDBOX_ADAPTER_BACKEND"] == "claude-code"

    @patch.dict("os.environ", {"GITHUB_TOKEN": "ghp_abc"}, clear=False)
    def test_forwards_github_token(self):
        env = DockerSandbox._a2a_adapter_env(self._cfg("copilot"))
        assert env["GITHUB_TOKEN"] == "ghp_abc"

    @patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-ant-abc"}, clear=False)
    def test_forwards_anthropic_key(self):
        env = DockerSandbox._a2a_adapter_env(self._cfg("claude-code"))
        assert env["ANTHROPIC_API_KEY"] == "sk-ant-abc"

    @patch.dict("os.environ", {"OPENAI_API_KEY": "sk-oai-abc"}, clear=False)
    def test_forwards_openai_key(self):
        env = DockerSandbox._a2a_adapter_env(self._cfg("codex"))
        assert env["OPENAI_API_KEY"] == "sk-oai-abc"

    @patch.dict("os.environ", {}, clear=True)
    def test_empty_tokens_not_forwarded(self):
        env = DockerSandbox._a2a_adapter_env(self._cfg("copilot"))
        assert "GITHUB_TOKEN" not in env
        assert "GH_TOKEN" not in env
        assert "ANTHROPIC_API_KEY" not in env
        assert "OPENAI_API_KEY" not in env
        assert env == {"SANDBOX_ADAPTER_BACKEND": "copilot"}

    @patch.dict(
        "os.environ",
        {"GITHUB_TOKEN": "ghp_1", "ANTHROPIC_API_KEY": "sk-ant-2", "OPENAI_API_KEY": "sk-oai-3"},
        clear=False,
    )
    def test_forwards_all_available_tokens(self):
        """All set tokens are forwarded regardless of selected backend."""
        env = DockerSandbox._a2a_adapter_env(self._cfg("copilot"))
        assert env["GITHUB_TOKEN"] == "ghp_1"
        assert env["ANTHROPIC_API_KEY"] == "sk-ant-2"
        assert env["OPENAI_API_KEY"] == "sk-oai-3"

    @patch.dict("os.environ", {}, clear=True)
    def test_long_horizon_agent_kind_overrides_timeouts(self):
        """deep_research agent kind gets the long-horizon adapter timeout."""
        env = DockerSandbox._a2a_adapter_env(
            self._cfg("copilot"), metadata={"agent_kind": "deep_research"}
        )
        assert env["A2A_COPILOT_TIMEOUT"] == "3600"
        assert env["A2A_CLAUDE_CODE_TIMEOUT"] == "3600"
        assert env["A2A_CODEX_TIMEOUT"] == "3600"
        assert env["A2A_COPILOT_ACTIVITY_TIMEOUT"] == "900"
        assert env["A2A_CLAUDE_CODE_ACTIVITY_TIMEOUT"] == "900"
        assert env["A2A_CODEX_ACTIVITY_TIMEOUT"] == "900"

    @patch.dict("os.environ", {"A2A_COPILOT_TIMEOUT": "900"}, clear=True)
    def test_non_long_horizon_agent_kind_does_not_override(self):
        """Non-long-horizon agent kinds keep the operator-configured timeout."""
        env = DockerSandbox._a2a_adapter_env(
            self._cfg("copilot"), metadata={"agent_kind": "general"}
        )
        assert env["A2A_COPILOT_TIMEOUT"] == "900"
        # Other backends' timeouts are not set when env is unset and not long-horizon.
        assert "A2A_CLAUDE_CODE_TIMEOUT" not in env
        assert "A2A_CODEX_TIMEOUT" not in env

    @patch.dict("os.environ", {"A2A_COPILOT_TIMEOUT": "900"}, clear=True)
    def test_missing_metadata_does_not_override(self):
        """Missing/None metadata behaves as non-long-horizon."""
        env = DockerSandbox._a2a_adapter_env(self._cfg("copilot"))
        assert env["A2A_COPILOT_TIMEOUT"] == "900"


class TestA2AAdapterGating:
    """Tests that the sandbox only allocates A2A resources in a2a mode."""

    def _cfg(self, inner_loop_mode: str = "native", backend: str = "copilot") -> MagicMock:
        cfg = MagicMock()
        cfg.agent.inner_loop_mode = inner_loop_mode
        cfg.agent.a2a_backend = backend
        cfg.agent.a2a_adapter_timeout_long_horizon = 3600
        cfg.agent.a2a_adapter_activity_timeout_long_horizon = 900
        cfg.agent.a2a_adapter_long_horizon_agent_kinds = {"deep_research"}
        cfg.sandbox.docker_image = "ii-agent-sandbox:latest"
        cfg.sandbox.docker_network = "test-net"
        cfg.sandbox.max_concurrent_sandboxes = 0
        cfg.sandbox.mcp_server_port = MCP_SERVER_PORT
        cfg.sandbox.code_server_port = CODE_SERVER_PORT
        cfg.sandbox.novnc_port = NOVNC_PORT
        cfg.sandbox.timeout_seconds = 0
        return cfg

    @patch("ii_agent.agents.sandboxes.docker.get_settings")
    @patch("ii_agent.agents.sandboxes.docker.DockerSandbox._get_docker_client")
    @patch("ii_agent.agents.sandboxes.docker.PortPoolManager.get_instance")
    @patch.dict("os.environ", {}, clear=True)
    async def test_native_mode_excludes_adapter_port(
        self, mock_pool_cls, mock_docker_cls, mock_settings
    ):
        """In native mode, the adapter port is not allocated."""
        cfg = self._cfg("native")
        mock_settings.return_value = cfg

        mock_pool = MagicMock()
        mock_pool.get_stats.return_value = {
            "sandboxes": 0,
            "free": 100,
            "port_range": "30000-39999",
        }
        port_set = MagicMock()
        port_set.to_docker_ports.return_value = {}
        port_set.allocations = {}
        mock_pool.allocate_ports.return_value = port_set
        mock_pool_cls.return_value = mock_pool

        mock_container = MagicMock()
        mock_container.id = "abc123456789"
        mock_client = MagicMock()
        mock_client.containers.run.return_value = mock_container
        mock_docker_cls.return_value = mock_client

        with patch.object(DockerSandbox, "_wait_for_ready", new_callable=AsyncMock):
            await DockerSandbox.create("sid", "sess")

        # Verify allocate_ports was called without the adapter port
        call_args = mock_pool.allocate_ports.call_args
        assert ADAPTER_CONTAINER_PORT not in call_args.kwargs.get(
            "container_ports", call_args[1].get("container_ports", [])
        )

        # Verify SANDBOX_ADAPTER_ENABLED is NOT in environment
        run_call = mock_client.containers.run.call_args
        env = run_call.kwargs.get("environment", run_call[1].get("environment", {}))
        assert "SANDBOX_ADAPTER_ENABLED" not in env
        assert "SANDBOX_ADAPTER_BACKEND" not in env

    @patch("ii_agent.agents.sandboxes.docker.get_settings")
    @patch("ii_agent.agents.sandboxes.docker.DockerSandbox._get_docker_client")
    @patch("ii_agent.agents.sandboxes.docker.PortPoolManager.get_instance")
    @patch.dict("os.environ", {"GITHUB_TOKEN": "ghp_test"}, clear=True)
    async def test_a2a_mode_includes_adapter_port_and_env(
        self, mock_pool_cls, mock_docker_cls, mock_settings
    ):
        """In a2a mode, the adapter port is allocated and env is set."""
        cfg = self._cfg("a2a", "copilot")
        mock_settings.return_value = cfg

        mock_pool = MagicMock()
        mock_pool.get_stats.return_value = {
            "sandboxes": 0,
            "free": 100,
            "port_range": "30000-39999",
        }
        port_set = MagicMock()
        port_set.to_docker_ports.return_value = {}
        port_set.allocations = {}
        mock_pool.allocate_ports.return_value = port_set
        mock_pool_cls.return_value = mock_pool

        mock_container = MagicMock()
        mock_container.id = "abc123456789"
        mock_client = MagicMock()
        mock_client.containers.run.return_value = mock_container
        mock_docker_cls.return_value = mock_client

        with patch.object(DockerSandbox, "_wait_for_ready", new_callable=AsyncMock):
            await DockerSandbox.create("sid", "sess")

        # Verify allocate_ports includes the adapter port
        call_args = mock_pool.allocate_ports.call_args
        container_ports = call_args.kwargs.get(
            "container_ports", call_args[1].get("container_ports", [])
        )
        assert ADAPTER_CONTAINER_PORT in container_ports

        # Verify environment includes adapter vars
        run_call = mock_client.containers.run.call_args
        env = run_call.kwargs.get("environment", run_call[1].get("environment", {}))
        assert env["SANDBOX_ADAPTER_ENABLED"] == "true"
        assert env["SANDBOX_ADAPTER_BACKEND"] == "copilot"
        assert env["GITHUB_TOKEN"] == "ghp_test"

    @patch("ii_agent.agents.sandboxes.docker.get_settings")
    @patch("ii_agent.agents.sandboxes.docker.DockerSandbox._get_docker_client")
    @patch("ii_agent.agents.sandboxes.docker.PortPoolManager.get_instance")
    @patch.dict("os.environ", {}, clear=True)
    async def test_native_mode_needs_fewer_ports(
        self, mock_pool_cls, mock_docker_cls, mock_settings
    ):
        """Native mode requires 6 ports; a2a mode requires 7."""
        cfg_native = self._cfg("native")
        mock_settings.return_value = cfg_native

        mock_pool = MagicMock()
        # Only 6 ports available — should succeed for native
        mock_pool.get_stats.return_value = {"sandboxes": 0, "free": 6, "port_range": "30000-30005"}
        mock_pool_cls.return_value = mock_pool

        port_set = MagicMock()
        port_set.to_docker_ports.return_value = {}
        port_set.allocations = {}
        mock_pool.allocate_ports.return_value = port_set

        mock_container = MagicMock()
        mock_container.id = "abc123456789"
        mock_client = MagicMock()
        mock_client.containers.run.return_value = mock_container
        mock_docker_cls.return_value = mock_client

        with patch.object(DockerSandbox, "_wait_for_ready", new_callable=AsyncMock):
            await DockerSandbox.create("sid", "sess")

        # Now test a2a with same 6 ports — should fail
        cfg_a2a = self._cfg("a2a")
        mock_settings.return_value = cfg_a2a

        with pytest.raises(SandboxCreationError, match="Insufficient ports"):
            await DockerSandbox.create("sid2", "sess2")

    @patch("ii_agent.agents.sandboxes.docker.get_settings")
    @patch("ii_agent.agents.sandboxes.docker.DockerSandbox._get_docker_client")
    @patch("ii_agent.agents.sandboxes.docker.PortPoolManager.get_instance")
    @patch.dict(
        "os.environ",
        {"GITHUB_TOKEN": "ghp_leaked", "ANTHROPIC_API_KEY": "sk-ant-leaked"},
        clear=True,
    )
    async def test_native_mode_does_not_leak_tokens(
        self, mock_pool_cls, mock_docker_cls, mock_settings
    ):
        """API tokens in the backend env must NOT appear in native sandbox env."""
        cfg = self._cfg("native")
        mock_settings.return_value = cfg

        mock_pool = MagicMock()
        mock_pool.get_stats.return_value = {
            "sandboxes": 0,
            "free": 100,
            "port_range": "30000-39999",
        }
        port_set = MagicMock()
        port_set.to_docker_ports.return_value = {}
        port_set.allocations = {}
        mock_pool.allocate_ports.return_value = port_set
        mock_pool_cls.return_value = mock_pool

        mock_container = MagicMock()
        mock_container.id = "abc123456789"
        mock_client = MagicMock()
        mock_client.containers.run.return_value = mock_container
        mock_docker_cls.return_value = mock_client

        with patch.object(DockerSandbox, "_wait_for_ready", new_callable=AsyncMock):
            await DockerSandbox.create("sid", "sess")

        run_call = mock_client.containers.run.call_args
        env = run_call.kwargs.get("environment", run_call[1].get("environment", {}))
        # None of the A2A-related env vars should be present
        for key in (
            "SANDBOX_ADAPTER_ENABLED",
            "SANDBOX_ADAPTER_BACKEND",
            "GITHUB_TOKEN",
            "GH_TOKEN",
            "ANTHROPIC_API_KEY",
            "OPENAI_API_KEY",
            "A2A_COPILOT_TIMEOUT",
            "A2A_CLAUDE_CODE_TIMEOUT",
            "A2A_CODEX_TIMEOUT",
        ):
            assert key not in env, f"{key} leaked into native-mode sandbox env"
