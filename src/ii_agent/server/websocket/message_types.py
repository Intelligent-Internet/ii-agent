"""WebSocket message types and handlers."""

from enum import Enum
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from datetime import datetime


class MessageType(str, Enum):
    """WebSocket message types."""

    # Connection management
    CONNECTION_ESTABLISHED = "connection_established"
    USER_CONNECTED = "user_connected"
    USER_DISCONNECTED = "user_disconnected"

    # Chat messages
    CHAT_MESSAGE = "chat_message"
    MESSAGE_RECEIVED = "message_received"
    MESSAGE_ERROR = "message_error"

    # Agent responses
    AGENT_RESPONSE = "agent_response"
    AGENT_THINKING = "agent_thinking"
    AGENT_TOOL_USE = "agent_tool_use"
    AGENT_ERROR = "agent_error"

    # Session management
    SESSION_CREATED = "session_created"
    SESSION_UPDATED = "session_updated"
    SESSION_PAUSED = "session_paused"
    SESSION_RESUMED = "session_resumed"

    # File operations
    FILE_UPLOADED = "file_uploaded"
    FILE_PROCESSING = "file_processing"
    FILE_PROCESSED = "file_processed"
    FILE_ERROR = "file_error"

    # Real-time indicators
    TYPING_INDICATOR = "typing_indicator"
    PRESENCE_UPDATE = "presence_update"

    # System notifications
    SYSTEM_NOTIFICATION = "system_notification"
    ERROR = "error"

    # Heartbeat
    PING = "ping"
    PONG = "pong"


class BaseMessage(BaseModel):
    """Base WebSocket message model."""

    type: MessageType
    timestamp: str = datetime.now().isoformat()
    session_id: Optional[str] = None
    user_id: Optional[str] = None


class ChatMessage(BaseMessage):
    """Chat message from user."""

    type: MessageType = MessageType.CHAT_MESSAGE
    content: str
    files: Optional[List[str]] = []
    metadata: Optional[Dict[str, Any]] = {}


class AgentResponse(BaseMessage):
    """Agent response message."""

    type: MessageType = MessageType.AGENT_RESPONSE
    content: str
    thinking_content: Optional[str] = None
    tool_uses: Optional[List[Dict[str, Any]]] = []
    metadata: Optional[Dict[str, Any]] = {}


class AgentThinking(BaseMessage):
    """Agent thinking indicator."""

    type: MessageType = MessageType.AGENT_THINKING
    thinking_content: str
    is_complete: bool = False


class AgentToolUse(BaseMessage):
    """Agent tool usage message."""

    type: MessageType = MessageType.AGENT_TOOL_USE
    tool_name: str
    tool_input: Dict[str, Any]
    tool_output: Optional[Dict[str, Any]] = None
    is_complete: bool = False
    error: Optional[str] = None


class FileUpload(BaseMessage):
    """File upload message."""

    type: MessageType = MessageType.FILE_UPLOADED
    file_id: str
    file_name: str
    file_size: int
    file_url: str
    content_type: str


class FileProcessing(BaseMessage):
    """File processing message."""

    type: MessageType = MessageType.FILE_PROCESSING
    file_id: str
    processing_type: str  # ocr, summarization, etc.
    progress: Optional[float] = None


class FileProcessed(BaseMessage):
    """File processed message."""

    type: MessageType = MessageType.FILE_PROCESSED
    file_id: str
    processing_type: str
    result: Dict[str, Any]


class TypingIndicator(BaseMessage):
    """Typing indicator message."""

    type: MessageType = MessageType.TYPING_INDICATOR
    is_typing: bool
    device_id: Optional[str] = None


class PresenceUpdate(BaseMessage):
    """Presence update message."""

    type: MessageType = MessageType.PRESENCE_UPDATE
    status: str  # online, away, busy, offline
    device_id: Optional[str] = None


class SessionUpdate(BaseMessage):
    """Session update message."""

    type: MessageType = MessageType.SESSION_UPDATED
    session_data: Dict[str, Any]


class SystemNotification(BaseMessage):
    """System notification message."""

    type: MessageType = MessageType.SYSTEM_NOTIFICATION
    title: str
    content: str
    level: str = "info"  # info, warning, error, success
    action_url: Optional[str] = None


class ErrorMessage(BaseMessage):
    """Error message."""

    type: MessageType = MessageType.ERROR
    error_code: str
    error_message: str
    details: Optional[Dict[str, Any]] = {}


class PingMessage(BaseMessage):
    """Ping message for heartbeat."""

    type: MessageType = MessageType.PING


class PongMessage(BaseMessage):
    """Pong response for heartbeat."""

    type: MessageType = MessageType.PONG


# Message type mappings for parsing
MESSAGE_TYPE_MAP = {
    MessageType.CHAT_MESSAGE: ChatMessage,
    MessageType.AGENT_RESPONSE: AgentResponse,
    MessageType.AGENT_THINKING: AgentThinking,
    MessageType.AGENT_TOOL_USE: AgentToolUse,
    MessageType.FILE_UPLOADED: FileUpload,
    MessageType.FILE_PROCESSING: FileProcessing,
    MessageType.FILE_PROCESSED: FileProcessed,
    MessageType.TYPING_INDICATOR: TypingIndicator,
    MessageType.PRESENCE_UPDATE: PresenceUpdate,
    MessageType.SESSION_UPDATED: SessionUpdate,
    MessageType.SYSTEM_NOTIFICATION: SystemNotification,
    MessageType.ERROR: ErrorMessage,
    MessageType.PING: PingMessage,
    MessageType.PONG: PongMessage,
}


def parse_message(message_data: dict) -> BaseMessage:
    """Parse a WebSocket message into the appropriate model."""
    message_type = MessageType(message_data.get("type"))
    message_class = MESSAGE_TYPE_MAP.get(message_type, BaseMessage)
    return message_class(**message_data)
