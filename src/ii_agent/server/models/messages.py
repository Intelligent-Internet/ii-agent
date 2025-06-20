from typing import Dict, List, Any
from pydantic import BaseModel

from ii_agent.core.storage.models.settings import Settings


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
    workspace_dir: str
    created_at: str
    device_id: str
    name: str = ""


class SessionResponse(BaseModel):
    """Response model for session queries."""

    sessions: List[SessionInfo]


class EventInfo(BaseModel):
    """Model for event information."""

    id: str
    session_id: str
    timestamp: str
    event_type: str
    event_payload: Dict[str, Any]
    workspace_dir: str


class EventResponse(BaseModel):
    """Response model for event queries."""

    events: List[EventInfo]


class QueryContent(BaseModel):
    """Model for query message content."""

    text: str = ""
    resume: bool = False
    files: List[str] = []


class InitAgentContent(BaseModel):
    """Model for agent initialization content."""

    model_name: str
    tool_args: Dict[str, Any] = {}
    thinking_tokens: int = 0


class EnhancePromptContent(BaseModel):
    """Model for prompt enhancement content."""

    model_name: str
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
