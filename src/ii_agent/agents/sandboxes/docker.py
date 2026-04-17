"""Docker sandbox provider implementation.

Local Docker-based sandbox for air-gapped/self-hosted environments.
Pure provider — all database persistence is handled by :class:`SandboxService`.
"""

from __future__ import annotations

import asyncio
import io
import os
import re
import tarfile
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import PurePosixPath
from typing import IO, TYPE_CHECKING, Any, AsyncIterator, Dict, List, Literal, Optional

if TYPE_CHECKING:
    from ii_agent.agents.sandboxes.docker_shell import DockerShell

import docker
from docker.errors import APIError, NotFound
from docker.models.containers import Container

from ii_agent.agents.sandboxes.base import Sandbox
from ii_agent.agents.sandboxes.exceptions import (
    SandboxCreationError,
    SandboxNotFoundException,
    SandboxNotInitializedError,
    SandboxOperationError,
    SandboxTimeoutException,
)
from ii_agent.agents.sandboxes.port_manager import PortPoolManager
from ii_agent.agents.sandboxes.schemas import (
    EXCLUDED_DIRS,
    FileContentResponse,
    FileTreeNode,
    FileUpload,
    SandboxFileInfo,
    SandboxInfo,
    detect_language,
    guess_mime_type,
    is_binary_file_path,
    is_image_file_path,
    INLINE_CONTENT_MAX_SIZE,
    INLINE_CONTENT_TOTAL_MAX,
    MAX_FILE_CONTENT_SIZE,
)
from ii_agent.agents.sandboxes.terminal import (
    LiveTerminalHandle,
    TerminalDataCallback,
)
from ii_agent.agents.sandboxes.types import SandboxProviderType, SandboxStatus
from ii_agent.core.config.settings import Settings, get_settings
from ii_agent.core.logger import logger


# Default timeout for container operations
CONTAINER_STARTUP_TIMEOUT = 120

# Well-known container ports for sandbox services
MCP_SERVER_PORT = 6060
CODE_SERVER_PORT = 9000
NOVNC_PORT = 6080
ADAPTER_CONTAINER_PORT = 18100  # A2A adapter process inside the sandbox

# Common dev server ports to pre-allocate
DEFAULT_EXPOSED_PORTS = [
    MCP_SERVER_PORT,
    CODE_SERVER_PORT,
    NOVNC_PORT,
    ADAPTER_CONTAINER_PORT,
    3000,
    5173,
    8080,
]

# Security: allowed workspace base paths
ALLOWED_WORKSPACE_BASES = ("/workspace", "/tmp", "/home")

# Default UID/GID for the non-root sandbox user ("user") created by e2b.Dockerfile.
# Files written via put_archive use these so the sandbox process can manage them
# without needing CAP_FOWNER (which is intentionally not granted).
_SANDBOX_USER_UID = 1001
_SANDBOX_USER_GID = 1001

# Security: dangerous shell patterns to reject in strict mode
DANGEROUS_PATTERNS = re.compile(
    r"[;&|`$(){}\[\]<>\\!]"
    r"|\.\."
    r"|/etc/|/proc/|/sys/|/dev/"
)


def _validate_path(path: str, allow_absolute: bool = True) -> str:
    """Validate and sanitize file paths to prevent traversal attacks."""
    if not path:
        raise ValueError("Path cannot be empty")

    normalized = PurePosixPath(path)
    resolved = str(normalized)

    if ".." in resolved:
        raise ValueError(f"Path traversal detected: {path}")

    if normalized.is_absolute():
        if not allow_absolute:
            raise ValueError(f"Absolute paths not allowed: {path}")
        if not any(resolved.startswith(base) for base in ALLOWED_WORKSPACE_BASES):
            raise ValueError(
                f"Path must be within allowed directories {ALLOWED_WORKSPACE_BASES}: {path}"
            )

    return resolved


class DockerSandbox(Sandbox):
    """Local Docker-based sandbox implementation.

    Handles only provider-level operations (create, connect, run commands,
    file I/O).  No database awareness.
    """

    PROVIDER: SandboxProviderType = SandboxProviderType.DOCKER

    _docker_client: Optional[docker.DockerClient] = None
    _docker_client_lock: threading.Lock = threading.Lock()

    def __init__(
        self,
        sandbox_id: str,
        session_id: str,
        provider_sandbox_id: str,
        status: SandboxStatus = SandboxStatus.NOT_INITIALIZED,
        metadata: Optional[Dict[str, Any]] = None,
        expired_at: Optional[datetime] = None,
        container: Optional[Container] = None,
        port_mappings: Optional[Dict[int, int]] = None,
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
        self._container = container
        self._port_mappings: Dict[int, int] = port_mappings or {}
        self._config = config or get_settings()
        self._timeout_task: Optional[asyncio.Task] = None
        self._shell: Optional["DockerShell"] = None

    # ── Shell ─────────────────────────────────────────────────────────────

    @property
    def shell(self) -> "DockerShell":
        """Return the persistent shell backend for this Docker sandbox."""
        if self._shell is None:
            from ii_agent.agents.sandboxes.docker_shell import DockerShell

            self._shell = DockerShell(self)
        return self._shell

    # ── Docker client ─────────────────────────────────────────────────────

    @classmethod
    def _get_docker_client(cls) -> docker.DockerClient:
        """Get or create a Docker client singleton (thread-safe)."""
        if cls._docker_client is None:
            with cls._docker_client_lock:
                if cls._docker_client is None:
                    cls._docker_client = docker.from_env()
        return cls._docker_client

    # ── Info ──────────────────────────────────────────────────────────────

    def get_provider_id(self) -> str:
        return self.provider_sandbox_id

    @property
    def upload_path(self) -> str:
        return self._config.workspace_upload_path

    async def get_info(self) -> SandboxInfo:
        vscode_url = None
        vnc_url = None
        if self.status == SandboxStatus.RUNNING:
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
            provider=SandboxProviderType.DOCKER,
            vscode_url=vscode_url,
            vnc_url=vnc_url,
        )

    async def get_status(self) -> SandboxStatus:
        if self._container is None:
            return SandboxStatus.INITIALIZING
        try:
            self._container.reload()
        except NotFound:
            return SandboxStatus.DELETED
        except APIError:
            return SandboxStatus.ERROR
        container_status = self._container.status
        if container_status == "running":
            return SandboxStatus.RUNNING
        if container_status in ("exited", "paused"):
            return SandboxStatus.PAUSED
        return SandboxStatus.ERROR

    # ── Lifecycle ─────────────────────────────────────────────────────────

    @classmethod
    async def create(
        cls,
        sandbox_id: str,
        session_id: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "DockerSandbox":
        """Provision a new Docker container sandbox."""
        cfg = get_settings()
        client = cls._get_docker_client()
        port_manager = PortPoolManager.get_instance()

        image = cfg.sandbox.docker_image
        network = cfg.sandbox.docker_network

        # R8: Enforce concurrent sandbox cap before allocating resources
        max_sandboxes = cfg.sandbox.max_concurrent_sandboxes
        if max_sandboxes > 0:
            stats = port_manager.get_stats()
            if stats["sandboxes"] >= max_sandboxes:
                raise SandboxCreationError(
                    f"Concurrent sandbox limit reached ({max_sandboxes}). "
                    f"Wait for existing sandboxes to be cleaned up."
                )

        # R7: Check port availability before attempting container creation
        required_ports = 7  # Number of ports per sandbox
        stats = port_manager.get_stats()
        if stats["free"] < required_ports:
            raise SandboxCreationError(
                f"Insufficient ports available ({stats['free']} free, "
                f"{required_ports} needed). Port range: {stats['port_range']}."
            )

        # Use configurable port constants from settings
        mcp_port = cfg.sandbox.mcp_server_port
        cs_port = cfg.sandbox.code_server_port
        vnc_port = cfg.sandbox.novnc_port

        exposed_ports = [mcp_port, cs_port, vnc_port, ADAPTER_CONTAINER_PORT, 3000, 5173, 8080]

        # Allocate ports from the pool
        service_names = {
            mcp_port: "mcp_server",
            cs_port: "code_server",
            vnc_port: "novnc",
            ADAPTER_CONTAINER_PORT: "a2a_adapter",
            3000: "dev_server",
            5173: "vite",
            8080: "http",
        }
        port_set = port_manager.allocate_ports(
            sandbox_id=sandbox_id,
            container_ports=exposed_ports,
            service_names=service_names,
        )

        docker_ports = port_set.to_docker_ports()
        port_mappings = {
            alloc.container_port: alloc.host_port for alloc in port_set.allocations.values()
        }

        labels = {
            "ii-agent.sandbox": "true",
            "ii-agent.sandbox-id": sandbox_id,
            "ii-agent.session-id": session_id,
            "ii-agent.created-at": datetime.now(timezone.utc).isoformat(),
        }
        sandbox_metadata = {
            "ii_sandbox_id": sandbox_id,
            "session_id": session_id,
        }
        if metadata:
            sandbox_metadata.update(metadata)
            for key, value in metadata.items():
                labels[f"ii-agent.meta.{key}"] = str(value)

        volume_name = f"ii-sandbox-workspace-{sandbox_id}"

        # Build sandbox environment: always include operational vars,
        # plus A2A adapter backend selection and auth tokens when the inner
        # loop is configured for A2A delegation.
        sandbox_env: dict[str, str] = {
            "SANDBOX_ID": sandbox_id,
            "WORKSPACE_DIR": "/workspace",
            "AGENT_BROWSER_HEADED": "1",
        }
        sandbox_env.update(cls._a2a_adapter_env(cfg))

        try:
            container = client.containers.run(
                image,
                detach=True,
                name=f"ii-sandbox-{sandbox_id[:12]}",
                labels=labels,
                ports=docker_ports,
                volumes={
                    volume_name: {"bind": "/workspace", "mode": "rw"},
                },
                environment=sandbox_env,
                shm_size="512m",
                mem_limit="3072m",
                cpu_period=100000,
                cpu_quota=200000,
                pids_limit=512,
                security_opt=["no-new-privileges"],
                cap_drop=["ALL"],
                cap_add=["CHOWN", "SETUID", "SETGID", "DAC_OVERRIDE", "FOWNER"],
                read_only=False,
                network=network,
                extra_hosts={"host.docker.internal": "host-gateway"},
            )

            port_manager.set_container_id(sandbox_id, container.id)

            logger.info(
                f"Created Docker sandbox {sandbox_id} "
                f"(container: {container.id[:12]}), ports: {port_mappings}"
            )

        except docker.errors.ImageNotFound:
            port_manager.release_ports(sandbox_id)
            raise SandboxCreationError(
                f"Docker image '{image}' not found. Build it with: "
                f"docker build -t {image} -f e2b.Dockerfile ."
            )
        except APIError as e:
            port_manager.release_ports(sandbox_id)
            raise SandboxCreationError(f"Failed to create Docker sandbox: {e}")

        instance = cls(
            sandbox_id=sandbox_id,
            session_id=session_id,
            provider_sandbox_id=container.id,
            container=container,
            port_mappings=port_mappings,
            metadata=sandbox_metadata,
            status=SandboxStatus.RUNNING,
            config=cfg,
        )

        await instance._wait_for_ready(timeout=CONTAINER_STARTUP_TIMEOUT)

        if cfg.sandbox.timeout_seconds:
            await instance.set_timeout(cfg.sandbox.timeout_seconds)

        return instance

    @staticmethod
    def _a2a_adapter_env(cfg: "Settings") -> dict[str, str]:
        """Build environment variables for the sandbox A2A adapter.

        Forwards the configured adapter backend and the corresponding
        authentication tokens so ``start-services.sh`` can launch the
        adapter with the correct backend and credentials.

        Tokens are read from the **backend process** environment (i.e. the
        env vars that docker-compose injects from ``.stack.env.local``).
        Only non-empty values are forwarded.
        """
        env: dict[str, str] = {}

        # Always tell the adapter which backend to use.
        a2a_backend = cfg.agent.a2a_backend
        env["SANDBOX_ADAPTER_BACKEND"] = a2a_backend

        # Forward authentication tokens based on the selected backend.
        # We also forward all tokens unconditionally when available so the
        # adapter can be switched at runtime or used for fallback.
        _TOKEN_MAP: dict[str, list[str]] = {
            "copilot": ["GITHUB_TOKEN", "GH_TOKEN"],
            "claude-code": ["ANTHROPIC_API_KEY"],
            "codex": ["OPENAI_API_KEY"],
        }

        # Always forward tokens for the primary backend, plus any other
        # token that happens to be set (enables backend switching).
        keys_to_forward: set[str] = set()
        for token_keys in _TOKEN_MAP.values():
            keys_to_forward.update(token_keys)

        for key in keys_to_forward:
            value = os.environ.get(key, "")
            if value:
                env[key] = value

        return env

    @classmethod
    async def connect(
        cls,
        sandbox_id: str,
        session_id: str,
        provider_sandbox_id: str,
    ) -> "DockerSandbox":
        """Re-attach to an existing Docker container sandbox."""
        cfg = get_settings()
        client = cls._get_docker_client()
        port_manager = PortPoolManager.get_instance()

        try:
            container = client.containers.get(provider_sandbox_id)
        except NotFound:
            # Fallback: look up by sandbox-id label (handles migrated data where
            # provider_sandbox_id stores the sandbox UUID instead of container ID)
            matches = client.containers.list(
                all=True,
                filters={"label": f"ii-agent.sandbox-id={provider_sandbox_id}"},
            )
            if not matches:
                raise SandboxNotFoundException(provider_sandbox_id)
            container = matches[0]

        container.reload()

        # Handle paused or stopped containers
        if container.status == "paused":
            logger.info(f"Unpausing Docker sandbox {sandbox_id}")
            container.unpause()
            container.reload()
        elif container.status in ("exited", "created"):
            logger.info(f"Restarting stopped Docker sandbox {sandbox_id}")
            try:
                container.start()
            except APIError as e:
                raise SandboxNotInitializedError(
                    f"Cannot restart sandbox {sandbox_id}: {e.explanation or e}"
                )
            container.reload()
            needs_readiness_check = True
        else:
            needs_readiness_check = False

        if container.status != "running":
            raise SandboxNotInitializedError(f"Sandbox container not running: {sandbox_id}")

        # Extract port mappings from the running container
        ports = container.attrs.get("NetworkSettings", {}).get("Ports", {})
        port_mappings: Dict[int, int] = {}
        for container_port_proto, bindings in ports.items():
            if bindings and "/tcp" in container_port_proto:
                container_port = int(container_port_proto.split("/")[0])
                host_port = int(bindings[0].get("HostPort", 0))
                if host_port:
                    port_mappings[container_port] = host_port

        # Register ports with pool manager to prevent conflicts on reconnect
        _register_existing_ports(port_manager, sandbox_id, port_mappings, container.id)

        instance = cls(
            sandbox_id=sandbox_id,
            session_id=session_id,
            provider_sandbox_id=container.id,
            container=container,
            port_mappings=port_mappings,
            status=SandboxStatus.RUNNING,
            config=cfg,
        )

        # Wait for services to be ready after restarting a stopped container
        if needs_readiness_check:
            await instance._wait_for_ready(timeout=CONTAINER_STARTUP_TIMEOUT)

        return instance

    async def pause(self) -> None:
        """Pause (stop) the Docker container."""
        self._ensure_container()
        try:
            self._container.stop(timeout=10)
            self.status = SandboxStatus.PAUSED
            logger.info(
                f"Stopped Docker sandbox {self.sandbox_id} "
                f"(container: {self.provider_sandbox_id[:12]})"
            )
        except NotFound:
            raise SandboxNotFoundException(self.sandbox_id)
        except APIError as e:
            raise SandboxOperationError("pause", str(e))

    async def set_timeout(self, timeout_seconds: int) -> None:
        """Set or update the sandbox timeout.

        R6: Stores the deadline in the DB via ``timeout_at`` column so the
        cleanup loop can enforce it even after a backend restart.  Also keeps
        an in-memory task as a best-effort fast path.
        """
        if self._timeout_task:
            self._timeout_task.cancel()

        # Persist deadline to DB so it survives restarts
        try:
            from ii_agent.agents.sandboxes.models import AgentSandbox
            from ii_agent.core.db import get_db_session_local

            deadline = datetime.now(timezone.utc) + timedelta(seconds=timeout_seconds)
            async with get_db_session_local() as db:
                from sqlalchemy import select

                result = await db.execute(
                    select(AgentSandbox).where(AgentSandbox.id == uuid.UUID(self.sandbox_id))
                )
                record = result.scalar_one_or_none()
                if record:
                    record.timeout_at = deadline
                    await db.commit()
        except Exception as e:
            logger.warning(f"Failed to persist timeout_at for sandbox {self.sandbox_id}: {e}")

        async def _timeout_handler():
            await asyncio.sleep(timeout_seconds)
            logger.info(f"Timeout reached for sandbox {self.sandbox_id}, stopping...")
            try:
                await self.pause()
            except Exception as e:
                logger.error(f"Error stopping sandbox on timeout: {e}")

        self._timeout_task = asyncio.create_task(_timeout_handler())

    async def kill(self) -> bool:
        """Kill and remove the Docker container and release resources."""
        client = self._get_docker_client()
        port_manager = PortPoolManager.get_instance()

        try:
            if self._container:
                try:
                    self._container.remove(force=True)
                except NotFound:
                    pass  # Container already gone — continue cleanup
                except APIError as e:
                    logger.error(f"Failed to remove container for sandbox {self.sandbox_id}: {e}")
                    # Fall through to still release ports and clean up volume
        finally:
            released = port_manager.release_ports(self.sandbox_id)
            volume_cleaned = _cleanup_sandbox_volume(client, self.sandbox_id)

            logger.info(
                f"Killed Docker sandbox {self.sandbox_id}, "
                f"released {released} ports, volume cleaned: {volume_cleaned}"
            )
            self.status = SandboxStatus.DELETED

        return True

    # ── Command execution ─────────────────────────────────────────────────

    async def run_command(
        self,
        command: str,
        background: bool = False,
        timeout: Optional[int] = None,
        cwd: Optional[str] = None,
        user: Optional[str] = None,
        **kwargs,
    ) -> str:
        self._ensure_container()

        workdir = cwd or "/workspace"
        exec_kwargs: dict[str, Any] = {"workdir": workdir}
        if user:
            exec_kwargs["user"] = user

        if background:
            self._container.exec_run(
                ["/bin/sh", "-c", f"nohup {command} > /dev/null 2>&1 &"],
                detach=True,
                **exec_kwargs,
            )
            return ""

        exit_code, output = self._container.exec_run(
            ["/bin/sh", "-c", command],
            **exec_kwargs,
        )
        result = output.decode("utf-8") if output else ""

        if exit_code != 0:
            error_msg = result or f"Exit code: {exit_code}"
            raise SandboxOperationError("run_command", f"Command failed: {error_msg}")

        return result

    async def run_python_code(self, code: str, timeout: int = 120) -> str:
        self._ensure_container()
        import shlex as _shlex

        exit_code, output = self._container.exec_run(
            ["/bin/sh", "-c", f"python3 -c {_shlex.quote(code)}"],
            workdir="/workspace",
        )
        result = output.decode("utf-8") if output else ""

        if exit_code != 0:
            raise SandboxOperationError("run_python_code", f"Execution failed: {result}")
        return result

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
        raise SandboxOperationError(
            "create_live_terminal",
            "Live terminals are not supported by the Docker sandbox provider",
        )

    # ── File operations ───────────────────────────────────────────────────

    async def read_file(self, file_path: str) -> str:
        self._ensure_container()
        validated = _validate_path(file_path)

        try:
            bits, _ = self._container.get_archive(validated)
        except NotFound:
            raise FileNotFoundError(f"File not found: {file_path}")

        tar_stream = io.BytesIO()
        for chunk in bits:
            tar_stream.write(chunk)
        tar_stream.seek(0)

        with tarfile.open(fileobj=tar_stream, mode="r") as tar:
            member = tar.getmembers()[0]
            f = tar.extractfile(member)
            if f:
                return f.read().decode("utf-8")
        raise SandboxOperationError("read_file", f"Could not read: {file_path}")

    async def write_file(
        self,
        file_path: str,
        content: str | bytes | IO,
    ) -> SandboxFileInfo:
        self._ensure_container()
        validated = _validate_path(file_path)
        await self._put_file(validated, content)
        return SandboxFileInfo(
            name=os.path.basename(validated),
            type="file",
            path=file_path,
        )

    async def write_files(self, files: List[FileUpload]) -> List[SandboxFileInfo]:
        results = []
        for f in files:
            info = await self.write_file(f.path, f.content)
            results.append(info)
        return results

    async def upload_file(
        self,
        file_content: str | bytes | IO,
        remote_file_path: str,
    ) -> bool:
        self._ensure_container()
        validated = _validate_path(remote_file_path)
        await self._put_file(validated, file_content)
        return True

    async def download_file(
        self,
        remote_file_path: str,
        format: Literal["text", "bytes"] = "text",
    ) -> Optional[str | bytes]:
        self._ensure_container()
        validated = _validate_path(remote_file_path)

        try:
            bits, _ = self._container.get_archive(validated)
        except NotFound:
            return None

        tar_stream = io.BytesIO()
        for chunk in bits:
            tar_stream.write(chunk)
        tar_stream.seek(0)

        with tarfile.open(fileobj=tar_stream, mode="r") as tar:
            member = tar.getmembers()[0]
            f = tar.extractfile(member)
            if f:
                data = f.read()
                if format == "text":
                    return data.decode("utf-8")
                return data
        return None

    async def download_file_stream(
        self,
        remote_file_path: str,
    ) -> AsyncIterator[bytes]:
        self._ensure_container()

        async def _stream():
            try:
                bits, _ = self._container.get_archive(remote_file_path)
                for chunk in bits:
                    yield chunk
            except NotFound:
                return

        return _stream()

    async def delete_file(self, file_path: str) -> bool:
        self._ensure_container()
        validated = _validate_path(file_path)
        exit_code, _ = self._container.exec_run(["/bin/rm", "-f", validated])
        return exit_code == 0

    async def create_directory(
        self,
        directory_path: str,
        exist_ok: bool = False,
    ) -> bool:
        self._ensure_container()
        validated = _validate_path(directory_path)
        cmd = ["/bin/mkdir"]
        if exist_ok:
            cmd.append("-p")
        cmd.append(validated)
        exit_code, _ = self._container.exec_run(cmd)
        return exit_code == 0

    async def file_exists(self, file_path: str) -> bool:
        self._ensure_container()
        validated = _validate_path(file_path)
        exit_code, _ = self._container.exec_run(["/bin/sh", "-c", f"test -e {validated}"])
        return exit_code == 0

    # ── File tree & content ────────────────────────────────────────────────

    async def list_files_recursive(
        self,
        path: str,
        max_depth: int = 10,
        _current_depth: int = 0,
    ) -> FileTreeNode:
        """Recursively list files/dirs under *path*, returning a tree."""
        self._ensure_container()

        basename = os.path.basename(path.rstrip("/")) or path

        # List directory contents via exec
        exit_code, output = self._container.exec_run(
            ["/bin/sh", "-c", f"ls -1apL {path}"],
        )
        if exit_code != 0:
            return FileTreeNode(name=basename, path=path, type="directory", children=[])

        raw = output.decode("utf-8", errors="replace")
        entries = [e for e in raw.strip().splitlines() if e and e not in ("./", "../")]

        children: list[FileTreeNode] = []
        for entry_name in entries:
            is_dir = entry_name.endswith("/")
            clean_name = entry_name.rstrip("/")
            entry_path = f"{path.rstrip('/')}/{clean_name}"

            if is_dir:
                if clean_name in EXCLUDED_DIRS:
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
                                name=clean_name, path=entry_path, type="directory", children=[]
                            )
                        )
                else:
                    children.append(
                        FileTreeNode(
                            name=clean_name, path=entry_path, type="directory", children=[]
                        )
                    )
            else:
                children.append(FileTreeNode(name=clean_name, path=entry_path, type="file"))

        children.sort(key=lambda n: (0 if n.type == "directory" else 1, n.name.lower()))
        return FileTreeNode(name=basename, path=path, type="directory", children=children)

    async def list_files_with_contents(
        self,
        path: str,
        max_depth: int = 10,
        inline_content_max_depth: int | None = None,
    ) -> tuple[FileTreeNode, dict[str, dict[str, str]]]:
        """Return recursive file tree and pre-read contents of small text files."""
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
                    text = await self.read_file(node.path)
                    total_bytes += len(text.encode("utf-8"))
                    contents[node.path] = {"content": text, "language": detect_language(node.path)}
                except Exception:
                    pass

        tree = await self.list_files_recursive(path, max_depth=max_depth)
        await _collect(tree, current_depth=0)
        return tree, contents

    async def read_file_content(
        self,
        file_path: str,
        *,
        skip_metadata_check: bool = False,
    ) -> FileContentResponse:
        """Read file content with language detection."""
        self._ensure_container()

        mime_type = guess_mime_type(file_path)

        if is_image_file_path(file_path, include_svg=False):
            return FileContentResponse(
                path=file_path,
                file_kind="image",
                mime_type=mime_type or "application/octet-stream",
            )

        if is_binary_file_path(file_path):
            return FileContentResponse(
                path=file_path,
                file_kind="binary",
                mime_type=mime_type,
                message="Binary preview is not supported here. Open VS Code to view.",
            )

        try:
            content = await self.read_file(file_path)
        except FileNotFoundError:
            raise SandboxOperationError("read_file_content", f"File not found: {file_path}")

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

    # ── Networking ────────────────────────────────────────────────────────

    async def get_host(self) -> str:
        """Get the Docker sandbox host address."""
        if self._container is None:
            return "localhost"
        networks = self._container.attrs.get("NetworkSettings", {}).get("Networks", {})
        for net_info in networks.values():
            ip = net_info.get("IPAddress")
            if ip:
                return ip
        return "localhost"

    async def watch_dir(
        self,
        path: str,
        on_event: Any,
        on_exit: Any,
        *,
        timeout: int = 0,
        recursive: bool = True,
    ) -> Any:
        """Watch a directory for filesystem changes using inotifywait in the container."""
        self._ensure_container()

        return _DockerWatchHandle(
            container=self._container,
            path=path,
            on_event=on_event,
            on_exit=on_exit,
            timeout=timeout,
            recursive=recursive,
        )

    async def expose_port(self, port: int, *, external: bool = True) -> str:
        self._ensure_container()
        self._container.reload()

        host = self._config.sandbox.docker_host

        if external:
            # Return host-mapped port URL
            if port in self._port_mappings:
                return f"http://{host}:{self._port_mappings[port]}"

            ports = self._container.attrs.get("NetworkSettings", {}).get("Ports", {})
            bindings = ports.get(f"{port}/tcp")
            if bindings:
                host_port = bindings[0].get("HostPort")
                if host_port:
                    return f"http://{host}:{host_port}"

            available = list(self._port_mappings.keys())
            raise SandboxOperationError(
                "expose_port",
                f"Port {port} is not exposed to the host. "
                f"Available host-accessible ports: {available}",
            )

        # Internal container-to-container access
        networks = self._container.attrs.get("NetworkSettings", {}).get("Networks", {})
        for _net_name, net_config in networks.items():
            ip = net_config.get("IPAddress")
            if ip:
                return f"http://{ip}:{port}"

        # Fallback to host-mapped
        if port in self._port_mappings:
            return f"http://{host}:{self._port_mappings[port]}"

        raise SandboxOperationError("expose_port", f"Cannot resolve address for port {port}")

    def get_mcp_client(self, sandbox_url: str):
        """Get an MCP client for this sandbox."""
        from fastmcp import Client

        mcp_url = sandbox_url + "/mcp/"
        return Client(mcp_url, timeout=self._config.mcp.timeout)

    # ── Docker-specific helpers ───────────────────────────────────────────

    @classmethod
    def list_sandboxes(cls) -> list[dict]:
        """List all Docker sandboxes (by label)."""
        client = cls._get_docker_client()
        containers = client.containers.list(
            all=True,
            filters={"label": "ii-agent.sandbox=true"},
        )
        result = []
        for c in containers:
            labels = c.labels
            result.append(
                {
                    "sandbox_id": labels.get("ii-agent.sandbox-id"),
                    "container_id": c.id,
                    "status": c.status,
                    "created_at": labels.get("ii-agent.created-at"),
                    "name": c.name,
                }
            )
        return result

    # ── Internal helpers ──────────────────────────────────────────────────

    def _ensure_container(self) -> None:
        if self._container is None:
            raise SandboxNotInitializedError(self.sandbox_id)
        self._container.reload()
        if self._container.status != "running":
            raise SandboxNotInitializedError(f"Container not running: {self.sandbox_id}")

    async def _wait_for_ready(self, timeout: int = 60) -> None:
        """Wait for the container's MCP server health endpoint."""
        import httpx

        start = asyncio.get_event_loop().time()
        mcp_port = self._config.sandbox.mcp_server_port

        self._container.reload()
        network_name = self._config.sandbox.docker_network
        networks = self._container.attrs.get("NetworkSettings", {}).get("Networks", {})

        container_ip = None
        if network_name in networks:
            container_ip = networks[network_name].get("IPAddress")
        if not container_ip:
            for net_info in networks.values():
                if net_info.get("IPAddress"):
                    container_ip = net_info["IPAddress"]
                    break

        if container_ip:
            url = f"http://{container_ip}:{mcp_port}/health"
        else:
            host_port = self._port_mappings.get(mcp_port, 0)
            url = f"http://localhost:{host_port}/health"

        logger.debug(f"Waiting for sandbox {self.sandbox_id} at {url}")

        async with httpx.AsyncClient() as client:
            while True:
                elapsed = asyncio.get_event_loop().time() - start
                if elapsed > timeout:
                    raise SandboxTimeoutException(
                        self.sandbox_id,
                        f"Container did not become ready within {timeout}s",
                    )
                try:
                    response = await client.get(url, timeout=2)
                    if response.status_code == 200:
                        logger.info(f"Docker sandbox {self.sandbox_id} is ready")
                        return
                except Exception:
                    pass
                await asyncio.sleep(1)

    async def _put_file(self, validated_path: str, content: str | bytes | IO) -> None:
        """Write content to a file inside the container via tar archive."""
        if isinstance(content, str):
            raw = content.encode("utf-8")
        elif hasattr(content, "read"):
            raw = content.read()
            if isinstance(raw, str):
                raw = raw.encode("utf-8")
        else:
            raw = content

        tar_buf = io.BytesIO()
        with tarfile.open(fileobj=tar_buf, mode="w") as tar:
            info = tarfile.TarInfo(name=os.path.basename(validated_path))
            info.size = len(raw)
            # Set ownership to the sandbox user so the non-root process
            # can manage (and clean up) the file without needing CAP_FOWNER.
            info.uid = _SANDBOX_USER_UID
            info.gid = _SANDBOX_USER_GID
            info.uname = "user"
            info.gname = "user"
            tar.addfile(info, io.BytesIO(raw))
        tar_buf.seek(0)

        dir_path = os.path.dirname(validated_path) or "/workspace"
        # Docker put_archive requires an absolute path; relative paths
        # (e.g. from slide tools) are resolved against /workspace.
        if not dir_path.startswith("/"):
            dir_path = f"/workspace/{dir_path}"
        # Ensure target directory exists inside the container.
        self._container.exec_run(
            ["/bin/sh", "-c", f"mkdir -p {dir_path}"],
            user=f"{_SANDBOX_USER_UID}:{_SANDBOX_USER_GID}",
        )
        self._container.put_archive(dir_path, tar_buf)


# ── Module-level helpers ──────────────────────────────────────────────────


class _DockerWatchHandle:
    """Lightweight directory watcher using inotifywait inside a container.

    Spawns ``inotifywait -m`` via ``docker exec`` and streams filesystem events
    back through the ``on_event`` callback.  Calling ``stop()`` kills the
    background process.
    """

    def __init__(
        self,
        container: Container,
        path: str,
        on_event: Any,
        on_exit: Any,
        timeout: int,
        recursive: bool,
    ) -> None:
        self._container = container
        self._path = path
        self._on_event = on_event
        self._on_exit = on_exit
        self._stopped = False
        self._task: asyncio.Task | None = None

        cmd = ["inotifywait", "-m", "--format", "%e %w%f"]
        if recursive:
            cmd.append("-r")
        cmd.extend(
            [
                "-e",
                "create",
                "-e",
                "modify",
                "-e",
                "delete",
                "-e",
                "moved_from",
                "-e",
                "moved_to",
                path,
            ]
        )

        self._exec_id: str | None = None
        # Start the watcher in a background task
        self._task = asyncio.get_event_loop().create_task(self._run(cmd, timeout))

    async def _run(self, cmd: list[str], timeout: int) -> None:
        """Run inotifywait and stream events."""
        try:
            # Use the low-level Docker API for streaming exec
            api = self._container.client.api
            exec_id = api.exec_create(
                self._container.id,
                cmd,
                stdout=True,
                stderr=True,
            )
            self._exec_id = exec_id["Id"]
            stream = api.exec_start(self._exec_id, stream=True)

            buffer = b""

            for chunk in stream:
                if self._stopped:
                    break
                buffer += chunk
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    decoded = line.decode("utf-8", errors="replace").strip()
                    if decoded:
                        # Parse inotifywait output: "EVENT_TYPE /path/to/file"
                        parts = decoded.split(" ", 1)
                        if len(parts) == 2:
                            event = _InotifyEvent(event_type=parts[0], path=parts[1])
                            try:
                                self._on_event(event)
                            except Exception:
                                pass

                # Yield control to event loop periodically
                await asyncio.sleep(0)

        except Exception as e:
            if not self._stopped:
                logger.debug(f"Watch dir error for {self._path}: {e}")
        finally:
            try:
                await self._on_exit(None if self._stopped else Exception("watcher ended"))
            except Exception:
                pass

    def stop(self) -> None:
        """Stop the directory watcher."""
        self._stopped = True
        if self._task and not self._task.done():
            self._task.cancel()
        # Try to kill the exec process
        if self._exec_id:
            try:
                self._container.exec_run(
                    [
                        "/bin/sh",
                        "-c",
                        f"kill $(pgrep -f 'inotifywait.*{self._path}') 2>/dev/null || true",
                    ],
                    detach=True,
                )
            except Exception:
                pass


class _InotifyEvent:
    """Minimal event object matching the E2B filesystem event interface."""

    __slots__ = ("type", "name")

    def __init__(self, event_type: str, path: str) -> None:
        # Map inotify events to a simplified type
        etype = event_type.upper()
        if "CREATE" in etype:
            self.type = "create"
        elif "DELETE" in etype:
            self.type = "remove"
        elif "MODIFY" in etype or "CLOSE_WRITE" in etype:
            self.type = "write"
        elif "MOVED_FROM" in etype:
            self.type = "remove"
        elif "MOVED_TO" in etype:
            self.type = "create"
        else:
            self.type = "write"
        self.name = path


def _register_existing_ports(
    port_manager: PortPoolManager,
    sandbox_id: str,
    port_mappings: Dict[int, int],
    container_id: str,
) -> None:
    """Register existing port mappings with the port pool manager on reconnect."""
    service_names: Dict[int, str] = {}
    for container_port in port_mappings:
        if container_port == MCP_SERVER_PORT:
            service_names[container_port] = "mcp_server"
        elif container_port == CODE_SERVER_PORT:
            service_names[container_port] = "code_server"

    port_manager.register_existing_ports(
        sandbox_id=sandbox_id,
        port_mappings=port_mappings,
        container_id=container_id,
        service_names=service_names,
    )


def _cleanup_sandbox_volume(
    client: docker.DockerClient,
    sandbox_id: Optional[str],
) -> bool:
    """Clean up the named workspace volume for a sandbox."""
    if not sandbox_id:
        return False

    volume_name = f"ii-sandbox-workspace-{sandbox_id}"
    try:
        volume = client.volumes.get(volume_name)
        volume.remove(force=True)
        logger.debug(f"Removed workspace volume: {volume_name}")
        return True
    except NotFound:
        return False
    except APIError as e:
        logger.warning(f"Failed to remove volume {volume_name}: {e}")
        return False
