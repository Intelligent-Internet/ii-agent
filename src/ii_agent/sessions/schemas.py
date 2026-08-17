"""Pydantic schemas (DTOs) for sessions domain."""

from enum import StrEnum
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, Dict, Any, List, Literal

from ii_agent.sessions.types import AppKind, SessionState
from ii_agent.settings.llm.schemas import ModelConfig


class SessionCreate(BaseModel):
    """Model for creating a new session."""

    name: Optional[str] = None
    settings: Optional[Dict[str, Any]] = None
    sandbox_template: Optional[str] = "base"


class SessionUpdate(BaseModel):
    """Model for updating a session."""

    name: Optional[str] = None
    status: Optional[SessionState] = None
    settings: Optional[Dict[str, Any]] = None
    is_public: Optional[bool] = None


class SessionInfo(BaseModel):
    """Model for session information."""

    id: UUID
    user_id: UUID
    api_version: Optional[str] = None
    name: Optional[str] = None
    status: SessionState
    workspace_dir: str
    is_public: bool
    public_url: Optional[str] = None
    token_usage: Optional[Dict[str, Any]] = None
    settings: Optional[Dict[str, Any]] = None
    project_id: Optional[UUID] = None
    created_at: str
    updated_at: Optional[str] = None
    last_message_at: Optional[str] = None
    # Session rows still store non-agent values such as "chat" plus legacy values
    # from older data migrations, so this DTO must remain string-based.
    agent_type: Optional[str] = None
    app_kind: AppKind = AppKind.AGENT
    title_pending: bool = False
    model_setting_id: Optional[UUID] = None
    session_metadata: Optional[Dict[str, Any]] = None
    delete_after: Optional[str] = None


class ValidatedSessionResult(BaseModel):
    """Result of session validation before an agent run."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    is_valid: bool
    session_info: Optional[SessionInfo] = None
    llm_config: Optional[ModelConfig] = None
    error_code: Optional[str] = None


class SessionResponse(BaseModel):
    """Model for session list response."""

    sessions: List[SessionInfo]
    total: int
    page: int
    per_page: int


class SessionStats(BaseModel):
    """Model for session statistics."""

    total_sessions: int
    active_sessions: int
    paused_sessions: int
    sessions_today: int
    sessions_this_week: int
    sessions_this_month: int
    total_messages: int
    average_session_duration: Optional[float] = None


class SessionPlan(BaseModel):
    """Model for session execution plan."""

    id: UUID
    title: str
    description: str
    steps: List[Dict[str, Any]]
    status: str = "pending"  # pending, running, completed, failed
    created_at: str
    updated_at: Optional[str] = None


class SessionFile(BaseModel):
    """Model for session file."""

    id: UUID
    name: str
    size: int
    content_type: str
    url: str


class SessionMilestoneUpdate(BaseModel):
    """Model for updating milestones in a session plan."""

    id: UUID
    content: str
    status: Literal["pending", "in_progress", "completed"] = "pending"
    details: Optional[str] = None
    dependencies: Optional[List[str]] = None


class SessionPlanUpdate(BaseModel):
    """Model for updating a session plan."""

    summary: str = ""
    milestones: List[SessionMilestoneUpdate] = []


# ==================== Bulk Delete ====================


class BulkDeleteRequest(BaseModel):
    """Request for bulk deleting sessions."""

    session_ids: List[UUID] = Field(..., min_length=1, max_length=50)


class BulkDeleteResponse(BaseModel):
    """Response for bulk delete."""

    deleted_ids: List[UUID]
    failed_ids: List[UUID]


class ScheduleDeleteRequest(BaseModel):
    """Request to schedule a session for timed deletion.

    Provide either ``delete_after_seconds`` (relative delay from now) or
    ``delete_at`` (absolute UTC timestamp).  If both are given,
    ``delete_after_seconds`` takes precedence.
    """

    delete_after_seconds: Optional[int] = Field(
        None,
        gt=0,
        description="Seconds from now until the session should be deleted",
    )
    delete_at: Optional[str] = Field(
        None,
        description="ISO-8601 UTC timestamp at which the session should be deleted",
    )


# ==================== Fork ====================


class ForkType(StrEnum):
    """Fork type - defines source → target transformation."""

    RESEARCH_TO_WEBSITE = "research_to_website"


class SandboxMode(StrEnum):
    """How to handle sandbox for forked session."""

    SHARE = "share"
    NEW = "new"


class ForkContext(BaseModel):
    """Context from parent session (from send_user_files tool output)."""

    attachments: List[str] = Field(..., min_length=1)
    additional_instruction: Optional[str] = None


class ForkSessionRequest(BaseModel):
    """Request for POST /sessions/{session_id}/fork."""

    fork_type: ForkType
    sandbox_mode: SandboxMode = SandboxMode.SHARE
    context: ForkContext
    model_setting_id: Optional[UUID] = None


class ForkSessionResponse(BaseModel):
    """Response for fork endpoint."""

    session_id: UUID
    parent_session_id: UUID
    name: str
    agent_type: str
    sandbox_mode: SandboxMode
    model_setting_id: Optional[UUID] = None


# ==================== Fork Validation ====================

FORK_TYPE_TARGET_AGENT: Dict[ForkType, str] = {
    ForkType.RESEARCH_TO_WEBSITE: "research_to_website",
}

FORK_TYPE_VALID_SOURCES: Dict[ForkType, List[str]] = {
    ForkType.RESEARCH_TO_WEBSITE: ["deep_research", "fast_research"],
}


def get_target_agent_type(fork_type: ForkType) -> str:
    """Get the target agent type for a fork type."""
    return FORK_TYPE_TARGET_AGENT[fork_type]


def validate_fork_source(fork_type: ForkType, source_agent_type: Optional[str]) -> bool:
    """Validate that fork_type is valid for the source session's agent_type."""
    if source_agent_type is None:
        return False
    return source_agent_type in FORK_TYPE_VALID_SOURCES.get(fork_type, [])


# ==================== Event Schemas ====================


class SessionEventDetail(BaseModel):
    """Event detail returned by the session events service method."""

    id: Optional[UUID] = None
    session_id: Optional[UUID] = None
    created_at: str
    type: str
    content: Dict[str, Any]
    workspace_dir: str
    run_id: Optional[UUID] = None


class EventInfo(BaseModel):
    """Single event entry returned from session events endpoint.

    ``name`` is the dotted event name (e.g. ``"agent.response"``) used
    by the FE as the dispatch discriminator.
    """

    model_config = ConfigDict(extra="allow")

    id: Optional[UUID] = None
    name: Optional[str] = None
    event_type: Optional[str] = None
    event_group: Optional[str] = None
    content: Optional[Dict[str, Any]] = None
    created_at: Optional[str] = None
    run_id: Optional[str] = None
    session_id: Optional[UUID] = None


class EventResponse(BaseModel):
    """Response for GET /sessions/{session_id}/events."""

    events: List[EventInfo] = Field(default_factory=list)
    run_status: Optional[str] = None
