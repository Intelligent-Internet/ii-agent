"""Unit tests for event types and event handling."""

import pytest

from ii_agent.core.event import EventType


class TestEventTypesEnum:
    """Tests for EventType enum values."""

    def test_sub_agent_complete_exists(self):
        """SUB_AGENT_COMPLETE event type should exist."""
        assert hasattr(EventType, "SUB_AGENT_COMPLETE")
        assert EventType.SUB_AGENT_COMPLETE.value == "sub_agent_complete"

    def test_sub_agent_interrupted_exists(self):
        """SUB_AGENT_INTERRUPTED event type should exist for interrupt handling."""
        assert hasattr(EventType, "SUB_AGENT_INTERRUPTED")
        assert EventType.SUB_AGENT_INTERRUPTED.value == "sub_agent_interrupted"

    def test_sub_agent_interrupted_is_allowed_when_aborted(self):
        """SUB_AGENT_INTERRUPTED should be allowed when session is aborted."""
        assert EventType.is_allowed_when_aborted(EventType.SUB_AGENT_INTERRUPTED)

    def test_agent_response_interrupted_is_allowed_when_aborted(self):
        """AGENT_RESPONSE_INTERRUPTED should be allowed when session is aborted."""
        assert EventType.is_allowed_when_aborted(EventType.AGENT_RESPONSE_INTERRUPTED)

    def test_stream_complete_is_allowed_when_aborted(self):
        """STREAM_COMPLETE should be allowed when session is aborted."""
        assert EventType.is_allowed_when_aborted(EventType.STREAM_COMPLETE)

    def test_connection_established_is_allowed_when_aborted(self):
        """CONNECTION_ESTABLISHED should be allowed when session is aborted."""
        assert EventType.is_allowed_when_aborted(EventType.CONNECTION_ESTABLISHED)


class TestEventTypeIsAllowedWhenAborted:
    """Tests for the is_allowed_when_aborted static method."""

    def test_returns_true_for_allowed_events(self):
        """is_allowed_when_aborted should return True for allowed events."""
        allowed_events = [
            EventType.STATUS_UPDATE,
            EventType.SYSTEM,
            EventType.ERROR,
            EventType.PONG,
            EventType.STREAM_COMPLETE,
            EventType.CONNECTION_ESTABLISHED,
            EventType.AGENT_RESPONSE_INTERRUPTED,
            EventType.SUB_AGENT_INTERRUPTED,
            EventType.WORKSPACE_INFO,
            EventType.SANDBOX_STATUS,
        ]
        
        for event_type in allowed_events:
            assert EventType.is_allowed_when_aborted(event_type), f"{event_type} should be allowed when aborted"

    def test_returns_false_for_regular_events(self):
        """is_allowed_when_aborted should return False for regular events."""
        regular_events = [
            EventType.AGENT_RESPONSE,
            EventType.TOOL_CALL,
            EventType.TOOL_RESULT,
            EventType.FILE_EDIT,
        ]
        
        for event_type in regular_events:
            assert not EventType.is_allowed_when_aborted(event_type), f"{event_type} should NOT be allowed when aborted"

