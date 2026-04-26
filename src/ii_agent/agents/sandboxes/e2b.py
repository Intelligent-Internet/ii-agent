"""E2B Sandbox provider implementation.

Pure provider — all database persistence is handled by :class:`SandboxService`.
"""

import os
import stat as _stat_mod
from datetime import datetime, timedelta, timezone
from functools import wraps
from typing import IO, TYPE_CHECKING, Any, AsyncIterator, Dict, List, Literal, Optional

from e2b import CommandResult, PtySize, SandboxState
from e2b.exceptions import (
    AuthenticationException,
    NotFoundException,
    TimeoutException,
)
from e2b_code_interpreter import AsyncSandbox
from e2b_code_interpreter.models import Execution
from fastmcp import Client
from ii_agent.agents.sandboxes.base import Sandbox
from ii_agent.agents.sandboxes.e2b_shell import E2BShell
from ii_agent.agents.sandboxes.exceptions import (
    SandboxAuthenticationError,
    SandboxNotFoundException,
    SandboxNotInitializedError,
    SandboxOperationError,
    SandboxTimeoutException,
)
from ii_agent.agents.sandboxes.schemas import (
    EXCLUDED_DIRS,
    INLINE_CONTENT_MAX_SIZE,
    INLINE_CONTENT_TOTAL_MAX,
    MAX_FILE_CONTENT_SIZE,
    FileContentResponse,
    FileTreeNode,
    FileUpload,
    SandboxFileInfo,
    SandboxInfo,
    detect_language,
    guess_mime_type,
    is_binary_file_path,
    is_image_file_path,
)
from ii_agent.agents.sandboxes.terminal import (
    LiveTerminalHandle,
    LiveTerminalNotFoundError,
    TerminalDataCallback,
)
from ii_agent.agents.sandboxes.types import SandboxProviderType, SandboxStatus
from ii_agent.core.config.settings import Settings, get_settings
from ii_agent.core.logger import logger

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


def _is_dir_entry(entry: Any) -> bool:
    """Check whether a filesystem entry from E2B is a directory."""
    raw_type = entry.type
    if raw_type is not None:
        type_val = raw_type.value if hasattr(raw_type, "value") else str(raw_type)
        if type_val.lower() in ("dir", "directory", "file_type_directory"):
            return True
    if hasattr(entry, "mode") and entry.mode is not None:
        if _stat_mod.S_ISDIR(entry.mode):
            return True
    return False


def e2b_exception_handler(func):
    """Decorator to handle E2B-specific exceptions and convert to sandbox exceptions."""

    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except NotFoundException as e:
            sandbox_id = "unknown"
            if args and hasattr(args[0], "sandbox_id"):
                sandbox_id = args[0].sandbox_id
            raise SandboxNotFoundException(str(sandbox_id)) from e
        except AuthenticationException as e:
            raise SandboxAuthenticationError(str(e)) from e
        except TimeoutException as e:
            sandbox_id = "unknown"
            if args and hasattr(args[0], "sandbox_id"):
                sandbox_id = args[0].sandbox_id
            raise SandboxTimeoutException(str(sandbox_id), func.__name__) from e
        except (
            SandboxNotFoundException,
            SandboxAuthenticationError,
            SandboxTimeoutException,
            SandboxNotInitializedError,
            SandboxOperationError,
        ):
            raise
        except Exception as e:
            raise SandboxOperationError(func.__name__, str(e)) from e

    return wrapper


class E2BLiveTerminalHandle(LiveTerminalHandle):
    """Provider-agnostic wrapper around E2B PTY handles."""

    def __init__(self, *, pty, handle) -> None:
        self._pty = pty
        self._handle = handle

    @property
    def pid(self) -> int:
        return self._handle.pid

    async def send_input(self, data: bytes) -> None:
        try:
            await self._pty.send_stdin(self.pid, data)
        except NotFoundException as exc:
            raise LiveTerminalNotFoundError(f"PTY process {self.pid} not found") from exc

    async def resize(self, cols: int, rows: int) -> None:
        try:
            await self._pty.resize(self.pid, PtySize(cols=cols, rows=rows))
        except NotFoundException as exc:
            raise LiveTerminalNotFoundError(f"PTY process {self.pid} not found") from exc

    async def kill(self) -> bool:
        try:
            return await self._handle.kill()
        except NotFoundException as exc:
            raise LiveTerminalNotFoundError(f"PTY process {self.pid} not found") from exc

    async def disconnect(self) -> None:
        await self._handle.disconnect()

    async def wait(self) -> int | None:
        try:
            result = await self._handle.wait()
        except NotFoundException as exc:
            raise LiveTerminalNotFoundError(f"PTY process {self.pid} not found") from exc
        return getattr(result, "exit_code", None)


class E2BSandbox(Sandbox):
    """E2B cloud sandbox implementation.

    Handles only provider-level operations (create, connect, pause,
    run commands, file I/O).  No database awareness.
    """

    PROVIDER: SandboxProviderType = SandboxProviderType.E2B

    def __init__(
        self,
        sandbox_id: str,
        session_id: str,
        provider_sandbox_id: str,
        status: SandboxStatus = SandboxStatus.NOT_INITIALIZED,
        metadata: Optional[Dict[str, Any]] = None,
        sandbox: Optional[AsyncSandbox] = None,
        expired_at: Optional[datetime] = None,
        config: Optional[Settings] = None,
    ):
        super().__init__(
            sandbox_id=sandbox_id,
            session_id=session_id,
            provider_sandbox_id=provider_sandbox_id,
            status=status,
            metadata=metadata,
            expired_at=expired_at,
        )
        self.sandbox = sandbox
        self.mcp_client: Optional[Client] = None
        self._config = config or get_settings()
        self._shell = E2BShell(self)

    # ── Info ──────────────────────────────────────────────────────────────

    def get_provider_id(self) -> str:
        return self.provider_sandbox_id

    @property
    def upload_path(self) -> str:
        return self._config.workspace_upload_path

    @property
    def shell(self) -> E2BShell:
        return self._shell

    async def get_info(self) -> SandboxInfo:
        vscode_url = None
        vnc_url = None
        if self.status == SandboxStatus.RUNNING and self.sandbox:
            try:
                vscode_url = await self.expose_port(self._config.vscode_port, external=True)
            except Exception:
                pass
            try:
                vnc_base = await self.expose_port(self._config.sandbox.novnc_port, external=True)
                vnc_url = f"{vnc_base}/vnc.html?autoconnect=true" if vnc_base else None
            except Exception:
                pass
        return SandboxInfo(
            id=self.sandbox_id,
            session_id=self.session_id,
            status=self.status,
            expired_at=self.expired_at,
            provider=SandboxProviderType.E2B,
            vscode_url=vscode_url,
            vnc_url=vnc_url,
        )

    async def get_status(self) -> SandboxStatus:
        if self.sandbox is None:
            return SandboxStatus.INITIALIZING
        sandbox_info = await AsyncSandbox.get_info(
            sandbox_id=self.provider_sandbox_id,
            api_key=self._config.sandbox.e2b_api_key,
            domain=self._config.sandbox.e2b_domain,
        )
        return self._to_sandbox_status(sandbox_info.state)

    # ── Lifecycle ─────────────────────────────────────────────────────────

    @classmethod
    async def create(
        cls,
        sandbox_id: str,
        session_id: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "E2BSandbox":
        """Provision a new E2B sandbox."""
        cfg = get_settings()

        sandbox_metadata = {
            "ii_sandbox_id": sandbox_id,
            "session_id": session_id,
            "template_id": cfg.sandbox.e2b_template_id,
            "env": cfg.environment,
        }
        if metadata:
            sandbox_metadata.update(metadata)

        expired_at = datetime.now(timezone.utc) + timedelta(seconds=cfg.sandbox.timeout_seconds)

        sandbox = await AsyncSandbox.beta_create(
            template=cfg.sandbox.e2b_template_id,
            api_key=cfg.sandbox.e2b_api_key,
            metadata=sandbox_metadata,
            auto_pause=cfg.sandbox.auto_pause,
            timeout=cfg.sandbox.timeout_seconds,
            domain=cfg.sandbox.e2b_domain,
        )

        instance = cls(
            sandbox_id=sandbox_id,
            session_id=session_id,
            provider_sandbox_id=sandbox.sandbox_id,
            sandbox=sandbox,
            metadata=sandbox_metadata,
            status=SandboxStatus.RUNNING,
            expired_at=expired_at,
            config=cfg,
        )

        logger.info(
            f"Created E2B sandbox {sandbox_id} (provider: {sandbox.sandbox_id}) "
            f"with timeout {cfg.sandbox.timeout_seconds}s"
        )
        return instance

    @classmethod
    async def connect(
        cls,
        sandbox_id: str,
        session_id: str,
        provider_sandbox_id: str,
    ) -> "E2BSandbox":
        """Connect to an existing E2B sandbox."""
        cfg = get_settings()

        sandbox = await AsyncSandbox.connect(
            sandbox_id=provider_sandbox_id,
            api_key=cfg.sandbox.e2b_api_key,
            timeout=cfg.sandbox.timeout_seconds,
            domain=cfg.sandbox.e2b_domain,
        )
        sandbox_info = await sandbox.get_info()
        status = cls._to_sandbox_status(sandbox_info.state)

        return cls(
            sandbox_id=sandbox_id,
            session_id=session_id,
            provider_sandbox_id=sandbox.sandbox_id,
            sandbox=sandbox,
            metadata=sandbox_info.metadata,
            status=status,
            expired_at=sandbox_info.end_at,
            config=cfg,
        )

    @e2b_exception_handler
    async def pause(self) -> None:
        is_running = await self.sandbox.is_running()
        if is_running:
            await self.sandbox.beta_pause()
            self.status = SandboxStatus.PAUSED
            logger.info(f"Paused sandbox {self.sandbox_id} (provider: {self.provider_sandbox_id})")

    @e2b_exception_handler
    async def set_timeout(
        self,
        timeout_seconds: int,
        db: "AsyncSession | None" = None,
    ) -> None:
        # E2B does not persist a per-row deadline (the provider tracks its own
        # timeout), so the ``db`` parameter is accepted for interface parity
        # with DockerSandbox but not used.
        del db
        await self.sandbox.set_timeout(timeout=timeout_seconds)
        self.expired_at = self.expired_at + timedelta(seconds=timeout_seconds)
        logger.debug(
            f"Set timeout for sandbox (provider: {self.provider_sandbox_id}): {timeout_seconds}s"
        )

    # ── Command execution ─────────────────────────────────────────────────

    @e2b_exception_handler
    async def run_command(
        self,
        command: str,
        background: bool = False,
        timeout: Optional[int] = None,
        cwd: Optional[str] = None,
        user: Optional[str] = None,
        **kwargs,
    ) -> str:
        await self._ensure_sandbox_connection()
        if user is not None:
            kwargs["user"] = user
        result = await self.sandbox.commands.run(
            command,
            background=background,
            timeout=timeout,
            cwd=cwd,
            **kwargs,
        )

        if not isinstance(result, CommandResult):
            raise SandboxOperationError("run_command", f"Unexpected result: {result}")

        if result.exit_code != 0:
            error_msg = result.stderr or result.stdout or f"Exit code: {result.exit_code}"
            raise SandboxOperationError("run_command", f"Command failed: {error_msg}")

        return result.stdout

    @e2b_exception_handler
    async def run_python_code(self, code: str, timeout: int = 120) -> str:
        await self._ensure_sandbox_connection()
        result = await self.sandbox.run_code(
            code,
            language="python",
            background=False,
            timeout=timeout,
            cwd=None,
        )

        if not isinstance(result, Execution):
            raise SandboxOperationError("run_python_code", f"Unexpected result: {result}")

        if result.error:
            raise SandboxOperationError(
                "run_python_code",
                f"Execution failed:{result.error.name} {result.error.value}",
            )

        return result.results[0].text or ""

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
        await self._ensure_sandbox_connection()
        handle = await self.sandbox.pty.create(
            PtySize(cols=cols, rows=rows),
            on_data=on_data,
            cwd=cwd,
            envs=envs,
            timeout=timeout,
        )
        return E2BLiveTerminalHandle(pty=self.sandbox.pty, handle=handle)

    # ── File operations ───────────────────────────────────────────────────

    @e2b_exception_handler
    async def read_file(self, file_path: str) -> str:
        await self._ensure_sandbox_connection()
        return await self.sandbox.files.read(file_path, format="text")

    @e2b_exception_handler
    async def write_file(
        self,
        file_path: str,
        content: str | bytes | IO,
    ) -> SandboxFileInfo:
        await self._ensure_sandbox_connection()
        write_info = await self.sandbox.files.write(file_path, content)
        return SandboxFileInfo(name=write_info.name, type="file", path=file_path)

    @e2b_exception_handler
    async def write_files(self, files: List[FileUpload]) -> List[SandboxFileInfo]:
        await self._ensure_sandbox_connection()
        files_data = [{"path": file.path, "data": file.content} for file in files]
        results = await self.sandbox.files.write_files(files_data)
        return [SandboxFileInfo(name=r.name, type=r.type, path=r.path) for r in results]

    @e2b_exception_handler
    async def upload_file(
        self,
        file_content: str | bytes | IO,
        remote_file_path: str,
    ) -> bool:
        await self._ensure_sandbox_connection()
        if await self.sandbox.files.exists(remote_file_path):
            logger.warning(f"File {remote_file_path} already exists, overwriting")
        await self.sandbox.files.write(remote_file_path, file_content)
        return True

    @e2b_exception_handler
    async def download_file(
        self,
        remote_file_path: str,
        format: Literal["text", "bytes"] = "text",
    ) -> Optional[str | bytes]:
        await self._ensure_sandbox_connection()
        content = await self.sandbox.files.read(path=remote_file_path, format=format)
        if isinstance(content, bytes):
            return content
        elif isinstance(content, bytearray):
            return bytes(content)
        elif isinstance(content, str):
            return content if format == "text" else content.encode("utf-8")
        else:
            raise SandboxOperationError(
                "download_file", f"Unsupported content type: {type(content)}"
            )

    async def download_file_stream(
        self,
        remote_file_path: str,
    ) -> AsyncIterator[bytes]:
        await self._ensure_sandbox_connection()
        return await self.sandbox.files.read(path=remote_file_path, format="stream")

    @e2b_exception_handler
    async def delete_file(self, file_path: str) -> bool:
        await self._ensure_sandbox_connection()
        await self.sandbox.files.remove(file_path)
        return True

    @e2b_exception_handler
    async def create_directory(
        self,
        directory_path: str,
        exist_ok: bool = False,
    ) -> bool:
        await self._ensure_sandbox_connection()
        created = await self.sandbox.files.make_dir(directory_path)
        if not created and not exist_ok:
            raise SandboxOperationError(
                "create_directory", f"Directory {directory_path} already exists"
            )
        return True

    @e2b_exception_handler
    async def file_exists(self, file_path: str) -> bool:
        await self._ensure_sandbox_connection()
        return await self.sandbox.files.exists(file_path)

    # ── File tree & content ────────────────────────────────────────────────

    async def list_files_recursive(
        self,
        path: str,
        max_depth: int = 10,
        _current_depth: int = 0,
    ) -> FileTreeNode:
        """Recursively list all files/dirs under *path*, returning a tree."""
        await self._ensure_sandbox_connection()

        basename = os.path.basename(path.rstrip("/")) or path
        entries = await self.sandbox.files.list(path)

        children: list[FileTreeNode] = []
        for entry in entries:
            entry_name = entry.name
            entry_path = f"{path.rstrip('/')}/{entry_name}"
            is_dir = _is_dir_entry(entry)

            if is_dir:
                if entry_name in EXCLUDED_DIRS:
                    continue
                if _current_depth < max_depth:
                    try:
                        subtree = await self.list_files_recursive(
                            entry_path,
                            max_depth=max_depth,
                            _current_depth=_current_depth + 1,
                        )
                        children.append(subtree)
                    except Exception:
                        children.append(
                            FileTreeNode(
                                name=entry_name, path=entry_path, type="directory", children=[]
                            )
                        )
                else:
                    children.append(
                        FileTreeNode(
                            name=entry_name, path=entry_path, type="directory", children=[]
                        )
                    )
            else:
                children.append(
                    FileTreeNode(
                        name=entry_name,
                        path=entry_path,
                        type="file",
                        size=entry.size if hasattr(entry, "size") else None,
                    )
                )

        children.sort(key=lambda n: (0 if n.type == "directory" else 1, n.name.lower()))
        return FileTreeNode(name=basename, path=path, type="directory", children=children)

    @e2b_exception_handler
    async def list_files_with_contents(
        self,
        path: str,
        max_depth: int = 10,
        inline_content_max_depth: int | None = None,
    ) -> tuple[FileTreeNode, dict[str, dict[str, str]]]:
        """Return the recursive file tree and pre-read contents of small text files."""
        contents: dict[str, dict[str, str]] = {}
        total_bytes = 0

        async def _collect(node: FileTreeNode, *, current_depth: int) -> None:
            nonlocal total_bytes
            if node.type == "directory" and node.children:
                for child in node.children:
                    await _collect(child, current_depth=current_depth + 1)
            elif node.type == "file":
                if (
                    inline_content_max_depth is not None
                    and current_depth > inline_content_max_depth
                ):
                    return
                if is_binary_file_path(node.path):
                    return
                file_size = node.size if node.size is not None else INLINE_CONTENT_MAX_SIZE + 1
                if file_size > INLINE_CONTENT_MAX_SIZE:
                    return
                if total_bytes + file_size > INLINE_CONTENT_TOTAL_MAX:
                    return
                try:
                    raw = await self.sandbox.files.read(node.path, format="text")
                    text = raw if isinstance(raw, str) else raw.decode("utf-8", errors="replace")
                    total_bytes += len(text.encode("utf-8"))
                    contents[node.path] = {"content": text, "language": detect_language(node.path)}
                except Exception:
                    pass

        tree = await self.list_files_recursive(path, max_depth=max_depth)
        await _collect(tree, current_depth=0)
        return tree, contents

    @e2b_exception_handler
    async def read_file_content(
        self,
        file_path: str,
        *,
        skip_metadata_check: bool = False,
    ) -> FileContentResponse:
        """Read file content with language detection."""
        await self._ensure_sandbox_connection()

        mime_type = guess_mime_type(file_path)
        entry_size: int | None = None

        if not skip_metadata_check:
            parent = os.path.dirname(file_path)
            basename = os.path.basename(file_path)
            try:
                entries = await self.sandbox.files.list(parent)
                for entry in entries:
                    if entry.name == basename:
                        if _is_dir_entry(entry):
                            raise SandboxOperationError(
                                "read_file_content", f"path '{file_path}' is a directory"
                            )
                        if hasattr(entry, "size") and entry.size:
                            entry_size = int(entry.size)
                        break
            except SandboxOperationError:
                raise
            except Exception:
                pass

        if is_image_file_path(file_path, include_svg=False):
            return FileContentResponse(
                path=file_path, file_kind="image", mime_type=mime_type or "application/octet-stream"
            )

        if entry_size is not None and entry_size > MAX_FILE_CONTENT_SIZE:
            return FileContentResponse(
                path=file_path,
                file_kind="binary",
                mime_type=mime_type,
                message="File too big. Open VS Code to view.",
                too_big=True,
            )

        if is_binary_file_path(file_path):
            return FileContentResponse(
                path=file_path,
                file_kind="binary",
                mime_type=mime_type,
                message="Binary preview is not supported here. Open VS Code to view.",
            )

        content = await self.sandbox.files.read(file_path, format="text")
        if isinstance(content, bytes):
            content = content.decode("utf-8", errors="replace")

        if len(content) > MAX_FILE_CONTENT_SIZE:
            return FileContentResponse(
                path=file_path,
                file_kind="binary",
                mime_type=mime_type,
                message="File too big. Open VS Code to view.",
                too_big=True,
            )

        language = detect_language(file_path)
        return FileContentResponse(
            path=file_path, content=content, language=language, mime_type=mime_type
        )

    async def watch_dir(
        self,
        path: str,
        on_event: Any,
        on_exit: Any,
        *,
        timeout: int = 0,
        recursive: bool = True,
    ) -> Any:
        """Start an E2B filesystem watcher on *path*."""
        await self._ensure_sandbox_connection()
        return await self.sandbox.files.watch_dir(
            path,
            on_event=on_event,
            on_exit=on_exit,
            timeout=timeout,
            recursive=recursive,
        )

    # ── Networking ────────────────────────────────────────────────────────

    async def expose_port(self, port: int, *, external: bool = False) -> str:
        # E2B sandboxes return the same public https URL regardless of
        # ``external`` — the cloud platform doesn't distinguish between
        # backend-internal and browser-accessible endpoints. The kwarg
        # exists purely for ``Sandbox`` interface parity with Docker.
        await self._ensure_sandbox_connection()
        host = self.sandbox.get_host(port)
        return f"https://{host}"

    async def get_host(self) -> str:
        return f"{self.provider_sandbox_id}.{self.sandbox.connection_config.domain}"

    def get_mcp_client(self, sandbox_url: str) -> Client:
        mcp_url = sandbox_url + "/mcp/"
        if self.mcp_client is None:
            self.mcp_client = Client(mcp_url, timeout=self._config.mcp.timeout)
        return self.mcp_client

    # ── Internal helpers ──────────────────────────────────────────────────

    async def _ensure_sandbox_connection(self) -> None:
        if self.sandbox is None:
            raise SandboxNotInitializedError(
                f"Sandbox not yet initialized provider = {self.provider}, "
                f"provider_id = {self.provider_sandbox_id}"
            )

        sandbox_info = await AsyncSandbox.get_info(
            sandbox_id=self.provider_sandbox_id,
            api_key=self._config.sandbox.e2b_api_key,
            domain=self._config.sandbox.e2b_domain,
        )
        timeout_buffer = timedelta(seconds=60)
        should_connect = (sandbox_info.state == SandboxState.PAUSED) or (
            sandbox_info.end_at < datetime.now(timezone.utc) - timeout_buffer
        )
        if should_connect:
            self.sandbox = await AsyncSandbox.connect(
                self.provider_sandbox_id,
                api_key=self._config.sandbox.e2b_api_key,
                timeout=self._config.sandbox.extended_timeout_seconds,
                domain=self._config.sandbox.e2b_domain,
            )
            self.status = SandboxStatus.RUNNING

    @staticmethod
    def _to_sandbox_status(sandbox_state: SandboxState) -> SandboxStatus:
        if sandbox_state.RUNNING:
            return SandboxStatus.RUNNING
        if sandbox_state.PAUSED:
            return SandboxStatus.PAUSED
        raise ValueError(f"Unrecognized sandbox status: {sandbox_state}")
