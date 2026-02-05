"""
Public Event Payload Schema

Defines the public schema for orchestrator events, providing:
- Type-safe event payload definitions
- Validation for event data
- Documentation of event contracts
- Backward-compatible schema versioning

Follows ralph's pattern of defined schemas like DistributionRecord, HolderEngagement.

Usage:
    from ii_skills.shared.event_schema import (
        EventPayload,
        RunStartedPayload,
        TaskCompletedPayload,
        validate_payload,
    )

    # Create typed payload
    payload = RunStartedPayload(
        run_id="abc123",
        run_type="deal_analysis",
        metadata={"company": "Acme"},
    )

    # Validate and serialize
    data = payload.to_dict()
    validated = validate_payload(data, RunStartedPayload)
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, Type, TypeVar, Union
from enum import Enum
import json

# Schema version for backward compatibility
SCHEMA_VERSION = "1.0.0"


class EventType(Enum):
    """Standard event types for orchestration."""
    # Run lifecycle
    RUN_STARTED = "run_started"
    RUN_COMPLETED = "run_completed"
    RUN_FAILED = "run_failed"
    RUN_CANCELLED = "run_cancelled"

    # Phase lifecycle
    PHASE_STARTED = "phase_started"
    PHASE_COMPLETED = "phase_completed"
    PHASE_FAILED = "phase_failed"
    PHASE_SKIPPED = "phase_skipped"

    # Task lifecycle
    TASK_QUEUED = "task_queued"
    TASK_STARTED = "task_started"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"
    TASK_RETRYING = "task_retrying"
    TASK_SKIPPED = "task_skipped"

    # Tool execution (new)
    TOOL_STARTED = "tool_started"
    TOOL_COMPLETED = "tool_completed"
    TOOL_FAILED = "tool_failed"

    # Sub-agent lifecycle (new)
    SUB_AGENT_START = "sub_agent_start"
    SUB_AGENT_PROGRESS = "sub_agent_progress"
    SUB_AGENT_COMPLETE = "sub_agent_complete"
    SUB_AGENT_ERROR = "sub_agent_error"

    # Progress
    PROGRESS_UPDATE = "progress_update"
    CHECKPOINT_SAVED = "checkpoint_saved"

    # Budget
    BUDGET_WARNING = "budget_warning"
    BUDGET_EXCEEDED = "budget_exceeded"

    # Custom
    CUSTOM = "custom"


class Severity(Enum):
    """Event severity levels."""
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class EventPayload:
    """
    Base class for all event payloads.

    All payloads include standard metadata fields.
    """
    event_type: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    schema_version: str = SCHEMA_VERSION
    severity: str = Severity.INFO.value

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), default=str)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'EventPayload':
        """Create from dictionary."""
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


# =============================================================================
# RUN LIFECYCLE EVENTS
# =============================================================================

@dataclass
class RunStartedPayload(EventPayload):
    """Payload for run_started events."""
    event_type: str = field(default=EventType.RUN_STARTED.value)
    run_id: str = ""
    run_type: str = ""
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    budget_profile: Optional[str] = None


@dataclass
class RunCompletedPayload(EventPayload):
    """Payload for run_completed events."""
    event_type: str = field(default=EventType.RUN_COMPLETED.value)
    run_id: str = ""
    run_type: str = ""
    duration_ms: float = 0
    tasks_completed: int = 0
    tasks_failed: int = 0
    phases_completed: int = 0
    outputs: List[str] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RunFailedPayload(EventPayload):
    """Payload for run_failed events."""
    event_type: str = field(default=EventType.RUN_FAILED.value)
    severity: str = Severity.ERROR.value
    run_id: str = ""
    run_type: str = ""
    duration_ms: float = 0
    error_message: str = ""
    error_type: str = ""
    last_phase: Optional[str] = None
    last_task: Optional[str] = None
    tasks_completed: int = 0
    tasks_failed: int = 0


@dataclass
class RunCancelledPayload(EventPayload):
    """Payload for run_cancelled events."""
    event_type: str = field(default=EventType.RUN_CANCELLED.value)
    severity: str = Severity.WARNING.value
    run_id: str = ""
    run_type: str = ""
    duration_ms: float = 0
    reason: str = ""
    tasks_completed: int = 0
    tasks_pending: int = 0


# =============================================================================
# PHASE LIFECYCLE EVENTS
# =============================================================================

@dataclass
class PhaseStartedPayload(EventPayload):
    """Payload for phase_started events."""
    event_type: str = field(default=EventType.PHASE_STARTED.value)
    run_id: str = ""
    phase_id: str = ""
    phase_name: str = ""
    task_count: int = 0
    task_ids: List[str] = field(default_factory=list)
    parallel: bool = True


@dataclass
class PhaseCompletedPayload(EventPayload):
    """Payload for phase_completed events."""
    event_type: str = field(default=EventType.PHASE_COMPLETED.value)
    run_id: str = ""
    phase_id: str = ""
    phase_name: str = ""
    duration_ms: float = 0
    tasks_completed: int = 0
    tasks_failed: int = 0
    tasks_skipped: int = 0


@dataclass
class PhaseFailedPayload(EventPayload):
    """Payload for phase_failed events."""
    event_type: str = field(default=EventType.PHASE_FAILED.value)
    severity: str = Severity.ERROR.value
    run_id: str = ""
    phase_id: str = ""
    phase_name: str = ""
    duration_ms: float = 0
    error_message: str = ""
    failed_task_id: Optional[str] = None
    tasks_completed: int = 0
    tasks_failed: int = 0


@dataclass
class PhaseSkippedPayload(EventPayload):
    """Payload for phase_skipped events."""
    event_type: str = field(default=EventType.PHASE_SKIPPED.value)
    run_id: str = ""
    phase_id: str = ""
    phase_name: str = ""
    reason: str = ""


# =============================================================================
# TASK LIFECYCLE EVENTS
# =============================================================================

@dataclass
class TaskQueuedPayload(EventPayload):
    """Payload for task_queued events."""
    event_type: str = field(default=EventType.TASK_QUEUED.value)
    run_id: str = ""
    phase_id: str = ""
    task_id: str = ""
    task_name: str = ""
    dependencies: List[str] = field(default_factory=list)
    position_in_queue: int = 0


@dataclass
class TaskStartedPayload(EventPayload):
    """Payload for task_started events."""
    event_type: str = field(default=EventType.TASK_STARTED.value)
    run_id: str = ""
    phase_id: str = ""
    task_id: str = ""
    task_name: str = ""
    attempt: int = 1


@dataclass
class TaskCompletedPayload(EventPayload):
    """Payload for task_completed events."""
    event_type: str = field(default=EventType.TASK_COMPLETED.value)
    run_id: str = ""
    phase_id: str = ""
    task_id: str = ""
    task_name: str = ""
    duration_ms: float = 0
    attempt: int = 1
    result_summary: Optional[str] = None
    result_size_bytes: Optional[int] = None


@dataclass
class TaskFailedPayload(EventPayload):
    """Payload for task_failed events."""
    event_type: str = field(default=EventType.TASK_FAILED.value)
    severity: str = Severity.ERROR.value
    run_id: str = ""
    phase_id: str = ""
    task_id: str = ""
    task_name: str = ""
    duration_ms: float = 0
    attempt: int = 1
    max_attempts: int = 1
    error_message: str = ""
    error_type: str = ""
    will_retry: bool = False


@dataclass
class TaskRetryingPayload(EventPayload):
    """Payload for task_retrying events."""
    event_type: str = field(default=EventType.TASK_RETRYING.value)
    severity: str = Severity.WARNING.value
    run_id: str = ""
    phase_id: str = ""
    task_id: str = ""
    task_name: str = ""
    attempt: int = 1
    max_attempts: int = 3
    retry_delay_ms: float = 1000
    last_error: str = ""


@dataclass
class TaskSkippedPayload(EventPayload):
    """Payload for task_skipped events."""
    event_type: str = field(default=EventType.TASK_SKIPPED.value)
    run_id: str = ""
    phase_id: str = ""
    task_id: str = ""
    task_name: str = ""
    reason: str = ""


# =============================================================================
# PROGRESS EVENTS
# =============================================================================

@dataclass
class ProgressUpdatePayload(EventPayload):
    """Payload for progress_update events."""
    event_type: str = field(default=EventType.PROGRESS_UPDATE.value)
    run_id: str = ""
    current_phase: str = ""
    phases_completed: int = 0
    phases_total: int = 0
    tasks_completed: int = 0
    tasks_total: int = 0
    tasks_running: int = 0
    elapsed_ms: float = 0
    estimated_remaining_ms: Optional[float] = None
    percent_complete: float = 0


@dataclass
class CheckpointSavedPayload(EventPayload):
    """Payload for checkpoint_saved events."""
    event_type: str = field(default=EventType.CHECKPOINT_SAVED.value)
    run_id: str = ""
    checkpoint_id: str = ""
    phase_id: str = ""
    tasks_completed: int = 0
    checkpoint_path: Optional[str] = None


# =============================================================================
# BUDGET EVENTS
# =============================================================================

@dataclass
class BudgetWarningPayload(EventPayload):
    """Payload for budget_warning events."""
    event_type: str = field(default=EventType.BUDGET_WARNING.value)
    severity: str = Severity.WARNING.value
    run_id: str = ""
    warning_type: str = ""  # "tasks", "duration", "api_calls"
    current_value: float = 0
    limit_value: float = 0
    percent_used: float = 0
    message: str = ""


@dataclass
class BudgetExceededPayload(EventPayload):
    """Payload for budget_exceeded events."""
    event_type: str = field(default=EventType.BUDGET_EXCEEDED.value)
    severity: str = Severity.ERROR.value
    run_id: str = ""
    exceeded_type: str = ""  # "tasks", "duration", "api_calls", "failed_tasks"
    final_value: float = 0
    limit_value: float = 0
    action_taken: str = ""  # "stopped", "degraded"


# =============================================================================
# TOOL EXECUTION EVENTS
# =============================================================================

@dataclass
class ToolStartedPayload(EventPayload):
    """Payload for tool_started events."""
    event_type: str = field(default=EventType.TOOL_STARTED.value)
    run_id: str = ""
    tool_name: str = ""
    tool_type: str = ""  # e.g., "search", "file", "api"
    input_summary: Optional[str] = None


@dataclass
class ToolCompletedPayload(EventPayload):
    """Payload for tool_completed events."""
    event_type: str = field(default=EventType.TOOL_COMPLETED.value)
    run_id: str = ""
    tool_name: str = ""
    tool_type: str = ""
    duration_ms: float = 0
    output_size_bytes: Optional[int] = None
    output_summary: Optional[str] = None


@dataclass
class ToolFailedPayload(EventPayload):
    """Payload for tool_failed events with standardized error taxonomy."""
    event_type: str = field(default=EventType.TOOL_FAILED.value)
    severity: str = Severity.ERROR.value
    run_id: str = ""
    tool_name: str = ""
    tool_type: str = ""
    duration_ms: float = 0
    is_error: bool = True
    error_type: str = ""  # "timeout", "validation", "runtime", "not_found", "permission", "rate_limit", "network", "unknown"
    error_message: str = ""
    will_retry: bool = False


# =============================================================================
# SUB-AGENT EVENTS
# =============================================================================

@dataclass
class SubAgentStartPayload(EventPayload):
    """Payload for sub_agent_start events with parent-child linking."""
    event_type: str = field(default=EventType.SUB_AGENT_START.value)
    parent_run_id: str = ""  # Parent run ID for trace stitching
    child_run_id: str = ""   # This sub-agent's run ID
    agent_type: str = ""     # e.g., "research", "analysis", "generation"
    task_description: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SubAgentProgressPayload(EventPayload):
    """Payload for sub_agent_progress events."""
    event_type: str = field(default=EventType.SUB_AGENT_PROGRESS.value)
    parent_run_id: str = ""
    child_run_id: str = ""
    agent_type: str = ""
    progress: float = 0  # 0.0 to 1.0
    message: Optional[str] = None


@dataclass
class SubAgentCompletePayload(EventPayload):
    """Payload for sub_agent_complete events with parent-child linking."""
    event_type: str = field(default=EventType.SUB_AGENT_COMPLETE.value)
    parent_run_id: str = ""
    child_run_id: str = ""
    agent_type: str = ""
    task_description: str = ""
    duration_ms: float = 0
    status: str = "success"  # "success", "failed", "cancelled"
    result_summary: Optional[str] = None


@dataclass
class SubAgentErrorPayload(EventPayload):
    """Payload for sub_agent_error events."""
    event_type: str = field(default=EventType.SUB_AGENT_ERROR.value)
    severity: str = Severity.ERROR.value
    parent_run_id: str = ""
    child_run_id: str = ""
    agent_type: str = ""
    task_description: str = ""
    duration_ms: float = 0
    error_message: str = ""
    error_type: str = ""


# =============================================================================
# CUSTOM EVENTS
# =============================================================================

@dataclass
class CustomEventPayload(EventPayload):
    """Payload for custom application-specific events."""
    event_type: str = field(default=EventType.CUSTOM.value)
    run_id: str = ""
    custom_type: str = ""
    data: Dict[str, Any] = field(default_factory=dict)


# =============================================================================
# VALIDATION AND UTILITIES
# =============================================================================

# Registry of payload types by event type
PAYLOAD_REGISTRY: Dict[str, Type[EventPayload]] = {
    # Run lifecycle
    EventType.RUN_STARTED.value: RunStartedPayload,
    EventType.RUN_COMPLETED.value: RunCompletedPayload,
    EventType.RUN_FAILED.value: RunFailedPayload,
    EventType.RUN_CANCELLED.value: RunCancelledPayload,
    # Phase lifecycle
    EventType.PHASE_STARTED.value: PhaseStartedPayload,
    EventType.PHASE_COMPLETED.value: PhaseCompletedPayload,
    EventType.PHASE_FAILED.value: PhaseFailedPayload,
    EventType.PHASE_SKIPPED.value: PhaseSkippedPayload,
    # Task lifecycle
    EventType.TASK_QUEUED.value: TaskQueuedPayload,
    EventType.TASK_STARTED.value: TaskStartedPayload,
    EventType.TASK_COMPLETED.value: TaskCompletedPayload,
    EventType.TASK_FAILED.value: TaskFailedPayload,
    EventType.TASK_RETRYING.value: TaskRetryingPayload,
    EventType.TASK_SKIPPED.value: TaskSkippedPayload,
    # Tool execution
    EventType.TOOL_STARTED.value: ToolStartedPayload,
    EventType.TOOL_COMPLETED.value: ToolCompletedPayload,
    EventType.TOOL_FAILED.value: ToolFailedPayload,
    # Sub-agent lifecycle
    EventType.SUB_AGENT_START.value: SubAgentStartPayload,
    EventType.SUB_AGENT_PROGRESS.value: SubAgentProgressPayload,
    EventType.SUB_AGENT_COMPLETE.value: SubAgentCompletePayload,
    EventType.SUB_AGENT_ERROR.value: SubAgentErrorPayload,
    # Progress
    EventType.PROGRESS_UPDATE.value: ProgressUpdatePayload,
    EventType.CHECKPOINT_SAVED.value: CheckpointSavedPayload,
    # Budget
    EventType.BUDGET_WARNING.value: BudgetWarningPayload,
    EventType.BUDGET_EXCEEDED.value: BudgetExceededPayload,
    # Custom
    EventType.CUSTOM.value: CustomEventPayload,
}


T = TypeVar('T', bound=EventPayload)


def validate_payload(
    data: Dict[str, Any],
    expected_type: Optional[Type[T]] = None,
) -> Union[T, EventPayload]:
    """
    Validate and parse an event payload.

    Args:
        data: Raw payload dictionary
        expected_type: Optional expected payload type

    Returns:
        Validated payload object

    Raises:
        ValueError: If validation fails
    """
    event_type = data.get("event_type")
    if not event_type:
        raise ValueError("Missing event_type in payload")

    # Determine payload class
    if expected_type:
        payload_class = expected_type
    else:
        payload_class = PAYLOAD_REGISTRY.get(event_type, EventPayload)

    # Create payload from data
    try:
        valid_fields = {k: v for k, v in data.items() if k in payload_class.__dataclass_fields__}
        payload = payload_class(**valid_fields)
    except TypeError as e:
        raise ValueError(f"Invalid payload data: {e}")

    return payload


def create_payload(
    event_type: EventType,
    **kwargs,
) -> EventPayload:
    """
    Create a typed event payload.

    Args:
        event_type: The event type
        **kwargs: Payload fields

    Returns:
        Typed payload object
    """
    payload_class = PAYLOAD_REGISTRY.get(event_type.value, CustomEventPayload)
    return payload_class(**kwargs)


def parse_event(raw_data: Union[str, Dict[str, Any]]) -> EventPayload:
    """
    Parse raw event data into a typed payload.

    Args:
        raw_data: JSON string or dictionary

    Returns:
        Parsed payload object
    """
    if isinstance(raw_data, str):
        data = json.loads(raw_data)
    else:
        data = raw_data

    return validate_payload(data)


class EventSchemaMapper:
    """
    Maps between internal event representations and public schema.

    Use this to adapt existing event systems to the public schema.
    """

    def __init__(self):
        self._type_mappings: Dict[str, EventType] = {}
        self._field_mappings: Dict[str, Dict[str, str]] = {}

    def map_event_type(self, internal_type: str, public_type: EventType):
        """Map an internal event type to a public type."""
        self._type_mappings[internal_type] = public_type

    def map_field(self, event_type: str, internal_field: str, public_field: str):
        """Map an internal field name to a public field name."""
        if event_type not in self._field_mappings:
            self._field_mappings[event_type] = {}
        self._field_mappings[event_type][internal_field] = public_field

    def convert(self, internal_event: Dict[str, Any]) -> EventPayload:
        """Convert an internal event to public schema."""
        internal_type = internal_event.get("type", internal_event.get("event_type", ""))

        # Map event type
        public_type = self._type_mappings.get(internal_type)
        if not public_type:
            # Try to match by name
            for et in EventType:
                if et.value == internal_type:
                    public_type = et
                    break

        if not public_type:
            public_type = EventType.CUSTOM

        # Map fields
        field_map = self._field_mappings.get(internal_type, {})
        converted = {}
        for key, value in internal_event.items():
            new_key = field_map.get(key, key)
            converted[new_key] = value

        converted["event_type"] = public_type.value

        return validate_payload(converted)


# Default mapper for orchestrator events
def create_orchestrator_event_mapper() -> EventSchemaMapper:
    """Create a mapper for the existing orchestrator event system."""
    mapper = EventSchemaMapper()

    # Map DealEventType to public EventType
    mapper.map_event_type("deal_started", EventType.RUN_STARTED)
    mapper.map_event_type("deal_completed", EventType.RUN_COMPLETED)
    mapper.map_event_type("deal_error", EventType.RUN_FAILED)
    mapper.map_event_type("phase_started", EventType.PHASE_STARTED)
    mapper.map_event_type("phase_completed", EventType.PHASE_COMPLETED)
    mapper.map_event_type("task_started", EventType.TASK_STARTED)
    mapper.map_event_type("task_completed", EventType.TASK_COMPLETED)
    mapper.map_event_type("task_failed", EventType.TASK_FAILED)
    mapper.map_event_type("checkpoint_saved", EventType.CHECKPOINT_SAVED)

    # Map fields
    mapper.map_field("deal_started", "deal_id", "run_id")
    mapper.map_field("deal_started", "deal_type", "run_type")
    mapper.map_field("deal_completed", "deal_id", "run_id")
    mapper.map_field("task_completed", "duration_ms", "duration_ms")
    mapper.map_field("task_failed", "error", "error_message")

    return mapper
