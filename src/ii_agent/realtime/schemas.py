"""Pydantic V2 schemas for the Realtime (WebSocket) domain.

Each command has its own content type with a ``command`` literal discriminator,
enabling native Pydantic discriminated unions via ``Field(discriminator="command")``.
"""

from __future__ import annotations

import uuid
from enum import StrEnum
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ii_agent.agents.types import AgentType


# ---------------------------------------------------------------------------
# Command type enum
# ---------------------------------------------------------------------------


class CommandType(StrEnum):
    """All valid ``chat_message`` command types."""

    INIT_AGENT = "init_agent"
    QUERY = "query"
    PLAN = "plan"
    WORKSPACE_INFO = "workspace_info"
    AWAKE_SANDBOX = "awake_sandbox"
    SANDBOX_STATUS = "sandbox_status"
    PING = "ping"
    CANCEL = "cancel"
    CONTINUE_RUN = "continue_run"
    ENHANCE_PROMPT = "enhance_prompt"
    PUBLISH_PROJECT = "publish"
    PUBLISH_CLOUD_RUN = "publish_cloud_run"
    SAVE_ENV = "save_env"
    START_FORK = "start_fork"
    SUBMIT_TESTFLIGHT = "submit_testflight"

    # Design mode
    DESIGN_GET_STATE = "design_get_state"
    DESIGN_SAVE_STATE = "design_save_state"
    DESIGN_SYNC_STATE = "design_sync_state"
    SLIDE_DECK_SYNC_STATE = "slide_deck_sync_state"

    # File explorer
    FILE_TREE = "file_tree"
    FILE_CONTENT = "file_content"

    # Apple authentication flow
    APPLE_AUTH_LOGIN = "apple_auth_login"
    APPLE_AUTH_2FA = "apple_auth_2fa"
    APPLE_AUTH_SELECT_TEAM = "apple_auth_select_team"
    APPLE_APP_SETUP = "apple_app_setup"
    APPLE_LIST_APPS = "apple_list_apps"
    APPLE_CHECK_AUTH = "apple_check_auth"
    SAVE_EXPO_TOKEN = "save_expo_token"

    # Browser extension (ii-browser)
    BROWSER_EXTENSION_QUERY = "browser_extension_query"
    BROWSER_EXTENSION_CONTINUE_RUN = "browser_extension_continue_run"

# ---------------------------------------------------------------------------
# Base empty content (shared fields for no-payload commands)
# ---------------------------------------------------------------------------


class EmptyContent(BaseModel):
    """Base content model for handlers that require no payload."""

    model_config = ConfigDict(extra="allow")


# ---------------------------------------------------------------------------
# Per-command EmptyContent variants (each has a unique `command` literal)
# ---------------------------------------------------------------------------


class PingContent(EmptyContent):
    command: Literal[CommandType.PING] = CommandType.PING


class CancelContent(EmptyContent):
    command: Literal[CommandType.CANCEL] = CommandType.CANCEL


class SandboxStatusContent(EmptyContent):
    command: Literal[CommandType.SANDBOX_STATUS] = CommandType.SANDBOX_STATUS


class AwakeSandboxContent(EmptyContent):
    command: Literal[CommandType.AWAKE_SANDBOX] = CommandType.AWAKE_SANDBOX


class WorkspaceInfoContent(EmptyContent):
    command: Literal[CommandType.WORKSPACE_INFO] = CommandType.WORKSPACE_INFO


class AppleListAppsContent(EmptyContent):
    command: Literal[CommandType.APPLE_LIST_APPS] = CommandType.APPLE_LIST_APPS


class AppleCheckAuthContent(EmptyContent):
    command: Literal[CommandType.APPLE_CHECK_AUTH] = CommandType.APPLE_CHECK_AUTH


class FileTreeContent(EmptyContent):
    """Payload for the ``file_tree`` command (no extra fields needed)."""

    command: Literal[CommandType.FILE_TREE] = CommandType.FILE_TREE


class FileContentContent(BaseModel):
    """Payload for the ``file_content`` command."""

    command: Literal[CommandType.FILE_CONTENT] = CommandType.FILE_CONTENT
    path: str = ""


# ---------------------------------------------------------------------------
# Internal query models (not part of the discriminated union)
# ---------------------------------------------------------------------------


class QueryContentInternal(BaseModel):
    """Internal representation of a query after file pre-processing."""

    text: str = ""
    resume: bool = False
    file_upload_paths: list[str] = []
    images_data: list[dict[str, str]] = []


class QueryToolResultInternal(BaseModel):
    """Internal representation of a tool result forwarded by the client."""

    tool_call_id: str
    tool_name: str
    tool_input: dict[str, Any] = {}
    llm_content: Any = None
    user_display_content: Any = None
    is_error: bool = False
    is_interrupted: bool = False


# ---------------------------------------------------------------------------
# Query / Plan content (shared base, separate discriminators)
# ---------------------------------------------------------------------------


class BaseCommandQuery(BaseModel):
    """Shared fields for query and plan commands."""

    # Init agent parameters
    model_id: str | None = None
    provider: str | None = None
    source: Literal["user", "system"] | None = "system"
    agent_type: AgentType = AgentType.GENERAL
    tool_args: dict[str, Any] = {}
    thinking_tokens: int = 0
    metadata: dict[str, Any] | None = None

    # Query parameters
    text: str = ""
    resume: bool = False
    files: list[str] = []

    # Connector context
    github_repository: dict[str, str] | None = None

    # Plan mode parameters
    build_mode: (
        Literal["build", "plan", "design", "help", "modify_plan", "modify_plan_suggestions"] | None
    ) = "build"
    milestone_ids: list[str] | None = None
    plan_context: dict[str, Any] | None = None

    model_config = ConfigDict(extra="allow", validate_assignment=True)


class QueryCommandContent(BaseCommandQuery):
    """Payload for the ``query`` command."""

    command: Literal[CommandType.QUERY] = CommandType.QUERY


class PlanCommandContent(BaseCommandQuery):
    """Payload for the ``plan`` command."""

    command: Literal[CommandType.PLAN] = CommandType.PLAN


# ---------------------------------------------------------------------------
# Other command content models
# ---------------------------------------------------------------------------


class InitAgentContent(BaseModel):
    """Payload for agent initialization."""

    command: Literal[CommandType.INIT_AGENT] = CommandType.INIT_AGENT
    model_id: str | None = None
    tool_args: dict[str, Any] = {}
    source: Literal["user", "system"] | None = None
    thinking_tokens: int = 0
    agent_type: AgentType = AgentType.GENERAL
    metadata: dict[str, Any] | None = None


class EnhancePromptContent(BaseModel):
    """Payload for prompt enhancement."""

    command: Literal[CommandType.ENHANCE_PROMPT] = CommandType.ENHANCE_PROMPT
    text: str = ""
    files: list[str] = []


class EditQueryContent(BaseModel):
    """Payload for edit-query commands."""

    text: str = ""
    resume: bool = False
    files: list[str] = []


class ReviewResultContent(BaseModel):
    """Payload for review-result commands."""

    user_input: str = ""


class StartForkContent(BaseModel):
    """Payload for starting a forked session."""

    command: Literal[CommandType.START_FORK] = CommandType.START_FORK
    model_id: str | None = None
    source: Literal["user", "system"] | None = "system"
    agent_type: str | None = None
    tool_args: dict[str, Any] = {}
    thinking_tokens: int = 0
    metadata: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Continue run content
# ---------------------------------------------------------------------------


class ContinueRunContent(BaseModel):
    """Payload for continue_run command (Human-in-the-Loop)."""

    command: Literal[CommandType.CONTINUE_RUN] = CommandType.CONTINUE_RUN
    run_id: str
    confirmed: bool
    user_input: dict[str, str] = {}


# ---------------------------------------------------------------------------
# Publish / deploy content models
# ---------------------------------------------------------------------------


class PublishProjectContent(BaseModel):
    """Payload for publishing a project to Vercel."""

    command: Literal[CommandType.PUBLISH_PROJECT] = CommandType.PUBLISH_PROJECT
    project_path: str | None = None
    project_name: str | None = None
    vercel_api_key: str | None = None
    credentials: dict[str, Any] | None = None
    token: str | None = None

    model_config = ConfigDict(extra="allow")


class CloudRunPublishContent(BaseModel):
    """Payload for publishing a project to Google Cloud Run."""

    command: Literal[CommandType.PUBLISH_CLOUD_RUN] = CommandType.PUBLISH_CLOUD_RUN
    project_path: str | None = None
    project_name: str | None = None
    env_vars: dict[str, str] | None = None
    credentials: dict[str, Any] | None = None

    model_config = ConfigDict(extra="allow")


# ---------------------------------------------------------------------------
# Save env content
# ---------------------------------------------------------------------------


class SaveEnvContent(BaseModel):
    """Payload for saving environment variables and resuming agent loop."""

    command: Literal[CommandType.SAVE_ENV] = CommandType.SAVE_ENV
    tool_call_id: str
    tool_name: str
    secrets: list[dict[str, Any]] | dict[str, str] = []
    project_directory: str | None = None
    tool_args: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Mobile / Apple content models
# ---------------------------------------------------------------------------


class SubmitTestflightContent(BaseModel):
    """Payload for TestFlight build and submission."""

    command: Literal[CommandType.SUBMIT_TESTFLIGHT] = CommandType.SUBMIT_TESTFLIGHT
    expo_token: str = ""
    bundle_identifier: str = ""
    asc_app_id: str = ""
    app_specific_password: str = ""

    model_config = ConfigDict(extra="allow")


class AppleAuthLoginContent(BaseModel):
    """Payload for Apple ID login."""

    command: Literal[CommandType.APPLE_AUTH_LOGIN] = CommandType.APPLE_AUTH_LOGIN
    apple_id: str
    password: str


class AppleAuth2FAContent(BaseModel):
    """Payload for Apple 2FA verification."""

    command: Literal[CommandType.APPLE_AUTH_2FA] = CommandType.APPLE_AUTH_2FA
    code: str

    @field_validator("code")
    @classmethod
    def validate_code(cls, v: str) -> str:
        v = v.strip()
        if not v or len(v) != 6 or not v.isdigit():
            raise ValueError("Must be a 6-digit code")
        return v


class AppleAuthSelectTeamContent(BaseModel):
    """Payload for Apple team selection."""

    command: Literal[CommandType.APPLE_AUTH_SELECT_TEAM] = CommandType.APPLE_AUTH_SELECT_TEAM
    team_id: str


class AppleAppSetupContent(BaseModel):
    """Payload for Apple app setup (bundle ID + app name)."""

    command: Literal[CommandType.APPLE_APP_SETUP] = CommandType.APPLE_APP_SETUP
    bundle_identifier: str
    app_name: str
    password: str | None = None


class SaveExpoTokenContent(BaseModel):
    """Payload for saving Expo access token."""

    command: Literal[CommandType.SAVE_EXPO_TOKEN] = CommandType.SAVE_EXPO_TOKEN
    expo_token: str

    @field_validator("expo_token")
    @classmethod
    def validate_expo_token(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Expo token is required")
        return v


# ---------------------------------------------------------------------------
# Design mode content models
# ---------------------------------------------------------------------------


class DesignGetStateContent(BaseModel):
    """Payload for loading persisted design-mode state."""

    command: Literal[CommandType.DESIGN_GET_STATE] = CommandType.DESIGN_GET_STATE
    session_id: uuid.UUID
    request_id: str | None = None

    model_config = ConfigDict(extra="allow")


class DesignSaveStateContent(BaseModel):
    """Payload for saving design-mode state (pending changes)."""

    command: Literal[CommandType.DESIGN_SAVE_STATE] = CommandType.DESIGN_SAVE_STATE
    session_id: uuid.UUID
    changes: list[Any] = []
    redo_changes: list[Any] | None = None
    request_id: str | None = None

    model_config = ConfigDict(extra="allow")


class DesignSyncStateContent(BaseModel):
    """Payload for syncing persisted design-mode changes to source."""

    command: Literal[CommandType.DESIGN_SYNC_STATE] = CommandType.DESIGN_SYNC_STATE
    session_id: uuid.UUID
    request_id: str | None = None

    model_config = ConfigDict(extra="allow")


class SlideDeckSyncStateContent(BaseModel):
    """Payload for syncing persisted slide design-mode changes."""

    command: Literal[CommandType.SLIDE_DECK_SYNC_STATE] = CommandType.SLIDE_DECK_SYNC_STATE
    session_id: uuid.UUID
    presentation_name: str

    model_config = ConfigDict(extra="allow")


# ---------------------------------------------------------------------------
# Browser-extension (ii-browser) content models
# ---------------------------------------------------------------------------


class BrowserExtensionCommandContent(BaseCommandQuery):
    """Payload for ``browser_extension_query``."""

    command: Literal[CommandType.BROWSER_EXTENSION_QUERY] = (
        CommandType.BROWSER_EXTENSION_QUERY
    )
    system_prompt: str | None = None
    requested_capabilities: dict[str, Any] | None = None


class BrowserExtensionContinueRunContent(ContinueRunContent):
    """Payload for ``browser_extension_continue_run``."""

    command: Literal[CommandType.BROWSER_EXTENSION_CONTINUE_RUN] = (
        CommandType.BROWSER_EXTENSION_CONTINUE_RUN
    )
    run_id: str
    confirmed: bool
    user_input: dict[str, str] = {}
    external_tool_results: list[dict[str, Any]] | None = None


# ---------------------------------------------------------------------------
# Discriminated union of all command content types
# ---------------------------------------------------------------------------

CommandContent = Annotated[
    Union[
        QueryCommandContent,
        PlanCommandContent,
        InitAgentContent,
        EnhancePromptContent,
        StartForkContent,
        ContinueRunContent,
        BrowserExtensionCommandContent,
        BrowserExtensionContinueRunContent,
        PublishProjectContent,
        CloudRunPublishContent,
        SaveEnvContent,
        SubmitTestflightContent,
        AppleAuthLoginContent,
        AppleAuth2FAContent,
        AppleAuthSelectTeamContent,
        AppleAppSetupContent,
        AppleListAppsContent,
        AppleCheckAuthContent,
        SaveExpoTokenContent,
        PingContent,
        CancelContent,
        SandboxStatusContent,
        AwakeSandboxContent,
        WorkspaceInfoContent,
        FileTreeContent,
        FileContentContent,
        DesignGetStateContent,
        DesignSaveStateContent,
        DesignSyncStateContent,
        SlideDeckSyncStateContent,
    ],
    Field(discriminator="command"),
]


# ---------------------------------------------------------------------------
# Inbound chat_message envelope
# ---------------------------------------------------------------------------


class ChatMessageRequest(BaseModel):
    """Envelope for every ``chat_message`` Socket.IO event.

    FE sends ``command`` inside ``content`` — Pydantic's native discriminated
    union on ``content.command`` resolves the correct content type automatically.
    No model_validator needed.
    """

    model_config = ConfigDict(populate_by_name=True)

    session_uuid: uuid.UUID
    content: CommandContent


# ---------------------------------------------------------------------------
# Legacy alias
# ---------------------------------------------------------------------------


class WebSocketMessage(BaseModel):
    """Base model for WebSocket messages."""

    type: str
    content: dict[str, Any] = {}
