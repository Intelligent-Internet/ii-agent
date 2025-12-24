"""Unit tests for the PortPoolManager class.

This module contains tests for the port pool management system,
including allocation, release, and cleanup operations.
"""

import pytest
from unittest.mock import MagicMock, patch

from ii_sandbox_server.sandboxes.port_manager import (
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
