from __future__ import annotations
import asyncio
import os
import uuid
from typing import Dict, TYPE_CHECKING

import docker
from fastmcp.client import Client
from ii_agent.core.config.utils import load_ii_agent_config
from ii_agent.runtime.base import BaseRuntime
from ii_agent.runtime.config.runtime_config import RuntimeSettings
from ii_agent.runtime.runtime_registry import RuntimeRegistry
from ii_agent.runtime.model.constants import RuntimeMode
from ii_agent.runtime.utils.docker_utils import (
    build_if_not_exists,
    get_host_ip,
    get_project_root,
)

if TYPE_CHECKING:
    from ii_agent.core.storage.models.settings import Settings


@RuntimeRegistry.register(RuntimeMode.DOCKER)
class DockerRuntime(BaseRuntime):
    """Docker runtime environment.

    Provides a containerized execution environment with resource limits,
    file operations, and command execution capabilities.

    Attributes:
        config: Runtime configuration.
        volume_bindings: Volume mapping configuration.
        client: Docker client.
        container: Docker container instance.
    """

    mode: RuntimeMode = RuntimeMode.DOCKER

    def __init__(
        self,
        session_id: str,
        settings: Settings,
    ):
        """Initializes a docker runtime instance.

        Args:
            config: Docker runtime configuration. Default configuration used if None.
            volume_bindings: Volume mappings in {host_path: container_path} format.
        """
        super().__init__(session_id=session_id, settings=settings)
        self.docker_images = {
            "sandbox": {
                "path": os.path.join(get_project_root()),
                "dockerfile": "docker/sandbox/Dockerfile",
                "tag": "ii-agent-sandbox:latest",
            },
            "nginx": {
                "path": os.path.join(get_project_root()),
                "dockerfile": "docker/nginx/Dockerfile",
                "tag": "ii-agent-nginx:latest",
                "port": 8080,
            },
        }
        self.config = RuntimeSettings()
        self.volume_bindings = {
            load_ii_agent_config().workspace_root
            + "/"
            + str(self.session_id): self.config.work_dir
        }
        self.client = docker.from_env()

    async def stop(self):
        pass

    async def build(self):
        try:
            for _, config in self.docker_images.items():
                build_if_not_exists(
                    self.client, config["path"], config["dockerfile"], config["tag"]
                )
        except Exception as e:
            raise RuntimeError(f"Failed to build runtime: {e}")

    async def connect(self):
        self.host_url = (
            self.expose_port(self.settings.runtime_config.service_port) + "/mcp/"
        )

    async def start(self):
        """Start the runtime by ensuring network exists and nginx container is running."""
        pass

    def get_mcp_client(self, workspace_dir: str) -> Client:
        if not self.host_url:
            raise RuntimeError("Host URL is not set")
        return Client(self.host_url)

    def expose_port(self, port: int) -> str:
        try:
            public_url = f"http://{self.session_id}-{port}.{os.getenv('BASE_URL', get_host_ip())}.nip.io:{self.docker_images['nginx']['port']}"
            return public_url
        except Exception as e:
            raise RuntimeError(f"Failed to expose port: {e}")

    async def create(self):
        """Creates and starts the docker runtime container.

        Returns:
            Current runtime instance.

        Raises:
            docker.errors.APIError: If Docker API call fails.
            RuntimeError: If container creation or startup fails.
        """
        await self.build()
        await self._ensure_network_exists()
        await self._ensure_nginx_running()
        os.makedirs(load_ii_agent_config().workspace_root, exist_ok=True)
        try:
            # Prepare container config
            host_config = self.client.api.create_host_config(
                mem_limit=self.config.memory_limit,
                cpu_period=100000,
                cpu_quota=int(100000 * self.config.cpu_limit),
                network_mode=None
                if not self.config.network_enabled
                else self.config.network_name,
                binds=self._prepare_volume_bindings(),
            )

            # Create container
            container = await asyncio.to_thread(
                self.client.api.create_container,
                image=self.docker_images["sandbox"]["tag"],
                hostname="sandbox",
                host_config=host_config,
                name=str(self.session_id),
                labels={
                    "com.docker.compose.project": os.getenv(
                        "COMPOSE_PROJECT_NAME", "ii-agent"
                    )
                },
                tty=True,
                detach=True,
                stdin_open=True,  # Enable interactive mode
            )

            self.container = self.client.containers.get(container["Id"])
            self.container_id = container["Id"]
            self.container.start()
            await asyncio.sleep(3)

            self.host_url = (
                self.expose_port(self.settings.runtime_config.service_port) + "/mcp/"
            )
            self.runtime_id = self.container_id
            #print(f"Container created: {self.container_id}")
        except Exception as e:
            await self.cleanup()  # Ensure resources are cleaned up
            raise RuntimeError(f"Failed to create sandbox: {e}") from e

    def _prepare_volume_bindings(self) -> Dict[str, Dict[str, str]]:
        """Prepares volume binding configuration.

        Returns:
            Volume binding configuration dictionary.
        """
        bindings = {}
        # Add custom volume bindings
        for host_path, container_path in self.volume_bindings.items():
            bindings[host_path] = {"bind": container_path, "mode": "rw"}

        return bindings

    async def cleanup(self) -> None:
        """Cleans up sandbox resources."""
        errors = []
        try:
            if self.container:
                try:
                    await asyncio.to_thread(self.container.stop, timeout=5)
                except Exception as e:
                    errors.append(f"Container stop error: {e}")

                try:
                    await asyncio.to_thread(self.container.remove, force=True)
                except Exception as e:
                    errors.append(f"Container remove error: {e}")
                finally:
                    self.container = None

        except Exception as e:
            errors.append(f"General cleanup error: {e}")

        if errors:
            print(f"Warning: Errors during cleanup: {', '.join(errors)}")

    async def __aenter__(self) -> "DockerRuntime":
        await self.create()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.cleanup()

    async def _ensure_network_exists(self):
        """Create the network if it doesn't exist."""
        if not self.config.network_enabled:
            return

        try:
            # Check if network exists
            networks = await asyncio.to_thread(
                self.client.networks.list, names=[self.config.network_name]
            )
            if not networks:
                print(f"Creating network: {self.config.network_name}")
                await asyncio.to_thread(
                    self.client.networks.create,
                    name=self.config.network_name,
                    driver="bridge",
                )
                print(f"Network '{self.config.network_name}' created successfully")
            else:
                return
                #print(f"Network '{self.config.network_name}' already exists")
        except Exception as e:
            raise RuntimeError(f"Failed to ensure network exists: {e}")

    async def _ensure_nginx_running(self):
        """Create and start nginx container if none is running."""
        try:
            # Check if any nginx containers are running
            containers = await asyncio.to_thread(
                self.client.containers.list,
                filters={
                    "ancestor": self.docker_images["nginx"]["tag"],
                    "status": "running",
                },
            )

            if not containers:
                print("No running nginx containers found, creating one...")
                await self._create_nginx_container()
            else:
                return
                #print(f"Found {len(containers)} running nginx container(s)")
        except Exception as e:
            raise RuntimeError(f"Failed to ensure nginx is running: {e}")

    async def _create_nginx_container(self):
        """Create and start a new nginx container."""
        try:
            # Ensure nginx image is built
            build_if_not_exists(
                self.client,
                self.docker_images["nginx"]["path"],
                self.docker_images["nginx"]["dockerfile"],
                self.docker_images["nginx"]["tag"],
            )

            # Prepare nginx container config
            host_config = self.client.api.create_host_config(
                port_bindings={"80/tcp": self.docker_images["nginx"]["port"]},
                network_mode=self.config.network_name
                if self.config.network_enabled
                else None,
            )

            # Create nginx container
            nginx_container = await asyncio.to_thread(
                self.client.api.create_container,
                image=self.docker_images["nginx"]["tag"],
                hostname="nginx-proxy",
                host_config=host_config,
                name=f"nginx-proxy-{uuid.uuid4().hex[:8]}",
                labels={
                    "com.docker.compose.project": os.getenv(
                        "COMPOSE_PROJECT_NAME", "ii-agent"
                    ),
                    "service": "nginx-proxy",
                },
                environment={
                    "PUBLIC_DOMAIN": os.getenv("BASE_URL", get_host_ip() + ".nip.io")
                },
                detach=True,
            )

            nginx_container_obj = self.client.containers.get(nginx_container["Id"])
            nginx_container_obj.start()

            #print(f"Nginx container created and started: {nginx_container['Id']}")

        except Exception as e:
            raise RuntimeError(f"Failed to create nginx container: {e}")


if __name__ == "__main__":

    async def main():
        settings = Settings()
        runtime = DockerRuntime(uuid.uuid4().hex, settings)
        await runtime.start()  # This will now ensure network and nginx are ready
        await runtime.create()
        print("Runtime created")
        # await runtime.run_command("ls -la")

    asyncio.run(main())
