"""Sandbox service — orchestrates DB persistence + provider lifecycle + MCP config.

This is the single entry point for sandbox operations.  The agent and
socket handlers should call :class:`SandboxService` instead of touching
the provider (E2B, Docker, ...) or the database directly.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any, Dict, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.agents.sandboxes.base import Sandbox
from ii_agent.agents.sandboxes.docker import DockerSandbox
from ii_agent.agents.sandboxes.e2b import E2BSandbox
from ii_agent.agents.sandboxes.exceptions import SandboxCreationError, SandboxNotFoundException
from ii_agent.agents.sandboxes.models import AgentSandbox
from ii_agent.agents.sandboxes.repository import SandboxRepository
from ii_agent.agents.sandboxes.shell import (
    Shell,
    ShellBusyError,
    ShellOperationError,
    ShellResult,
    ShellSessionExistsError,
    ShellSessionNotFoundError,
    ShellSessionRecord,
    ShellSessionState,
)
from ii_agent.agents.sandboxes.types import SandboxProviderType, SandboxStatus
from ii_agent.core.config.settings import Settings
from ii_agent.core.db import get_db_session_local
from ii_agent.core.logger import logger
from ii_agent.sessions.repository import SessionRepository


_SHELL_LOCKS: dict[str, asyncio.Lock] = {}


class SandboxService:
    """Manages sandbox lifecycle with database persistence.

    Responsibilities:
    - Find-or-create sandbox records in the database
    - Delegate to the correct provider (E2B / Docker) for provisioning
    - Persist provider state back to the database
    - Configure MCP servers on newly created sandboxes
    """

    def __init__(
        self,
        sandbox_repo: SandboxRepository,
        session_repo: SessionRepository,
        config: Settings,
    ) -> None:
        self._sandbox_repo = sandbox_repo
        self._session_repo = session_repo
        self._config = config

    # ── Public API ────────────────────────────────────────────────────────

    async def init_sandbox(
        self,
        db: AsyncSession,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Sandbox:
        """Get or create a sandbox for the given session.

        1. Look for an existing active sandbox record.
        2. If the session is a fork, look up parent's sandbox via ``parent_session_id``.
        3. Otherwise, create a new DB record and provision via the provider.
        4. Configure MCP servers on newly created sandboxes.

        Returns the ready-to-use :class:`Sandbox`.
        """
        # 1. Try existing record, then fall back to the parent's sandbox for forks.
        record = await self._resolve_sandbox_record(db, session_id)

        # 3. Create new record if none found
        is_new = False
        if record is None:
            provider = self._resolve_provider()
            record = AgentSandbox(
                session_id=session_id,
                provider=provider,
                status=SandboxStatus.INITIALIZING,
            )
            record = await self._sandbox_repo.save(db, record)
            is_new = True
            logger.info(f"Created sandbox record {record.id} for session {session_id}")

        # 4. Connect or create provider sandbox
        if record.provider_sandbox_id:
            try:
                sandbox_mgr = await self._connect_provider(record)
            except SandboxNotFoundException:
                logger.warning(
                    "Sandbox container %s gone for session %s — marking deleted and creating new one",
                    record.provider_sandbox_id,
                    session_id,
                )
                await self._sandbox_repo.update_status(db, record.id, SandboxStatus.DELETED)
                provider = self._resolve_provider()
                record = AgentSandbox(
                    session_id=session_id,
                    provider=provider,
                    status=SandboxStatus.INITIALIZING,
                )
                record = await self._sandbox_repo.save(db, record)
                is_new = True
                sandbox_mgr = await self._create_provider(record, metadata)
        else:
            sandbox_mgr = await self._create_provider(record, metadata)

        # 5. Persist provider state
        await self._sandbox_repo.update_provider_info(
            db,
            record.id,
            status=sandbox_mgr.status,
            provider_sandbox_id=sandbox_mgr.provider_sandbox_id,
            expired_at=sandbox_mgr.expired_at,
            provider_data=sandbox_mgr.metadata,
        )

        # 6. Configure MCP on new sandboxes
        if is_new or not record.provider_sandbox_id:
            await self._configure_mcp(sandbox_mgr, user_id, db)

        return sandbox_mgr

    async def get_sandbox_for_session(
        self,
        db: AsyncSession,
        session_id: uuid.UUID,
    ) -> Optional[Sandbox]:
        """Get existing sandbox for a session without creating one.

        Returns ``None`` when no active sandbox record exists. Provider connection
        errors are allowed to propagate so callers can distinguish "not found"
        from "failed to reconnect".
        """
        record = await self._resolve_sandbox_record(
            db,
            session_id,
            require_provider_sandbox_id=True,
        )
        if record is None:
            return None
        return await self._connect_provider(record)

    async def get_sandbox_by_session_id(
        self,
        db: AsyncSession,
        session_id: uuid.UUID | str,
    ) -> Optional[Sandbox]:
        """Backward-compatible alias for fetching an existing sandbox."""
        return await self.get_sandbox_for_session(
            db,
            session_id=self._normalize_session_id(session_id),
        )

    async def get_sandbox_by_session(
        self,
        *args: Any,
        db: AsyncSession | None = None,
        session_id: uuid.UUID | str | None = None,
        user_id: uuid.UUID | str | None = None,
    ) -> Sandbox:
        """Backward-compatible get-or-create sandbox helper.

        Supports the historical call styles used across the codebase:

        - ``await service.get_sandbox_by_session(session_id)``
        - ``await service.get_sandbox_by_session(db, session_id=..., user_id=...)``
        """
        remaining = list(args)
        if remaining and db is None and not isinstance(remaining[0], (uuid.UUID, str)):
            db = remaining.pop(0)

        if session_id is None:
            if not remaining:
                raise TypeError("session_id is required")
            session_id = remaining.pop(0)

        if user_id is None and remaining:
            user_id = remaining.pop(0)

        if remaining:
            raise TypeError("Too many positional arguments provided")

        normalized_session_id = self._normalize_session_id(session_id)

        async def _init(db_session: AsyncSession) -> Sandbox:
            resolved_user_id = user_id
            if resolved_user_id is None:
                session = await self._session_repo.get_by_id(db_session, normalized_session_id)
                if session is None or getattr(session, "user_id", None) is None:
                    raise SandboxNotFoundException(str(normalized_session_id))
                resolved_user_id = session.user_id

            normalized_user_id = (
                resolved_user_id
                if isinstance(resolved_user_id, uuid.UUID)
                else uuid.UUID(str(resolved_user_id))
            )
            return await self.init_sandbox(
                db_session,
                session_id=normalized_session_id,
                user_id=normalized_user_id,
            )

        if db is not None:
            return await _init(db)

        async with get_db_session_local() as db_session:
            return await _init(db_session)

    async def get_by_session_id(
        self,
        db: AsyncSession,
        session_id: uuid.UUID,
    ) -> Optional[AgentSandbox]:
        """Get the active sandbox record for a session, falling back to the parent."""
        return await self._resolve_sandbox_record(db, session_id)

    async def pause_sandbox(
        self,
        db: AsyncSession,
        sandbox_id: uuid.UUID,
    ) -> None:
        """Pause a sandbox and update the database."""
        record = await self._sandbox_repo.get_by_id(db, sandbox_id)
        if record is None or record.provider_sandbox_id is None:
            return
        try:
            sandbox_mgr = await self._connect_provider(record)
            await sandbox_mgr.pause()
            await self._sandbox_repo.update_status(db, sandbox_id, SandboxStatus.PAUSED)
        except Exception:
            logger.error(f"Failed to pause sandbox {sandbox_id}", exc_info=True)

    async def update_status(
        self,
        db: AsyncSession,
        sandbox_id: uuid.UUID,
        status: SandboxStatus,
    ) -> None:
        """Update sandbox status in database."""
        await self._sandbox_repo.update_status(db, sandbox_id, status)

    async def load_provider_data(
        self,
        sandbox_id: uuid.UUID,
    ) -> dict[str, Any]:
        """Load provider metadata for a sandbox."""
        async with get_db_session_local() as db:
            record = await self._sandbox_repo.get_by_id(db, sandbox_id)
            if record is None:
                raise SandboxNotFoundException(str(sandbox_id))
            return dict(record.provider_data or {})

    async def persist_provider_data(
        self,
        sandbox_id: uuid.UUID,
        provider_data: dict[str, Any],
    ) -> None:
        """Persist provider metadata for a sandbox."""
        async with get_db_session_local() as db:
            record = await self._sandbox_repo.update_provider_info(
                db,
                sandbox_id,
                provider_data=provider_data,
            )
            if record is None:
                raise SandboxNotFoundException(str(sandbox_id))

    async def list_shell_sessions(
        self,
        session_id: uuid.UUID | str,
    ) -> list[str]:
        """List persistent shell sessions for a sandbox-backed session."""
        sandbox, shell = await self._get_shell_backend_for_session(session_id)
        async with self._get_shell_lock(sandbox.sandbox_id):
            sessions = await self._load_shell_sessions(sandbox.sandbox_id)
            live_sessions: dict[str, ShellSessionRecord] = {}
            stale_session_names: list[str] = []

            for session_name, record in sessions.items():
                if await shell.is_session_live(record):
                    live_sessions[session_name] = record
                else:
                    stale_session_names.append(session_name)

            if stale_session_names:
                logger.info(
                    "Pruning stale PTY sessions for sandbox %s: %s",
                    sandbox.sandbox_id,
                    stale_session_names,
                )
                await self._save_shell_sessions(
                    sandbox.sandbox_id,
                    shell,
                    live_sessions,
                )

            return sorted(live_sessions.keys())

    async def create_shell_session(
        self,
        session_id: uuid.UUID | str,
        session_name: str,
        start_directory: str,
        timeout: int = 60,
    ) -> None:
        """Create a persistent shell session for a sandbox-backed session."""
        sandbox, shell = await self._get_shell_backend_for_session(session_id)
        shell.validate_session_name(session_name)
        start_directory = await shell.normalize_directory(start_directory)

        async with self._get_shell_lock(sandbox.sandbox_id):
            sessions = await self._load_shell_sessions(sandbox.sandbox_id)
            existing_record = sessions.get(session_name)
            if existing_record is not None:
                if await shell.is_session_live(existing_record):
                    raise ShellSessionExistsError(f"Session '{session_name}' already exists")
                sessions.pop(session_name, None)
                await self._save_shell_sessions(sandbox.sandbox_id, shell, sessions)

            record = await shell.create_session_record(
                session_name,
                start_directory,
                timeout=timeout,
            )
            sessions[session_name] = record
            await self._save_shell_sessions(sandbox.sandbox_id, shell, sessions)

    async def delete_shell_session(
        self,
        session_id: uuid.UUID | str,
        session_name: str,
    ) -> None:
        """Delete a persistent shell session for a sandbox-backed session."""
        sandbox, shell = await self._get_shell_backend_for_session(session_id)

        async with self._get_shell_lock(sandbox.sandbox_id):
            sessions = await self._load_shell_sessions(sandbox.sandbox_id)
            record = sessions.get(session_name)
            if record is None:
                raise ShellSessionNotFoundError(f"Session '{session_name}' not found")

            await shell.delete_session(session_name, record)
            sessions.pop(session_name, None)
            await self._save_shell_sessions(sandbox.sandbox_id, shell, sessions)

    async def run_shell_command(
        self,
        session_id: uuid.UUID | str,
        session_name: str,
        command: str,
        *,
        run_dir: str | None = None,
        timeout: int = 60,
        wait_for_output: bool = True,
    ) -> ShellResult:
        """Run a command in a persistent shell session."""
        sandbox, shell = await self._get_shell_backend_for_session(session_id)
        if timeout > shell.max_timeout:
            raise ShellOperationError(
                "run_command",
                f"Timeout must be less than {shell.max_timeout} seconds",
            )

        normalized_run_dir = None
        if run_dir:
            normalized_run_dir = await shell.normalize_directory(run_dir)

        async with self._get_shell_lock(sandbox.sandbox_id):
            sessions = await self._load_shell_sessions(sandbox.sandbox_id)
            existing_record = sessions.get(session_name)
            default_directory = normalized_run_dir or (
                existing_record.cwd if existing_record is not None else shell.workspace_path
            )

            if existing_record is None:
                record = await shell.create_session_record(
                    session_name,
                    default_directory,
                    timeout=timeout,
                )
                sessions[session_name] = record
                await self._save_shell_sessions(sandbox.sandbox_id, shell, sessions)
            else:
                if not await shell.is_session_live(existing_record):
                    sessions.pop(session_name, None)
                    await self._save_shell_sessions(sandbox.sandbox_id, shell, sessions)
                    record = await shell.create_session_record(
                        session_name,
                        default_directory,
                        timeout=timeout,
                    )
                    sessions[session_name] = record
                    await self._save_shell_sessions(sandbox.sandbox_id, shell, sessions)
                else:
                    record, _ = await shell.refresh_session_record(existing_record)
                    if record.status == ShellSessionState.BUSY:
                        raise ShellBusyError("Session is busy, the last command is not finished.")

            request = await shell.build_command_request(
                record,
                command,
                run_dir=normalized_run_dir,
            )
            sessions[session_name] = request.record
            await self._save_shell_sessions(sandbox.sandbox_id, shell, sessions)

            try:
                await shell.send_stdin(session_name, request.record, request.stdin)
            except ShellSessionNotFoundError:
                sessions.pop(session_name, None)
                await self._save_shell_sessions(sandbox.sandbox_id, shell, sessions)
                raise

        if not wait_for_output:
            return await self.get_shell_session_output(session_id, session_name)

        await shell.wait_for_prompt(
            request.record,
            minimum_prompt_seq=request.expected_prompt_seq or request.record.prompt_seq,
            timeout=timeout,
        )

        async with self._get_shell_lock(sandbox.sandbox_id):
            sessions = await self._load_shell_sessions(sandbox.sandbox_id)
            latest_record = sessions.get(session_name)
            if latest_record is None:
                raise ShellSessionNotFoundError(f"Session '{session_name}' not found")
            latest_record, _ = await shell.refresh_session_record(latest_record)
            sessions[session_name] = latest_record
            await self._save_shell_sessions(sandbox.sandbox_id, shell, sessions)

        return await shell.read_command_output(
            request.record,
            start_offset=request.log_offset,
        )

    async def kill_shell_command(
        self,
        session_id: uuid.UUID | str,
        session_name: str,
        *,
        timeout: int = 60,
    ) -> ShellResult:
        """Interrupt the current command in a persistent shell session."""
        sandbox, shell = await self._get_shell_backend_for_session(session_id)

        async with self._get_shell_lock(sandbox.sandbox_id):
            sessions = await self._load_shell_sessions(sandbox.sandbox_id)
            record = sessions.get(session_name)
            if record is None:
                raise ShellSessionNotFoundError(f"Session '{session_name}' not found")

            if not await shell.is_session_live(record):
                sessions.pop(session_name, None)
                await self._save_shell_sessions(sandbox.sandbox_id, shell, sessions)
                raise ShellSessionNotFoundError(f"Session '{session_name}' not found")

            request = await shell.build_interrupt_request(record)
            sessions[session_name] = request.record
            await self._save_shell_sessions(sandbox.sandbox_id, shell, sessions)

            try:
                await shell.send_stdin(session_name, request.record, request.stdin)
            except ShellSessionNotFoundError:
                sessions.pop(session_name, None)
                await self._save_shell_sessions(sandbox.sandbox_id, shell, sessions)
                raise

        await shell.wait_for_prompt(
            request.record,
            minimum_prompt_seq=request.expected_prompt_seq or request.record.prompt_seq,
            timeout=timeout,
        )

        async with self._get_shell_lock(sandbox.sandbox_id):
            sessions = await self._load_shell_sessions(sandbox.sandbox_id)
            latest_record = sessions.get(session_name)
            if latest_record is None:
                raise ShellSessionNotFoundError(f"Session '{session_name}' not found")
            latest_record, _ = await shell.refresh_session_record(latest_record)
            sessions[session_name] = latest_record
            await self._save_shell_sessions(sandbox.sandbox_id, shell, sessions)

        return await shell.read_command_output(
            request.record,
            start_offset=request.log_offset,
        )

    async def get_shell_session_output(
        self,
        session_id: uuid.UUID | str,
        session_name: str,
    ) -> ShellResult:
        """Return the latest output for a persistent shell session."""
        sandbox, shell = await self._get_shell_backend_for_session(session_id)

        async with self._get_shell_lock(sandbox.sandbox_id):
            sessions = await self._load_shell_sessions(sandbox.sandbox_id)
            record = sessions.get(session_name)
            if record is None:
                raise ShellSessionNotFoundError(f"Session '{session_name}' not found")

            if not await shell.is_session_live(record):
                sessions.pop(session_name, None)
                await self._save_shell_sessions(sandbox.sandbox_id, shell, sessions)
                raise ShellSessionNotFoundError(f"Session '{session_name}' not found")

            record, changed = await shell.refresh_session_record(record)
            if changed:
                sessions[session_name] = record
                await self._save_shell_sessions(sandbox.sandbox_id, shell, sessions)

            return await shell.read_session_output(record)

    async def write_to_shell_process(
        self,
        session_id: uuid.UUID | str,
        session_name: str,
        data: str,
        press_enter: bool,
    ) -> ShellResult:
        """Write stdin to a persistent shell session."""
        sandbox, shell = await self._get_shell_backend_for_session(session_id)

        async with self._get_shell_lock(sandbox.sandbox_id):
            sessions = await self._load_shell_sessions(sandbox.sandbox_id)
            record = sessions.get(session_name)
            if record is None:
                raise ShellSessionNotFoundError(f"Session '{session_name}' not found")

            if not await shell.is_session_live(record):
                sessions.pop(session_name, None)
                await self._save_shell_sessions(sandbox.sandbox_id, shell, sessions)
                raise ShellSessionNotFoundError(f"Session '{session_name}' not found")

            request = await shell.build_process_input_request(record, data, press_enter)
            if press_enter:
                sessions[session_name] = request.record
                await self._save_shell_sessions(sandbox.sandbox_id, shell, sessions)

            try:
                await shell.send_stdin(session_name, request.record, request.stdin)
            except ShellSessionNotFoundError:
                sessions.pop(session_name, None)
                await self._save_shell_sessions(sandbox.sandbox_id, shell, sessions)
                raise

        await asyncio.sleep(shell.poll_interval)
        return await self.get_shell_session_output(session_id, session_name)

    # ── Provider resolution ───────────────────────────────────────────────

    def _resolve_provider(self) -> SandboxProviderType:
        """Map config ``sandbox.provider`` to our enum."""
        provider = self._config.sandbox.provider
        if provider == "e2b":
            return SandboxProviderType.E2B
        if provider == "docker":
            return SandboxProviderType.DOCKER
        raise SandboxCreationError(f"Unsupported sandbox provider: {provider}")

    async def _create_provider(
        self,
        record: AgentSandbox,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Sandbox:
        """Provision a new sandbox via the correct provider."""
        if record.provider == SandboxProviderType.E2B:
            return await E2BSandbox.create(
                sandbox_id=str(record.id),
                session_id=str(record.session_id),
                metadata=metadata,
            )
        if record.provider == SandboxProviderType.DOCKER:
            return await DockerSandbox.create(
                sandbox_id=str(record.id),
                session_id=str(record.session_id),
                metadata=metadata,
            )
        raise SandboxCreationError(f"Unsupported provider: {record.provider}")

    async def _connect_provider(self, record: AgentSandbox) -> Sandbox:
        """Connect to an existing provider sandbox."""
        if record.provider == SandboxProviderType.E2B:
            return await E2BSandbox.connect(
                sandbox_id=str(record.id),
                session_id=str(record.session_id),
                provider_sandbox_id=record.provider_sandbox_id,
            )
        if record.provider == SandboxProviderType.DOCKER:
            return await DockerSandbox.connect(
                sandbox_id=str(record.id),
                session_id=str(record.session_id),
                provider_sandbox_id=record.provider_sandbox_id,
            )
        raise SandboxCreationError(f"Unsupported provider: {record.provider}")

    @staticmethod
    def _normalize_session_id(session_id: uuid.UUID | str) -> uuid.UUID:
        return session_id if isinstance(session_id, uuid.UUID) else uuid.UUID(str(session_id))

    def _get_shell_lock(self, sandbox_id: str) -> asyncio.Lock:
        return _SHELL_LOCKS.setdefault(sandbox_id, asyncio.Lock())

    async def _load_shell_sessions(
        self,
        sandbox_id: str,
    ) -> dict[str, ShellSessionRecord]:
        provider_data = await self.load_provider_data(uuid.UUID(sandbox_id))
        raw_sessions = provider_data.get("pty_sessions") or {}
        if not isinstance(raw_sessions, dict):
            return {}

        sessions: dict[str, ShellSessionRecord] = {}
        for session_name, raw_record in raw_sessions.items():
            try:
                sessions[session_name] = ShellSessionRecord.model_validate(raw_record)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Invalid shell session metadata for sandbox %s session %s: %s",
                    sandbox_id,
                    session_name,
                    exc,
                )
        return sessions

    async def _save_shell_sessions(
        self,
        sandbox_id: str,
        shell: Shell,
        sessions: dict[str, ShellSessionRecord],
    ) -> None:
        provider_data = await self.load_provider_data(uuid.UUID(sandbox_id))
        provider_data["pty_sessions"] = {
            session_name: record.model_dump(mode="json")
            for session_name, record in sessions.items()
        }
        await self.persist_provider_data(uuid.UUID(sandbox_id), provider_data)

    async def _get_shell_backend_for_session(
        self,
        session_id: uuid.UUID | str,
    ) -> tuple[Sandbox, Shell]:
        normalized_session_id = self._normalize_session_id(session_id)
        async with get_db_session_local() as db:
            sandbox = await self.get_sandbox_for_session(
                db,
                session_id=normalized_session_id,
            )

        if sandbox is None:
            raise ShellOperationError(
                "resolve_shell_session",
                f"No sandbox found for session {normalized_session_id}",
            )

        shell = getattr(sandbox, "shell", None)
        if shell is None:
            raise ShellOperationError(
                "resolve_shell_session",
                f"Persistent shell sessions are not supported by sandbox {sandbox.sandbox_id}",
            )

        return sandbox, shell

    async def _resolve_sandbox_record(
        self,
        db: AsyncSession,
        session_id: uuid.UUID,
        *,
        require_provider_sandbox_id: bool = False,
    ) -> Optional[AgentSandbox]:
        """Resolve the active sandbox record for a session or its parent."""

        def _usable(record: AgentSandbox | None) -> bool:
            return record is not None and (
                not require_provider_sandbox_id or record.provider_sandbox_id is not None
            )

        record = await self._sandbox_repo.get_active_by_session_id(db, session_id)
        if _usable(record):
            return record

        session = await self._session_repo.get_by_id(db, session_id)
        if session and session.parent_session_id:
            parent_record = await self._sandbox_repo.get_active_by_session_id(
                db, session.parent_session_id
            )
            if _usable(parent_record):
                logger.info(
                    "Session %s sharing sandbox from parent %s",
                    session_id,
                    session.parent_session_id,
                )
                return parent_record

        if require_provider_sandbox_id:
            return None
        return record

    # ── MCP configuration ─────────────────────────────────────────────────

    async def _configure_mcp(
        self,
        sandbox: Sandbox,
        user_id: uuid.UUID,
        db: AsyncSession,
    ) -> None:
        """Configure MCP servers on a sandbox."""
        try:
            sandbox_url = await sandbox.expose_port(self._config.mcp.port)
            # Build and set credentials
            sandbox.get_mcp_client(sandbox_url=sandbox_url)

            # Register user MCP servers
            await self._register_user_mcp_servers(sandbox, user_id, sandbox_url, db)

        except Exception as e:
            logger.warning(f"Failed to configure MCP for sandbox {sandbox.sandbox_id}: {e}")

    async def _register_user_mcp_servers(
        self,
        sandbox: Sandbox,
        user_id: uuid.UUID,
        sandbox_url: str,
        db: AsyncSession,
    ) -> None:
        """Register user's custom + composio MCP servers with the sandbox."""
        from ii_agent.settings.mcp.service import MCPSettingService
        from ii_agent.settings.mcp.repository import MCPSettingRepository
        from ii_agent.settings.mcp.schemas import CodexMetadata, ClaudeCodeMetadata
        from ii_server.mcp.client import MCPClient

        mcp_svc = MCPSettingService(repo=MCPSettingRepository(), config=self._config)
        mcp_settings = await mcp_svc.list_mcp_settings(db, user_id=user_id, only_active=True)

        combined_config = (
            mcp_settings.get_combined_active_config() if mcp_settings.settings else None
        )
        config_dict = combined_config.model_dump(exclude_none=True) if combined_config else {}

        # Get composio servers
        composio_mcp_servers = await self._get_composio_mcp_servers(user_id, db)

        merged_mcp_servers: dict = {}
        if config_dict.get("mcpServers"):
            merged_mcp_servers.update(config_dict["mcpServers"])
        if composio_mcp_servers:
            merged_mcp_servers.update(composio_mcp_servers)

        async with MCPClient(sandbox_url) as client:
            if combined_config:
                is_codex = any(isinstance(m, CodexMetadata) for m in combined_config.metadatas)
                for md in combined_config.metadatas:
                    if isinstance(md, CodexMetadata):
                        store_path = f"{self._config.sandbox.user}/.codex/auth.json"
                        await sandbox.write_file(store_path, json.dumps(md.auth_json))
                    if isinstance(md, ClaudeCodeMetadata):
                        store_path = f"{self._config.sandbox.user}/.claude/.credentials.json"
                        await sandbox.write_file(store_path, json.dumps(md.auth_json))

                if is_codex:
                    logger.info("Codex metadata found, ensuring Codex setup in sandbox")
                    await client.register_codex()

            if merged_mcp_servers:
                logger.info(f"Registering {len(merged_mcp_servers)} MCP servers for user {user_id}")
                await client.register_custom_mcp({"mcpServers": merged_mcp_servers})

    async def _get_composio_mcp_servers(
        self,
        user_id: uuid.UUID,
        db: AsyncSession,
    ) -> Optional[dict]:
        """Get user's Composio MCP server configurations."""
        try:
            # Use the composio service to get decrypted MCP configs
            from ii_agent.core.container import get_app_container

            container = get_app_container()
            composio_mcp_servers = await container.composio_service.get_user_composio_mcp_configs(
                db, user_id
            )
            if not composio_mcp_servers:
                return None

            logger.info(
                f"Found {len(composio_mcp_servers)} Composio MCP servers for user {user_id}"
            )
            return composio_mcp_servers
        except Exception as e:
            logger.error(f"Failed to get Composio MCP servers for user {user_id}: {e}")
            return None
