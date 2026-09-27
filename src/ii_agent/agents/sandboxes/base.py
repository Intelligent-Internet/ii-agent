"""Abstract sandbox manager interface.

Defines the execution-only contract for sandbox providers.
All database persistence is handled by :class:`SandboxService`.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import IO, TYPE_CHECKING, AsyncIterator, Dict, Any, List, Literal, Optional

from fastmcp import Client

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.agents.sandboxes.schemas import (
    FileContentResponse,
    FileTreeNode,
    FileUpload,
    SandboxFileInfo,
    SandboxInfo,
)
from ii_agent.agents.sandboxes.shell import Shell
from ii_agent.agents.sandboxes.terminal import LiveTerminalHandle, TerminalDataCallback
from ii_agent.agents.sandboxes.types import SandboxProviderType, SandboxStatus


class Sandbox(ABC):
    """Abstract interface for sandbox execution environments.

    Implementations provide isolated environments for running code, commands,
    and file operations.  They are **stateless with respect to persistence** --
    the service layer owns all database operations.

    Attributes:
        sandbox_id: Internal sandbox ID (from the ``agent_sandboxes`` table).
        session_id: Session this sandbox belongs to.
        provider_sandbox_id: Provider-specific sandbox ID (e.g. E2B's ID).
        provider: Provider backend type.
        status: Current lifecycle status.
        expired_at: When the sandbox expires (provider-managed).
    """

    PROVIDER: SandboxProviderType

    def __init__(
        self,
        sandbox_id: str,
        session_id: str,
        provider_sandbox_id: str,
        status: SandboxStatus = SandboxStatus.NOT_INITIALIZED,
        metadata: Optional[Dict[str, Any]] = None,
        expired_at: Optional[datetime] = None,
    ):
        self.sandbox_id = sandbox_id
        self.session_id = session_id
        self.provider_sandbox_id = provider_sandbox_id
        self.status = status
        self.provider = self.PROVIDER
        self.metadata = metadata or {}
        self.expired_at = expired_at

    # ── Info ──────────────────────────────────────────────────────────────

    @abstractmethod
    async def get_info(self) -> SandboxInfo:
        """Return current sandbox information."""
        ...

    @abstractmethod
    async def get_status(self) -> SandboxStatus:
        """Query the provider for the current sandbox status."""
        ...

    @abstractmethod
    def get_provider_id(self) -> str:
        """Return the provider-specific sandbox ID."""
        ...

    @property
    @abstractmethod
    def upload_path(self) -> str:
        """Default upload directory inside the sandbox."""
        ...

    @property
    def shell(self) -> Shell | None:
        """Return the persistent shell capability when the provider supports it."""
        return None

    # ── Lifecycle ─────────────────────────────────────────────────────────

    @classmethod
    @abstractmethod
    async def create(
        cls,
        sandbox_id: str,
        session_id: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "Sandbox":
        """Provision a new sandbox instance from the provider."""
        ...

    @classmethod
    @abstractmethod
    async def connect(
        cls,
        sandbox_id: str,
        session_id: str,
        provider_sandbox_id: str,
    ) -> "Sandbox":
        """Re-attach to an existing provider sandbox."""
        ...

    @abstractmethod
    async def pause(self) -> None:
        """Pause the sandbox for later resumption."""
        ...

    @abstractmethod
    async def set_timeout(
        self,
        timeout_seconds: int,
        db: "AsyncSession | None" = None,
    ) -> None:
        """Set or update the sandbox timeout.

        When ``db`` is provided, any persistent-deadline write performed by
        the implementation MUST run on that session (no separate DB session).
        This avoids a row-lock self-deadlock when the caller is mid-transaction
        on the same ``agent_sandboxes`` row. The caller retains ownership of
        commit/rollback. When ``db`` is ``None``, the implementation may open
        its own short-lived session (with a ``lock_timeout`` backstop).
        """
        ...

    # ── Command execution ─────────────────────────────────────────────────

    @abstractmethod
    async def run_command(
        self,
        command: str,
        background: bool = False,
        timeout: Optional[int] = None,
        cwd: Optional[str] = None,
        user: Optional[str] = None,
    ) -> str:
        """Run a shell command and return stdout.

        Args:
            command: Shell command to execute.
            background: If True, launch detached and return immediately.
            timeout: Maximum seconds to wait for completion.
            cwd: Working directory inside the sandbox.
            user: Override the executing Unix user (e.g. "root").
                  Provider support: Docker — honoured via exec_run user=.
                  E2B — honoured if the E2B SDK accepts the parameter;
                  otherwise ignored (E2B sandboxes typically run as a
                  fixed user configured in the template).
                  Callers MUST NOT rely on ``user`` for security-critical
                  isolation — use only for file-ownership convenience where
                  the provider is known to be Docker.
        """
        ...

    @abstractmethod
    async def run_python_code(self, code: str) -> str:
        """Run Python code and return output."""
        ...

    @abstractmethod
    async def create_live_terminal(
        self,
        *,
        cols: int,
        rows: int,
        cwd: str,
        on_data: TerminalDataCallback,
        envs: dict[str, str] | None = None,
        timeout: float | None = 0,
    ) -> LiveTerminalHandle:
        """Create a live PTY bound to the current sandbox."""
        ...

    # ── File operations ───────────────────────────────────────────────────

    @abstractmethod
    async def read_file(self, file_path: str) -> str: ...

    @abstractmethod
    async def write_file(
        self,
        file_path: str,
        content: str | bytes | IO,
    ) -> SandboxFileInfo: ...

    @abstractmethod
    async def write_files(self, files: List[FileUpload]) -> List[SandboxFileInfo]: ...

    @abstractmethod
    async def upload_file(
        self,
        file_content: str | bytes | IO,
        remote_file_path: str,
    ) -> bool: ...

    @abstractmethod
    async def download_file(
        self,
        remote_file_path: str,
        format: Literal["text", "bytes"] = "text",
    ) -> Optional[str | bytes]: ...

    @abstractmethod
    async def download_file_stream(
        self,
        remote_file_path: str,
    ) -> AsyncIterator[bytes]: ...

    @abstractmethod
    async def delete_file(self, file_path: str) -> bool: ...

    @abstractmethod
    async def create_directory(
        self,
        directory_path: str,
        exist_ok: bool = False,
    ) -> bool: ...

    @abstractmethod
    async def file_exists(self, file_path: str) -> bool: ...

    # ── Workspace exploration ─────────────────────────────────────────────

    @abstractmethod
    async def list_files_with_contents(
        self,
        path: str,
        max_depth: int = 10,
        inline_content_max_depth: int | None = None,
    ) -> tuple[FileTreeNode, dict[str, dict[str, str]]]:
        """Return the recursive file tree and pre-read contents of small text files."""
        ...

    @abstractmethod
    async def read_file_content(
        self,
        file_path: str,
        *,
        skip_metadata_check: bool = False,
    ) -> FileContentResponse:
        """Read file content with language detection and metadata."""
        ...

    @abstractmethod
    async def watch_dir(
        self,
        path: str,
        on_event: Any,
        on_exit: Any,
        *,
        timeout: int = 0,
        recursive: bool = True,
    ) -> Any:
        """Start watching a directory for filesystem changes.

        Returns a handle with a ``stop()`` method to cancel the watcher.
        """
        ...

    # ── Networking ────────────────────────────────────────────────────────

    @abstractmethod
    async def expose_port(self, port: int, *, external: bool = False) -> str:
        """Expose a port and return its URL.

        Args:
            port: The port number to expose.
            external: If False (default), return a backend/sandbox-internal URL
                using the container IP. This is the correct mode for any
                backend code that needs to talk to a service inside the
                sandbox (MCP server, A2A adapter, codex, etc.) — it does not
                rely on host-network routing or hairpin NAT.
                If True, return a browser-accessible URL (host-mapped port
                with the configured ``SANDBOX_DOCKER_HOST``, or the public
                cloud URL on E2B). Use this only when minting a URL the
                browser will fetch directly.

        The default flipped to ``False`` on 2026-04-25 — see
        ``docs/design-docs/sandbox-pool-claim-mcp-handoff-audit.md``
        for the rationale and blast-radius analysis.
        """
        ...

    @abstractmethod
    async def get_host(self) -> str:
        """Get the sandbox host address."""
        ...

    @abstractmethod
    def get_mcp_client(self, sandbox_url: str) -> Client:
        """Build an MCP client for the given sandbox URL."""
        ...
