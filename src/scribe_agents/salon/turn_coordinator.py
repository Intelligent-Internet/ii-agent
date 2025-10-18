"""Turn Coordinator - Manages turn-taking strategies for salon conversations.

This module implements various turn scheduling strategies (round-robin, priority-based,
debate-style) and coordinates which participant speaks next.
"""

from enum import Enum
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
import random
import logging

logger = logging.getLogger(__name__)


class TurnStrategy(str, Enum):
    """Turn-taking strategies for different conversation modes."""

    ROUND_ROBIN = "round_robin"  # Sequential, each participant gets equal turns
    PRIORITY = "priority"  # Based on participant priority/expertise
    DEBATE = "debate"  # Alternating positions with rebuttal rounds
    FREE_FORM = "free_form"  # Participants can speak when they have something to add
    MODERATED = "moderated"  # Moderator explicitly assigns turns
    RANDOM = "random"  # Random selection (for brainstorming)


@dataclass
class Turn:
    """Represents a turn assignment for a participant."""

    participant_id: str
    turn_number: int
    strategy: TurnStrategy
    expected_duration_seconds: Optional[int] = None
    rebuttal_to: Optional[str] = None  # For debate mode
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class TurnCoordinator:
    """Coordinates turn-taking between salon participants.

    Implements multiple turn strategies and tracks turn history
    to ensure fair distribution of speaking opportunities.
    """

    def __init__(
        self,
        participants: List[str],
        strategy: TurnStrategy = TurnStrategy.ROUND_ROBIN,
        moderator_id: Optional[str] = None,
    ):
        """Initialize turn coordinator.

        Args:
            participants: List of participant IDs
            strategy: Turn-taking strategy to use
            moderator_id: Optional moderator ID (for moderated strategy)
        """
        self.participants = participants
        self.strategy = strategy
        self.moderator_id = moderator_id

        # Track turn history
        self.turn_count = 0
        self.turn_history: List[Turn] = []
        self.participant_turn_counts: Dict[str, int] = {
            p: 0 for p in participants
        }

        # Strategy-specific state
        self._round_robin_index = 0
        self._debate_side_a: List[str] = []
        self._debate_side_b: List[str] = []
        self._priority_scores: Dict[str, float] = {p: 1.0 for p in participants}

        logger.info(
            f"Initialized TurnCoordinator with {len(participants)} participants, "
            f"strategy={strategy}"
        )

    def get_next_turn(self, context: Optional[Dict[str, Any]] = None) -> Turn:
        """Get the next turn assignment based on the current strategy.

        Args:
            context: Optional context (e.g., last speaker, topic, etc.)

        Returns:
            Turn assignment for the next participant
        """
        if self.strategy == TurnStrategy.ROUND_ROBIN:
            participant_id = self._next_round_robin()
        elif self.strategy == TurnStrategy.DEBATE:
            participant_id = self._next_debate(context)
        elif self.strategy == TurnStrategy.PRIORITY:
            participant_id = self._next_priority()
        elif self.strategy == TurnStrategy.RANDOM:
            participant_id = self._next_random()
        elif self.strategy == TurnStrategy.MODERATED:
            # For moderated, this should be called with explicit participant_id
            # Default to moderator
            participant_id = self.moderator_id or self.participants[0]
        elif self.strategy == TurnStrategy.FREE_FORM:
            # Free form doesn't strictly assign turns, return next available
            participant_id = self._next_available()
        else:
            participant_id = self._next_round_robin()

        turn = Turn(
            participant_id=participant_id,
            turn_number=self.turn_count,
            strategy=self.strategy,
        )

        self._record_turn(turn)
        return turn

    def assign_turn(self, participant_id: str) -> Turn:
        """Explicitly assign a turn to a specific participant.

        Used for moderated strategy or manual intervention.

        Args:
            participant_id: ID of participant to assign turn to

        Returns:
            Turn assignment
        """
        if participant_id not in self.participants:
            raise ValueError(f"Participant {participant_id} not in salon")

        turn = Turn(
            participant_id=participant_id,
            turn_number=self.turn_count,
            strategy=TurnStrategy.MODERATED,
        )

        self._record_turn(turn)
        return turn

    def setup_debate(self, side_a: List[str], side_b: List[str]):
        """Configure debate mode with two sides.

        Args:
            side_a: Participant IDs for side A
            side_b: Participant IDs for side B
        """
        if self.strategy != TurnStrategy.DEBATE:
            logger.warning("Setting up debate sides for non-debate strategy")

        self._debate_side_a = side_a
        self._debate_side_b = side_b
        logger.info(f"Debate configured: {len(side_a)} vs {len(side_b)} participants")

    def set_priority(self, participant_id: str, priority: float):
        """Set priority score for a participant (for priority strategy).

        Args:
            participant_id: Participant to set priority for
            priority: Priority score (higher = more turns)
        """
        if participant_id not in self.participants:
            raise ValueError(f"Participant {participant_id} not in salon")

        self._priority_scores[participant_id] = priority
        logger.debug(f"Set priority for {participant_id}: {priority}")

    def get_turn_statistics(self) -> Dict[str, Any]:
        """Get statistics about turn distribution.

        Returns:
            Dictionary with turn statistics
        """
        total_turns = sum(self.participant_turn_counts.values())
        avg_turns = total_turns / len(self.participants) if self.participants else 0

        return {
            "total_turns": total_turns,
            "participant_turn_counts": self.participant_turn_counts.copy(),
            "average_turns_per_participant": avg_turns,
            "strategy": self.strategy,
            "fairness_variance": self._calculate_fairness_variance(),
        }

    def _next_round_robin(self) -> str:
        """Get next participant in round-robin order."""
        participant = self.participants[self._round_robin_index]
        self._round_robin_index = (self._round_robin_index + 1) % len(self.participants)
        return participant

    def _next_debate(self, context: Optional[Dict[str, Any]] = None) -> str:
        """Get next participant for debate mode.

        Alternates between sides, allowing for rebuttals.
        """
        if not self._debate_side_a or not self._debate_side_b:
            # Not configured, fall back to round-robin
            return self._next_round_robin()

        # Determine which side should speak next
        side_a_turns = sum(
            self.participant_turn_counts[p] for p in self._debate_side_a
        )
        side_b_turns = sum(
            self.participant_turn_counts[p] for p in self._debate_side_b
        )

        if side_a_turns <= side_b_turns:
            # Side A's turn
            side = self._debate_side_a
        else:
            # Side B's turn
            side = self._debate_side_b

        # Within the side, use round-robin or least-used
        participant = min(side, key=lambda p: self.participant_turn_counts[p])
        return participant

    def _next_priority(self) -> str:
        """Get next participant based on priority scores.

        Uses weighted random selection based on priority and
        recent participation (to maintain some fairness).
        """
        # Adjust priorities based on recent participation
        adjusted_scores = {}
        for p in self.participants:
            base_priority = self._priority_scores[p]
            turn_count = self.participant_turn_counts[p]
            # Reduce priority for participants who have spoken more
            adjusted = base_priority / (1 + turn_count * 0.1)
            adjusted_scores[p] = adjusted

        # Weighted random selection
        total_score = sum(adjusted_scores.values())
        rand = random.random() * total_score

        cumulative = 0
        for participant, score in adjusted_scores.items():
            cumulative += score
            if rand <= cumulative:
                return participant

        return self.participants[0]  # Fallback

    def _next_random(self) -> str:
        """Get random participant."""
        return random.choice(self.participants)

    def _next_available(self) -> str:
        """Get next available participant (least recent turns)."""
        return min(self.participants, key=lambda p: self.participant_turn_counts[p])

    def _record_turn(self, turn: Turn):
        """Record a turn in history."""
        self.turn_history.append(turn)
        self.participant_turn_counts[turn.participant_id] += 1
        self.turn_count += 1
        logger.debug(
            f"Turn {self.turn_count} assigned to {turn.participant_id} "
            f"(total: {self.participant_turn_counts[turn.participant_id]})"
        )

    def _calculate_fairness_variance(self) -> float:
        """Calculate variance in turn distribution (lower = more fair)."""
        if not self.participants:
            return 0.0

        counts = list(self.participant_turn_counts.values())
        mean = sum(counts) / len(counts)
        variance = sum((c - mean) ** 2 for c in counts) / len(counts)
        return variance
