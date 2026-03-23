from typing import IO, AsyncIterator, Literal, Optional

from ii_agent.core.client_host import client_host_var
from ii_sandbox_server.client.client import SandboxClient


class IISandbox:
    """Sandbox instance that communicates with the sandbox server."""

    def __init__(
        self,
        sandbox_id: Optional[str],
        sandbox_server_url: str,
        user_id: str
    ):
        self._sandbox_id = sandbox_id
        self._user_id = user_id
        self.client = SandboxClient(sandbox_server_url, timeout=60)

    @property
    def sandbox_id(self) -> str:
        if not self._sandbox_id:
            raise RuntimeError("Sandbox not initialized")
        return self._sandbox_id

    @property
    async def status(self) -> str:
        """Get the status of the sandbox."""
        response = await self.client.get_sandbox_status(self.sandbox_id)
        return response.status

    async def create(self, sandbox_template_id: str | None = None):
        """Create a new sandbox."""
        self._sandbox_id = await self.client.create_sandbox(self._user_id, sandbox_template_id)

    async def connect(self):
        """Connect to a sandbox. If the sandbox is paused, it will be resumed."""
        await self.client.connect_sandbox(self.sandbox_id)

    async def expose_port(self, port: int, external: bool = False) -> str:
        """Expose a port in the sandbox.

        Args:
            port: Port to expose
            external: If True, return host-accessible URL (for browser access).
                     The hostname is taken from the current request's client_host_var
                     so the URL is routable from whichever machine made the request.
        """
        url = await self.client.expose_port(self.sandbox_id, port, external)
        if external:
            client_host = client_host_var.get()
            if client_host != "localhost":
                # Replace localhost / 127.0.0.1 with the caller's host so the
                # returned URL works from the browser that initiated this request.
                url = url.replace("localhost", client_host).replace(
                    "127.0.0.1", client_host
                )
        return url

    async def schedule_timeout(self, timeout_seconds: int):
        """Schedule a timeout for the sandbox."""
        await self.client.schedule_timeout(self.sandbox_id, timeout_seconds)

    async def upload_file(self, file_content: str | bytes | IO, remote_file_path: str):
        """Upload a file to the sandbox."""
        response = await self.client.write_file(self.sandbox_id, remote_file_path, file_content)
        return response.success

    async def upload_file_from_url(self, url: str, remote_file_path: str):
        """Upload a file to the sandbox by downloading it from a URL."""
        response = await self.client.upload_file_from_url(self.sandbox_id, remote_file_path, url)
        return response.success

    async def download_to_presigned_url(self, sandbox_path: str, presigned_url: str, format: Literal["text", "bytes"] = "bytes"):
        """Download a file from the sandbox to a presigned URL."""
        response = await self.client.download_to_presigned_url(self.sandbox_id, sandbox_path, presigned_url, format)
        return response.success

    async def download_file(
        self, remote_file_path: str, format: Literal["text", "bytes", "stream"] = "text"
    ) -> Optional[str | bytes | AsyncIterator[bytes]]:
        """Download a file from the sandbox."""
        content = await self.client.download_file(
            self.sandbox_id, remote_file_path, format
        )
        return content

    async def write_file(self, file_content: str | bytes | IO, file_path: str) -> bool:
        """Write content to a file in the sandbox."""
        response = await self.client.write_file(self.sandbox_id, file_path, file_content)
        return response.success

    async def read_file(self, file_path: str) -> str | bytes | AsyncIterator[bytes]:
        """Read a file from the sandbox."""
        response = await self.client.read_file(self.sandbox_id, file_path)
        return response.content or ""

    async def run_cmd(self, command: str, background: bool = False) -> str:
        """Run a command in the sandbox."""
        return await self.client.run_cmd(self.sandbox_id, command, background)

    async def create_directory(
        self, directory_path: str, exist_ok: bool = False
    ) -> bool:
        """Create a directory in the sandbox."""
        await self.client.create_directory(self.sandbox_id, directory_path, exist_ok)
        return True
