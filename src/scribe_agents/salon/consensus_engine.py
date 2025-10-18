"""Consensus Engine - Detects agreement and synthesizes common ground.

This module analyzes salon conversation to detect when participants
reach consensus, areas of agreement, and synthesize common positions.
"""

from enum import Enum
from typing import List, Dict, Optional, Any, Set
from dataclasses import dataclass, field
from datetime import datetime
import logging
import re

logger = logging.getLogger(__name__)


class ConsensusLevel(str, Enum):
    """Level of consensus reached."""

    NONE = "none"  # No agreement
    PARTIAL = "partial"  # Some agreement on aspects
    STRONG = "strong"  # Majority agreement
    UNANIMOUS = "unanimous"  # Full agreement


@dataclass
class ConsensusPoint:
    """A specific point of agreement."""

    statement: str
    supporting_participants: Set[str]
    confidence: float
    detected_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class ConsensusResult:
    """Result of consensus analysis."""

    level: ConsensusLevel
    consensus_points: List[ConsensusPoint]
    areas_of_disagreement: List[str]
    synthesis: Optional[str] = None
    confidence: float = 0.0


class ConsensusEngine:
    """Analyzes salon conversations to detect consensus and synthesize positions.

    Uses keyword matching, sentiment analysis, and pattern detection to
    identify when participants are reaching agreement.
    """

    def __init__(
        self,
        participants: List[str],
        consensus_threshold: float = 0.6,
    ):
        """Initialize consensus engine.

        Args:
            participants: List of participant IDs in the salon
            consensus_threshold: Fraction of participants needed for consensus (0.0-1.0)
        """
        self.participants = participants
        self.consensus_threshold = consensus_threshold

        # Track consensus points discovered
        self.consensus_points: List[ConsensusPoint] = []

        # Agreement indicators (keywords and phrases)
        self.agreement_keywords = {
            "agree", "agreed", "consensus", "correct", "exactly",
            "yes", "true", "right", "indeed", "absolutely",
            "concur", "same", "likewise", "similarly",
        }

        self.disagreement_keywords = {
            "disagree", "no", "wrong", "incorrect", "however",
            "but", "although", "contrary", "oppose", "different",
        }

        logger.info(
            f"Initialized ConsensusEngine with {len(participants)} participants, "
            f"threshold={consensus_threshold}"
        )

    def analyze_messages(
        self,
        messages: List[Dict[str, Any]],
        topic: Optional[str] = None,
    ) -> ConsensusResult:
        """Analyze messages to detect consensus.

        Args:
            messages: List of message dictionaries with 'participant_id' and 'content'
            topic: Optional topic context

        Returns:
            ConsensusResult with detected consensus level and points
        """
        if not messages:
            return ConsensusResult(
                level=ConsensusLevel.NONE,
                consensus_points=[],
                areas_of_disagreement=[],
            )

        # Extract statements and participant positions
        participant_positions = self._extract_positions(messages)

        # Detect areas of agreement
        consensus_points = self._detect_agreement(participant_positions)

        # Detect areas of disagreement
        disagreements = self._detect_disagreement(messages)

        # Calculate consensus level
        level = self._calculate_consensus_level(consensus_points)

        # Generate synthesis if strong consensus
        synthesis = None
        if level in [ConsensusLevel.STRONG, ConsensusLevel.UNANIMOUS]:
            synthesis = self._synthesize_position(consensus_points)

        # Calculate overall confidence
        confidence = self._calculate_confidence(consensus_points, messages)

        return ConsensusResult(
            level=level,
            consensus_points=consensus_points,
            areas_of_disagreement=disagreements,
            synthesis=synthesis,
            confidence=confidence,
        )

    def track_consensus_point(self, point: ConsensusPoint):
        """Track a consensus point for historical analysis.

        Args:
            point: ConsensusPoint to track
        """
        self.consensus_points.append(point)
        logger.info(
            f"Tracked consensus point: {point.statement[:50]}... "
            f"(support: {len(point.supporting_participants)}/{len(self.participants)})"
        )

    def get_consensus_history(self) -> List[ConsensusPoint]:
        """Get all tracked consensus points.

        Returns:
            List of ConsensusPoints
        """
        return self.consensus_points.copy()

    def _extract_positions(
        self,
        messages: List[Dict[str, Any]]
    ) -> Dict[str, List[str]]:
        """Extract participant positions from messages.

        Args:
            messages: List of message dictionaries

        Returns:
            Dictionary mapping participant_id to list of position statements
        """
        positions: Dict[str, List[str]] = {p: [] for p in self.participants}

        for msg in messages:
            participant = msg.get("participant_id")
            content = msg.get("content", "")

            if participant not in positions:
                continue

            # Extract key statements (sentences with assertions)
            statements = self._extract_statements(content)
            positions[participant].extend(statements)

        return positions

    def _extract_statements(self, content: str) -> List[str]:
        """Extract key statements from content.

        Args:
            content: Message content

        Returns:
            List of statement strings
        """
        # Split into sentences
        sentences = re.split(r'[.!?]+', content)

        statements = []
        for sentence in sentences:
            sentence = sentence.strip()
            # Filter out questions and very short statements
            if len(sentence) > 20 and not sentence.endswith('?'):
                statements.append(sentence)

        return statements

    def _detect_agreement(
        self,
        participant_positions: Dict[str, List[str]]
    ) -> List[ConsensusPoint]:
        """Detect points of agreement across participants.

        Args:
            participant_positions: Dict mapping participants to their statements

        Returns:
            List of ConsensusPoints
        """
        consensus_points = []

        # Simple keyword-based consensus detection
        # In production, would use semantic similarity (embeddings)

        # Group similar statements
        all_statements = []
        for participant, statements in participant_positions.items():
            for statement in statements:
                all_statements.append((participant, statement))

        # Find common themes (very simplified)
        # TODO: Replace with semantic similarity clustering
        statement_groups: Dict[str, Set[str]] = {}

        for participant, statement in all_statements:
            # Extract key terms
            words = set(re.findall(r'\w+', statement.lower()))
            key_terms = words - {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at'}

            # Find or create group
            matched_group = None
            for group_key in statement_groups:
                group_terms = set(re.findall(r'\w+', group_key.lower()))
                # If significant overlap, add to group
                overlap = len(key_terms & group_terms) / max(len(key_terms), 1)
                if overlap > 0.3:
                    matched_group = group_key
                    break

            if matched_group:
                statement_groups[matched_group].add(participant)
            else:
                statement_groups[statement] = {participant}

        # Create consensus points for groups with sufficient support
        min_support = max(2, int(len(self.participants) * self.consensus_threshold))

        for statement, supporters in statement_groups.items():
            if len(supporters) >= min_support:
                point = ConsensusPoint(
                    statement=statement,
                    supporting_participants=supporters,
                    confidence=len(supporters) / len(self.participants),
                )
                consensus_points.append(point)

        return consensus_points

    def _detect_disagreement(self, messages: List[Dict[str, Any]]) -> List[str]:
        """Detect areas of disagreement.

        Args:
            messages: List of message dictionaries

        Returns:
            List of disagreement descriptions
        """
        disagreements = []

        for msg in messages:
            content = msg.get("content", "").lower()

            # Check for disagreement keywords
            if any(keyword in content for keyword in self.disagreement_keywords):
                # Extract the context of disagreement
                sentences = re.split(r'[.!?]+', msg.get("content", ""))
                for sentence in sentences:
                    if any(kw in sentence.lower() for kw in self.disagreement_keywords):
                        disagreements.append(sentence.strip())

        return disagreements

    def _calculate_consensus_level(
        self,
        consensus_points: List[ConsensusPoint]
    ) -> ConsensusLevel:
        """Calculate overall consensus level.

        Args:
            consensus_points: List of detected consensus points

        Returns:
            ConsensusLevel enum value
        """
        if not consensus_points:
            return ConsensusLevel.NONE

        # Calculate average support across points
        avg_support = sum(
            len(p.supporting_participants) for p in consensus_points
        ) / (len(consensus_points) * len(self.participants))

        if avg_support >= 0.9:
            return ConsensusLevel.UNANIMOUS
        elif avg_support >= self.consensus_threshold:
            return ConsensusLevel.STRONG
        elif avg_support >= 0.3:
            return ConsensusLevel.PARTIAL
        else:
            return ConsensusLevel.NONE

    def _synthesize_position(self, consensus_points: List[ConsensusPoint]) -> str:
        """Synthesize a unified position from consensus points.

        Args:
            consensus_points: List of ConsensusPoints

        Returns:
            Synthesized position statement
        """
        if not consensus_points:
            return "No consensus reached."

        # Simple concatenation of top points
        # TODO: Use LLM to generate better synthesis
        top_points = sorted(
            consensus_points,
            key=lambda p: len(p.supporting_participants),
            reverse=True
        )[:3]

        synthesis_parts = []
        for i, point in enumerate(top_points, 1):
            support_pct = len(point.supporting_participants) / len(self.participants) * 100
            synthesis_parts.append(
                f"{i}. {point.statement} (supported by {support_pct:.0f}% of participants)"
            )

        return "\n".join(synthesis_parts)

    def _calculate_confidence(
        self,
        consensus_points: List[ConsensusPoint],
        messages: List[Dict[str, Any]]
    ) -> float:
        """Calculate confidence in consensus analysis.

        Args:
            consensus_points: Detected consensus points
            messages: Original messages

        Returns:
            Confidence score 0.0-1.0
        """
        if not messages or not consensus_points:
            return 0.0

        # Factors: number of messages, diversity of participants, strength of agreement
        message_count = len(messages)
        unique_participants = len(set(m.get("participant_id") for m in messages))
        avg_support = sum(
            len(p.supporting_participants) for p in consensus_points
        ) / (len(consensus_points) * len(self.participants))

        # Normalize factors
        message_factor = min(1.0, message_count / 10)  # Plateau at 10 messages
        participation_factor = unique_participants / len(self.participants)
        agreement_factor = avg_support

        confidence = (message_factor + participation_factor + agreement_factor) / 3
        return min(1.0, confidence)
