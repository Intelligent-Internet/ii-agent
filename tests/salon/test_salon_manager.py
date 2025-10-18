"""
Unit tests for SalonManager.

TODO: Implement full test suite
"""

import pytest
from scribe_agents.salon import SalonManager, SalonMode, SalonState
from scribe_agents.salon.salon_personas import SalonTopic


def test_salon_manager_initialization():
    """Test basic salon manager initialization."""
    topic = SalonTopic(
        id="test-topic-1",
        question="How to optimize API performance?",
        context="Web application with high traffic",
    )

    manager = SalonManager(
        salon_id="test-salon-1",
        mode=SalonMode.DISCUSSION,
        topic=topic,
        participants=["participant-1", "participant-2", "participant-3"],
    )

    assert manager.salon_id == "test-salon-1"
    assert manager.mode == SalonMode.DISCUSSION
    assert manager.state == SalonState.INITIALIZING
    assert len(manager.participants) == 3


def test_salon_manager_start():
    """Test starting a salon."""
    topic = SalonTopic(
        id="test-topic-1",
        question="Test question",
        context="Test context",
    )

    manager = SalonManager(
        salon_id="test-salon-1",
        mode=SalonMode.DISCUSSION,
        topic=topic,
        participants=["p1", "p2"],
    )

    manager.start()
    assert manager.state == SalonState.ACTIVE
    assert manager.current_turn == 0


def test_salon_manager_add_message():
    """Test adding messages to salon."""
    topic = SalonTopic(
        id="test-topic-1",
        question="Test question",
        context="Test context",
    )

    manager = SalonManager(
        salon_id="test-salon-1",
        mode=SalonMode.DISCUSSION,
        topic=topic,
        participants=["p1", "p2"],
    )

    manager.start()
    manager.add_message(
        participant_id="p1",
        content="This is a test message",
        metadata={},
    )

    messages = manager.get_messages()
    assert len(messages) == 1
    assert messages[0].participant_id == "p1"
    assert messages[0].content == "This is a test message"


# TODO: Add more comprehensive tests:
# - test_salon_manager_pause_resume
# - test_salon_manager_complete
# - test_salon_manager_advance_turn
# - test_salon_manager_get_statistics
# - test_salon_manager_format_conversation_history
# - test_salon_manager_export_conversation
# - test_salon_manager_mode_switching
# - test_salon_manager_error_states
