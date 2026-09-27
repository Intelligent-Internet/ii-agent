"""Tests for AppEvent discriminated union.

Validates that:
- Every concrete event in the union can be parsed via TypeAdapter
- The discriminator field ``name`` routes to the correct subclass
- Invalid/unknown names are rejected
- Events round-trip through model_dump → validate_python
"""

from __future__ import annotations

import uuid

import pytest
from pydantic import TypeAdapter, ValidationError

from ii_agent.realtime.events.app_events import (
    AgentAppEvent,
    AppEvent,
    BillingAppEvent,
    ConnectionAppEvent,
    FileAppEvent,
    MediaAppEvent,
    MobileAppEvent,
    PlanAppEvent,
    SandboxAppEvent,
    SessionAppEvent,
    SystemAppEvent,
    AgentCompleteEvent,
    AgentContinueEvent,
    AgentInitializedEvent,
    AgentModelCompactEvent,
    AgentProcessingEvent,
    AgentPromptGeneratedEvent,
    AgentResponseDeltaEvent,
    AgentResponseEvent,
    AgentResponseInterruptedEvent,
    AgentStatusUpdateEvent,
    AgentStreamCompleteEvent,
    AgentReasoningDeltaEvent,
    AgentReasoningEvent,
    AgentReasoningStartEvent,
    AgentToolCallEvent,
    AgentToolConfirmationEvent,
    AgentToolResultEvent,
    CompactionAuthorityEvent,
    CompactionSkippedEvent,
    DelegationFallbackEvent,
    Apple2FARequiredEvent,
    AppleAppSetupStatusEvent,
    AppleAppsListEvent,
    AppleAuthCheckResultEvent,
    AppleAuthStatusEvent,
    AppleTeamSelectionEvent,
    BrowserScreenshotEvent,
    ConnectionEstablishedEvent,
    CreditsDeductedEvent,
    ExpoTokenSavedEvent,
    FileEditedEvent,
    FileUploadedEvent,
    MediaGeneratedEvent,
    MediaProgressEvent,
    MetricsUpdatedEvent,
    MilestoneUpdatedEvent,
    PlanGeneratedEvent,
    PlanModificationOptionsEvent,
    PlanWaitingForUserInputEvent,
    SandboxInitializedEvent,
    SandboxStatusChangedEvent,
    SessionCreatedEvent,
    SessionDeletedEvent,
    SessionForkedEvent,
    SessionSummaryCompletedEvent,
    SessionSummaryStartedEvent,
    SubAgentCompleteEvent,
    SystemErrorEvent,
    SystemNotificationEvent,
    SystemPongEvent,
    TestFlightLogEvent,
    UserMessageEvent,
    WorkspaceInfoEvent,
)

adapter = TypeAdapter(AppEvent)

# All concrete event classes in the union with their expected name
CONCRETE_EVENTS: list[tuple[type, str]] = [
    (AgentStatusUpdateEvent, "agent.status.update"),
    (AgentInitializedEvent, "agent.initialized"),
    (AgentProcessingEvent, "agent.processing"),
    (AgentReasoningStartEvent, "agent.reasoning.start"),
    (AgentReasoningEvent, "agent.reasoning"),
    (AgentReasoningDeltaEvent, "agent.reasoning.delta"),
    (AgentToolCallEvent, "agent.tool.call"),
    (AgentToolResultEvent, "agent.tool.result"),
    (AgentToolConfirmationEvent, "agent.tool.confirmation"),
    (AgentResponseEvent, "agent.response"),
    (AgentResponseDeltaEvent, "agent.response.delta"),
    (AgentResponseInterruptedEvent, "agent.response.interrupted"),
    (AgentStreamCompleteEvent, "agent.stream.complete"),
    (AgentCompleteEvent, "agent.complete"),
    (SubAgentCompleteEvent, "agent.sub_agent.complete"),
    (AgentModelCompactEvent, "agent.model.compact"),
    (AgentContinueEvent, "agent.continue"),
    (AgentPromptGeneratedEvent, "agent.prompt.generated"),
    (DelegationFallbackEvent, "agent.delegation.fallback"),
    (CompactionAuthorityEvent, "agent.compaction.authority"),
    (CompactionSkippedEvent, "agent.compaction.skipped"),
    (SessionCreatedEvent, "session.created"),
    (SessionDeletedEvent, "session.deleted"),
    (SessionForkedEvent, "session.forked"),
    (SessionSummaryStartedEvent, "session.summary.started"),
    (SessionSummaryCompletedEvent, "session.summary.completed"),
    (UserMessageEvent, "session.user_message"),
    (ConnectionEstablishedEvent, "connection.established"),
    (WorkspaceInfoEvent, "connection.workspace_info"),
    (SandboxInitializedEvent, "sandbox.initialized"),
    (SandboxStatusChangedEvent, "sandbox.status_changed"),
    (CreditsDeductedEvent, "billing.credits.deducted"),
    (MetricsUpdatedEvent, "billing.metrics.updated"),
    (PlanGeneratedEvent, "plan.milestone.generated"),
    (MilestoneUpdatedEvent, "plan.milestone.updated"),
    (PlanModificationOptionsEvent, "plan.modification.options"),
    (PlanWaitingForUserInputEvent, "plan.input.awaited"),
    (FileUploadedEvent, "file.uploaded"),
    (FileEditedEvent, "file.edited"),
    (MediaGeneratedEvent, "media.generated"),
    (MediaProgressEvent, "media.progress"),
    (BrowserScreenshotEvent, "media.browser_screenshot"),
    (SystemErrorEvent, "system.error"),
    (SystemPongEvent, "system.pong"),
    (SystemNotificationEvent, "system.notification"),
    (AppleAuthStatusEvent, "integration.apple.auth.status"),
    (Apple2FARequiredEvent, "integration.apple.auth.2fa_required"),
    (AppleTeamSelectionEvent, "integration.apple.auth.team_selection"),
    (AppleAppSetupStatusEvent, "integration.apple.app.setup_status"),
    (AppleAppsListEvent, "integration.apple.app.list"),
    (AppleAuthCheckResultEvent, "integration.apple.auth.check_result"),
    (ExpoTokenSavedEvent, "integration.expo.token_saved"),
    (TestFlightLogEvent, "integration.testflight.log"),
]

# SessionUpdatedEvent is also in the union but not in EventType enum — add it separately
CONCRETE_EVENTS.append(
    (
        __import__(
            "ii_agent.realtime.events.app_events", fromlist=["SessionUpdatedEvent"]
        ).SessionUpdatedEvent,
        "session.updated",
    ),
)


class TestAppEventDiscriminator:
    """AppEvent union correctly routes on ``name`` discriminator."""

    @pytest.mark.parametrize(
        "cls,name",
        CONCRETE_EVENTS,
        ids=[name for _, name in CONCRETE_EVENTS],
    )
    def test_parse_by_name_returns_correct_type(self, cls: type, name: str) -> None:
        """Given a dict with the correct ``name``, parsing produces the right class."""
        data = {"name": name, "group": cls.model_fields["group"].default}
        result = adapter.validate_python(data)
        assert isinstance(result, cls)
        assert result.name == name

    @pytest.mark.parametrize(
        "cls,name",
        CONCRETE_EVENTS,
        ids=[name for _, name in CONCRETE_EVENTS],
    )
    def test_round_trip(self, cls: type, name: str) -> None:
        """An event model_dump → validate_python round-trips to the same type."""
        event = cls(group=cls.model_fields["group"].default, session_id=uuid.uuid4())
        dumped = event.model_dump(mode="json")
        restored = adapter.validate_python(dumped)
        assert type(restored) is type(event)
        assert restored.name == event.name

    def test_rejects_unknown_name(self) -> None:
        with pytest.raises(ValidationError):
            adapter.validate_python({"name": "nonexistent.event", "group": "system"})

    def test_rejects_base_event_name(self) -> None:
        """BaseEvent with a bare string name (no Literal) cannot be parsed via AppEvent."""
        with pytest.raises(ValidationError):
            adapter.validate_python({"name": "some.random.event", "group": "agent"})


class TestToSocketPayload:
    """to_socket_payload() uses ``name`` as the FE dispatch key."""

    def test_payload_contains_name(self) -> None:
        event = AgentResponseEvent(group="agent", session_id=uuid.uuid4(), content={"text": "hi"})
        payload = event.to_socket_payload()
        assert payload["name"] == "agent.response"
        assert "type" not in payload

    def test_payload_excludes_none_fields(self) -> None:
        event = SystemPongEvent(group="system")
        payload = event.to_socket_payload()
        assert "session_id" not in payload
        assert "user_id" not in payload


# ---------------------------------------------------------------------------
# Group-level union tests
# ---------------------------------------------------------------------------

# Map each group TypeAlias to (sample_name, expected_class)
GROUP_CASES: list[tuple[str, type, str, type]] = [
    ("AgentAppEvent", AgentAppEvent, "agent.response", AgentResponseEvent),
    ("SessionAppEvent", SessionAppEvent, "session.created", SessionCreatedEvent),
    (
        "ConnectionAppEvent",
        ConnectionAppEvent,
        "connection.established",
        ConnectionEstablishedEvent,
    ),
    ("SandboxAppEvent", SandboxAppEvent, "sandbox.status_changed", SandboxStatusChangedEvent),
    ("BillingAppEvent", BillingAppEvent, "billing.credits.deducted", CreditsDeductedEvent),
    ("PlanAppEvent", PlanAppEvent, "plan.milestone.generated", PlanGeneratedEvent),
    ("FileAppEvent", FileAppEvent, "file.uploaded", FileUploadedEvent),
    ("MediaAppEvent", MediaAppEvent, "media.browser_screenshot", BrowserScreenshotEvent),
    ("SystemAppEvent", SystemAppEvent, "system.error", SystemErrorEvent),
    ("MobileAppEvent", MobileAppEvent, "integration.testflight.log", TestFlightLogEvent),
]


class TestGroupUnions:
    """Each group-level TypeAlias can be used independently via TypeAdapter."""

    @pytest.mark.parametrize(
        "alias_name,alias,sample_name,expected_cls",
        GROUP_CASES,
        ids=[name for name, *_ in GROUP_CASES],
    )
    def test_group_adapter_parses_member(
        self, alias_name: str, alias: type, sample_name: str, expected_cls: type
    ) -> None:
        ta = TypeAdapter(alias)
        group_val = expected_cls.model_fields["group"].default
        result = ta.validate_python({"name": sample_name, "group": group_val})
        assert isinstance(result, expected_cls)

    @pytest.mark.parametrize(
        "alias_name,alias,sample_name,expected_cls",
        GROUP_CASES,
        ids=[name for name, *_ in GROUP_CASES],
    )
    def test_group_rejects_wrong_group_member(
        self, alias_name: str, alias: type, sample_name: str, expected_cls: type
    ) -> None:
        """A group union rejects events that belong to a different group."""
        ta = TypeAdapter(alias)
        with pytest.raises(ValidationError):
            ta.validate_python({"name": "nonexistent.event", "group": "system"})
