"""Unit tests for the PortPoolManager class.

This module contains tests for the port pool management system,
including allocation, release, and cleanup operations.
"""

import pytest
from unittest.mock import MagicMock

from ii_agent.agents.sandboxes.port_manager import (
    PortPoolManager,
    PortAllocation,
    SandboxPortSet,
    get_default_port_allocations,
    DEFAULT_PORT_RANGE_START,
    DEFAULT_PORT_RANGE_END,
    COMMON_DEV_PORTS,
)


class TestPortAllocation:
    """Tests for the PortAllocation dataclass."""

    def test_create_allocation(self):
        """Test creating a port allocation."""
        alloc = PortAllocation(
            sandbox_id="sandbox-123",
            container_port=3000,
            host_port=30000,
            service_name="dev_server",
        )
        assert alloc.sandbox_id == "sandbox-123"
        assert alloc.container_port == 3000
        assert alloc.host_port == 30000
        assert alloc.service_name == "dev_server"

    def test_allocation_without_service_name(self):
        """Test allocation with default service_name."""
        alloc = PortAllocation(
            sandbox_id="sandbox-123",
            container_port=8080,
            host_port=30001,
        )
        assert alloc.service_name is None


class TestSandboxPortSet:
    """Tests for the SandboxPortSet dataclass."""

    def test_create_empty_port_set(self):
        """Test creating an empty port set."""
        port_set = SandboxPortSet(sandbox_id="sandbox-abc")
        assert port_set.sandbox_id == "sandbox-abc"
        assert port_set.container_id is None
        assert len(port_set.allocations) == 0

    def test_get_host_port_existing(self):
        """Test getting host port for existing allocation."""
        port_set = SandboxPortSet(sandbox_id="sandbox-abc")
        port_set.allocations[3000] = PortAllocation(
            sandbox_id="sandbox-abc",
            container_port=3000,
            host_port=30005,
        )
        assert port_set.get_host_port(3000) == 30005

    def test_get_host_port_nonexistent(self):
        """Test getting host port for non-existent allocation."""
        port_set = SandboxPortSet(sandbox_id="sandbox-abc")
        assert port_set.get_host_port(3000) is None

    def test_to_docker_ports(self):
        """Test converting to Docker ports dict format."""
        port_set = SandboxPortSet(sandbox_id="sandbox-abc")
        port_set.allocations[3000] = PortAllocation(
            sandbox_id="sandbox-abc",
            container_port=3000,
            host_port=30000,
        )
        port_set.allocations[6060] = PortAllocation(
            sandbox_id="sandbox-abc",
            container_port=6060,
            host_port=30001,
        )

        docker_ports = port_set.to_docker_ports()

        assert docker_ports == {
            "3000/tcp": 30000,
            "6060/tcp": 30001,
        }


class TestPortPoolManager:
    """Tests for the PortPoolManager class."""

    def setup_method(self):
        """Reset singleton before each test."""
        PortPoolManager.reset_instance()

    def teardown_method(self):
        """Clean up singleton after each test."""
        PortPoolManager.reset_instance()

    def test_singleton_pattern(self):
        """Test that get_instance returns the same instance."""
        instance1 = PortPoolManager.get_instance()
        instance2 = PortPoolManager.get_instance()
        assert instance1 is instance2

    def test_reset_instance(self):
        """Test that reset_instance creates a new instance."""
        instance1 = PortPoolManager.get_instance()
        PortPoolManager.reset_instance()
        instance2 = PortPoolManager.get_instance()
        assert instance1 is not instance2

    def test_default_port_range(self):
        """Test default port range."""
        manager = PortPoolManager.get_instance()
        stats = manager.get_stats()
        assert stats["port_range"] == f"{DEFAULT_PORT_RANGE_START}-{DEFAULT_PORT_RANGE_END}"

    def test_custom_port_range(self):
        """Test custom port range."""
        PortPoolManager.reset_instance()
        manager = PortPoolManager(port_range_start=40000, port_range_end=40099)
        stats = manager.get_stats()
        assert stats["port_range"] == "40000-40099"
        assert stats["total_available"] == 100

    def test_allocate_ports_success(self):
        """Test successful port allocation."""
        manager = PortPoolManager.get_instance()

        port_set = manager.allocate_ports(
            sandbox_id="sandbox-123",
            container_ports=[3000, 6060, 9000],
        )

        assert port_set.sandbox_id == "sandbox-123"
        assert len(port_set.allocations) == 3
        assert 3000 in port_set.allocations
        assert 6060 in port_set.allocations
        assert 9000 in port_set.allocations

        # Host ports should be unique
        host_ports = [a.host_port for a in port_set.allocations.values()]
        assert len(host_ports) == len(set(host_ports))

    def test_allocate_ports_with_service_names(self):
        """Test port allocation with service names."""
        manager = PortPoolManager.get_instance()

        port_set = manager.allocate_ports(
            sandbox_id="sandbox-123",
            container_ports=[3000, 6060],
            service_names={3000: "dev_server", 6060: "mcp"},
        )

        assert port_set.allocations[3000].service_name == "dev_server"
        assert port_set.allocations[6060].service_name == "mcp"

    def test_allocate_ports_duplicate_sandbox_raises(self):
        """Test that allocating to same sandbox twice raises error."""
        manager = PortPoolManager.get_instance()

        manager.allocate_ports(
            sandbox_id="sandbox-123",
            container_ports=[3000],
        )

        with pytest.raises(ValueError, match="already has port allocations"):
            manager.allocate_ports(
                sandbox_id="sandbox-123",
                container_ports=[6060],
            )

    def test_allocate_additional_port(self):
        """Test allocating additional port to existing sandbox."""
        manager = PortPoolManager.get_instance()

        manager.allocate_ports(
            sandbox_id="sandbox-123",
            container_ports=[3000],
        )

        host_port = manager.allocate_additional_port(
            sandbox_id="sandbox-123",
            container_port=6060,
            service_name="mcp",
        )

        assert host_port >= DEFAULT_PORT_RANGE_START
        assert host_port <= DEFAULT_PORT_RANGE_END

        port_set = manager.get_sandbox_ports("sandbox-123")
        assert 6060 in port_set.allocations

    def test_allocate_additional_port_returns_existing(self):
        """Test that requesting existing port returns same allocation."""
        manager = PortPoolManager.get_instance()

        port_set = manager.allocate_ports(
            sandbox_id="sandbox-123",
            container_ports=[3000],
        )
        original_host_port = port_set.allocations[3000].host_port

        returned_port = manager.allocate_additional_port(
            sandbox_id="sandbox-123",
            container_port=3000,
        )

        assert returned_port == original_host_port

    def test_allocate_additional_port_unknown_sandbox(self):
        """Test allocating additional port to unknown sandbox raises."""
        manager = PortPoolManager.get_instance()

        with pytest.raises(ValueError, match="not found"):
            manager.allocate_additional_port(
                sandbox_id="nonexistent",
                container_port=3000,
            )

    def test_release_ports(self):
        """Test releasing ports."""
        manager = PortPoolManager.get_instance()

        manager.allocate_ports(
            sandbox_id="sandbox-123",
            container_ports=[3000, 6060, 9000],
        )

        initial_stats = manager.get_stats()
        assert initial_stats["allocated"] == 3

        released = manager.release_ports("sandbox-123")

        assert released == 3
        final_stats = manager.get_stats()
        assert final_stats["allocated"] == 0
        assert manager.get_sandbox_ports("sandbox-123") is None

    def test_release_ports_nonexistent(self):
        """Test releasing ports for nonexistent sandbox returns 0."""
        manager = PortPoolManager.get_instance()
        released = manager.release_ports("nonexistent")
        assert released == 0

    def test_get_host_port(self):
        """Test getting host port for sandbox/container port combo."""
        manager = PortPoolManager.get_instance()

        port_set = manager.allocate_ports(
            sandbox_id="sandbox-123",
            container_ports=[3000],
        )
        expected = port_set.allocations[3000].host_port

        result = manager.get_host_port("sandbox-123", 3000)
        assert result == expected

    def test_get_host_port_nonexistent(self):
        """Test getting host port for nonexistent returns None."""
        manager = PortPoolManager.get_instance()
        assert manager.get_host_port("nonexistent", 3000) is None

    def test_set_container_id(self):
        """Test setting container ID for port set."""
        manager = PortPoolManager.get_instance()

        manager.allocate_ports(
            sandbox_id="sandbox-123",
            container_ports=[3000],
        )

        manager.set_container_id("sandbox-123", "container-abc")

        port_set = manager.get_sandbox_ports("sandbox-123")
        assert port_set.container_id == "container-abc"

    def test_get_stats(self):
        """Test getting port pool statistics."""
        manager = PortPoolManager.get_instance()

        manager.allocate_ports(
            sandbox_id="sandbox-1",
            container_ports=[3000, 6060],
        )
        manager.allocate_ports(
            sandbox_id="sandbox-2",
            container_ports=[3000],
        )

        stats = manager.get_stats()

        assert stats["allocated"] == 3
        assert stats["sandboxes"] == 2
        assert stats["free"] == stats["total_available"] - 3

    def test_list_allocations(self):
        """Test listing all allocations."""
        manager = PortPoolManager.get_instance()

        manager.allocate_ports(
            sandbox_id="sandbox-123456789012",
            container_ports=[3000],
            service_names={3000: "dev"},
        )

        allocations = manager.list_allocations()

        assert len(allocations) == 1
        assert allocations[0]["sandbox_id"] == "sandbox-1234"  # truncated to 12 chars
        assert allocations[0]["container_port"] == 3000
        assert allocations[0]["service"] == "dev"

    def test_cleanup_orphaned_allocations(self):
        """Test cleaning up orphaned allocations."""
        manager = PortPoolManager.get_instance()

        # Allocate ports and set container ID
        manager.allocate_ports(
            sandbox_id="sandbox-123",
            container_ports=[3000],
        )
        manager.set_container_id("sandbox-123", "dead-container-id")

        # Mock Docker client that returns NotFound
        mock_client = MagicMock()
        from docker.errors import NotFound

        mock_client.containers.get.side_effect = NotFound("not found")

        cleaned = manager.cleanup_orphaned_allocations(mock_client)

        assert cleaned == 1
        assert manager.get_sandbox_ports("sandbox-123") is None

    def test_port_exhaustion_raises(self):
        """Test that exhausting ports raises RuntimeError."""
        # Create manager with very small range
        PortPoolManager.reset_instance()
        manager = PortPoolManager(port_range_start=50000, port_range_end=50001)

        # Allocate all ports
        manager.allocate_ports(
            sandbox_id="sandbox-1",
            container_ports=[3000, 6060],
        )

        # Try to allocate more
        with pytest.raises(RuntimeError, match="No available ports"):
            manager.allocate_ports(
                sandbox_id="sandbox-2",
                container_ports=[3000],
            )


class TestGetDefaultPortAllocations:
    """Tests for get_default_port_allocations function."""

    def test_returns_ports_and_names(self):
        """Test that function returns ports and service names."""
        ports, names = get_default_port_allocations()

        assert isinstance(ports, list)
        assert isinstance(names, dict)
        assert len(ports) > 0
        assert 6060 in ports  # MCP server
        assert 9000 in ports  # Code server

    def test_names_map_to_ports(self):
        """Test that all named ports are in the ports list."""
        ports, names = get_default_port_allocations()

        for port in names:
            assert port in ports


class TestCommonDevPorts:
    """Tests for COMMON_DEV_PORTS constant."""

    def test_includes_common_ports(self):
        """Test that common dev server ports are included."""
        assert 3000 in COMMON_DEV_PORTS  # React
        assert 5173 in COMMON_DEV_PORTS  # Vite
        assert 8080 in COMMON_DEV_PORTS  # General
        assert 4200 in COMMON_DEV_PORTS  # Angular
        assert 8000 in COMMON_DEV_PORTS  # Django/FastAPI


class TestScanExistingContainers:
    """Tests for scan_existing_containers method.

    This tests the startup scan that discovers existing sandbox containers
    and registers their port allocations to prevent conflicts after restart.
    """

    def setup_method(self):
        """Reset singleton before each test."""
        PortPoolManager.reset_instance()

    def teardown_method(self):
        """Clean up singleton after each test."""
        PortPoolManager.reset_instance()

    def _create_mock_container(
        self, name: str, status: str, port_mappings: dict, container_id: str = "abc123"
    ) -> MagicMock:
        """Helper to create a mock container with port mappings."""
        container = MagicMock()
        container.name = name
        container.status = status
        container.id = container_id

        # Build Ports structure like Docker returns
        ports = {}
        for container_port, host_port in port_mappings.items():
            ports[f"{container_port}/tcp"] = [{"HostPort": str(host_port)}]

        container.attrs = {
            "NetworkSettings": {"Ports": ports},
            "HostConfig": {"PortBindings": ports},
        }
        return container

    def test_scan_discovers_running_container(self):
        """Test that scan discovers a running sandbox container."""
        manager = PortPoolManager.get_instance()

        mock_container = self._create_mock_container(
            name="ii-sandbox-abc123def456",
            status="running",
            port_mappings={3000: 30000, 6060: 30001, 9000: 30002},
            container_id="container123",
        )

        mock_client = MagicMock()
        mock_client.containers.list.return_value = [mock_container]

        discovered = manager.scan_existing_containers(mock_client)

        assert discovered == 1
        stats = manager.get_stats()
        assert stats["allocated"] == 3
        assert 30000 in manager._allocated_ports
        assert 30001 in manager._allocated_ports
        assert 30002 in manager._allocated_ports

    def test_scan_skips_non_sandbox_containers(self):
        """Test that scan ignores containers not named ii-sandbox-*."""
        manager = PortPoolManager.get_instance()

        mock_container = self._create_mock_container(
            name="postgres", status="running", port_mappings={5432: 5432}
        )

        mock_client = MagicMock()
        mock_client.containers.list.return_value = [mock_container]

        discovered = manager.scan_existing_containers(mock_client)

        assert discovered == 0
        assert manager.get_stats()["allocated"] == 0

    def test_scan_skips_exited_containers(self):
        """Test that scan ignores exited containers (they don't hold ports)."""
        manager = PortPoolManager.get_instance()

        mock_container = self._create_mock_container(
            name="ii-sandbox-abc123", status="exited", port_mappings={3000: 30000}
        )

        mock_client = MagicMock()
        mock_client.containers.list.return_value = [mock_container]

        discovered = manager.scan_existing_containers(mock_client)

        assert discovered == 0

    def test_scan_handles_multiple_containers(self):
        """Test that scan handles multiple sandbox containers."""
        manager = PortPoolManager.get_instance()

        container1 = self._create_mock_container(
            name="ii-sandbox-sandbox1",
            status="running",
            port_mappings={3000: 30000, 6060: 30001},
            container_id="container1",
        )
        container2 = self._create_mock_container(
            name="ii-sandbox-sandbox2",
            status="running",
            port_mappings={3000: 30005, 6060: 30006},
            container_id="container2",
        )

        mock_client = MagicMock()
        mock_client.containers.list.return_value = [container1, container2]

        discovered = manager.scan_existing_containers(mock_client)

        assert discovered == 2
        assert manager.get_stats()["allocated"] == 4

    def test_scan_only_runs_once(self):
        """Test that scan only initializes once (idempotent)."""
        manager = PortPoolManager.get_instance()

        mock_container = self._create_mock_container(
            name="ii-sandbox-abc123", status="running", port_mappings={3000: 30000}
        )

        mock_client = MagicMock()
        mock_client.containers.list.return_value = [mock_container]

        # First scan
        discovered1 = manager.scan_existing_containers(mock_client)
        assert discovered1 == 1

        # Second scan should be skipped
        discovered2 = manager.scan_existing_containers(mock_client)
        assert discovered2 == 0

        # Should still only have 1 port allocated
        assert manager.get_stats()["allocated"] == 1

    def test_scan_ignores_ports_outside_range(self):
        """Test that scan ignores ports outside the managed range."""
        manager = PortPoolManager.get_instance()

        mock_container = self._create_mock_container(
            name="ii-sandbox-abc123",
            status="running",
            port_mappings={
                3000: 30000,  # In range
                5432: 5432,  # Out of range (below)
                50000: 50000,  # Out of range (above)
            },
        )

        mock_client = MagicMock()
        mock_client.containers.list.return_value = [mock_container]

        discovered = manager.scan_existing_containers(mock_client)

        assert discovered == 1
        # Only the port in range should be allocated
        assert manager.get_stats()["allocated"] == 1
        assert 30000 in manager._allocated_ports
        assert 5432 not in manager._allocated_ports

    def test_scan_handles_docker_error(self):
        """Test that scan handles Docker API errors gracefully."""
        manager = PortPoolManager.get_instance()

        mock_client = MagicMock()
        mock_client.containers.list.side_effect = Exception("Docker daemon not running")

        # Should not raise, just log and return 0
        discovered = manager.scan_existing_containers(mock_client)

        assert discovered == 0
        # Manager should be marked as initialized to prevent repeated failures
        assert manager._initialized is True

    def test_scan_prevents_port_conflicts(self):
        """Test that scanned ports are unavailable for new allocations."""
        manager = PortPoolManager.get_instance()

        # Simulate existing container using port 30000
        mock_container = self._create_mock_container(
            name="ii-sandbox-existing", status="running", port_mappings={3000: 30000}
        )

        mock_client = MagicMock()
        mock_client.containers.list.return_value = [mock_container]

        manager.scan_existing_containers(mock_client)

        # Now allocate ports for a new sandbox
        port_set = manager.allocate_ports(sandbox_id="new-sandbox", container_ports=[3000])

        # Should get a different port, not 30000
        assert port_set.allocations[3000].host_port != 30000
        assert port_set.allocations[3000].host_port >= DEFAULT_PORT_RANGE_START

    def test_scan_handles_container_with_no_ports(self):
        """Test that scan handles containers with no port mappings."""
        manager = PortPoolManager.get_instance()

        mock_container = MagicMock()
        mock_container.name = "ii-sandbox-abc123"
        mock_container.status = "running"
        mock_container.id = "container123"
        mock_container.attrs = {
            "NetworkSettings": {"Ports": None},
            "HostConfig": {"PortBindings": {}},
        }

        mock_client = MagicMock()
        mock_client.containers.list.return_value = [mock_container]

        discovered = manager.scan_existing_containers(mock_client)

        # Container found but no ports to register
        assert discovered == 0


class TestRescanContainers:
    """Tests for rescan_containers method.

    This tests the on-demand rescan that can be called at any time to
    synchronize port manager state with actual running containers.
    Unlike scan_existing_containers, rescan clears existing state first.
    """

    def setup_method(self):
        """Reset singleton before each test."""
        PortPoolManager.reset_instance()

    def teardown_method(self):
        """Clean up singleton after each test."""
        PortPoolManager.reset_instance()

    def _create_mock_container(
        self, name: str, status: str, port_mappings: dict, container_id: str = "abc123"
    ) -> MagicMock:
        """Helper to create a mock container with port mappings."""
        container = MagicMock()
        container.name = name
        container.status = status
        container.id = container_id

        # Build Ports structure like Docker returns
        ports = {}
        for container_port, host_port in port_mappings.items():
            ports[f"{container_port}/tcp"] = [{"HostPort": str(host_port)}]

        container.attrs = {
            "NetworkSettings": {"Ports": ports},
            "HostConfig": {"PortBindings": ports},
        }
        return container

    def test_rescan_discovers_running_container(self):
        """Test that rescan discovers a running sandbox container."""
        manager = PortPoolManager.get_instance()

        mock_container = self._create_mock_container(
            name="ii-sandbox-abc123def456",
            status="running",
            port_mappings={3000: 30000, 6060: 30001},
        )

        mock_client = MagicMock()
        mock_client.containers.list.return_value = [mock_container]

        discovered = manager.rescan_containers(mock_client)

        assert discovered == 1
        port_set = manager.get_sandbox_ports("abc123def456")
        assert port_set is not None
        assert port_set.get_host_port(3000) == 30000
        assert port_set.get_host_port(6060) == 30001

    def test_rescan_clears_previous_allocations(self):
        """Test that rescan clears previous state before rebuilding."""
        manager = PortPoolManager.get_instance()

        # First, manually allocate some ports
        manager.allocate_ports(
            sandbox_id="manual-sandbox",
            container_ports=[3000, 6060],
        )
        initial_stats = manager.get_stats()
        assert initial_stats["allocated"] == 2
        assert initial_stats["sandboxes"] == 1

        # Now rescan with a different container
        mock_container = self._create_mock_container(
            name="ii-sandbox-newcontainer",
            status="running",
            port_mappings={8080: 30010},
        )
        mock_client = MagicMock()
        mock_client.containers.list.return_value = [mock_container]

        discovered = manager.rescan_containers(mock_client)

        assert discovered == 1
        # Old allocation should be gone
        assert manager.get_sandbox_ports("manual-sandbox") is None
        # New allocation should exist
        port_set = manager.get_sandbox_ports("newcontainer")
        assert port_set is not None
        assert port_set.get_host_port(8080) == 30010

        final_stats = manager.get_stats()
        assert final_stats["allocated"] == 1
        assert final_stats["sandboxes"] == 1

    def test_rescan_is_idempotent(self):
        """Test that calling rescan multiple times gives same result."""
        manager = PortPoolManager.get_instance()

        mock_container = self._create_mock_container(
            name="ii-sandbox-abc123",
            status="running",
            port_mappings={3000: 30000},
        )
        mock_client = MagicMock()
        mock_client.containers.list.return_value = [mock_container]

        discovered1 = manager.rescan_containers(mock_client)
        stats1 = manager.get_stats()

        discovered2 = manager.rescan_containers(mock_client)
        stats2 = manager.get_stats()

        assert discovered1 == discovered2 == 1
        assert stats1["allocated"] == stats2["allocated"]
        assert stats1["sandboxes"] == stats2["sandboxes"]

    def test_rescan_skips_stopped_containers(self):
        """Test that rescan ignores stopped containers."""
        manager = PortPoolManager.get_instance()

        mock_running = self._create_mock_container(
            name="ii-sandbox-running",
            status="running",
            port_mappings={3000: 30000},
        )
        mock_exited = self._create_mock_container(
            name="ii-sandbox-exited",
            status="exited",
            port_mappings={3000: 30001},
        )

        mock_client = MagicMock()
        mock_client.containers.list.return_value = [mock_running, mock_exited]

        discovered = manager.rescan_containers(mock_client)

        assert discovered == 1
        assert manager.get_sandbox_ports("running") is not None
        assert manager.get_sandbox_ports("exited") is None

    def test_rescan_handles_exception_gracefully(self):
        """Test that rescan returns 0 and sets initialized on error."""
        manager = PortPoolManager.get_instance()

        mock_client = MagicMock()
        mock_client.containers.list.side_effect = Exception("Docker error")

        discovered = manager.rescan_containers(mock_client)

        assert discovered == 0
        # Manager should still be marked as initialized
        assert manager._initialized is True

    def test_rescan_ignores_ports_outside_range(self):
        """Test that rescan ignores ports outside the configured range."""
        manager = PortPoolManager.get_instance()

        mock_container = self._create_mock_container(
            name="ii-sandbox-abc123",
            status="running",
            port_mappings={
                3000: 30000,  # In range
                8080: 99999,  # Outside default range
            },
        )

        mock_client = MagicMock()
        mock_client.containers.list.return_value = [mock_container]

        discovered = manager.rescan_containers(mock_client)

        assert discovered == 1
        port_set = manager.get_sandbox_ports("abc123")
        # Only the in-range port should be registered
        assert port_set.get_host_port(3000) == 30000
        assert 8080 not in port_set.allocations

    def test_rescan_can_be_called_after_scan_existing(self):
        """Test that rescan works after scan_existing_containers was called."""
        manager = PortPoolManager.get_instance()

        # First do initial scan
        mock_container1 = self._create_mock_container(
            name="ii-sandbox-first",
            status="running",
            port_mappings={3000: 30000},
        )
        mock_client = MagicMock()
        mock_client.containers.list.return_value = [mock_container1]

        manager.scan_existing_containers(mock_client)
        assert manager.get_sandbox_ports("first") is not None

        # Now rescan with different container
        mock_container2 = self._create_mock_container(
            name="ii-sandbox-second",
            status="running",
            port_mappings={6060: 30010},
        )
        mock_client.containers.list.return_value = [mock_container2]

        discovered = manager.rescan_containers(mock_client)

        assert discovered == 1
        # First container's allocation should be gone
        assert manager.get_sandbox_ports("first") is None
        # Second container should be registered
        assert manager.get_sandbox_ports("second") is not None


class TestRegisterExistingPorts:
    """Tests for the register_existing_ports public method."""

    def setup_method(self):
        PortPoolManager.reset_instance()

    def teardown_method(self):
        PortPoolManager.reset_instance()

    def test_registers_ports_successfully(self):
        """Test registering pre-existing port mappings."""
        manager = PortPoolManager.get_instance()
        result = manager.register_existing_ports(
            sandbox_id="sandbox-abc",
            port_mappings={6060: 30100, 9000: 30101},
            container_id="container-xyz",
        )

        assert result is True
        port_set = manager.get_sandbox_ports("sandbox-abc")
        assert port_set is not None
        assert port_set.container_id == "container-xyz"
        assert port_set.get_host_port(6060) == 30100
        assert port_set.get_host_port(9000) == 30101
        assert 30100 in manager._allocated_ports
        assert 30101 in manager._allocated_ports

    def test_returns_false_if_already_registered(self):
        """Test that duplicate registration returns False."""
        manager = PortPoolManager.get_instance()
        manager.register_existing_ports(
            sandbox_id="sandbox-abc",
            port_mappings={6060: 30100},
            container_id="container-1",
        )
        result = manager.register_existing_ports(
            sandbox_id="sandbox-abc",
            port_mappings={9000: 30200},
            container_id="container-2",
        )

        assert result is False
        # Original allocation unchanged
        port_set = manager.get_sandbox_ports("sandbox-abc")
        assert port_set.container_id == "container-1"
        assert len(port_set.allocations) == 1

    def test_with_service_names(self):
        """Test registering ports with service name mappings."""
        manager = PortPoolManager.get_instance()
        manager.register_existing_ports(
            sandbox_id="sandbox-abc",
            port_mappings={6060: 30100, 9000: 30101},
            container_id="container-xyz",
            service_names={6060: "mcp_server", 9000: "code_server"},
        )

        port_set = manager.get_sandbox_ports("sandbox-abc")
        assert port_set.allocations[6060].service_name == "mcp_server"
        assert port_set.allocations[9000].service_name == "code_server"

    def test_prevents_allocation_conflicts(self):
        """Test that registered ports are excluded from new allocations."""
        PortPoolManager.reset_instance()
        manager = PortPoolManager(port_range_start=40000, port_range_end=40003)

        manager.register_existing_ports(
            sandbox_id="existing",
            port_mappings={6060: 40000, 9000: 40001},
            container_id="container-old",
        )

        port_set = manager.allocate_ports(
            sandbox_id="new-sandbox",
            container_ports=[8080, 8081],
        )
        new_ports = {a.host_port for a in port_set.allocations.values()}
        assert new_ports == {40002, 40003}
