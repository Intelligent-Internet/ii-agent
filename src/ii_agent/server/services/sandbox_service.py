"""Simplified sandbox service that communicates with the standalone sandbox server."""

import json
import uuid
import logging
import asyncio
from typing import Optional, Dict

from ii_agent.sandbox import IISandbox
from ii_agent.core.config.ii_agent_config import IIAgentConfig
from ii_agent.db.manager import Sessions, APIKeys, get_db_session_local
from ii_agent.server.mcp_settings.models import ClaudeCodeMetadata, CodexMetadata
from ii_agent.server.mcp_settings.service import list_mcp_settings
from ii_tool.mcp.client import MCPClient
from ii_agent.core.config.ii_agent_config import config


logger = logging.getLogger(__name__)

MAX_ATTEMPT = 3
RETRY_DELAY_SECONDS = 1

class SandboxService:
    """Simplified sandbox service that delegates to the sandbox server."""

    def __init__(self, config: IIAgentConfig):
        self.config = config
        self.tool_server_url = config.tool_server_url
        self.sandbox_server_url = config.sandbox_server_url
        self.sandbox_template_id = config.sandbox_template_id

    async def get_sandbox_by_session(self, session_uuid: uuid.UUID) -> IISandbox:
        """Ensure a sandbox exists for the given session ID."""
        existing_session = await Sessions.get_session_by_id(session_uuid)
        if not existing_session:
            # Session not found exception
            raise Exception(f"Session {session_uuid} not found")

        if await Sessions.session_has_sandbox(session_uuid):
            # Connect to existing sandbox
            sandbox = IISandbox(
                str(existing_session.sandbox_id),
                self.sandbox_server_url,
                str(existing_session.user_id),
            )
            await sandbox.connect()
            await self.reset_tool_server(
                sandbox,
                session_uuid=session_uuid,
                user_id=str(existing_session.user_id),
            )
            return sandbox

        # Create new sandbox
        sandbox = IISandbox(
            sandbox_id = None,
            sandbox_server_url=self.sandbox_server_url,
            user_id=str(existing_session.user_id)
        )

        last_error = None
        for attempt in range(MAX_ATTEMPT):
            try:
                await self._initialize_sandbox(sandbox, session_uuid, str(existing_session.user_id))
                await Sessions.update_sandbox_id(
                    session_uuid=session_uuid,
                    sandbox_id=sandbox.sandbox_id,
                )
                logger.info(
                    f"Created new session {session_uuid} with sandbox {sandbox.sandbox_id}"
                )
                return sandbox
            except Exception as e:
                last_error = e
                logger.warning(
                    "Sandbox initialization failed for session %s (attempt %d/%d): %s",
                    session_uuid,
                    attempt + 1,
                    MAX_ATTEMPT,
                    str(e),
                    exc_info=True,
                )
                # Cleanup failed sandbox (best effort)
                try:
                    await sandbox.schedule_timeout(1)
                except Exception as cleanup_error:
                    logger.debug(
                        "Failed to cleanup sandbox for session %s: %s",
                        session_uuid,
                        cleanup_error
                    )
                # Don't sleep after last attempt
                if attempt < MAX_ATTEMPT - 1:
                    await asyncio.sleep(RETRY_DELAY_SECONDS)

        raise RuntimeError(
            f"Failed to initialize sandbox for session {session_uuid} after {MAX_ATTEMPT} attempts"
        ) from last_error


    async def _initialize_sandbox(
        self,
        sandbox: IISandbox,
        session_uuid: uuid.UUID,
        user_id: str
    ) -> None:
        """Initialize sandbox with template and MCP servers."""
        await sandbox.create(self.sandbox_template_id)

        user_api_key = await APIKeys.get_active_api_key_for_user(user_id)
        # For local dev mode without API keys, use a placeholder
        if not user_api_key:
            user_api_key = "dev-mode-api-key"

        credentials = {
            "session_id": str(session_uuid),
            "user_api_key": user_api_key,
        }

        await self.pre_configure_mcp_server(sandbox, credentials)
        await self._register_user_mcp_servers(user_id, sandbox)

    async def get_sandbox_by_session_id(self, session_id: uuid.UUID) -> IISandbox | None:
        """Get sandbox status by session ID."""
        session = await Sessions.get_session_by_id(session_id)
        if not session or not str(session.sandbox_id):
            return None

        sandbox = IISandbox(
            str(session.sandbox_id), self.sandbox_server_url, str(session.user_id)
        )

        return sandbox

    async def get_sandbox_status_by_session(self, session_id: uuid.UUID) -> str:
        """Get sandbox status by session ID."""
        session = await Sessions.get_session_by_id(session_id)
        if not session or not str(session.sandbox_id):
            return "not initialized"

        sandbox = IISandbox(
            str(session.sandbox_id), self.sandbox_server_url, str(session.user_id)
        )
        return await sandbox.status

    async def wake_up_sandbox_by_session(self, session_id: uuid.UUID):
        """Wake up a paused sandbox by session ID."""
        session = await Sessions.get_session_by_id(session_id)
        if not session or not str(session.sandbox_id):
            raise Exception(f"Session {session_id} not found or not initialized")

        sandbox = IISandbox(
            str(session.sandbox_id), self.sandbox_server_url, str(session.user_id)
        )
        await sandbox.connect()

    async def cleanup_sandbox_for_session(
        self, session_uuid: uuid.UUID, time_til_clean_up: Optional[int] = None
    ):
        """Schedule a timeout for a session's sandbox."""
        if time_til_clean_up is None:
            time_til_clean_up = self.config.time_til_clean_up
        existing_session = await Sessions.get_session_by_id(session_uuid)
        if not existing_session:
            raise Exception(f"Session {session_uuid} not found")
        if not await Sessions.session_has_sandbox(session_uuid):
            logger.info(f"Session {session_uuid} has no sandbox to clean up")
            return
        sandbox = IISandbox(
            str(existing_session.sandbox_id),
            self.sandbox_server_url,
            str(existing_session.user_id),
        )
        await sandbox.schedule_timeout(time_til_clean_up)

    async def execute_code(
        self,
        session_uuid: uuid.UUID,
        command: str,
        *,
        background: bool = False,
    ) -> str:
        """Run a shell command inside the session's sandbox."""
        sandbox = await self.get_sandbox_by_session(session_uuid)
        return await sandbox.run_cmd(command, background=background)

    async def reset_tool_server(
        self,
        sandbox: IISandbox,
        session_uuid: uuid.UUID | None = None,
        user_id: str | None = None,
    ):
        mcp_port = self.config.mcp_port
        try:
            sandbox_url = await sandbox.expose_port(mcp_port)

            # Build credentials so the MCP server accepts tool registration
            user_api_key = None
            if user_id:
                user_api_key = await APIKeys.get_active_api_key_for_user(user_id)
            if not user_api_key:
                user_api_key = "dev-mode-api-key"

            credential = {
                "session_id": str(session_uuid) if session_uuid else "unknown",
                "user_api_key": user_api_key,
            }

            async with MCPClient(sandbox_url) as client:
                await client.set_credential(credential)
                await client.set_tool_server_url(self.config.tool_server_url)
            return True
        except Exception as e:
            logger.warning("reset_tool_server failed for sandbox %s: %s", sandbox.sandbox_id, e)
            return False

    async def pre_configure_mcp_server(self, sandbox: IISandbox, credential: Dict):
        """Set the tool server url for the sandbox."""
        mcp_port = self.config.mcp_port
        sandbox_url = await sandbox.expose_port(mcp_port)
        async with MCPClient(sandbox_url) as client:
            await client.set_credential(credential)
            await client.set_tool_server_url(self.config.tool_server_url)
            # Ensure that service is available
            await client.ping()
            await client.list_tools()
        return True

    async def _register_user_mcp_servers(
        self, user_id: str, sandbox: IISandbox
    ) -> bool:
        """Register user's MCP servers with the sandbox.

        Returns:
            bool: True if registration succeeded or no servers to register, False on error
        """
        if not user_id or not sandbox.sandbox_id:
            logger.info("No user_id or sandbox available for MCP registration")
            return True

        # Get sandbox URL for MCP registration
        mcp_port = self.config.mcp_port
        sandbox_url = await sandbox.expose_port(mcp_port)

        # Query active MCP settings for user
        async with get_db_session_local() as db_session:
            mcp_settings = await list_mcp_settings(
                db_session=db_session, user_id=user_id, only_active=True
            )
        if not mcp_settings.settings:
            logger.info(f"No active MCP servers to register for user {user_id}")
            return True  # No MCP servers to register

        # Get combined configuration using the new method
        combined_config = mcp_settings.get_combined_active_config()

        # Convert to dict for registration
        config_dict = combined_config.model_dump(exclude_none=True)

        # Register with sandbox using MCPClient
        async with MCPClient(sandbox_url) as client:
            is_codex = any(
                isinstance(metadata, CodexMetadata)
                for metadata in combined_config.metadatas
            )

            for metadata in combined_config.metadatas:
                if isinstance(metadata, CodexMetadata):
                    store_path = f"{config.sandbox_user}/.codex/auth.json"
                    await sandbox.write_file(json.dumps(metadata.auth_json), store_path)
                if isinstance(metadata, ClaudeCodeMetadata):
                    store_path = f"{config.sandbox_user}/.claude/.credentials.json"
                    await sandbox.write_file(json.dumps(metadata.auth_json), store_path)

            if is_codex:
                logger.info("Codex metadata found, ensuring Codex setup in sandbox")
                await client.register_codex()
            else:
                logger.info("No Codex metadata found, skipping Codex setup")

            # Only register if we have servers to register
            if config_dict.get("mcpServers"):
                server_names = list(config_dict["mcpServers"].keys())
                logger.info(
                    f"Registering {len(server_names)} MCP server(s) for user {user_id}: {server_names}"
                )
                await client.register_custom_mcp(config_dict)

        return True
