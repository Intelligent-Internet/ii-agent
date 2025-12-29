"""Base sandbox provider abstract class for the sandbox server."""

from abc import ABC, abstractmethod
from typing import IO, AsyncIterator, Literal, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ii_sandbox_server.lifecycle.queue import SandboxQueueScheduler

from ii_sandbox_server.config import SandboxConfig


class BaseSandbox(ABC):
    """Abstract base class for sandbox providers."""

    @property
    def sandbox_id(self) -> str:
        raise NotImplementedError

    @property
    def provider_sandbox_id(self) -> str:
        raise NotImplementedError

    @classmethod
    async def create(
        cls,
        config: SandboxConfig,
        queue: Optional["SandboxQueueScheduler"] = None,
        sandbox_id: Optional[str] = None,
        metadata: Optional[dict] = None,
        sandbox_template_id: Optional[str] = None,
    ) -> "BaseSandbox":
        """Create a new sandbox instance.

        Returns:
            Sandbox instance
        """
        raise NotImplementedError

    @classmethod
    async def connect(
        cls,
        provider_sandbox_id: str,
        config: SandboxConfig,
        queue: Optional["SandboxQueueScheduler"] = None,
        sandbox_id: Optional[str] = None,
    ) -> "BaseSandbox":
        """Connect to an existing sandbox instance.

        Returns:
            Sandbox instance
        """
        raise NotImplementedError

    @classmethod
    async def resume(
        cls,
        provider_sandbox_id: str,
        config: SandboxConfig,
        queue: Optional["SandboxQueueScheduler"] = None,
        sandbox_id: Optional[str] = None,
    ) -> "BaseSandbox":
        """Resume a paused sandbox instance.

        Returns:
            Sandbox instance
        """
        raise NotImplementedError

    @classmethod
    async def delete(
        cls,
        provider_sandbox_id: str,
        config: SandboxConfig,
        queue: Optional["SandboxQueueScheduler"] = None,
        sandbox_id: Optional[str] = None,
    ) -> bool:
        """Delete a sandbox instance.

        Returns:
            True if deleted successfully
        """
        raise NotImplementedError

    @classmethod
    async def stop(
        cls,
        provider_sandbox_id: str,
        config: SandboxConfig,
        queue: Optional["SandboxQueueScheduler"] = None,
        sandbox_id: Optional[str] = None,
    ) -> bool:
        """Stop a sandbox instance.

        Returns:
            True if stopped successfully
        """
        raise NotImplementedError

    @classmethod
    async def schedule_timeout(
        cls,
        provider_sandbox_id: str,
        sandbox_id: str,
        config: SandboxConfig,
        queue: Optional["SandboxQueueScheduler"] = None,
        timeout_seconds: int = 0,
    ):
        """Schedule a timeout for the sandbox."""
        raise NotImplementedError

    @abstractmethod
    async def expose_port(self, port: int, external: bool = False) -> str:
        """Expose a port in a sandbox.

        Args:
            port: Port to expose
            external: If True, return host-accessible URL (for browser access).
                     If False, return internal URL (for container-to-container).

        Returns:
            URL to access the port
        """
        pass

    @abstractmethod
    async def upload_file(self, file_content: str | bytes | IO, remote_file_path: str):
        """Upload a file to the sandbox.

        Args:
            file_content: Content of the file
            remote_file_path: Path to the file in the sandbox

        Returns:
            True if uploaded successfully
        """
        pass

    @abstractmethod
    async def download_file(
        self, remote_file_path: str, format: Literal["text", "bytes"] = "text"
    ) -> Optional[str | bytes]:
        """Download a file from the sandbox.

        Args:
            remote_file_path: Path to the file in the sandbox
            format: Format of the file content ("text", "bytes", or "stream")

        Returns:
            File content as string, bytes, or iterator of bytes
        """
        pass

    @abstractmethod
    async def download_file_stream(self, remote_file_path: str) -> AsyncIterator[bytes]:
        """Download a file from the sandbox."""
        pass

    @abstractmethod
    async def delete_file(self, file_path: str) -> bool:
        """Delete a file from the sandbox.

        Args:
            file_path: Path to the file in the sandbox

        Returns:
            True if deleted successfully
        """
        pass

    @abstractmethod
    async def write_file(self, file_content: str | bytes | IO, file_path: str) -> bool:
        """Write content to a file in the sandbox.

        Args:
            file_path: Path to the file in the sandbox
            file_content: Content to write

        Returns:
            True if written successfully
        """
        pass

    @abstractmethod
    async def read_file(self, file_path: str) -> str:
        """Read a file from the sandbox.

        Args:
            file_path: Path to the file in the sandbox

        Returns:
            File content as string
        """
        pass

    @abstractmethod
    async def run_cmd(self, command: str, background: bool = False) -> str:
        """Run a command in the sandbox.

        Args:
            command: Command to run

        Returns:
            Output of the command
        """
        pass

    @abstractmethod
    async def create_directory(
        self, directory_path: str, exist_ok: bool = False
    ) -> bool:
        """Create a directory in the sandbox.

        Args:
            directory_path: Path to the directory in the sandbox
            exist_ok: If True, do not raise an error if the directory already exists
        Returns:
            True if created successfully
        """
        pass
