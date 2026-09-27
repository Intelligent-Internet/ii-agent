"""
Main application settings - consolidates all configuration modules.

This module brings together all configuration subsections and provides:
- Unified Settings class with nested configuration
- Cached settings singleton via get_settings()
- Global config instance
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Literal, Optional

from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from ii_agent.core.config.database import DatabaseSettings
from ii_agent.core.config.redis import RedisSettings
from ii_agent.core.config.sandbox import SandboxSettings
from ii_agent.core.config.storage import StorageSettings
from ii_agent.core.config.oauth import OAuth2Settings
from ii_agent.core.config.mcp import MCPSettings
from ii_agent.core.config.stripe import StripeSettings
from ii_agent.core.config.credits import CreditsSettings
from ii_agent.core.config.agent import AgentSettings
from ii_agent.core.config.mobile import MobileSettings
from ii_agent.core.config.enhance_prompt_config import EnhancePromptConfig
from ii_agent.core.config.nano_banana import NanoBananaConfig
from ii_agent.core.config.session_title import SessionTitleConfig
from ii_agent.core.config.sessions import SessionsSettings

if TYPE_CHECKING:
    from ii_agent.core.storage.providers.base import StorageProvider

logger = logging.getLogger(__name__)

# Constants
II_AGENT_DIR = Path(__file__).parent.parent.parent

# Type aliases
Environment = Literal["dev", "staging", "production", "local"]


class DevUserConfig(BaseModel):
    """One named local-mode dev user.

    Used by ``POST /auth/dev/login`` to support multiple distinct local users
    (e.g. household members) without OAuth. Identity is selected by the human
    (username + PIN), not inferred from client IP.
    """

    username: str = Field(
        description="Short identifier; becomes part of email dev+<username>@localhost",
    )
    pin: str = Field(
        description="Shared PIN entered at login. Stored as plain string in env.",
    )
    display_name: Optional[str] = Field(
        default=None,
        description="Human-readable name shown in the chooser UI.",
    )

    @field_validator("username")
    @classmethod
    def _validate_username(cls, v: str) -> str:
        v = v.strip().lower()
        if not v:
            raise ValueError("dev user username must be non-empty")
        # Restrict to characters safe inside an email local-part and a URL.
        if not all(c.isalnum() or c in "-_." for c in v):
            raise ValueError("dev user username may only contain alphanumerics, '-', '_', '.'")
        return v

    @field_validator("pin")
    @classmethod
    def _validate_pin(cls, v: str) -> str:
        v = str(v).strip()
        if len(v) < 4:
            raise ValueError("dev user pin must be at least 4 characters")
        return v


class Settings(BaseSettings):
    """Main application settings.

    This consolidates all configuration from environment variables and .env file.
    All subsections are nested and can use their own env_prefix.

    Environment variables (top-level, no prefix):
        ENVIRONMENT: Application environment (dev, staging, production)
        II_FRONTEND_URL: Frontend URL for OAuth redirects
        WORKSPACE_PATH: Workspace path in sandbox
        WORKSPACE_UPLOAD_SUBPATH: Upload subpath in workspace
        USE_CONTAINER_WORKSPACE: Use container workspace
        DOCKER_CONTAINER_ID: Docker container ID
        VSCODE_PORT: VS Code server port
        CODEX_PORT: Codex server port
        TOOL_SERVER_URL: Tool server URL
        MINIMIZE_STDOUT_LOGS: Minimize stdout logs
        TIME_TIL_CLEAN_UP: Time until sandbox cleanup (seconds)

    Nested sections use their own prefixes (DB_, REDIS_, SANDBOX_, etc.)
    See individual settings classes for their configuration options.

    Example .env:
        ENVIRONMENT=production
        II_FRONTEND_URL=https://agent.ii.inc
        DATABASE_URL=postgresql+asyncpg://user:pass@localhost/dbname
        REDIS_SESSION_URL=redis://localhost:6379/0
        REDIS_SESSION_ENABLED=true
        SANDBOX_PROVIDER=e2b
        SANDBOX_E2B_API_KEY=your-api-key
        STORAGE_PROVIDER=gcs
        STORAGE_FILE_UPLOAD_BUCKET_NAME=my-bucket
        MOBILE_APPLE_WIDGET_KEY=83545bf919730e51dbfba24e7e8a78d2
        STRIPE_SECRET_KEY=sk_test_...
        GOOGLE_CLIENT_ID=your-client-id
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_nested_delimiter="__",
        nested_model_default_partial_update=True,
    )

    # ========== Top-level Configuration ==========

    # Environment
    environment: Environment = Field(
        default="dev",
        description="Application environment (dev, staging, production)",
    )

    # Frontend URL
    ii_frontend_url: str = Field(
        default="https://agent.ii.inc",
        description="Frontend URL for OAuth redirects and MCP consent page",
    )

    # Local-mode dev users (multi-tenant dev login)
    dev_users: list[DevUserConfig] = Field(
        default_factory=list,
        description=(
            "Named local-mode dev users for POST /auth/dev/login. "
            "Set via DEV_USERS env var as a JSON list, e.g. "
            'DEV_USERS=\'[{"username":"alice","pin":"4729","display_name":"Alice"}]\'. '
            "Only honoured when SANDBOX_LOCAL_MODE=true. "
            "Empty list disables dev login entirely."
        ),
    )

    # ========== Nested Configuration Sections ==========

    database: DatabaseSettings = Field(
        default_factory=DatabaseSettings,
        description="Database configuration (PostgreSQL)",
    )

    redis: RedisSettings = Field(
        default_factory=RedisSettings,
        description="Redis configuration for caching and sessions",
    )

    sandbox: SandboxSettings = Field(
        default_factory=SandboxSettings,
        description="Sandbox environment configuration",
    )

    storage: StorageSettings = Field(
        default_factory=StorageSettings,
        description="File storage configuration",
    )

    oauth: OAuth2Settings = Field(
        default_factory=OAuth2Settings,
        description="OAuth 2.0 provider configurations",
    )

    mcp: MCPSettings = Field(
        default_factory=MCPSettings,
        description="MCP (Model Context Protocol) configuration",
    )

    stripe: StripeSettings = Field(
        default_factory=StripeSettings,
        description="Stripe billing configuration",
    )

    credits: CreditsSettings = Field(
        default_factory=CreditsSettings,
        description="Credits and subscription configuration",
    )

    agent: AgentSettings = Field(
        default_factory=AgentSettings,
        description="Agent execution configuration",
    )

    mobile: MobileSettings = Field(
        default_factory=MobileSettings,
        description="Mobile app and Apple integration configuration",
    )

    enhance_prompt: EnhancePromptConfig = Field(
        default_factory=EnhancePromptConfig,
        description="Enhance prompt configuration (OpenAI-based prompt enhancement)",
    )

    nano_banana: NanoBananaConfig = Field(
        default_factory=NanoBananaConfig,
        description="Nano Banana slide detection LLM configuration",
    )

    session_title: SessionTitleConfig = Field(
        default_factory=SessionTitleConfig,
        description="LLM-generated session title configuration (OpenAI-based)",
    )

    sessions: SessionsSettings = Field(
        default_factory=SessionsSettings,
        description="Session purge subsystem (§4) — three-phase purge driver and storage reaper.",
    )

    # ========== Workspace Configuration ==========

    workspace_path: str = Field(
        default="/workspace",
        description="Workspace path in sandbox environment",
    )

    workspace_upload_subpath: str = Field(
        default="uploads",
        description="Upload subdirectory within workspace",
    )

    docker_container_id: Optional[str] = Field(
        default=None,
        description="Docker container ID for workspace",
    )

    # ========== Server Ports ==========

    vscode_port: int = Field(
        default=9000,
        description="VS Code server port",
        ge=1,
        le=65535,
    )

    codex_port: int = Field(
        default=1324,
        description="Codex server port",
        ge=1,
        le=65535,
    )

    tool_server_url: str = Field(
        default="http://localhost:1236",
        description="Tool server URL for external tool execution",
    )

    # ========== Composio Configuration ==========

    composio_api_key: Optional[str] = Field(
        default=None,
        description="Composio API key for toolkit integrations",
    )

    composio_encryption_key: Optional[str] = Field(
        default=None,
        description="Fernet encryption key for MCP URLs (generate with: Fernet.generate_key())",
    )

    composio_webhook_secret: Optional[str] = Field(
        default=None,
        description="Webhook secret for Composio event verification",
    )

    composio_redirect_uri: str = Field(
        default="http://localhost:1420/auth/oauth/composio/callback",
        description="OAuth Redirect URI for Composio toolkit integration",
    )

    # ========== LLM Configuration ==========

    researcher_agent_config: Optional[Any] = Field(
        default=None,
        description="Configuration for the researcher agent pipeline",
    )

    # ========== Logging Configuration ==========

    minimize_stdout_logs: bool = Field(
        default=False,
        description="Minimize stdout logging output",
    )

    log_level: str = Field(
        default="INFO",
        description="Log level for the application (DEBUG, INFO, WARNING, ERROR, CRITICAL)",
    )

    # ========== JWT Configuration ==========

    jwt_secret_key: str = Field(
        default="your-secret-key-change-in-production",
        description="Secret key for JWT token signing",
    )

    access_token_expire_minutes: int = Field(
        default=15,
        description="Access token expiration time in minutes",
        gt=0,
    )

    refresh_token_expire_days: int = Field(
        default=7,
        description="Refresh token expiration time in days",
        gt=0,
    )

    model_configs: Optional[list[Dict[str, Any]]] = Field(
        default=None,
        description=(
            "List of LLM model configurations for system seeding. "
            "Each entry is validated as ModelConfigEntry (model_id, provider, params, ...). "
            "Set via MODEL_CONFIGS env var (JSON array) or MODEL_CONFIGS_FILE (YAML file)."
        ),
    )

    @field_validator("model_configs", mode="before")
    @classmethod
    def parse_model_configs(cls, v: Any) -> Any:
        """Parse JSON string or validate list of model config entries."""
        if not v:
            return v
        # If it's a JSON string (from env var), parse it
        if isinstance(v, str):
            import json

            v = json.loads(v)
        if not isinstance(v, list):
            return v
        # Validate each entry through ModelConfigEntry
        from ii_agent.settings.llm.schemas import ModelConfigEntry

        return [
            ModelConfigEntry.model_validate(entry).model_dump()
            if isinstance(entry, dict)
            else entry
            for entry in v
        ]

    # ========== GCP Secret Manager ==========

    gcp_project_id: Optional[str] = Field(
        default=None,
        description="GCP project ID for Secret Manager integration",
    )

    gcp_secret_prefix: str = Field(
        default="ii-agent",
        description="Prefix for secret names in GCP Secret Manager",
    )

    # ========== Validators ==========

    @field_validator("composio_api_key", "composio_encryption_key")
    @classmethod
    def validate_composio_config(cls, v, info):
        if not v and info.field_name == "composio_api_key":
            logger.warning("COMPOSIO_API_KEY is not set - Composio features will be unavailable")
        return v

    # ========== Computed Properties ==========

    @property
    def storage_client(self) -> StorageProvider:
        """Get storage client singleton."""
        # Use lazy import to avoid circular import
        from ii_agent.core.storage.client import get_storage

        return get_storage()

    @property
    def sync_database_url(self) -> str:
        """Return the synchronous database URL."""
        db_url = self.database.url or ""
        if "+asyncpg" in db_url:
            return db_url.replace("+asyncpg", "")
        elif "+aiosqlite" in db_url:
            return db_url.replace("+aiosqlite", "")
        return db_url

    @property
    def is_redis_ssl(self) -> bool:
        """Check if the Redis connection uses SSL."""
        return self.redis.session_url.startswith("rediss://")

    @property
    def logs_path(self) -> str:
        return os.path.join(self.storage.file_store_path, "logs")

    @property
    def workspace_upload_path(self) -> str:
        return os.path.join(self.workspace_path, self.workspace_upload_subpath)

    @property
    def workspace_root(self) -> str:
        """Resolve the absolute filesystem path used for local workspace operations."""
        workspace = Path(os.path.expanduser(self.storage.file_store_path)) / "workspace"
        try:
            workspace.mkdir(parents=True, exist_ok=True)
            return str(workspace.resolve())
        except (PermissionError, OSError) as exc:
            raise PermissionError(
                f"Unable to initialize workspace directory at {workspace}: {exc}"
            ) from exc

    @property
    def ii_auth_url(self) -> str:
        return f"{self.oauth.ii_auth_base.rstrip('/')}/oauth2/auth"

    @property
    def ii_token_url(self) -> str:
        return f"{self.oauth.ii_auth_base.rstrip('/')}/oauth2/token"

    @property
    def ii_revoke_url(self) -> str:
        return f"{self.oauth.ii_auth_base.rstrip('/')}/oauth2/revoke"

    @property
    def ii_issuer(self) -> str:
        return self.oauth.ii_auth_base.rstrip("/")

    # MCP OAuth computed URLs (use ii_auth_base for MCP external OAuth too)
    @property
    def mcp_ii_auth_url(self) -> str:
        return self.ii_auth_url

    @property
    def mcp_ii_token_url(self) -> str:
        return self.ii_token_url


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance (singleton pattern).

    This ensures only one Settings instance is created and reused.

    Returns:
        Settings: Cached settings instance
    """
    return Settings()
