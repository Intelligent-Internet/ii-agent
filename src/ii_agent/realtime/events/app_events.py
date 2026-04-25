from __future__ import annotations

import time
import uuid
from enum import StrEnum
from typing import TYPE_CHECKING, Annotated, Any, Literal, TypeAlias, Union

from pydantic import BaseModel, ConfigDict, Field
from ii_agent.settings.llm import PricingInfo, Provider
from ii_agent.tasks.types import RunStatus

if TYPE_CHECKING:
    from ii_agent.agents.runs.agent import RunOutputEvent


class ErrorCode(StrEnum):
    """Strict error codes emitted in :class:`SystemErrorEvent`.

    Every error flowing through the real-time channel MUST use one of these
    codes so the FE can match on a known set of values.
    """

    # Validation
    VALIDATION_ERROR = "validation_error"
    UNSUPPORTED_API_VERSION = "unsupported_api_version"

    # Auth
    AUTH_ERROR = "auth_error"
    SESSION_EXPIRED = "session_expired"
    SESSION_ERROR = "session_error"

    # Throttle
    RATE_LIMIT = "rate_limit"

    # Resource not found
    RUN_NOT_FOUND = "run_not_found"
    SESSION_NOT_FOUND = "session_not_found"
    PROJECT_NOT_FOUND = "project_not_found"
    MISSING_PROJECT_PATH = "missing_project_path"
    MISSING_CREDENTIALS = "missing_credentials"

    # Deployment
    DEPLOY_FAILED = "deploy_failed"
    DEPLOY_LINK_FAILED = "deploy_link_failed"
    SANDBOX_CONNECTION_FAILED = "sandbox_connection_failed"
    SOURCE_DOWNLOAD_FAILED = "source_download_failed"

    # Billing
    INSUFFICIENT_CREDITS = "insufficient_credits"

    # Execution
    EXECUTION_ERROR = "execution_error"
    UNEXPECTED_ERROR = "unexpected_error"
    INTERNAL_ERROR = "internal_error"
    CONCURRENT_OPERATION = "concurrent_operation"
    DUPLICATE_TASK = "duplicate_task"

    # Sandbox
    SANDBOX_ERROR = "sandbox_error"

    # Integration: Apple
    NAME_TAKEN = "name_taken"
    BUNDLE_ID_TAKEN = "bundle_id_taken"
    BUNDLE_ERROR = "bundle_error"
    CERTIFICATE_ERROR = "certificate_error"

    # Integration: Other
    ENHANCE_PROMPT_ERROR = "enhance_prompt_error"

    # Fork
    INVALID_FORK_SESSION = "invalid_fork_session"
    UNKNOWN_FORK_TYPE = "unknown_fork_type"

    # Design mode
    DESIGN_SYNC_STATE_ERROR = "design_sync_state_error"
    SLIDE_DECK_SYNC_STATE_ERROR = "slide_deck_sync_state_error"


ERROR_MESSAGES: dict[ErrorCode, str] = {
    ErrorCode.VALIDATION_ERROR: "The request payload failed validation.",
    ErrorCode.UNSUPPORTED_API_VERSION: "The requested API version is not supported.",
    ErrorCode.AUTH_ERROR: "Authentication failed. Please sign in again.",
    ErrorCode.SESSION_EXPIRED: "Your session has expired. Please re-authenticate.",
    ErrorCode.SESSION_ERROR: "A session error occurred. Please try again.",
    ErrorCode.RATE_LIMIT: "Too many requests. Please wait and try again.",
    ErrorCode.RUN_NOT_FOUND: "The requested run could not be found.",
    ErrorCode.SESSION_NOT_FOUND: "The requested session could not be found.",
    ErrorCode.PROJECT_NOT_FOUND: "The requested project could not be found.",
    ErrorCode.MISSING_PROJECT_PATH: "No project path is configured for this session.",
    ErrorCode.MISSING_CREDENTIALS: "Required credentials are missing.",
    ErrorCode.DEPLOY_FAILED: "Deployment failed. Check logs for details.",
    ErrorCode.DEPLOY_LINK_FAILED: "Failed to link the deployment to the project.",
    ErrorCode.SANDBOX_CONNECTION_FAILED: "Could not connect to the sandbox environment.",
    ErrorCode.SOURCE_DOWNLOAD_FAILED: "Failed to download source files from the sandbox.",
    ErrorCode.INSUFFICIENT_CREDITS: "Insufficient credits. Please add more credits to continue.",
    ErrorCode.EXECUTION_ERROR: "An error occurred during execution.",
    ErrorCode.UNEXPECTED_ERROR: "An unexpected error occurred. Please try again.",
    ErrorCode.INTERNAL_ERROR: "An internal server error occurred.",
    ErrorCode.CONCURRENT_OPERATION: "Another operation is already in progress for this session.",
    ErrorCode.DUPLICATE_TASK: "This task is already running. Please wait for it to complete.",
    ErrorCode.SANDBOX_ERROR: "A sandbox error occurred.",
    ErrorCode.NAME_TAKEN: "That app name is already taken on App Store Connect.",
    ErrorCode.BUNDLE_ID_TAKEN: "That bundle ID is already registered.",
    ErrorCode.BUNDLE_ERROR: "An error occurred with the app bundle configuration.",
    ErrorCode.CERTIFICATE_ERROR: "A certificate provisioning error occurred.",
    ErrorCode.ENHANCE_PROMPT_ERROR: "Failed to enhance the prompt.",
    ErrorCode.INVALID_FORK_SESSION: "The source session for forking is invalid.",
    ErrorCode.UNKNOWN_FORK_TYPE: "The requested fork type is not supported.",
    ErrorCode.DESIGN_SYNC_STATE_ERROR: "Failed to sync design mode changes.",
    ErrorCode.SLIDE_DECK_SYNC_STATE_ERROR: "Failed to sync slide deck design changes.",
}


class EventGroup(StrEnum):
    """Groups events by functional area for subscription and filtering."""

    AGENT = "agent"
    SESSION = "session"
    CONNECTION = "connection"
    SANDBOX = "sandbox"
    BILLING = "billing"
    PLAN = "plan"
    FILE = "file"
    MEDIA = "media"
    SYSTEM = "system"
    INTEGRATION = "integration"
    METRICS = "metrics"
    # Sub-groups used by A2A adapters
    AGENT_RUN = "agent_run"
    AGENT_TOOL = "agent_tool"
    AGENT_REASONING = "agent_reasoning"


class EventType(StrEnum):
    """Canonical event-type identifiers used by the A2A adapter layer.

    These values are the canonical names for the events that flow through the
    realtime event bus.  They map 1-to-1 to the ``name`` field of
    :class:`BaseEvent` subclasses and are used by :class:`EventStreamAdapter`
    to classify incoming events for A2A SSE translation.
    """

    # System / connection
    CONNECTION_ESTABLISHED = "connection.established"
    STATUS_UPDATE = "status.update"
    AGENT_INITIALIZED = "agent.initialized"
    WORKSPACE_INFO = "workspace.info"
    SANDBOX_STATUS = "sandbox.status"
    STREAM_COMPLETE = "stream.complete"
    ERROR = "error"

    # Agent run lifecycle
    PROCESSING = "agent.processing"
    RUN_CONTENT = "agent.response"
    RUN_INTERRUPTED = "run.interrupted"
    SUB_AGENT_COMPLETED = "sub_agent.completed"

    # Agent reasoning
    REASONING_DELTA = "agent.reasoning_delta"

    # Tool calls
    TOOL_CALL_STARTED = "agent.tool_call"
    TOOL_CALL_COMPLETED = "agent.tool_result"

    # File mutations
    FILE_EDIT = "file.edit"

    # A2A delegation events
    DELEGATION_FALLBACK = "agent.delegation.fallback"


class BaseEvent(BaseModel):
    """Base event on the bus.

    Every event flowing through the :class:`EventBus` is an
    ``ApplicationEvent``.  Subclasses add domain-specific metadata
    (e.g. :class:`AgentEvent` carries ``agent_id``, ``model``, …).

    Required attributes — ``id``, ``group``, ``name`` — are always
    present so that subscribers can route and filter without
    inspecting the ``payload`` dict.
    """

    model_config = ConfigDict(frozen=True)

    id: uuid.UUID = Field(default_factory=uuid.uuid4)

    group: EventGroup

    name: str

    session_id: uuid.UUID | None = None

    user_id: uuid.UUID | None = None

    run_id: uuid.UUID | None = None
    # --- Payload ---
    content: dict[str, Any] = Field(default_factory=dict)

    # --- Timing ---
    timestamp: float = Field(default_factory=time.time)

    # Transient events (deltas, pongs) are dispatched but NOT persisted.
    transient: bool = False

    # Internal events are persisted but NOT broadcast to the frontend.
    internal: bool = False

    metadata: dict[str, Any] = Field(default_factory=dict)

    def to_socket_payload(self) -> dict[str, Any]:
        """Serialise for Socket.IO emission.

        The FE dispatches on ``data.name`` (e.g. ``"agent.response"``).
        ``name`` is already part of the Pydantic model, so no extra
        field is injected.
        """
        return self.model_dump(mode="json", exclude_none=True)


class ApplicationEvent(BaseEvent):
    """Mutable variant of :class:`BaseEvent` for use as a live event DTO.

    Unlike :class:`BaseEvent`, this class is not frozen so its fields can be
    updated after construction.  It is the canonical type used by the A2A
    adapter and event-stream tests.
    """

    model_config = ConfigDict(frozen=False)


class AgentRunEvent(BaseEvent):
    """Extra metadata carried by agent-originated events.

    Use :func:`~ii_agent.agents.factory.converter.convert_agent_event_to_realtime`
    to convert runtime agent events into the correct :class:`BaseEvent` subclass.
    """

    model_config = ConfigDict(frozen=True)

    agent_id: str = ""
    agent_name: str = ""
    model: str | None = None
    run_id: uuid.UUID | None = None
    parent_run_id: uuid.UUID | None = None
    status: RunStatus | None = None

    @classmethod
    def from_agent_output_event(cls, event: RunOutputEvent) -> AgentRunEvent:
        """Convert a runtime agent event to an :class:`AgentEvent`.

        Uses the runtime event's own ``group`` and ``event`` fields,
        and serialises the full dataclass via ``to_dict()`` as content.
        """
        status: RunStatus = getattr(event, "status", None)

        return cls(
            agent_id=event.agent_id,
            group=EventGroup.AGENT,
            name=event.event,
            session_id=event.session_id,
            run_id=event.run_id,
            content=event.to_dict(),
            agent_name=event.agent_name,
            model=event.model,
            status=status,
        )


class AgentStatusUpdateEvent(AgentRunEvent):
    """Generic status update during agent operations (publish, deploy, etc.)."""

    model_config = ConfigDict(frozen=True)

    group: EventGroup = EventGroup.AGENT
    name: Literal["agent.status.update"] = "agent.status.update"
    message: str = ""
    status: str = ""


class AgentInitializedEvent(AgentRunEvent):
    """Agent was created and is ready to process."""

    model_config = ConfigDict(frozen=True)

    group: EventGroup = EventGroup.AGENT
    name: Literal["agent.initialized"] = "agent.initialized"
    agent_type: str = ""
    model_id: str = ""


class AgentProcessingEvent(AgentRunEvent):
    """Agent is actively processing a request."""

    model_config = ConfigDict(frozen=True)

    group: EventGroup = EventGroup.AGENT
    name: Literal["agent.processing"] = "agent.processing"
    message: str = ""


class AgentReasoningStartEvent(AgentRunEvent):
    """Agent started its reasoning phase."""

    model_config = ConfigDict(frozen=True)

    group: EventGroup = EventGroup.AGENT
    name: Literal["agent.reasoning.start"] = "agent.reasoning.start"
    transient: bool = True


class AgentReasoningEvent(AgentRunEvent):
    """Agent thinking content (full block)."""

    model_config = ConfigDict(frozen=True)

    group: EventGroup = EventGroup.AGENT
    name: Literal["agent.reasoning"] = "agent.reasoning"
    transient: bool = False


class AgentReasoningDeltaEvent(AgentRunEvent):
    """Incremental thinking content delta (transient, not persisted)."""

    model_config = ConfigDict(frozen=True)

    group: EventGroup = EventGroup.AGENT
    name: Literal["agent.reasoning.delta"] = "agent.reasoning.delta"
    transient: bool = True


class AgentToolCallEvent(AgentRunEvent):
    """Agent is invoking a tool."""

    model_config = ConfigDict(frozen=True)

    group: EventGroup = EventGroup.AGENT
    name: Literal["agent.tool.call"] = "agent.tool.call"
    tool_name: str = ""
    tool_call_id: str = ""


class AgentToolResultEvent(AgentRunEvent):
    """Tool execution completed with a result."""

    model_config = ConfigDict(frozen=True)

    group: EventGroup = EventGroup.AGENT
    name: Literal["agent.tool.result"] = "agent.tool.result"
    tool_name: str = ""
    tool_call_id: str = ""


class AgentToolConfirmationEvent(AgentRunEvent):
    """Tool requires user confirmation before execution."""

    model_config = ConfigDict(frozen=True)

    group: EventGroup = EventGroup.AGENT
    name: Literal["agent.tool.confirmation"] = "agent.tool.confirmation"
    tool_name: str = ""
    tool_call_id: str = ""


class AgentResponseEvent(AgentRunEvent):
    """Agent produced a final response (full block)."""

    model_config = ConfigDict(frozen=True)

    group: EventGroup = EventGroup.AGENT
    name: Literal["agent.response"] = "agent.response"


class AgentResponseDeltaEvent(AgentRunEvent):
    """Incremental response content delta (transient, not persisted)."""

    model_config = ConfigDict(frozen=True)

    group: EventGroup = EventGroup.AGENT
    name: Literal["agent.response.delta"] = "agent.response.delta"
    transient: bool = True


class AgentResponseInterruptedEvent(AgentRunEvent):
    """Agent response was interrupted (cancelled or aborted)."""

    model_config = ConfigDict(frozen=True)

    group: EventGroup = EventGroup.AGENT
    name: Literal["agent.response.interrupted"] = "agent.response.interrupted"


class AgentStreamCompleteEvent(AgentRunEvent):
    """Agent streaming finished for the current turn."""

    model_config = ConfigDict(frozen=True)

    group: EventGroup = EventGroup.AGENT
    name: Literal["agent.stream.complete"] = "agent.stream.complete"


class AgentCompleteEvent(AgentRunEvent):
    """Agent run completed (final event for a run)."""

    model_config = ConfigDict(frozen=True)

    group: EventGroup = EventGroup.AGENT
    name: Literal["agent.complete"] = "agent.complete"


class SubAgentCompleteEvent(AgentRunEvent):
    """A delegated sub-agent finished its work."""

    model_config = ConfigDict(frozen=True)

    group: EventGroup = EventGroup.AGENT
    name: Literal["agent.sub_agent.complete"] = "agent.sub_agent.complete"
    sub_agent_id: str = ""
    sub_agent_name: str = ""


class AgentModelCompactEvent(AgentRunEvent):
    """Agent context was compacted to stay within token limits."""

    model_config = ConfigDict(frozen=True)

    group: EventGroup = EventGroup.AGENT
    name: Literal["agent.model.compact"] = "agent.model.compact"


class AgentContinueEvent(AgentRunEvent):
    """Agent is continuing execution after a pause or user input."""

    model_config = ConfigDict(frozen=True)

    group: EventGroup = EventGroup.AGENT
    name: Literal["agent.continue"] = "agent.continue"


class AgentPromptGeneratedEvent(AgentRunEvent):
    """An enhanced prompt was generated (e.g. from enhance_prompt)."""

    model_config = ConfigDict(frozen=True)

    group: EventGroup = EventGroup.AGENT
    name: Literal["agent.prompt.generated"] = "agent.prompt.generated"
    prompt: str = ""


class DelegationFallbackEvent(AgentRunEvent):
    """Emitted when the A2A inner loop falls back to native execution.

    Carries the circuit-breaker state and failure counters so the frontend
    can display a warning and the backend can log detailed telemetry.

    The event is **not** transient — it is persisted so that post-hoc analysis
    can identify which sessions experienced A2A instability.
    """

    model_config = ConfigDict(frozen=True)

    group: EventGroup = EventGroup.AGENT
    name: Literal["agent.delegation.fallback"] = "agent.delegation.fallback"
    transient: bool = False
    reason: str = ""
    context_id: str = ""
    circuit_state: str = ""  # CircuitState value
    failure_count: int = 0
    cooldown_remaining: float = 0.0


class CompactionAuthorityEvent(AgentRunEvent):
    """Records which compaction authority is active for a delegated turn.

    Emitted at the start of an A2A-delegated turn so telemetry can attribute
    any subsequent compaction to the correct authority (``native``,
    ``copilot_sdk``, ``claude_code``, or ``codex``).
    """

    model_config = ConfigDict(frozen=True)

    group: EventGroup = EventGroup.AGENT
    name: Literal["agent.compaction.authority"] = "agent.compaction.authority"
    transient: bool = False
    authority: str = ""  # e.g. "native", "copilot_sdk", "claude_code", "codex"
    context_id: str = ""
    compaction_locked: bool = False  # True when ii-agent holds the compaction lock


class CompactionSkippedEvent(AgentRunEvent):
    """Native summarization was skipped because a delegated turn held the lock.

    Persisted for post-hoc analysis of compaction contention.
    """

    model_config = ConfigDict(frozen=True)

    group: EventGroup = EventGroup.AGENT
    name: Literal["agent.compaction.skipped"] = "agent.compaction.skipped"
    transient: bool = False
    reason: str = ""  # e.g. "a2a_lock_held"
    context_id: str = ""


class AgentWarningEvent(AgentRunEvent):
    """Soft warning surfaced from infrastructure into the agent UI.

    Used for non-fatal degradations that the user should know about (a
    subset of tools may be unavailable, a sandbox may be slower than
    usual, etc.) without aborting the run. The frontend can display a
    banner and the backend persists the event for post-hoc telemetry.

    See ``docs/design-docs/sandbox-pool-claim-mcp-handoff-audit.md``
    item #7 for the original motivating case (``mcp_configure_failed``).
    """

    model_config = ConfigDict(frozen=True)

    group: EventGroup = EventGroup.AGENT
    name: Literal["agent.warning"] = "agent.warning"
    transient: bool = False
    warning_kind: str = ""  # e.g. "mcp_configure_failed"
    message: str = ""
    details: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Session events
# ---------------------------------------------------------------------------


class SessionEvent(BaseEvent):
    """Session lifecycle events."""

    model_config = ConfigDict(frozen=True)

    group: EventGroup = EventGroup.SESSION


class SessionCreatedEvent(SessionEvent):
    """A new session was created."""

    name: Literal["session.created"] = "session.created"
    session_name: str = ""
    agent_type: str | None = None
    model_id: str | None = None


class SessionUpdatedEvent(SessionEvent):
    """An existing session was updated."""

    name: Literal["session.updated"] = "session.updated"


class SessionDeletedEvent(SessionEvent):
    """A session was deleted."""

    name: Literal["session.deleted"] = "session.deleted"


class SessionForkedEvent(SessionEvent):
    """A session was forked from another session."""

    name: Literal["session.forked"] = "session.forked"
    source_session_id: uuid.UUID | None = None


class SessionSummaryStartedEvent(SessionEvent):
    """Session summarisation has started."""

    name: Literal["session.summary.started"] = "session.summary.started"


class SessionSummaryCompletedEvent(SessionEvent):
    """Session summarisation completed."""

    name: Literal["session.summary.completed"] = "session.summary.completed"


class UserMessageEvent(SessionEvent):
    """A user sent a message in the session."""

    name: Literal["session.user_message"] = "session.user_message"
    message: str = ""


# ---------------------------------------------------------------------------
# Connection events
# ---------------------------------------------------------------------------


class ConnectionEvent(BaseEvent):
    """Socket.IO connection lifecycle events.

    Most connection events are transient (not persisted to DB).
    """

    model_config = ConfigDict(frozen=True)

    group: EventGroup = EventGroup.CONNECTION
    transient: bool = True
    sid: str | None = None


class ConnectionEstablishedEvent(ConnectionEvent):
    """Client successfully connected via Socket.IO."""

    name: Literal["connection.established"] = "connection.established"


class WorkspaceInfoEvent(ConnectionEvent):
    """Workspace metadata sent after connection."""

    name: Literal["connection.workspace_info"] = "connection.workspace_info"
    transient: bool = False  # persist — used for session reconstruction
    workspace_path: str = ""
    sandbox_id: uuid.UUID | None = None
    sandbox_status: str | None = None


# ---------------------------------------------------------------------------
# Sandbox events
# ---------------------------------------------------------------------------


class SandboxEvent(BaseEvent):
    """Sandbox lifecycle events — provisioning, status changes, teardown."""

    model_config = ConfigDict(frozen=True)

    group: EventGroup = EventGroup.SANDBOX
    sandbox_id: uuid.UUID | None = None
    provider: str | None = None


class SandboxInitializedEvent(SandboxEvent):
    """A sandbox was provisioned and is ready."""

    name: Literal["sandbox.initialized"] = "sandbox.initialized"
    template_id: uuid.UUID | None = None


class SandboxStatusChangedEvent(SandboxEvent):
    """Sandbox status changed (starting -> ready -> paused -> terminated)."""

    name: Literal["sandbox.status_changed"] = "sandbox.status_changed"
    status: Literal["starting", "ready", "paused", "terminated", "error"] = "starting"
    vscode_url: str | None = None
    vnc_url: str | None = None
    # Host-health backpressure flag. True when the integrated host
    # monitor reports WARN or CRIT (``HostHealthState.is_degraded()``).
    # Frontends can surface a banner; payload stays backward-compatible
    # because the field defaults to False.
    degraded: bool = False
    host_state: str | None = None


# ---------------------------------------------------------------------------
# Billing events
# ---------------------------------------------------------------------------


class BillingEvent(BaseEvent):
    """Billing and credit-related events."""

    model_config = ConfigDict(frozen=True)

    group: EventGroup = EventGroup.BILLING


class ModelUsageEvent(BillingEvent):
    """Emitted after each LLM API call with token usage data.

    Published by the agent layer. Consumed by ``CreditUsageHandler``
    for credit deduction. Persisted for audit trail. Not broadcast to frontend.
    """

    setting_id: uuid.UUID
    name: Literal["billing.llm.usage"] = "billing.llm.usage"
    internal: bool = True
    model_id: str = ""
    provider: Provider = Provider.ANTHROPIC
    pricing: PricingInfo | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    reasoning_tokens: int = 0
    is_user_key: bool = False
    # Backend-aware billing: which inner-loop backend served this turn.
    # Values: "native", "a2a:copilot", "a2a:claude-code", "a2a:codex".
    billing_backend: str = "native"
    # Cost reported by the backend itself (e.g. Copilot SDK cost field).
    # Only meaningful when billing_backend != "native".
    provider_reported_cost: float = 0.0
    # Premium requests consumed by this turn (Copilot billing model).
    premium_requests: int = 0


class ToolUsageEvent(BillingEvent):
    """Emitted after a tool execution that incurs a direct USD cost.

    Published by the agent layer. Consumed by ``CreditUsageHandler``
    for credit deduction. Persisted for audit trail. Not broadcast to frontend.
    """

    name: Literal["billing.tool.usage"] = "billing.tool.usage"
    internal: bool = True
    tool_name: str = ""
    cost_usd: float = 0.0


class CreditsDeductedEvent(BillingEvent):
    """Credits were deducted from a user's balance.

    Published by ``CreditUsageHandler`` after a successful deduction.
    Sent to the frontend for real-time balance updates. Persisted for audit.
    """

    name: Literal["billing.credits.deducted"] = "billing.credits.deducted"
    credits_used: float = 0.0
    credits_remaining: float = 0.0
    source: str = "llm_usage"
    # Audit fields
    model_id: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    tool_name: str = ""


class MetricsUpdatedEvent(BillingEvent):
    """Token usage metrics update (transient — streamed but not persisted)."""

    name: Literal["billing.metrics.updated"] = "billing.metrics.updated"
    transient: bool = True
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    model_id: str = ""


# ---------------------------------------------------------------------------
# Plan events
# ---------------------------------------------------------------------------


class PlanEvent(BaseEvent):
    """Events related to the planning system (milestones, plan generation)."""

    model_config = ConfigDict(frozen=True)

    group: EventGroup = EventGroup.PLAN


class PlanGeneratedEvent(PlanEvent):
    """A plan with milestones was generated or updated."""

    name: Literal["plan.milestone.generated"] = "plan.milestone.generated"
    summary: str = ""
    milestones: list[dict[str, Any]] = Field(default_factory=list)


class MilestoneUpdatedEvent(PlanEvent):
    """A milestone's status changed during plan execution."""

    name: Literal["plan.milestone.updated"] = "plan.milestone.updated"
    milestone_id: str = ""
    status: Literal["pending", "in_progress", "completed", "failed"] = "pending"


class PlanModificationOptionsEvent(PlanEvent):
    """Suggested modifications to the current plan."""

    name: Literal["plan.modification.options"] = "plan.modification.options"
    suggestions: list[dict[str, Any]] = Field(default_factory=list)


class PlanWaitingForUserInputEvent(PlanEvent):
    """Plan execution is paused, waiting for user input."""

    name: Literal["plan.input.awaited"] = "plan.input.awaited"
    prompt: str = ""


# ---------------------------------------------------------------------------
# File events
# ---------------------------------------------------------------------------


class FileEvent(BaseEvent):
    """File upload and edit events."""

    model_config = ConfigDict(frozen=True)

    group: EventGroup = EventGroup.FILE


class FileUploadedEvent(FileEvent):
    """A file was uploaded by the user or imported from a connector."""

    name: Literal["file.uploaded"] = "file.uploaded"
    asset_id: uuid.UUID | None = None
    filename: str = ""
    content_type: str = ""
    size_bytes: int = 0


class FileEditedEvent(FileEvent):
    """A file was created, modified, or deleted in the sandbox."""

    name: Literal["file.edited"] = "file.edited"
    file_path: str = ""
    edit_type: Literal["created", "modified", "deleted"] = "modified"


class FileTreeEvent(FileEvent):
    """Full file tree snapshot returned to the client."""

    name: Literal["file.tree.listed"] = "file.tree.listed"
    transient: bool = True


class FileContentEvent(FileEvent):
    """Content of a single file returned to the client."""

    name: Literal["file.content.read"] = "file.content.read"
    transient: bool = True


class FileTreeUpdateEvent(FileEvent):
    """Incremental file tree update pushed by the watcher."""

    name: Literal["file.tree.updated"] = "file.tree.updated"
    transient: bool = True


# ---------------------------------------------------------------------------
# Media events
# ---------------------------------------------------------------------------


class MediaEvent(BaseEvent):
    """Media generation and progress events."""

    model_config = ConfigDict(frozen=True)

    group: EventGroup = EventGroup.MEDIA


class MediaGeneratedEvent(MediaEvent):
    """A media asset (image, video, audio) was generated."""

    name: Literal["media.generated"] = "media.generated"
    media_type: Literal["image", "video", "audio"] = "image"
    asset_id: uuid.UUID | None = None
    url: str | None = None
    provider: str = ""


class MediaProgressEvent(MediaEvent):
    """Progress update during media generation (transient)."""

    name: Literal["media.progress"] = "media.progress"
    transient: bool = True
    progress: float = 0.0
    step: str = ""


class BrowserScreenshotEvent(MediaEvent):
    """A browser screenshot was captured."""

    name: Literal["media.browser_screenshot"] = "media.browser_screenshot"
    url: str | None = None


# ---------------------------------------------------------------------------
# System events
# ---------------------------------------------------------------------------


class SystemEvent(BaseEvent):
    """Infrastructure and system-level events."""

    model_config = ConfigDict(frozen=True)

    group: EventGroup = EventGroup.SYSTEM


class SystemErrorEvent(SystemEvent):
    """A system error occurred."""

    name: Literal["system.error"] = "system.error"
    error_code: ErrorCode = ErrorCode.INTERNAL_ERROR
    detail: str = ""
    recoverable: bool = False


class SystemPongEvent(SystemEvent):
    """Heartbeat pong response (transient)."""

    name: Literal["system.pong"] = "system.pong"
    transient: bool = True


class SystemNotificationEvent(SystemEvent):
    """A system notification for the user."""

    name: Literal["system.notification"] = "system.notification"
    message: str = ""


# ---------------------------------------------------------------------------
# Integration events (Apple, Expo, TestFlight)
# ---------------------------------------------------------------------------


class IntegrationEvent(BaseEvent):
    """External integration events (Apple, Expo, etc.)."""

    model_config = ConfigDict(frozen=True)

    group: EventGroup = EventGroup.INTEGRATION


class AppleAuthStatusEvent(IntegrationEvent):
    """Apple authentication status update."""

    name: Literal["integration.apple.auth.status"] = "integration.apple.auth.status"
    status: Literal["success", "failed", "in_progress"] = "in_progress"
    message: str = ""


class Apple2FARequiredEvent(IntegrationEvent):
    """Apple account requires two-factor authentication."""

    name: Literal["integration.apple.auth.2fa_required"] = "integration.apple.auth.2fa_required"
    message: str = ""


class AppleTeamSelectionEvent(IntegrationEvent):
    """Apple Developer team selection required."""

    name: Literal["integration.apple.auth.team_selection"] = "integration.apple.auth.team_selection"
    teams: list[dict[str, Any]] = Field(default_factory=list)


class AppleAppSetupStatusEvent(IntegrationEvent):
    """Apple app setup/provisioning status update."""

    name: Literal["integration.apple.app.setup_status"] = "integration.apple.app.setup_status"
    status: str = ""
    message: str = ""


class AppleAppsListEvent(IntegrationEvent):
    """List of Apple apps returned for selection."""

    name: Literal["integration.apple.app.list"] = "integration.apple.app.list"
    apps: list[dict[str, Any]] = Field(default_factory=list)


class AppleAuthCheckResultEvent(IntegrationEvent):
    """Result of an Apple authentication check."""

    name: Literal["integration.apple.auth.check_result"] = "integration.apple.auth.check_result"
    authenticated: bool = False


class ExpoTokenSavedEvent(IntegrationEvent):
    """Expo access token was saved successfully."""

    name: Literal["integration.expo.token_saved"] = "integration.expo.token_saved"
    message: str = ""


class TestFlightLogEvent(IntegrationEvent):
    """TestFlight build/upload log entry."""

    name: Literal["integration.testflight.log"] = "integration.testflight.log"
    message: str = ""
    level: Literal["info", "warning", "error"] = "info"


# ---------------------------------------------------------------------------
# Group-level unions — each usable independently via TypeAdapter
# ---------------------------------------------------------------------------

AgentAppEvent: TypeAlias = Union[
    AgentStatusUpdateEvent,
    AgentInitializedEvent,
    AgentProcessingEvent,
    AgentReasoningStartEvent,
    AgentReasoningEvent,
    AgentReasoningDeltaEvent,
    AgentToolCallEvent,
    AgentToolResultEvent,
    AgentToolConfirmationEvent,
    AgentResponseEvent,
    AgentResponseDeltaEvent,
    AgentResponseInterruptedEvent,
    AgentStreamCompleteEvent,
    AgentCompleteEvent,
    SubAgentCompleteEvent,
    AgentModelCompactEvent,
    AgentContinueEvent,
    AgentPromptGeneratedEvent,
    DelegationFallbackEvent,
    CompactionAuthorityEvent,
    CompactionSkippedEvent,
    AgentWarningEvent,
]

SessionAppEvent: TypeAlias = Union[
    SessionCreatedEvent,
    SessionUpdatedEvent,
    SessionDeletedEvent,
    SessionForkedEvent,
    SessionSummaryStartedEvent,
    SessionSummaryCompletedEvent,
    UserMessageEvent,
]

ConnectionAppEvent: TypeAlias = Union[
    ConnectionEstablishedEvent,
    WorkspaceInfoEvent,
]

SandboxAppEvent: TypeAlias = Union[
    SandboxInitializedEvent,
    SandboxStatusChangedEvent,
]

BillingAppEvent: TypeAlias = Union[
    ModelUsageEvent,
    ToolUsageEvent,
    CreditsDeductedEvent,
    MetricsUpdatedEvent,
]

PlanAppEvent: TypeAlias = Union[
    PlanGeneratedEvent,
    MilestoneUpdatedEvent,
    PlanModificationOptionsEvent,
    PlanWaitingForUserInputEvent,
]

FileAppEvent: TypeAlias = Union[
    FileUploadedEvent,
    FileEditedEvent,
    FileTreeEvent,
    FileContentEvent,
    FileTreeUpdateEvent,
]

MediaAppEvent: TypeAlias = Union[
    MediaGeneratedEvent,
    MediaProgressEvent,
    BrowserScreenshotEvent,
]

SystemAppEvent: TypeAlias = Union[
    SystemErrorEvent,
    SystemPongEvent,
    SystemNotificationEvent,
]

MobileAppEvent: TypeAlias = Union[
    AppleAuthStatusEvent,
    Apple2FARequiredEvent,
    AppleTeamSelectionEvent,
    AppleAppSetupStatusEvent,
    AppleAppsListEvent,
    AppleAuthCheckResultEvent,
    ExpoTokenSavedEvent,
    TestFlightLogEvent,
]

# ---------------------------------------------------------------------------
# Top-level discriminated union — Python flattens nested Unions automatically
# ---------------------------------------------------------------------------

AppEvent = Annotated[
    Union[
        AgentAppEvent,
        SessionAppEvent,
        ConnectionAppEvent,
        SandboxAppEvent,
        BillingAppEvent,
        PlanAppEvent,
        FileAppEvent,
        MediaAppEvent,
        SystemAppEvent,
        MobileAppEvent,
    ],
    Field(discriminator="name"),
]
