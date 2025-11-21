from uuid import UUID, uuid4
from pydantic import BaseModel, Field
from typing import Any, Optional
import enum
import time


class AgentStatus(str, enum.Enum):
    READY = "ready"
    RUNNING = "running"
    CANCELLED = "cancelled"


class EventType(str, enum.Enum):
    CONNECTION_ESTABLISHED = "connection_established"
    STATUS_UPDATE = "status_update"
    AGENT_INITIALIZED = "agent_initialized"
    WORKSPACE_INFO = "workspace_info"
    PROCESSING = "processing"
    AGENT_THINKING = "agent_thinking"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    AGENT_RESPONSE = "agent_response"
    AGENT_RESPONSE_INTERRUPTED = "agent_response_interrupted"
    STREAM_COMPLETE = "stream_complete"
    ERROR = "error"
    SYSTEM = "system"
    PONG = "pong"
    UPLOAD_SUCCESS = "upload_success"
    BROWSER_USE = "browser_use"
    FILE_EDIT = "file_edit"
    USER_MESSAGE = "user_message"
    PROMPT_GENERATED = "prompt_generated"
    TOOL_CONFIRMATION = "tool_confirmation"
    SANDBOX_STATUS = "sandbox_status"
    COMPLETE = "complete"
    SUB_AGENT_COMPLETE = "sub_agent_complete"
    METRICS_UPDATE = "metrics_update"
    MODEL_COMPACT = "model_compact"
    CHECKPOINT_CREATED = "checkpoint_created"
    TILE_GENERATED = "tile_generated"
    SUMMARY_CREATED = "summary_created"
    PERFORMANCE_WARNING = "performance_warning"
    MONITORING = "monitoring"

    @staticmethod
    def is_allowed_when_aborted(event_type: "EventType") -> bool:
        return event_type in [
            EventType.STATUS_UPDATE,
            EventType.SYSTEM,
            EventType.ERROR,
            EventType.PONG,
            EventType.STREAM_COMPLETE,
            EventType.CONNECTION_ESTABLISHED,
            EventType.AGENT_RESPONSE_INTERRUPTED,
            EventType.WORKSPACE_INFO,
            EventType.SANDBOX_STATUS,
        ]


class RealtimeEvent(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    type: EventType
    session_id: Optional[UUID] = None
    run_id: Optional[UUID] = None
    content: dict[str, Any]
    timestamp: Optional[float] = Field(default_factory=time.time)
