from typing import Dict, List, Any, Literal, Optional
from pydantic import BaseModel, field_validator

from ii_agent.config.agent_types import AgentType
from ii_agent.core.storage.models.settings import Settings


def normalize_agent_type(value: Any) -> AgentType:
    """
    Normalize agent_type values to valid AgentType enum values.
    
    The database stores 'chat' for sessions created via the /v1/chat API,
    which is used for frontend routing (different UI for chat vs agent sessions).
    However, 'chat' is not a valid AgentType enum value for agent initialization.
    
    This function converts 'chat' to 'general' so that chat sessions can be
    seamlessly resumed via Socket.IO agent mode with general agent capabilities.
    
    Args:
        value: The agent_type value to normalize (string or AgentType)
        
    Returns:
        A valid AgentType enum value
    """
    if isinstance(value, AgentType):
        return value
    if isinstance(value, str):
        # Normalize 'chat' to 'general' for compatibility
        if value == "chat":
            return AgentType.GENERAL
        return AgentType(value)
    raise ValueError(f"Invalid agent_type: {value}")


class WebSocketMessage(BaseModel):
    """Base model for WebSocket messages."""

    type: str
    content: Dict[str, Any] = {}


class FileInfo(BaseModel):
    """Model for file information in uploads."""

    path: str
    content: str


class UploadRequest(BaseModel):
    """Model for file upload requests."""

    session_id: str
    file: FileInfo


class SessionInfo(BaseModel):
    """Model for session information."""

    id: str
    created_at: str
    name: str = ""


class SessionResponse(BaseModel):
    """Response model for session queries."""

    sessions: List[SessionInfo]


class EventInfo(BaseModel):
    """Model for event information."""

    id: str
    session_id: str
    created_at: str
    type: str
    content: Dict[str, Any]
    workspace_dir: str


class EventResponse(BaseModel):
    """Response model for event queries."""

    events: List[EventInfo]


class QueryContentRequest(BaseModel):
    """Model for query message content."""

    text: str = ""
    resume: bool = False
    file_ids: List[str] = []


class QueryContentInternal(BaseModel):
    text: str = ""
    resume: bool = False
    file_upload_paths: List[str] = []
    images_data: List[
        Dict[str, str]
    ] = []  # in form of [{"content_type": ..., "url": ...}, ...]


class InitAgentContent(BaseModel):
    """Model for agent initialization content."""

    model_id: Optional[str] = None  # Used model_name for system model
    tool_args: Dict[str, Any] = {}
    source: Optional[Literal["user", "system"]] = None
    thinking_tokens: int = 0
    agent_type: AgentType = (
        AgentType.GENERAL
    )  # Agent type: 'general', 'video_generate', 'image', 'slide', 'website_build'
    metadata: Optional[Dict[str, Any]] = (
        None  # Optional metadata (e.g., template_id for slides)
    )

    @field_validator("agent_type", mode="before")
    @classmethod
    def validate_agent_type(cls, v: Any) -> AgentType:
        """Normalize agent_type, converting 'chat' to 'general'."""
        return normalize_agent_type(v)


class QueryCommandContent(BaseModel):
    """Model for query command content that combines init_agent and query parameters."""

    # Init agent parameters (required for agent initialization)
    model_id: Optional[str]
    provider: Optional[str]
    source: Optional[Literal["user", "system"]] = "system"
    agent_type: AgentType
    tool_args: Dict[str, Any] = {}
    thinking_tokens: int = 0
    metadata: Optional[Dict[str, Any]] = None

    # Query parameters (required for query processing)
    text: str = ""
    resume: bool = False
    files: List[str] = []

    @field_validator("agent_type", mode="before")
    @classmethod
    def validate_agent_type(cls, v: Any) -> AgentType:
        """Normalize agent_type, converting 'chat' to 'general'."""
        return normalize_agent_type(v)

    class Config:
        """Pydantic configuration."""

        extra = "allow"
        validate_assignment = True


class EnhancePromptContent(BaseModel):
    """Model for prompt enhancement content."""

    text: str = ""
    files: List[str] = []


class EditQueryContent(BaseModel):
    """Model for edit query content."""

    text: str = ""
    resume: bool = False
    files: List[str] = []


class ReviewResultContent(BaseModel):
    """Model for review result content."""

    user_input: str = ""


class GETSettingsModel(Settings):
    """Model for GET settings."""

    llm_api_key_set: bool
    search_api_key_set: bool
