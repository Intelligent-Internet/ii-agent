"""Session management Pydantic models."""

from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List


class SessionCreate(BaseModel):
    """Model for creating a new session."""

    name: Optional[str] = None
    settings: Optional[Dict[str, Any]] = None
    sandbox_template: Optional[str] = "base"


class SessionUpdate(BaseModel):
    """Model for updating a session."""

    name: Optional[str] = None
    status: Optional[str] = Field(None, regex="^(pending|active|pause)$")
    settings: Optional[Dict[str, Any]] = None
    is_public: Optional[bool] = None


class SessionInfo(BaseModel):
    """Model for session information."""

    id: str
    user_id: str
    name: Optional[str] = None
    status: str
    sandbox_id: Optional[str] = None
    workspace_dir: str
    is_public: bool
    public_url: Optional[str] = None
    token_usage: Optional[Dict[str, Any]] = None
    settings: Optional[Dict[str, Any]] = None
    created_at: str
    updated_at: Optional[str] = None
    last_message_at: Optional[str] = None
    device_id: Optional[str] = None


class SessionList(BaseModel):
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


class TokenUsage(BaseModel):
    """Model for token usage tracking."""

    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0
    model: Optional[str] = None


class SessionPlan(BaseModel):
    """Model for session execution plan."""

    id: str
    title: str
    description: str
    steps: List[Dict[str, Any]]
    status: str = "pending"  # pending, running, completed, failed
    created_at: str
    updated_at: Optional[str] = None
