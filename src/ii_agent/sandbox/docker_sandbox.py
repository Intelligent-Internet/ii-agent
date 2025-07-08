import asyncio
import os
import uuid
from typing import Dict

import docker
from ii_agent.core.config.utils import load_ii_agent_config
from ii_agent.core.storage.models.settings import Settings
from ii_agent.sandbox.base_sandbox import BaseSandbox
from ii_agent.sandbox.config import SandboxSettings
from ii_agent.sandbox.sandbox_registry import SandboxRegistry
from ii_agent.utils.constants import WorkSpaceMode


@SandboxRegistry.register(WorkSpaceMode.DOCKER)
class DockerSandbox(BaseSandbox):
    """Docker sandbox environment.

    Provides a containerized execution environment with resource limits,
    file operations, and command execution capabilities.

    Attributes:
        config: Sandbox configuration.
        volume_bindings: Volume mapping configuration.
        client: Docker client.
        container: Docker container instance.
    """

    mode: WorkSpaceMode = WorkSpaceMode.DOCKER

    def __init__(
        self,
        container_name: str,
        settings: Settings,
    ):
        """Initializes a sandbox instance.

        Args:
            config: Sandbox configuration. Default configuration used if None.
            volume_bindings: Volume mappings in {host_path: container_path} format.
        """
        super().__init__(session_id=container_name, settings=settings)
        self.config = SandboxSettings()
        self.volume_bindings = {
            load_ii_agent_config().host_workspace
            + "/"
            + container_name: self.config.work_dir
        }
        self.client = docker.from_env()

    async def start(self):
        pass

    async def stop(self):
        pass

    async def connect(self):
        self.host_url = (
            f"http://{self.session_id}:{self.settings.sandbox_config.service_port}"
        )

    def expose_port(self, port: int) -> str:
        public_url = f"http://{self.session_id}-{port}.{os.getenv('BASE_URL')}"
        return public_url

    async def create(self):
        """Creates and starts the sandbox container.

        Returns:
            Current sandbox instance.

        Raises:
            docker.errors.APIError: If Docker API call fails.
            RuntimeError: If container creation or startup fails.
        """
        os.makedirs(self.config.work_dir, exist_ok=True)
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
                image=self.config.image,
                hostname="sandbox",
                host_config=host_config,
                name=self.session_id,
                labels={
                    "com.docker.compose.project": os.getenv("COMPOSE_PROJECT_NAME")
                },
                tty=True,
                detach=True,
                stdin_open=True,  # Enable interactive mode
            )

            self.container = self.client.containers.get(container["Id"])
            self.container_id = container["Id"]
            self.container.start()

            self.host_url = (
                f"http://{self.session_id}:{self.settings.sandbox_config.service_port}"
            )
            self.sandbox_id = self.container_id
            print(f"Container created: {self.container_id}")
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

    def _safe_resolve_path(self, path: str) -> str:
        """Safely resolves container path, preventing path traversal.

        Args:
            path: Original path.

        Returns:
            Resolved absolute path.

        Raises:
            ValueError: If path contains potentially unsafe patterns.
        """
        # Check for path traversal attempts
        if ".." in path.split("/"):
            raise ValueError("Path contains potentially unsafe patterns")

        resolved = (
            os.path.join(self.config.work_dir, path)
            if not os.path.isabs(path)
            else path
        )
        return resolved

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

    async def __aenter__(self) -> "DockerSandbox":
        """Async context manager entry."""
        return await self.create()

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.cleanup()


if __name__ == "__main__":

    async def main():
        sandbox = DockerSandbox(uuid.uuid4().hex)
        await sandbox.create()
        print("Sandbox created")
        # await sandbox.run_command("ls -la")

    asyncio.run(main())
