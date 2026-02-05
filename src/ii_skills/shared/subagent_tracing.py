"""
Sub-Agent Tracing

Parent-child run linking and lifecycle events for sub-agent operations.
Enables trace stitching across parent and child runs.

Usage:
    from ii_skills.shared.subagent_tracing import SubAgentTracer, SubAgentEvent

    tracer = SubAgentTracer(parent_run_id="parent-123")

    # Start a sub-agent
    child_run_id = tracer.start_subagent(
        agent_type="research",
        task_description="Find competitor data",
    )

    # ... sub-agent executes ...

    # Complete the sub-agent
    tracer.complete_subagent(
        child_run_id=child_run_id,
        status="success",
        result={"data": "..."},
    )
"""

import uuid
import logging
from datetime import datetime
from enum import Enum
from typing import Dict, Any, Optional, List, Callable
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


class SubAgentEventType(Enum):
    """Sub-agent lifecycle event types."""
    SUB_AGENT_START = "sub_agent_start"
    SUB_AGENT_PROGRESS = "sub_agent_progress"
    SUB_AGENT_COMPLETE = "sub_agent_complete"
    SUB_AGENT_ERROR = "sub_agent_error"


class SubAgentStatus(Enum):
    """Sub-agent execution status."""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class SubAgentEvent:
    """
    Sub-agent lifecycle event with parent-child linking.

    Includes parent_run_id for trace stitching across runs.
    """
    event_type: SubAgentEventType
    timestamp: datetime
    parent_run_id: str
    child_run_id: str
    agent_type: str
    task_description: Optional[str] = None
    status: Optional[SubAgentStatus] = None
    progress: Optional[float] = None  # 0.0 to 1.0
    result: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    duration_ms: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for event emission."""
        return {
            "event_type": self.event_type.value,
            "timestamp": self.timestamp.isoformat(),
            "parent_run_id": self.parent_run_id,
            "child_run_id": self.child_run_id,
            "agent_type": self.agent_type,
            "task_description": self.task_description,
            "status": self.status.value if self.status else None,
            "progress": self.progress,
            "result": self.result,
            "error_message": self.error_message,
            "duration_ms": self.duration_ms,
            "metadata": self.metadata,
        }


@dataclass
class SubAgentRecord:
    """Record of a sub-agent execution."""
    child_run_id: str
    parent_run_id: str
    agent_type: str
    task_description: str
    start_time: datetime
    end_time: Optional[datetime] = None
    status: SubAgentStatus = SubAgentStatus.PENDING
    result: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def duration_ms(self) -> Optional[float]:
        """Calculate duration in milliseconds."""
        if self.end_time and self.start_time:
            return (self.end_time - self.start_time).total_seconds() * 1000
        return None


class SubAgentTracer:
    """
    Traces sub-agent executions with parent-child linking.

    Emits start and complete events for timeline observability.
    Supports event listeners for integration with telemetry systems.
    """

    def __init__(
        self,
        parent_run_id: str,
        event_callback: Optional[Callable[[SubAgentEvent], None]] = None,
    ):
        """
        Initialize the tracer.

        Args:
            parent_run_id: ID of the parent run (for linking)
            event_callback: Optional callback for event emission
        """
        self.parent_run_id = parent_run_id
        self.event_callback = event_callback
        self._records: Dict[str, SubAgentRecord] = {}
        self._event_history: List[SubAgentEvent] = []

    def start_subagent(
        self,
        agent_type: str,
        task_description: str,
        child_run_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Record sub-agent start and emit start event.

        Args:
            agent_type: Type of sub-agent (e.g., "research", "analysis")
            task_description: Description of the task
            child_run_id: Optional custom run ID (generated if not provided)
            metadata: Optional additional metadata

        Returns:
            The child run ID
        """
        child_run_id = child_run_id or str(uuid.uuid4())

        record = SubAgentRecord(
            child_run_id=child_run_id,
            parent_run_id=self.parent_run_id,
            agent_type=agent_type,
            task_description=task_description,
            start_time=datetime.now(),
            status=SubAgentStatus.RUNNING,
            metadata=metadata or {},
        )
        self._records[child_run_id] = record

        # Emit start event
        event = SubAgentEvent(
            event_type=SubAgentEventType.SUB_AGENT_START,
            timestamp=record.start_time,
            parent_run_id=self.parent_run_id,
            child_run_id=child_run_id,
            agent_type=agent_type,
            task_description=task_description,
            status=SubAgentStatus.RUNNING,
            metadata=metadata or {},
        )
        self._emit_event(event)

        logger.info(
            f"Sub-agent started: {agent_type} (child={child_run_id[:8]}, parent={self.parent_run_id[:8]})"
        )

        return child_run_id

    def report_progress(
        self,
        child_run_id: str,
        progress: float,
        message: Optional[str] = None,
    ):
        """
        Report progress for a running sub-agent.

        Args:
            child_run_id: The sub-agent's run ID
            progress: Progress value (0.0 to 1.0)
            message: Optional progress message
        """
        record = self._records.get(child_run_id)
        if not record:
            logger.warning(f"Unknown sub-agent: {child_run_id}")
            return

        event = SubAgentEvent(
            event_type=SubAgentEventType.SUB_AGENT_PROGRESS,
            timestamp=datetime.now(),
            parent_run_id=self.parent_run_id,
            child_run_id=child_run_id,
            agent_type=record.agent_type,
            status=SubAgentStatus.RUNNING,
            progress=progress,
            metadata={"message": message} if message else {},
        )
        self._emit_event(event)

    def complete_subagent(
        self,
        child_run_id: str,
        status: str = "success",
        result: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None,
    ):
        """
        Record sub-agent completion and emit complete event.

        Args:
            child_run_id: The sub-agent's run ID
            status: Completion status ("success", "failed", "cancelled")
            result: Optional result data
            error_message: Optional error message (if failed)
        """
        record = self._records.get(child_run_id)
        if not record:
            logger.warning(f"Unknown sub-agent: {child_run_id}")
            return

        # Update record
        record.end_time = datetime.now()
        record.status = SubAgentStatus(status) if status in [s.value for s in SubAgentStatus] else SubAgentStatus.SUCCESS
        record.result = result
        record.error_message = error_message

        # Determine event type
        event_type = (
            SubAgentEventType.SUB_AGENT_ERROR
            if record.status == SubAgentStatus.FAILED
            else SubAgentEventType.SUB_AGENT_COMPLETE
        )

        # Emit completion event
        event = SubAgentEvent(
            event_type=event_type,
            timestamp=record.end_time,
            parent_run_id=self.parent_run_id,
            child_run_id=child_run_id,
            agent_type=record.agent_type,
            task_description=record.task_description,
            status=record.status,
            result=result,
            error_message=error_message,
            duration_ms=record.duration_ms,
            metadata=record.metadata,
        )
        self._emit_event(event)

        logger.info(
            f"Sub-agent completed: {record.agent_type} ({record.status.value}, "
            f"{record.duration_ms:.0f}ms)"
        )

    def get_record(self, child_run_id: str) -> Optional[SubAgentRecord]:
        """Get a sub-agent record by ID."""
        return self._records.get(child_run_id)

    def get_all_records(self) -> Dict[str, SubAgentRecord]:
        """Get all sub-agent records."""
        return dict(self._records)

    def get_event_history(self) -> List[SubAgentEvent]:
        """Get all emitted events."""
        return list(self._event_history)

    def get_active_subagents(self) -> List[SubAgentRecord]:
        """Get currently running sub-agents."""
        return [
            r for r in self._records.values()
            if r.status == SubAgentStatus.RUNNING
        ]

    def _emit_event(self, event: SubAgentEvent):
        """Emit an event and record in history."""
        self._event_history.append(event)

        if self.event_callback:
            try:
                self.event_callback(event)
            except Exception as e:
                logger.error(f"Error in event callback: {e}")


class SubAgentContext:
    """
    Context manager for sub-agent execution.

    Usage:
        tracer = SubAgentTracer(parent_run_id="parent-123")

        async with tracer.context("research", "Find data") as ctx:
            result = await do_research()
            ctx.set_result(result)
    """

    def __init__(
        self,
        tracer: SubAgentTracer,
        agent_type: str,
        task_description: str,
        metadata: Optional[Dict] = None,
    ):
        self.tracer = tracer
        self.agent_type = agent_type
        self.task_description = task_description
        self.metadata = metadata
        self.child_run_id: Optional[str] = None
        self._result: Optional[Dict] = None
        self._error: Optional[str] = None

    def set_result(self, result: Dict[str, Any]):
        """Set the result for this sub-agent execution."""
        self._result = result

    def report_progress(self, progress: float, message: Optional[str] = None):
        """Report progress during execution."""
        if self.child_run_id:
            self.tracer.report_progress(self.child_run_id, progress, message)

    async def __aenter__(self):
        """Start the sub-agent execution."""
        self.child_run_id = self.tracer.start_subagent(
            agent_type=self.agent_type,
            task_description=self.task_description,
            metadata=self.metadata,
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Complete the sub-agent execution."""
        if exc_type is not None:
            self.tracer.complete_subagent(
                child_run_id=self.child_run_id,
                status="failed",
                error_message=str(exc_val),
            )
        else:
            self.tracer.complete_subagent(
                child_run_id=self.child_run_id,
                status="success",
                result=self._result,
            )
        return False  # Don't suppress exceptions


# Convenience function for creating traced sub-agent context
def traced_subagent(
    parent_run_id: str,
    agent_type: str,
    task_description: str,
    event_callback: Optional[Callable] = None,
    metadata: Optional[Dict] = None,
) -> SubAgentContext:
    """
    Create a traced sub-agent context.

    Usage:
        async with traced_subagent("parent-123", "research", "Find data") as ctx:
            result = await do_research()
            ctx.set_result(result)
    """
    tracer = SubAgentTracer(parent_run_id, event_callback)
    return SubAgentContext(tracer, agent_type, task_description, metadata)
