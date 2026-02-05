"""
Data models for the Spaced Repetition skill.

Card, Deck, and DeckMetadata dataclasses used across all modules.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


@dataclass
class Card:
    """A single flashcard with question and answer."""

    question: str
    answer: str
    tags: List[str] = field(default_factory=list)
    difficulty: str = ""  # Easy, Medium, Hard
    source: str = ""  # Where this card came from (prompt, manual, deck)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Card":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    def matches(self, keyword: str) -> bool:
        """Check if keyword appears in question or answer (case-insensitive)."""
        kw = keyword.lower()
        return kw in self.question.lower() or kw in self.answer.lower()


@dataclass
class DeckMetadata:
    """YAML frontmatter metadata for a deck file."""

    deck: str = ""
    category: str = ""
    card_count: int = 0
    last_updated: str = ""
    difficulty: str = "Intermediate"
    description: str = ""
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DeckMetadata":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class Deck:
    """A collection of flashcards with metadata."""

    metadata: DeckMetadata
    cards: List[Card] = field(default_factory=list)
    file_path: str = ""  # Absolute path to the .md file

    @property
    def name(self) -> str:
        return self.metadata.deck

    @property
    def card_count(self) -> int:
        return len(self.cards)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "metadata": self.metadata.to_dict(),
            "cards": [c.to_dict() for c in self.cards],
            "file_path": self.file_path,
        }

    def search(self, keyword: str) -> List[Card]:
        """Return cards matching a keyword."""
        return [c for c in self.cards if c.matches(keyword)]


@dataclass
class StudyPlan:
    """A generated study schedule."""

    exam_date: str
    decks: List[str]
    total_cards: int
    cards_per_day: int
    schedule: List[Dict[str, Any]] = field(default_factory=list)
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
