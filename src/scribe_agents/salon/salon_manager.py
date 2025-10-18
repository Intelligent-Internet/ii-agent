"""Salon Manager - Conversation state machine for multi-LLM salons.

This module manages the overall state and lifecycle of a salon conversation,
coordinating between participants, managing turns, and tracking conversation history.
"""

from enum import Enum
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
import logging
import uuid

logger = logging.getLogger(__name__)


class SalonMode(str, Enum):
    """Conversation modes with different turn-taking and interaction patterns."""

    DEBATE = "debate"  # Adversarial, moderated turns with rebuttals
    DISCUSSION = "discussion"  # Collaborative exploration, free-form
    PANEL = "panel"  # Expert Q&A with moderator routing questions
    CONSENSUS = "consensus"  # Agreement-seeking with synthesis
    BRAINSTORM = "brainstorm"  # Rapid idea generation, minimal structure


class SalonState(str, Enum):
    """State of the salon conversation."""

    INITIALIZING = "initializing"
    ACTIVE = "active"
    PAUSED = "paused"
    CONSENSUS_BUILDING = "consensus_building"
    COMPLETED = "completed"
    ERROR = "error"


@dataclass
class SalonMessage:
    """A single message in the salon conversation."""

    id: str
    participant_id: str
    content: str
    timestamp: datetime
    turn_number: int
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SalonTopic:
    """Topic or question being discussed in the salon."""

    id: str
    question: str
    context: Optional[str] = None
    subtopics: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)


class SalonManager:
    """Manages the state and lifecycle of a multi-LLM salon conversation.

    Responsibilities:
    - Initialize and configure salon sessions
    - Track participants and their state
    - Manage conversation history
    - Coordinate with turn_coordinator for turn scheduling
    - Interface with consensus_engine for agreement detection
    - Handle pause/resume/completion lifecycle
    """

    def __init__(
        self,
        salon_id: str,
        mode: SalonMode,
        topic: SalonTopic,
        participants: List[str],
        moderator_id: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
    ):
        """Initialize a salon session.

        Args:
            salon_id: Unique identifier for this salon
            mode: Conversation mode (debate, discussion, etc.)
            topic: Topic or question being discussed
            participants: List of participant IDs
            moderator_id: Optional moderator participant ID
            config: Optional configuration overrides
        """
        self.salon_id = salon_id
        self.mode = mode
        self.topic = topic
        self.participants = participants
        self.moderator_id = moderator_id
        self.config = config or {}

        # State management
        self.state = SalonState.INITIALIZING
        self.current_turn = 0
        self.messages: List[SalonMessage] = []
        self.participant_stats: Dict[str, Dict[str, Any]] = {}

        # Timing
        self.started_at: Optional[datetime] = None
        self.completed_at: Optional[datetime] = None

        # Initialize participant stats
        for participant_id in participants:
            self.participant_stats[participant_id] = {
                "turn_count": 0,
                "total_characters": 0,
                "last_message_at": None,
            }

        logger.info(
            f"Initialized salon {salon_id} with mode={mode}, "
            f"{len(participants)} participants"
        )

    def start(self):
        """Start the salon conversation."""
        if self.state != SalonState.INITIALIZING:
            raise ValueError(f"Cannot start salon in state {self.state}")

        self.state = SalonState.ACTIVE
        self.started_at = datetime.utcnow()
        logger.info(f"Started salon {self.salon_id}")

    def pause(self):
        """Pause the salon conversation."""
        if self.state != SalonState.ACTIVE:
            raise ValueError(f"Cannot pause salon in state {self.state}")

        self.state = SalonState.PAUSED
        logger.info(f"Paused salon {self.salon_id}")

    def resume(self):
        """Resume a paused salon conversation."""
        if self.state != SalonState.PAUSED:
            raise ValueError(f"Cannot resume salon in state {self.state}")

        self.state = SalonState.ACTIVE
        logger.info(f"Resumed salon {self.salon_id}")

    def complete(self):
        """Mark the salon as completed."""
        if self.state not in [SalonState.ACTIVE, SalonState.CONSENSUS_BUILDING]:
            logger.warning(f"Completing salon from state {self.state}")

        self.state = SalonState.COMPLETED
        self.completed_at = datetime.utcnow()
        logger.info(f"Completed salon {self.salon_id}")

    def add_message(
        self,
        participant_id: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SalonMessage:
        """Add a message from a participant.

        Args:
            participant_id: ID of the participant sending the message
            content: Message content
            metadata: Optional metadata (voice data, confidence, etc.)

        Returns:
            The created SalonMessage
        """
        if participant_id not in self.participants:
            raise ValueError(f"Participant {participant_id} not in salon")

        message = SalonMessage(
            id=str(uuid.uuid4()),
            participant_id=participant_id,
            content=content,
            timestamp=datetime.utcnow(),
            turn_number=self.current_turn,
            metadata=metadata or {},
        )

        self.messages.append(message)

        # Update stats
        stats = self.participant_stats[participant_id]
        stats["turn_count"] += 1
        stats["total_characters"] += len(content)
        stats["last_message_at"] = message.timestamp

        logger.debug(
            f"Added message from {participant_id} (turn {self.current_turn})"
        )

        return message

    def advance_turn(self):
        """Advance to the next turn."""
        self.current_turn += 1
        logger.debug(f"Advanced to turn {self.current_turn}")

    def get_messages(
        self,
        participant_id: Optional[str] = None,
        since_turn: Optional[int] = None,
    ) -> List[SalonMessage]:
        """Get messages, optionally filtered.

        Args:
            participant_id: Filter by participant ID
            since_turn: Only return messages from this turn onward

        Returns:
            List of SalonMessages
        """
        messages = self.messages

        if participant_id:
            messages = [m for m in messages if m.participant_id == participant_id]

        if since_turn is not None:
            messages = [m for m in messages if m.turn_number >= since_turn]

        return messages

    def get_conversation_history(self, max_turns: Optional[int] = None) -> str:
        """Get formatted conversation history.

        Args:
            max_turns: Optional limit on number of recent turns to include

        Returns:
            Formatted conversation history as string
        """
        messages = self.messages
        if max_turns:
            # Get messages from recent turns
            min_turn = max(0, self.current_turn - max_turns)
            messages = [m for m in messages if m.turn_number >= min_turn]

        history_lines = []
        for msg in messages:
            timestamp = msg.timestamp.strftime("%H:%M:%S")
            history_lines.append(
                f"[{timestamp}] {msg.participant_id}: {msg.content}"
            )

        return "\n".join(history_lines)

    def get_statistics(self) -> Dict[str, Any]:
        """Get salon statistics.

        Returns:
            Dictionary with statistics
        """
        duration = None
        if self.started_at:
            end_time = self.completed_at or datetime.utcnow()
            duration = (end_time - self.started_at).total_seconds()

        return {
            "salon_id": self.salon_id,
            "mode": self.mode,
            "state": self.state,
            "total_turns": self.current_turn,
            "total_messages": len(self.messages),
            "participant_count": len(self.participants),
            "duration_seconds": duration,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "participant_stats": self.participant_stats,
        }

    def to_dict(self) -> Dict[str, Any]:
        """Export salon state to dictionary.

        Returns:
            Dictionary representation of salon state
        """
        return {
            "salon_id": self.salon_id,
            "mode": self.mode.value,
            "state": self.state.value,
            "topic": {
                "id": self.topic.id,
                "question": self.topic.question,
                "context": self.topic.context,
                "subtopics": self.topic.subtopics,
            },
            "participants": self.participants,
            "moderator_id": self.moderator_id,
            "current_turn": self.current_turn,
            "message_count": len(self.messages),
            "statistics": self.get_statistics(),
        }
