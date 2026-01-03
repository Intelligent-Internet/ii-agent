"""Docker-based local sandbox provider for air-gapped/secure deployments.

This provider runs sandboxes as local Docker containers instead of using E2B cloud.
It implements the same BaseSandbox interface for seamless substitution.

Key benefits:
- All data stays local (no cloud connectivity required)
- Uses the same Docker image as E2B for compatibility
- Suitable for privileged/NDA-protected data workflows
- Works in air-gapped environments
"""

import asyncio
import logging
import os
import re
import shlex
import uuid
from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import IO, AsyncIterator, Dict, Literal, Optional, TYPE_CHECKING

import docker
from docker.models.containers import Container
from docker.errors import NotFound, APIError

from ii_sandbox_server.config import SandboxConfig
from ii_sandbox_server.sandboxes.base import BaseSandbox
from ii_sandbox_server.sandboxes.port_manager import (
    PortPoolManager,
    get_default_port_allocations,
)
from ii_sandbox_server.models.exceptions import (
    SandboxNotFoundException,
    SandboxNotInitializedError,
    SandboxGeneralException,
    SandboxTimeoutException,
)

if TYPE_CHECKING:
    from ii_sandbox_server.lifecycle.queue import SandboxQueueScheduler

logger = logging.getLogger(__name__)

# Default timeout for container operations
DEFAULT_TIMEOUT = 3600
CONTAINER_STARTUP_TIMEOUT = 120  # Increased from 60s - sandbox startup can be slow

# Well-known container ports for sandbox services
MCP_SERVER_PORT = 6060
CODE_SERVER_PORT = 9000

# Common dev server ports to pre-allocate
# These are mapped to host ports from the port pool on container creation
DEFAULT_EXPOSED_PORTS = [
    MCP_SERVER_PORT,   # MCP server (required)
    CODE_SERVER_PORT,  # Code server (required)
    3000,   # React, Next.js, Express
    5173,   # Vite
    8080,   # General HTTP
]

# Security: allowed workspace base paths
ALLOWED_WORKSPACE_BASES = ("/workspace", "/tmp", "/home")

# Security: dangerous shell patterns to reject
DANGEROUS_PATTERNS = re.compile(
    r"[;&|`$(){}\[\]<>\\!]"
    r"|\.\."  # Path traversal
    r"|/etc/|/proc/|/sys/|/dev/"  # Sensitive paths
)


class DockerSandbox(BaseSandbox):
    """Local Docker-based sandbox provider.

    This sandbox runs in a local Docker container, providing the same
    capabilities as E2B but without cloud connectivity. Ideal for:
    - Development and testing
    - Air-gapped environments
    - Privileged data that cannot leave your infrastructure
    - Self-hosted deployments
    """

    _docker_client: Optional[docker.DockerClient] = None

    def __init__(
        self,
        container: Container,
        sandbox_id: str,
        queue: Optional["SandboxQueueScheduler"],
        port_mappings: Dict[int, int],  # container_port -> host_port
    ):
        super().__init__()
        self._container = container
        self._sandbox_id = sandbox_id
        self._queue = queue
        self._port_mappings = port_mappings  # container_port -> host_port
        self._timeout_task: Optional[asyncio.Task] = None

        # For backward compatibility, expose common ports as properties
        self._host_port_mcp = port_mappings.get(MCP_SERVER_PORT, 0)
        self._host_port_code_server = port_mappings.get(CODE_SERVER_PORT, 0)

    @classmethod
    def _get_docker_client(cls) -> docker.DockerClient:
        """Get or create a Docker client singleton."""
        if cls._docker_client is None:
            cls._docker_client = docker.from_env()
        return cls._docker_client

    @staticmethod
    def _validate_path(path: str, allow_absolute: bool = True) -> str:
        """Validate and sanitize file paths to prevent traversal attacks.

        Args:
            path: The path to validate
            allow_absolute: Whether to allow absolute paths

        Returns:
            Sanitized path

        Raises:
            ValueError: If path is invalid or attempts traversal
        """
        if not path:
            raise ValueError("Path cannot be empty")

        # Normalize the path
        normalized = PurePosixPath(path)

        # Check for path traversal attempts
        try:
            # Resolve .. and . components
            resolved = str(normalized)
            if ".." in resolved:
                raise ValueError(f"Path traversal detected: {path}")
        except Exception as e:
            raise ValueError(f"Invalid path: {path}") from e

        # For absolute paths, ensure they're in allowed directories
        if normalized.is_absolute():
            if not allow_absolute:
                raise ValueError(f"Absolute paths not allowed: {path}")
            if not any(resolved.startswith(base) for base in ALLOWED_WORKSPACE_BASES):
                raise ValueError(
                    f"Path must be within allowed directories {ALLOWED_WORKSPACE_BASES}: {path}"
                )

        return resolved

    @staticmethod
    def _sanitize_command(command: str, strict: bool = False) -> str:
        """Sanitize command input to prevent injection attacks.

        Args:
            command: The command to sanitize
            strict: If True, reject commands with shell metacharacters

        Returns:
            Sanitized command

        Raises:
            ValueError: If command contains dangerous patterns in strict mode
        """
        if not command:
            raise ValueError("Command cannot be empty")

        if strict and DANGEROUS_PATTERNS.search(command):
            raise ValueError(
                f"Command contains dangerous characters or patterns: {command[:50]}..."
            )

        return command

    def _ensure_container(self):
        """Ensure container is initialized and running."""
        if not self._container:
            raise SandboxNotInitializedError(
                f"Sandbox not initialized: {self._sandbox_id}"
            )
        self._container.reload()
        if self._container.status != "running":
            raise SandboxNotInitializedError(
                f"Sandbox container not running: {self._sandbox_id}"
            )

    @property
    def provider_sandbox_id(self) -> str:
        """Return the Docker container ID."""
        self._ensure_container()
        return self._container.id

    @property
    def sandbox_id(self) -> str:
        return self._sandbox_id

    @classmethod
    def _get_sandbox_image(cls, config: SandboxConfig) -> str:
        """Get the Docker image to use for sandboxes.

        Priority:
        1. config.docker_image if set
        2. SANDBOX_DOCKER_IMAGE env var
        3. Default to ii-agent sandbox image
        """
        return (
            getattr(config, 'docker_image', None)
            or os.getenv("SANDBOX_DOCKER_IMAGE", "ii-agent-sandbox:latest")
        )

    @classmethod
    def _find_available_ports(cls, count: int = 2) -> list[int]:
        """Find available ports for container port mapping."""
        import socket
        ports = []
        for _ in range(count):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('', 0))
                ports.append(s.getsockname()[1])
        return ports

    @classmethod
    def _register_existing_ports(
        cls,
        port_manager: PortPoolManager,
        sandbox_id: str,
        port_mappings: Dict[int, int],
        container_id: str,
    ) -> None:
        """Register existing port mappings with the port pool manager.

        This is called when reconnecting to existing containers to ensure
        the port manager knows about ports that are already in use.
        This prevents the port manager from allocating these ports to new sandboxes.

        Args:
            port_manager: The PortPoolManager instance
            sandbox_id: The sandbox identifier
            port_mappings: Dict of container_port -> host_port
            container_id: The Docker container ID
        """
        # Check if this sandbox already has ports registered
        existing = port_manager.get_sandbox_ports(sandbox_id)
        if existing:
            logger.debug(f"Sandbox {sandbox_id[:12]} already has ports registered")
            return

        # Register the ports by directly adding to internal structures
        # This is a reconnection scenario, so we need to mark these ports as used
        with port_manager._port_lock:
            from ii_sandbox_server.sandboxes.port_manager import SandboxPortSet, PortAllocation

            port_set = SandboxPortSet(sandbox_id=sandbox_id, container_id=container_id)

            for container_port, host_port in port_mappings.items():
                # Mark host port as allocated
                port_manager._allocated_ports.add(host_port)

                # Create allocation record
                service_name = None
                if container_port == MCP_SERVER_PORT:
                    service_name = "mcp_server"
                elif container_port == CODE_SERVER_PORT:
                    service_name = "code_server"

                allocation = PortAllocation(
                    sandbox_id=sandbox_id,
                    container_port=container_port,
                    host_port=host_port,
                    service_name=service_name,
                )
                port_set.allocations[container_port] = allocation

            port_manager._sandbox_ports[sandbox_id] = port_set

            logger.info(
                f"Registered {len(port_mappings)} existing ports for reconnected "
                f"sandbox {sandbox_id[:12]}: {port_mappings}"
            )

    @classmethod
    def _cleanup_sandbox_volume(cls, client: docker.DockerClient, sandbox_id: Optional[str]) -> bool:
        """Clean up the named workspace volume for a sandbox.

        Args:
            client: Docker client instance
            sandbox_id: The sandbox identifier (used to construct volume name)

        Returns:
            True if volume was removed, False if not found or error
        """
        if not sandbox_id:
            return False

        volume_name = f"ii-sandbox-workspace-{sandbox_id}"
        try:
            volume = client.volumes.get(volume_name)
            volume.remove(force=True)
            logger.debug(f"Removed workspace volume: {volume_name}")
            return True
        except NotFound:
            logger.debug(f"Volume {volume_name} not found (already removed)")
            return False
        except APIError as e:
            logger.warning(f"Failed to remove volume {volume_name}: {e}")
            return False

    @classmethod
    async def create(
        cls,
        config: SandboxConfig,
        queue: Optional["SandboxQueueScheduler"],
        sandbox_id: str,
        metadata: Optional[dict] = None,
        sandbox_template_id: Optional[str] = None,
    ) -> "DockerSandbox":
        """Create a new Docker container sandbox.

        Args:
            config: Sandbox configuration
            queue: Optional queue scheduler for timeout management
            sandbox_id: Unique identifier for this sandbox
            metadata: Optional metadata to attach to the container
            sandbox_template_id: Optional image override (uses config default if not set)

        Returns:
            DockerSandbox instance
        """
        client = cls._get_docker_client()
        port_manager = PortPoolManager.get_instance()

        # Determine which image to use
        image = sandbox_template_id or cls._get_sandbox_image(config)

        # Allocate ports from the pool for all default exposed ports
        service_names = {
            MCP_SERVER_PORT: "mcp_server",
            CODE_SERVER_PORT: "code_server",
            3000: "dev_server",
            5173: "vite",
            8080: "http",
        }
        port_set = port_manager.allocate_ports(
            sandbox_id=sandbox_id,
            container_ports=DEFAULT_EXPOSED_PORTS,
            service_names=service_names,
        )

        # Build Docker port mapping dict
        docker_ports = port_set.to_docker_ports()
        port_mappings = {
            alloc.container_port: alloc.host_port
            for alloc in port_set.allocations.values()
        }

        # Prepare container labels for metadata
        labels = {
            "ii-agent.sandbox": "true",
            "ii-agent.sandbox-id": sandbox_id,
            "ii-agent.created-at": datetime.now(timezone.utc).isoformat(),
        }
        if metadata:
            for key, value in metadata.items():
                labels[f"ii-agent.meta.{key}"] = str(value)

        # Create workspace directory using a named volume
        # The volume name includes sandbox_id to isolate each sandbox's workspace
        volume_name = f"ii-sandbox-workspace-{sandbox_id}"

        try:
            # Get memory limit from config (in MB) and convert to docker format
            mem_limit_mb = config.default_memory_limit if config else 3072
            mem_limit = f"{mem_limit_mb}m"

            # Run container
            container = client.containers.run(
                image,
                detach=True,
                name=f"ii-sandbox-{sandbox_id[:12]}",
                labels=labels,
                ports=docker_ports,
                volumes={
                    volume_name: {"bind": "/workspace", "mode": "rw"},
                },
                environment={
                    "SANDBOX_ID": sandbox_id,
                    "WORKSPACE_DIR": "/workspace",
                },
                # Resource limits
                mem_limit=mem_limit,
                cpu_period=100000,
                cpu_quota=200000,  # 2 CPUs
                pids_limit=512,  # Prevent fork bombs
                # Security hardening
                security_opt=[
                    "no-new-privileges",
                    # Note: Add "seccomp=default.json" for production
                ],
                cap_drop=["ALL"],  # Drop all capabilities
                cap_add=["CHOWN", "SETUID", "SETGID", "DAC_OVERRIDE"],  # Minimal required
                read_only=False,  # Workspace needs write access; consider tmpfs for /tmp
                # Network - use compose network for service discovery
                network=os.getenv("DOCKER_NETWORK", "bridge"),
                # Allow sandboxes to reach host services (e.g., MCP servers running on host)
                extra_hosts={"host.docker.internal": "host-gateway"},
            )

            # Associate container ID with port allocations for cleanup tracking
            port_manager.set_container_id(sandbox_id, container.id)

            logger.info(
                f"Created Docker sandbox {sandbox_id} with container {container.id[:12]}, "
                f"ports: {port_mappings}"
            )

        except docker.errors.ImageNotFound:
            port_manager.release_ports(sandbox_id)
            raise SandboxGeneralException(
                f"Docker image '{image}' not found. Build it with: "
                f"docker build -t {image} -f e2b.Dockerfile ."
            )
        except APIError as e:
            port_manager.release_ports(sandbox_id)
            raise SandboxGeneralException(f"Failed to create Docker sandbox: {e}")

        instance = cls(
            container=container,
            sandbox_id=sandbox_id,
            queue=queue,
            port_mappings=port_mappings,
        )

        # Wait for container to be ready
        await instance._wait_for_ready(timeout=CONTAINER_STARTUP_TIMEOUT)

        # Set up timeout if configured
        if config.timeout_seconds:
            await instance._set_timeout(config.timeout_seconds)

        return instance

    async def _wait_for_ready(self, timeout: int = 60):
        """Wait for the container's MCP server to be ready."""
        import httpx

        start_time = asyncio.get_event_loop().time()

        # Get the container's IP address on the shared network
        self._container.reload()
        network_name = os.getenv("DOCKER_NETWORK", "bridge")
        networks = self._container.attrs.get("NetworkSettings", {}).get("Networks", {})

        # Try to get IP from the configured network, fallback to first available
        container_ip = None
        if network_name in networks:
            container_ip = networks[network_name].get("IPAddress")
        if not container_ip:
            # Fallback: use first available network IP
            for net_info in networks.values():
                if net_info.get("IPAddress"):
                    container_ip = net_info["IPAddress"]
                    break

        if container_ip:
            # Use container IP directly (preferred when on same network)
            url = f"http://{container_ip}:{MCP_SERVER_PORT}/health"
            logger.debug(f"Waiting for sandbox {self._sandbox_id} at {url}")
        else:
            # Fallback to host port mapping
            docker_host = os.getenv("DOCKER_HOST_INTERNAL", "host.docker.internal")
            url = f"http://{docker_host}:{self._host_port_mcp}/health"
            logger.debug(f"Waiting for sandbox {self._sandbox_id} via host at {url}")

        async with httpx.AsyncClient() as client:
            while True:
                elapsed = asyncio.get_event_loop().time() - start_time
                if elapsed > timeout:
                    raise SandboxTimeoutException(
                        self._sandbox_id,
                        f"Container did not become ready within {timeout}s"
                    )

                try:
                    response = await client.get(url, timeout=2)
                    if response.status_code == 200:
                        logger.info(f"Sandbox {self._sandbox_id} is ready")
                        return
                except Exception:
                    pass

                await asyncio.sleep(1)

    async def _set_timeout(self, timeout_seconds: int):
        """Set a timeout after which the container will be stopped."""
        if self._timeout_task:
            self._timeout_task.cancel()

        async def timeout_handler():
            await asyncio.sleep(timeout_seconds)
            logger.info(f"Timeout reached for sandbox {self._sandbox_id}, stopping...")
            try:
                await self.stop()
            except Exception as e:
                logger.error(f"Error stopping sandbox on timeout: {e}")

        self._timeout_task = asyncio.create_task(timeout_handler())

    @classmethod
    async def connect(
        cls,
        provider_sandbox_id: str,
        config: SandboxConfig,
        queue: Optional["SandboxQueueScheduler"] = None,
        sandbox_id: Optional[str] = None,
    ) -> "DockerSandbox":
        """Connect to an existing Docker container sandbox."""
        client = cls._get_docker_client()
        port_manager = PortPoolManager.get_instance()

        try:
            container = client.containers.get(provider_sandbox_id)
        except NotFound:
            raise SandboxNotFoundException(provider_sandbox_id)

        # Extract all port mappings from running container
        container.reload()
        ports = container.attrs.get("NetworkSettings", {}).get("Ports", {})

        # Build port_mappings dict from container's actual port bindings
        port_mappings: Dict[int, int] = {}
        for container_port_proto, bindings in ports.items():
            if bindings and "/tcp" in container_port_proto:
                container_port = int(container_port_proto.split("/")[0])
                host_port = int(bindings[0].get("HostPort", 0))
                if host_port:
                    port_mappings[container_port] = host_port

        # Get sandbox_id from labels if not provided
        if not sandbox_id:
            labels = container.labels
            sandbox_id = labels.get("ii-agent.sandbox-id", provider_sandbox_id[:12])

        # Register discovered ports with PortPoolManager to prevent conflicts
        # This handles reconnecting to containers that were created before server restart
        cls._register_existing_ports(port_manager, sandbox_id, port_mappings, container.id)

        return cls(
            container=container,
            sandbox_id=sandbox_id,
            queue=queue,
            port_mappings=port_mappings,
        )

    @classmethod
    async def resume(
        cls,
        provider_sandbox_id: str,
        config: SandboxConfig,
        queue: Optional["SandboxQueueScheduler"] = None,
        sandbox_id: Optional[str] = None,
    ) -> "DockerSandbox":
        """Resume a stopped Docker container sandbox."""
        client = cls._get_docker_client()

        try:
            container = client.containers.get(provider_sandbox_id)
        except NotFound:
            raise SandboxNotFoundException(provider_sandbox_id)

        if container.status != "running":
            container.start()

        return await cls.connect(provider_sandbox_id, config, queue, sandbox_id)

    @classmethod
    async def delete(
        cls,
        provider_sandbox_id: str,
        config: SandboxConfig,
        queue: Optional["SandboxQueueScheduler"] = None,
        sandbox_id: Optional[str] = None,
    ) -> bool:
        """Delete a Docker container sandbox and its associated resources."""
        client = cls._get_docker_client()
        port_manager = PortPoolManager.get_instance()

        try:
            container = client.containers.get(provider_sandbox_id)

            # Get sandbox_id from labels if not provided (for port and volume cleanup)
            if not sandbox_id:
                sandbox_id = container.labels.get("ii-agent.sandbox-id")

            container.remove(force=True)

            # Release ports back to the pool
            released_ports = 0
            if sandbox_id:
                released_ports = port_manager.release_ports(sandbox_id)

            # Clean up the named workspace volume
            volume_cleaned = cls._cleanup_sandbox_volume(client, sandbox_id)

            logger.info(
                f"Deleted Docker sandbox container {provider_sandbox_id}, "
                f"released {released_ports} ports, volume cleaned: {volume_cleaned}"
            )

            return True
        except NotFound:
            # Container not found - still try to clean up ports and volume
            if sandbox_id:
                port_manager.release_ports(sandbox_id)
                cls._cleanup_sandbox_volume(client, sandbox_id)
            logger.warning(f"Container {provider_sandbox_id} not found for deletion")
            return False
        except APIError as e:
            logger.error(f"Failed to delete container {provider_sandbox_id}: {e}")
            return False

    @classmethod
    async def stop(
        cls,
        provider_sandbox_id: str,
        config: SandboxConfig,
        queue: Optional["SandboxQueueScheduler"] = None,
        sandbox_id: Optional[str] = None,
    ) -> bool:
        """Stop a Docker container sandbox."""
        client = cls._get_docker_client()

        try:
            container = client.containers.get(provider_sandbox_id)
            container.stop(timeout=10)
            logger.info(f"Stopped Docker sandbox container {provider_sandbox_id}")
            return True
        except NotFound:
            return False
        except APIError as e:
            logger.error(f"Failed to stop container {provider_sandbox_id}: {e}")
            return False

    @classmethod
    async def schedule_timeout(
        cls,
        provider_sandbox_id: str,
        sandbox_id: str,
        config: SandboxConfig,
        queue: Optional["SandboxQueueScheduler"] = None,
        timeout_seconds: int = 0,
    ):
        """Schedule a timeout for the sandbox.

        For Docker sandboxes, if timeout is 0 or very small, we delete immediately.
        Otherwise, we schedule deletion via the queue if available.
        """
        if timeout_seconds <= 1:
            await cls.delete(provider_sandbox_id, config, queue, sandbox_id)
        elif queue:
            # Use the queue for delayed deletion
            await queue.schedule_deletion(sandbox_id, timeout_seconds)
        else:
            # Fallback: create an async task for timeout
            async def delayed_delete():
                await asyncio.sleep(timeout_seconds)
                await cls.delete(provider_sandbox_id, config, queue, sandbox_id)
            asyncio.create_task(delayed_delete())

    @classmethod
    async def is_paused(cls, config: SandboxConfig, sandbox_id: str) -> bool:
        """Check if a sandbox is paused (stopped but not removed)."""
        client = cls._get_docker_client()

        try:
            # Find container by sandbox_id label
            containers = client.containers.list(
                all=True,
                filters={"label": f"ii-agent.sandbox-id={sandbox_id}"}
            )
            if containers:
                return containers[0].status in ("exited", "paused")
        except Exception:
            pass
        return False

    # === File Operations ===

    async def expose_port(self, port: int, external: bool = False) -> str:
        """Expose a port from the sandbox.

        Args:
            port: Port number to expose
            external: If True, return host-accessible URL (for browser access).
                     If False, return internal Docker network URL (for container-to-container).

        For Docker sandboxes running on the same network as other containers,
        we return the container's internal IP and the original port so other
        containers can access services directly.

        For browser/external access (like VS Code), we return the host-mapped port.
        """
        self._ensure_container()
        self._container.reload()

        # If external access is requested (e.g., for browser/VS Code), return host-mapped port
        if external:
            # Check if this port is in our mappings (pre-allocated or dynamic)
            if port in self._port_mappings:
                host_port = self._port_mappings[port]
                return f"http://localhost:{host_port}"

            # Check container's actual port bindings (for reconnected containers)
            ports = self._container.attrs.get("NetworkSettings", {}).get("Ports", {})
            port_info = ports.get(f"{port}/tcp", [{}])[0]
            host_port = port_info.get("HostPort")

            if host_port:
                return f"http://localhost:{host_port}"

            # Port not mapped to host
            raise SandboxGeneralException(
                f"Port {port} is not exposed to the host for external access."
            )

        # For internal container-to-container access, return internal Docker IP
        networks = self._container.attrs.get("NetworkSettings", {}).get("Networks", {})
        container_ip = None

        # Find the container's IP on any network (prefer the first one)
        for network_name, network_config in networks.items():
            ip = network_config.get("IPAddress")
            if ip:
                container_ip = ip
                break

        if container_ip:
            # Return the internal Docker network URL
            return f"http://{container_ip}:{port}"

        # Fallback to host-mapped ports if no internal IP found (shouldn't happen)
        # Check if this port is in our mappings (pre-allocated or dynamic)
        if port in self._port_mappings:
            host_port = self._port_mappings[port]
            return f"http://localhost:{host_port}"

        # Check container's actual port bindings (for reconnected containers)
        ports = self._container.attrs.get("NetworkSettings", {}).get("Ports", {})
        port_info = ports.get(f"{port}/tcp", [{}])[0]
        host_port = port_info.get("HostPort")

        if host_port:
            return f"http://localhost:{host_port}"

        # Port is not mapped to host - inform user which ports ARE available
        available_ports = list(self._port_mappings.keys()) if self._port_mappings else []
        if not available_ports:
            # Rebuild from container if port_mappings is empty
            for container_port_proto, bindings in ports.items():
                if bindings and "/tcp" in container_port_proto:
                    available_ports.append(int(container_port_proto.split("/")[0]))

        raise SandboxGeneralException(
            f"Port {port} is not exposed to the host. "
            f"Available host-accessible ports are: {available_ports}. "
            f"Please use one of these ports or restart the sandbox to get port {port} mapped."
        )

    async def upload_file(self, file_content: str | bytes | IO, remote_file_path: str):
        """Upload a file to the sandbox.

        Security: Path is validated to prevent traversal attacks.
        """
        self._ensure_container()

        # Security: validate path
        validated_path = self._validate_path(remote_file_path)

        import tarfile
        import io

        # Prepare content
        if isinstance(file_content, str):
            content = file_content.encode('utf-8')
        elif hasattr(file_content, 'read'):
            content = file_content.read()
            if isinstance(content, str):
                content = content.encode('utf-8')
        else:
            content = file_content

        # Create tar archive
        tar_stream = io.BytesIO()
        with tarfile.open(fileobj=tar_stream, mode='w') as tar:
            file_data = io.BytesIO(content)
            tarinfo = tarfile.TarInfo(name=os.path.basename(validated_path))
            tarinfo.size = len(content)
            tar.addfile(tarinfo, file_data)

        tar_stream.seek(0)

        # Extract to container
        dir_path = os.path.dirname(validated_path)
        self._container.put_archive(dir_path or "/workspace", tar_stream)

    async def download_file(
        self, remote_file_path: str, format: Literal["text", "bytes"] = "text"
    ) -> Optional[str | bytes]:
        """Download a file from the sandbox.

        Security: Path is validated to prevent traversal attacks.
        """
        self._ensure_container()

        # Security: validate path
        validated_path = self._validate_path(remote_file_path)

        import tarfile
        import io

        try:
            bits, stat = self._container.get_archive(validated_path)
        except NotFound:
            return None

        # Extract from tar
        tar_stream = io.BytesIO()
        for chunk in bits:
            tar_stream.write(chunk)
        tar_stream.seek(0)

        with tarfile.open(fileobj=tar_stream, mode='r') as tar:
            member = tar.getmembers()[0]
            file_obj = tar.extractfile(member)
            if file_obj:
                content = file_obj.read()
                if format == "text":
                    return content.decode('utf-8')
                return content
        return None

    async def download_file_stream(self, remote_file_path: str) -> AsyncIterator[bytes]:
        """Download a file from the sandbox as a stream."""
        self._ensure_container()

        try:
            bits, stat = self._container.get_archive(remote_file_path)
            for chunk in bits:
                yield chunk
        except NotFound:
            return

    async def delete_file(self, file_path: str) -> bool:
        """Delete a file from the sandbox.

        Security: Path is validated to prevent traversal attacks.
        """
        self._ensure_container()

        # Security: validate path
        validated_path = self._validate_path(file_path)

        exit_code, output = self._container.exec_run(
            ["/bin/rm", "-f", validated_path]  # Use list form to prevent injection
        )
        return exit_code == 0

    async def write_file(self, file_content: str | bytes | IO, file_path: str) -> bool:
        """Write content to a file in the sandbox."""
        try:
            await self.upload_file(file_content, file_path)
            return True
        except Exception as e:
            logger.error(f"Failed to write file {file_path}: {e}")
            return False

    async def read_file(self, file_path: str) -> str:
        """Read a file from the sandbox."""
        content = await self.download_file(file_path, format="text")
        if content is None:
            raise FileNotFoundError(f"File not found: {file_path}")
        return content

    async def run_cmd(self, command: str, background: bool = False) -> str:
        """Run a command in the sandbox.

        Security Note: Commands are executed via shell. For untrusted input,
        consider using strict=True in _sanitize_command or using exec_run
        with a command list instead of shell string.
        """
        self._ensure_container()

        # Basic sanitization - log potentially dangerous commands
        # Note: Full sanitization would break legitimate use cases
        # The sandbox container itself provides isolation
        if DANGEROUS_PATTERNS.search(command):
            logger.warning(f"Executing command with shell metacharacters: {command[:100]}...")

        if background:
            # Run in background using nohup
            # Use shell array form for slightly better safety
            self._container.exec_run(
                ["/bin/sh", "-c", f"nohup {command} > /dev/null 2>&1 &"],
                detach=True
            )
            return ""

        # Execute command - relies on container isolation for security
        exit_code, output = self._container.exec_run(
            ["/bin/sh", "-c", command],
            workdir="/workspace"
        )
        result = output.decode('utf-8') if output else ""

        if exit_code != 0:
            logger.warning(f"Command exited with code {exit_code}: {command[:100]}")

        return result

    async def create_directory(self, directory_path: str, exist_ok: bool = False) -> bool:
        """Create a directory in the sandbox.

        Security: Path is validated to prevent traversal attacks.
        """
        self._ensure_container()

        # Security: validate path
        validated_path = self._validate_path(directory_path)

        cmd = ["/bin/mkdir"]
        if exist_ok:
            cmd.append("-p")
        cmd.append(validated_path)

        exit_code, output = self._container.exec_run(cmd)
        return exit_code == 0

    # === Docker-specific Methods ===

    def get_mcp_url(self) -> str:
        """Get the URL for the MCP server."""
        return f"http://localhost:{self._host_port_mcp}"

    def get_code_server_url(self) -> str:
        """Get the URL for code-server."""
        return f"http://localhost:{self._host_port_code_server}"

    async def get_logs(self, tail: int = 100) -> str:
        """Get container logs."""
        self._ensure_container()
        return self._container.logs(tail=tail).decode('utf-8')

    @classmethod
    def list_sandboxes(cls) -> list[dict]:
        """List all Docker sandboxes."""
        client = cls._get_docker_client()

        containers = client.containers.list(
            all=True,
            filters={"label": "ii-agent.sandbox=true"}
        )

        result = []
        for container in containers:
            labels = container.labels
            result.append({
                "sandbox_id": labels.get("ii-agent.sandbox-id"),
                "container_id": container.id,
                "status": container.status,
                "created_at": labels.get("ii-agent.created-at"),
                "name": container.name,
            })

        return result
