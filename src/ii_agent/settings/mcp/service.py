"""Service layer for mcp_settings domain - business logic only."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional
import uuid

import httpx
from sqlalchemy.ext.asyncio import AsyncSession


from ii_agent.settings.mcp.models import MCPSetting
from ii_agent.settings.mcp.exceptions import MCPSettingNotFoundError
from ii_agent.settings.mcp.repository import MCPSettingRepository
from ii_agent.core.config.mcp import MCPSettings
from ii_agent.core.config.settings import Settings
from ii_agent.settings.mcp.schemas import (
    CodexMetadata,
    ClaudeCodeMetadata,
    MCPSettingCreate,
    MCPSettingUpdate,
    MCPSettingInfo,
    MCPSettingList,
    MCPServersConfig,
    validate_metadata,
)


class MCPSettingService:
    """Service for managing MCP settings - business logic layer."""

    def __init__(
        self,
        *,
        repo: MCPSettingRepository,
        config: Settings,
    ) -> None:
        self._config = config
        self._repo = repo

    async def create_mcp_settings(
        self, db: AsyncSession, *, mcp_setting_in: MCPSettingCreate, user_id: uuid.UUID
    ) -> MCPSettingInfo:
        """Create new MCP settings for a user."""
        # Deactivate any existing active settings for this user
        active_settings = await self._repo.list_active_by_user(db, user_id)
        for setting in active_settings:
            setting.is_active = False
            setting.updated_at = datetime.now(timezone.utc)
            await self._repo.update(db, setting)

        # Create new settings (always create, never update)
        new_setting = MCPSetting(
            id=str(uuid.uuid4()),
            user_id=user_id,
            mcp_config=mcp_setting_in.mcp_config.model_dump(exclude_none=True),
            mcp_metadata=None
            if not mcp_setting_in.metadata
            else mcp_setting_in.metadata.model_dump(exclude_none=True),
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        created = await self._repo.save(db, new_setting)
        return _to_mcp_setting_info(created)

    async def update_mcp_settings(
        self,
        db: AsyncSession,
        *,
        setting_id: str,
        setting_update: MCPSettingUpdate,
        user_id: uuid.UUID,
    ) -> MCPSettingInfo:
        """Update existing MCP settings.

        Raises:
            MCPSettingNotFoundError: If setting not found or access denied.
        """
        setting = await self._repo.get_by_id_and_user(db, setting_id, user_id)
        if not setting:
            raise MCPSettingNotFoundError(f"MCP setting {setting_id} not found or access denied")

        if setting_update.mcp_config is not None:
            setting.mcp_config = setting_update.mcp_config.model_dump(exclude_none=True)
        if setting_update.metadata is not None:
            setting.mcp_metadata = setting_update.metadata.model_dump(exclude_none=True)
        if setting_update.is_active is not None:
            setting.is_active = setting_update.is_active

        setting.updated_at = datetime.now(timezone.utc)
        updated = await self._repo.update(db, setting)
        return _to_mcp_setting_info(updated)

    async def get_mcp_settings(
        self, db: AsyncSession, *, setting_id: str, user_id: uuid.UUID
    ) -> MCPSettingInfo:
        """Get MCP settings by ID.

        Raises:
            MCPSettingNotFoundError: If setting not found or access denied.
        """
        setting = await self._repo.get_by_id_and_user(db, setting_id, user_id)
        if not setting:
            raise MCPSettingNotFoundError(f"MCP setting {setting_id} not found or access denied")
        return _to_mcp_setting_info(setting)

    async def list_mcp_settings(
        self,
        db: AsyncSession,
        *,
        user_id: uuid.UUID,
        only_active: bool = False,
        no_metadata: bool = False,
    ) -> MCPSettingList:
        """List all MCP settings for a user."""
        settings = await self._repo.list_by_user(
            db, user_id, only_active=only_active, no_metadata=no_metadata
        )
        settings_list = [_to_mcp_setting_info(s) for s in settings]
        return MCPSettingList(settings=settings_list)

    async def delete_mcp_settings(
        self, db: AsyncSession, *, setting_id: str, user_id: uuid.UUID
    ) -> bool:
        """Delete MCP settings by ID."""
        setting = await self._repo.get_by_id_and_user(db, setting_id, user_id)
        if not setting:
            return False

        await self._repo.delete(db, setting)
        return True

    # -- Codex / Claude Code convenience methods ----------------------------

    async def get_codex_setting(
        self, db: AsyncSession, *, user_id: uuid.UUID
    ) -> Optional[MCPSettingInfo]:
        """Return the Codex MCP setting for a user, or None."""
        setting = await self._repo.get_by_user_and_tool_type(db, user_id, "codex")
        if not setting:
            return None
        return _to_mcp_setting_info(setting)

    async def get_claude_code_setting(
        self, db: AsyncSession, *, user_id: uuid.UUID
    ) -> Optional[MCPSettingInfo]:
        """Return the Claude Code MCP setting for a user, or None."""
        setting = await self._repo.get_by_user_and_tool_type(db, user_id, "claude_code")
        if not setting:
            return None
        return _to_mcp_setting_info(setting)

    async def configure_codex(
        self,
        db: AsyncSession,
        *,
        user_id: uuid.UUID,
        auth_json: Optional[Dict[str, Any]],
        apikey: Optional[str],
        model: Optional[str],
        reasoning_effort: Optional[str],
        search: bool,
    ) -> MCPSettingInfo:
        """Build Codex MCP config and create-or-update the setting.

        Raises:
            ValueError: If neither auth_json nor apikey is provided.
        """
        if not auth_json and not apikey:
            from ii_agent.settings.mcp.exceptions import MCPOAuthError as _MCPOAuthError

            raise _MCPOAuthError("Authentication JSON or API Key is required")
        elif not auth_json and apikey:
            auth_json = {"OPENAI_API_KEY": apikey}
        elif auth_json and apikey:
            auth_json["OPENAI_API_KEY"] = apikey

        uvx_args = [
            "--from",
            "git+https://github.com/Intelligent-Internet/codex-as-mcp.git@main",
            "codex-as-mcp",
        ]
        server_args = ["--yolo"]
        if model:
            server_args.append(f"--model={model}")
        if reasoning_effort:
            server_args.append(f"--model_reasoning_effort={reasoning_effort}")
        if search:
            server_args.append("--search")

        mcp_config = MCPServersConfig.model_validate(
            {
                "mcpServers": {
                    "codex-as-mcp": {
                        "command": "uvx",
                        "type": "stdio",
                        "args": uvx_args + server_args,
                    }
                }
            }
        )
        metadata = CodexMetadata(auth_json=auth_json, store_path="")  # pyright: ignore

        return await self._upsert_by_metadata_type(
            db,
            user_id=user_id,
            metadata_cls=CodexMetadata,
            mcp_config=mcp_config,
            metadata=metadata,
        )

    async def configure_claude_code(
        self,
        db: AsyncSession,
        *,
        user_id: uuid.UUID,
        authorization_code: str,
    ) -> MCPSettingInfo:
        """Exchange OAuth code, build Claude Code MCP config and create-or-update.

        Raises:
            ValueError: If the authorization_code format is invalid.
            MCPOAuthError: If the OAuth token exchange fails.
        """
        splits = authorization_code.split("#")
        if len(splits) != 2:
            from ii_agent.settings.mcp.exceptions import MCPOAuthError as _MCPOAuthError

            raise _MCPOAuthError(
                "Invalid authorization code format. Expected format: code#verifier"
            )

        code, verifier = splits
        tokens = await _exchange_code_for_tokens(code, verifier, self._config.mcp)

        auth_json = {
            "claudeAiOauth": {
                "accessToken": tokens["access_token"],
                "refreshToken": tokens["refresh_token"],
                "expiresAt": int(time.time() * 1000) + tokens["expires_in"] * 1000,
                "scopes": ["user:inference", "user:profile"],
            }
        }
        metadata = ClaudeCodeMetadata(auth_json=auth_json, store_path="")  # pyright: ignore

        mcp_config = MCPServersConfig.model_validate(
            {
                "mcpServers": {
                    "claude-code-mcp": {
                        "command": "npx",
                        "args": ["-y", "@steipete/claude-code-mcp@latest"],
                    },
                }
            }
        )

        return await self._upsert_by_metadata_type(
            db,
            user_id=user_id,
            metadata_cls=ClaudeCodeMetadata,
            mcp_config=mcp_config,
            metadata=metadata,
        )

    # -- Internal helpers ---------------------------------------------------

    async def _upsert_by_metadata_type(
        self,
        db: AsyncSession,
        *,
        user_id: uuid.UUID,
        metadata_cls: type,
        mcp_config: MCPServersConfig,
        metadata: CodexMetadata | ClaudeCodeMetadata,
    ) -> MCPSettingInfo:
        """Find existing setting by metadata type and update, or create new."""
        existing = await self._repo.get_by_user_and_tool_type(db, user_id, metadata.tool_type)

        if existing:
            return await self.update_mcp_settings(
                db,
                setting_id=existing.id,
                setting_update=MCPSettingUpdate(
                    mcp_config=mcp_config, metadata=metadata, is_active=True
                ),
                user_id=user_id,
            )

        return await self.create_mcp_settings(
            db,
            mcp_setting_in=MCPSettingCreate(
                mcp_config=mcp_config,
                metadata=metadata,
            ),
            user_id=user_id,
        )


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

from ii_agent.settings.mcp.exceptions import MCPOAuthError  # noqa: E402


async def _exchange_code_for_tokens(code: str, verifier: str, mcp_config: MCPSettings) -> dict:
    """Exchange authorization code for access and refresh tokens.

    Raises:
        MCPOAuthError: If the token exchange request fails.
    """
    async with httpx.AsyncClient() as client:
        response = await client.post(
            mcp_config.anthropic_oauth_token_url,
            headers={"Content-Type": "application/json"},
            json={
                "code": code,
                "state": verifier,
                "grant_type": "authorization_code",
                "client_id": mcp_config.anthropic_oauth_client_id,
                "redirect_uri": mcp_config.anthropic_oauth_redirect_uri,
                "code_verifier": verifier,
            },
        )

    if not response.is_success:
        raise MCPOAuthError(f"Failed to exchange authorization code for tokens: {response.text}")

    data = response.json()
    return {
        "access_token": data["access_token"],
        "refresh_token": data["refresh_token"],
        "expires_in": data["expires_in"],
    }


def _to_mcp_setting_info(setting: MCPSetting) -> MCPSettingInfo:
    """Convert database model to Pydantic model."""
    mcp_config = setting.mcp_config or {}
    if isinstance(mcp_config, dict):
        mcp_config = MCPServersConfig(**mcp_config)

    metadata = None
    if setting.mcp_metadata is not None and isinstance(setting.mcp_metadata, dict):
        try:
            metadata = validate_metadata(setting.mcp_metadata)
        except (ValueError, TypeError):
            pass

    return MCPSettingInfo(
        id=setting.id,
        mcp_config=mcp_config,
        is_active=setting.is_active,
        metadata=metadata,
        created_at=setting.created_at.isoformat() if setting.created_at else "",
        updated_at=setting.updated_at.isoformat() if setting.updated_at else None,
    )
