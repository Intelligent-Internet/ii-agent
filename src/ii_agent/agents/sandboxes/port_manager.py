"""Port Pool Manager for Docker sandbox containers.

This module provides centralized port allocation for local Docker sandboxes,
ensuring no port conflicts between containers and automatic reclamation
when containers are removed.

Design Goals:
- Allocate ports from a configurable range (default: 30000-30999)
- Track which sandbox owns which ports
- Support dynamic port exposure after container creation
- Automatic cleanup when containers stop/crash
- Thread-safe for concurrent sandbox operations
"""

import logging
import threading
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

import docker
from docker.errors import NotFound

logger = logging.getLogger(__name__)

# Default port range for sandbox services (can be overridden via SandboxSettings)
DEFAULT_PORT_RANGE_START = 30000
DEFAULT_PORT_RANGE_END = 30999

# Common dev server ports that sandboxes might use
COMMON_DEV_PORTS = [
    3000,  # React, Next.js, Express
    3001,  # React secondary
    4000,  # GraphQL, various
    4200,  # Angular
    5000,  # Flask, various
    5173,  # Vite
    5174,  # Vite secondary
    8000,  # Django, FastAPI, Python http.server
    8080,  # General dev server
    8081,  # Secondary
    8888,  # Jupyter
]

# Reserved ports for sandbox infrastructure
INFRASTRUCTURE_PORTS = {
    6060: "mcp_server",
    9000: "code_server",
}

# Control-plane port range reserved for adapter and internal services.
# User deliverable ports (preview servers, app HTTP) MUST NOT overlap this range.
# PortPoolManager hard-excludes this range from the user-facing pool.
CONTROL_PLANE_PORT_START = 18000
CONTROL_PLANE_PORT_END = 18999


@dataclass
class PortAllocation:
    """Represents a port allocation for a sandbox."""

    sandbox_id: str
    container_port: int
    host_port: int
    service_name: Optional[str] = None


@dataclass
class SandboxPortSet:
    """All port allocations for a single sandbox."""

    sandbox_id: str
    container_id: Optional[str] = None
    allocations: Dict[int, PortAllocation] = field(default_factory=dict)

    def get_host_port(self, container_port: int) -> Optional[int]:
        """Get the host port for a container port."""
        if container_port in self.allocations:
            return self.allocations[container_port].host_port
        return None

    def to_docker_ports(self) -> Dict[str, int]:
        """Convert to Docker ports dict format."""
        return {
            f"{alloc.container_port}/tcp": alloc.host_port for alloc in self.allocations.values()
        }


class PortPoolManager:
    """Manages a pool of ports for Docker sandbox containers.

    This is a singleton that maintains state about which ports are allocated
    to which sandboxes. It handles:
    - Initial port allocation when creating sandboxes
    - Dynamic port allocation for expose_port requests
    - Port reclamation when sandboxes are removed
    - Cleanup of orphaned allocations from crashed containers

    Thread Safety:
    - All public methods are protected by a lock
    - Safe for concurrent sandbox creation/deletion

    Usage:
        manager = PortPoolManager.get_instance()
        port_set = manager.allocate_ports("sandbox-123", [3000, 6060, 9000])
        # Later...
        manager.release_ports("sandbox-123")
    """

    _instance: Optional["PortPoolManager"] = None
    _lock = threading.Lock()

    def __init__(
        self,
        port_range_start: int = DEFAULT_PORT_RANGE_START,
        port_range_end: int = DEFAULT_PORT_RANGE_END,
    ):
        self._port_range_start = port_range_start
        self._port_range_end = port_range_end
        self._allocated_ports: Set[int] = set()
        self._sandbox_ports: Dict[str, SandboxPortSet] = {}
        self._port_lock = threading.Lock()
        self._initialized = False
        # Ring-buffer cursor: always advances forward, wraps around.
        # Ensures recently-released ports are not immediately reused,
        # preventing port conflicts when restarting stopped containers
        # whose original ports were given to a newer sandbox.
        self._next_port: int = port_range_start

        logger.info(
            f"PortPoolManager initialized with range {port_range_start}-{port_range_end} "
            f"({port_range_end - port_range_start + 1} ports available)"
        )

    @classmethod
    def get_instance(cls) -> "PortPoolManager":
        """Get the singleton instance of the port manager."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    port_range_start = DEFAULT_PORT_RANGE_START
                    port_range_end = DEFAULT_PORT_RANGE_END
                    try:
                        from ii_agent.core.config.settings import get_settings

                        sandbox_settings = get_settings().sandbox
                        port_range_start = sandbox_settings.port_range_start
                        port_range_end = sandbox_settings.port_range_end
                    except Exception as exc:
                        logger.debug(
                            "Falling back to default sandbox port range due to settings load failure: %s",
                            exc,
                        )
                    cls._instance = cls(
                        port_range_start=port_range_start,
                        port_range_end=port_range_end,
                    )
        return cls._instance

    @classmethod
    def reset_instance(cls):
        """Reset the singleton (for testing)."""
        with cls._lock:
            cls._instance = None

    def scan_existing_containers(self, docker_client: docker.DockerClient) -> int:
        """Scan for existing sandbox containers and register their port allocations.

        This MUST be called on startup before allocating any new ports.
        It discovers running ii-sandbox-* containers and marks their ports as allocated
        to prevent conflicts.

        Args:
            docker_client: Docker client instance

        Returns:
            Number of containers discovered and registered
        """
        with self._port_lock:
            if self._initialized:
                logger.debug("Port manager already initialized, skipping scan")
                return 0

            discovered = 0

            try:
                # Find all sandbox containers (running or created)
                containers = docker_client.containers.list(
                    all=True, filters={"name": "ii-sandbox-"}
                )

                for container in containers:
                    # Skip containers that aren't running (they don't hold ports)
                    if container.status not in ("running", "created"):
                        continue

                    # Extract sandbox_id from container name (ii-sandbox-{id})
                    name = container.name
                    if not name.startswith("ii-sandbox-"):
                        continue

                    # The sandbox_id is embedded in the container name
                    # Format: ii-sandbox-{first_12_chars_of_sandbox_id}
                    sandbox_id_prefix = name.replace("ii-sandbox-", "")

                    # Get port mappings from the container
                    ports = container.attrs.get("NetworkSettings", {}).get("Ports", {})
                    if not ports:
                        # Also check HostConfig for containers in "created" state
                        ports = container.attrs.get("HostConfig", {}).get("PortBindings", {})

                    if not ports:
                        continue

                    # Create a port set for this container
                    # Use container name as sandbox_id since we don't have the full UUID
                    port_set = SandboxPortSet(
                        sandbox_id=sandbox_id_prefix, container_id=container.id
                    )

                    for container_port_proto, bindings in ports.items():
                        if not bindings:
                            continue

                        # Parse container port (e.g., "3000/tcp" -> 3000)
                        container_port = int(container_port_proto.split("/")[0])

                        # Get host port from binding
                        for binding in bindings:
                            host_port = int(binding.get("HostPort", 0))
                            if (
                                host_port
                                and self._port_range_start <= host_port <= self._port_range_end
                            ):
                                # Mark this port as allocated
                                self._allocated_ports.add(host_port)

                                # Record the allocation
                                allocation = PortAllocation(
                                    sandbox_id=sandbox_id_prefix,
                                    container_port=container_port,
                                    host_port=host_port,
                                )
                                port_set.allocations[container_port] = allocation

                    if port_set.allocations:
                        self._sandbox_ports[sandbox_id_prefix] = port_set
                        discovered += 1
                        logger.info(
                            f"Discovered existing container {name} with ports: "
                            f"{port_set.to_docker_ports()}"
                        )

                self._initialized = True

                # Position ring cursor past highest allocated port so new
                # sandboxes don't reuse ports still bound to stopped containers.
                self._advance_cursor_past_allocated()

                if discovered > 0:
                    logger.info(
                        f"Startup scan complete: discovered {discovered} existing containers, "
                        f"{len(self._allocated_ports)} ports marked as allocated, "
                        f"ring cursor at {self._next_port}"
                    )
                else:
                    logger.info("Startup scan complete: no existing sandbox containers found")

                return discovered

            except Exception as e:
                logger.error(f"Error scanning existing containers: {e}")
                self._initialized = True  # Mark as initialized to prevent repeated failures
                return 0

    def _advance_cursor_past_allocated(self) -> None:
        """Set cursor past the highest allocated port to maximise reuse distance.

        Called after startup/rescan so new allocations begin above existing ones
        rather than filling gaps that stopped containers still reference.
        """
        if not self._allocated_ports:
            return
        highest = max(self._allocated_ports)
        range_size = self._port_range_end - self._port_range_start + 1
        self._next_port = self._port_range_start + (
            (highest - self._port_range_start + 1) % range_size
        )

    def _find_available_port(self) -> int:
        """Find the next available port using ring-buffer allocation.

        Scans forward from an internal cursor that always advances and
        wraps around the configured range.  This guarantees that a port
        released by a stopped container will not be reused until the
        cursor has cycled through the entire range, giving the old
        container the maximum window in which it can be restarted
        without a port conflict.

        Returns:
            An available port number

        Raises:
            RuntimeError: If no ports are available
        """
        range_size = self._port_range_end - self._port_range_start + 1

        for _ in range(range_size):
            port = self._next_port
            # Advance cursor (wrap around)
            self._next_port = self._port_range_start + (
                (self._next_port - self._port_range_start + 1) % range_size
            )
            # Hard-exclude the control-plane port range (adapter + internal services).
            if CONTROL_PLANE_PORT_START <= port <= CONTROL_PLANE_PORT_END:
                continue
            if port not in self._allocated_ports:
                return port

        raise RuntimeError(
            f"No available ports in range {self._port_range_start}-{self._port_range_end}. "
            f"Consider cleaning up unused sandboxes or expanding the port range."
        )

    def allocate_ports(
        self,
        sandbox_id: str,
        container_ports: List[int],
        service_names: Optional[Dict[int, str]] = None,
    ) -> SandboxPortSet:
        """Allocate host ports for a new sandbox.

        Args:
            sandbox_id: Unique identifier for the sandbox
            container_ports: List of container ports that need host mappings
            service_names: Optional mapping of container ports to service names

        Returns:
            SandboxPortSet with all allocations

        Raises:
            RuntimeError: If not enough ports available
            ValueError: If sandbox already has allocations
        """
        service_names = service_names or {}

        with self._port_lock:
            if sandbox_id in self._sandbox_ports:
                raise ValueError(f"Sandbox {sandbox_id} already has port allocations")

            port_set = SandboxPortSet(sandbox_id=sandbox_id)
            allocated = []

            try:
                for container_port in container_ports:
                    host_port = self._find_available_port()
                    self._allocated_ports.add(host_port)
                    allocated.append(host_port)

                    allocation = PortAllocation(
                        sandbox_id=sandbox_id,
                        container_port=container_port,
                        host_port=host_port,
                        service_name=service_names.get(container_port),
                    )
                    port_set.allocations[container_port] = allocation

                    logger.debug(
                        f"Allocated port {host_port} -> {container_port} "
                        f"for sandbox {sandbox_id[:12]}"
                    )

                self._sandbox_ports[sandbox_id] = port_set
                logger.info(
                    f"Allocated {len(container_ports)} ports for sandbox {sandbox_id[:12]}: "
                    f"{port_set.to_docker_ports()}"
                )
                return port_set

            except RuntimeError:
                # Rollback any ports we allocated before the failure
                for port in allocated:
                    self._allocated_ports.discard(port)
                raise

    def allocate_additional_port(
        self,
        sandbox_id: str,
        container_port: int,
        service_name: Optional[str] = None,
    ) -> int:
        """Allocate an additional port for an existing sandbox.

        This is used when a sandbox needs to expose a new port dynamically.
        Note: For Docker, this can't add ports to a running container,
        but we track it for potential container recreation.

        Args:
            sandbox_id: Sandbox identifier
            container_port: Container port to map
            service_name: Optional service name

        Returns:
            The allocated host port
        """
        with self._port_lock:
            if sandbox_id not in self._sandbox_ports:
                raise ValueError(f"Sandbox {sandbox_id} not found in port manager")

            port_set = self._sandbox_ports[sandbox_id]

            if container_port in port_set.allocations:
                # Already allocated, return existing
                return port_set.allocations[container_port].host_port

            host_port = self._find_available_port()
            self._allocated_ports.add(host_port)

            allocation = PortAllocation(
                sandbox_id=sandbox_id,
                container_port=container_port,
                host_port=host_port,
                service_name=service_name,
            )
            port_set.allocations[container_port] = allocation

            logger.info(
                f"Allocated additional port {host_port} -> {container_port} "
                f"for sandbox {sandbox_id[:12]}"
            )
            return host_port

    def get_sandbox_ports(self, sandbox_id: str) -> Optional[SandboxPortSet]:
        """Get all port allocations for a sandbox."""
        with self._port_lock:
            return self._sandbox_ports.get(sandbox_id)

    def get_host_port(self, sandbox_id: str, container_port: int) -> Optional[int]:
        """Get the host port for a specific container port."""
        with self._port_lock:
            port_set = self._sandbox_ports.get(sandbox_id)
            if port_set:
                return port_set.get_host_port(container_port)
            return None

    def release_ports(self, sandbox_id: str) -> int:
        """Release all ports allocated to a sandbox.

        Returns:
            Number of ports released
        """
        with self._port_lock:
            port_set = self._sandbox_ports.pop(sandbox_id, None)
            if not port_set:
                return 0

            count = 0
            for allocation in port_set.allocations.values():
                self._allocated_ports.discard(allocation.host_port)
                count += 1

            logger.info(f"Released {count} ports for sandbox {sandbox_id[:12]}")
            return count

    def set_container_id(self, sandbox_id: str, container_id: str):
        """Associate a container ID with a sandbox's port allocations."""
        with self._port_lock:
            if sandbox_id in self._sandbox_ports:
                self._sandbox_ports[sandbox_id].container_id = container_id

    def register_existing_ports(
        self,
        sandbox_id: str,
        port_mappings: Dict[int, int],
        container_id: str,
        service_names: Optional[Dict[int, str]] = None,
    ) -> bool:
        """Register pre-existing port mappings (e.g. from a reconnecting container).

        If the sandbox already has allocations, this is a no-op and returns False.

        Args:
            sandbox_id: Sandbox identifier
            port_mappings: Mapping of container_port -> host_port
            container_id: Docker container ID
            service_names: Optional mapping of container_port -> service name

        Returns:
            True if ports were registered, False if sandbox already tracked
        """
        service_names = service_names or {}

        with self._port_lock:
            if sandbox_id in self._sandbox_ports:
                return False

            port_set = SandboxPortSet(sandbox_id=sandbox_id, container_id=container_id)

            for container_port, host_port in port_mappings.items():
                self._allocated_ports.add(host_port)
                allocation = PortAllocation(
                    sandbox_id=sandbox_id,
                    container_port=container_port,
                    host_port=host_port,
                    service_name=service_names.get(container_port),
                )
                port_set.allocations[container_port] = allocation

            self._sandbox_ports[sandbox_id] = port_set

            logger.info(
                f"Registered {len(port_mappings)} existing ports for "
                f"sandbox {sandbox_id[:12]}: {port_mappings}"
            )
            return True

    def cleanup_orphaned_allocations(self, docker_client: docker.DockerClient) -> int:
        """Clean up port allocations for containers that no longer exist.

        This should be called periodically or on startup to handle
        crashed containers.

        Returns:
            Number of orphaned allocations cleaned up
        """
        with self._port_lock:
            orphaned = []

            for sandbox_id, port_set in self._sandbox_ports.items():
                if port_set.container_id:
                    try:
                        docker_client.containers.get(port_set.container_id)
                    except NotFound:
                        orphaned.append(sandbox_id)

            for sandbox_id in orphaned:
                port_set = self._sandbox_ports.pop(sandbox_id)
                for allocation in port_set.allocations.values():
                    self._allocated_ports.discard(allocation.host_port)
                logger.info(f"Cleaned up orphaned ports for sandbox {sandbox_id[:12]}")

            return len(orphaned)

    def rescan_containers(self, docker_client: docker.DockerClient) -> int:
        """Rescan all running containers and rebuild port allocations from scratch.

        Unlike scan_existing_containers (which only runs once at startup), this
        method can be called at any time to synchronize the port manager's state
        with actual running containers. It clears existing allocations and rebuilds
        from the Docker state.

        This operation is idempotent - calling it multiple times produces the same
        result based on the current Docker container state.

        Use this after:
        - Manually starting stopped sandbox containers (docker start)
        - Recovering from sandbox-server restart
        - Suspected state desync

        Args:
            docker_client: Docker client instance

        Returns:
            Number of containers discovered and registered
        """
        with self._port_lock:
            # Clear existing state
            old_count = len(self._sandbox_ports)
            self._allocated_ports.clear()
            self._sandbox_ports.clear()
            self._initialized = False

            if old_count > 0:
                logger.info(f"Rescan: cleared {old_count} previous sandbox allocations")

            # Do the scan while still holding the lock to prevent race conditions
            # (We can't call scan_existing_containers here as it would deadlock)
            discovered = 0

            try:
                containers = docker_client.containers.list(
                    all=True, filters={"name": "ii-sandbox-"}
                )

                for container in containers:
                    if container.status not in ("running", "created"):
                        continue

                    name = container.name
                    if not name.startswith("ii-sandbox-"):
                        continue

                    sandbox_id_prefix = name.replace("ii-sandbox-", "")

                    ports = container.attrs.get("NetworkSettings", {}).get("Ports", {})
                    if not ports:
                        ports = container.attrs.get("HostConfig", {}).get("PortBindings", {})

                    if not ports:
                        continue

                    port_set = SandboxPortSet(
                        sandbox_id=sandbox_id_prefix, container_id=container.id
                    )

                    for container_port_proto, bindings in ports.items():
                        if not bindings:
                            continue

                        container_port = int(container_port_proto.split("/")[0])

                        for binding in bindings:
                            host_port = int(binding.get("HostPort", 0))
                            if (
                                host_port
                                and self._port_range_start <= host_port <= self._port_range_end
                            ):
                                self._allocated_ports.add(host_port)

                                allocation = PortAllocation(
                                    sandbox_id=sandbox_id_prefix,
                                    container_port=container_port,
                                    host_port=host_port,
                                )
                                port_set.allocations[container_port] = allocation

                    if port_set.allocations:
                        self._sandbox_ports[sandbox_id_prefix] = port_set
                        discovered += 1
                        logger.info(
                            f"Rescan: discovered container {name} with ports: "
                            f"{port_set.to_docker_ports()}"
                        )

                self._initialized = True

                # Position ring cursor past highest allocated port
                self._advance_cursor_past_allocated()

                logger.info(
                    f"Rescan complete: discovered {discovered} containers, "
                    f"{len(self._allocated_ports)} ports marked as allocated, "
                    f"ring cursor at {self._next_port}"
                )

                return discovered

            except Exception as e:
                logger.error(f"Error during rescan: {e}")
                self._initialized = True
                return 0

    def get_stats(self) -> Dict:
        """Get statistics about port usage."""
        with self._port_lock:
            total_range = self._port_range_end - self._port_range_start + 1
            return {
                "port_range": f"{self._port_range_start}-{self._port_range_end}",
                "total_available": total_range,
                "allocated": len(self._allocated_ports),
                "free": total_range - len(self._allocated_ports),
                "sandboxes": len(self._sandbox_ports),
            }

    def list_allocations(self) -> List[Dict]:
        """List all current port allocations."""
        with self._port_lock:
            result = []
            for sandbox_id, port_set in self._sandbox_ports.items():
                for container_port, alloc in port_set.allocations.items():
                    result.append(
                        {
                            "sandbox_id": sandbox_id[:12],
                            "container_id": port_set.container_id[:12]
                            if port_set.container_id
                            else None,
                            "container_port": container_port,
                            "host_port": alloc.host_port,
                            "service": alloc.service_name,
                        }
                    )
            return result


def get_default_port_allocations() -> Tuple[List[int], Dict[int, str]]:
    """Get the default container ports to allocate for new sandboxes.

    Returns:
        Tuple of (list of ports, dict of port->service_name)
    """
    ports = [
        6060,  # MCP server
        9000,  # Code server
        3000,  # Primary dev server
        5173,  # Vite
        8080,  # General
    ]
    names = {
        6060: "mcp_server",
        9000: "code_server",
        3000: "dev_server",
        5173: "vite",
        8080: "http",
    }
    return ports, names
