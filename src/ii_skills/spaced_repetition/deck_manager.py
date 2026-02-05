"""
Deck manager — load, save, search, and create decks.

Deck format: Markdown with YAML frontmatter.
Cards are stored as alternating question/answer line pairs separated by blank lines.
"""

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import yaml

from .config import DECKS_DIR, DECK_EXTENSION
from .models import Card, Deck, DeckMetadata

logger = logging.getLogger(__name__)


def _parse_deck_file(file_path: Path) -> Deck:
    """Parse a markdown deck file with YAML frontmatter into a Deck object."""
    text = file_path.read_text(encoding="utf-8")

    # Split frontmatter from body
    metadata = DeckMetadata()
    body = text
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            try:
                yaml_data = yaml.safe_load(parts[1]) or {}
                metadata = DeckMetadata.from_dict(yaml_data)
            except yaml.YAMLError as e:
                logger.warning(f"Bad YAML in {file_path}: {e}")
            body = parts[2]

    # Parse cards: pairs of non-empty lines separated by blank lines
    cards: List[Card] = []
    blocks = [b.strip() for b in body.strip().split("\n\n") if b.strip()]
    for block in blocks:
        lines = [ln for ln in block.split("\n") if ln.strip()]
        if len(lines) >= 2:
            question = lines[0].strip()
            answer = "\n".join(ln.strip() for ln in lines[1:])
            cards.append(
                Card(question=question, answer=answer, tags=list(metadata.tags))
            )

    return Deck(metadata=metadata, cards=cards, file_path=str(file_path))


def _serialize_deck(deck: Deck) -> str:
    """Serialize a Deck back to markdown with YAML frontmatter."""
    meta = deck.metadata.to_dict()
    meta["card_count"] = deck.card_count
    meta["last_updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    yaml_str = yaml.dump(meta, default_flow_style=False, sort_keys=False)

    lines = [f"---\n{yaml_str}---\n"]
    for card in deck.cards:
        lines.append(f"{card.question}\n{card.answer}\n")

    return "\n".join(lines)


def _deck_name_to_filename(name: str) -> str:
    """Convert a human-readable deck name to a filename slug."""
    return name.lower().replace(" ", "_").replace("-", "_")


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------


def load_deck(name: str, decks_dir: Optional[Path] = None) -> Optional[Deck]:
    """Load a single deck by name (filename without extension)."""
    directory = decks_dir or DECKS_DIR
    slug = _deck_name_to_filename(name)
    path = directory / f"{slug}{DECK_EXTENSION}"
    if not path.exists():
        # Try exact name
        path = directory / f"{name}{DECK_EXTENSION}"
    if not path.exists():
        return None
    return _parse_deck_file(path)


def list_decks(decks_dir: Optional[Path] = None) -> List[Dict]:
    """Return summary info for all decks in the directory."""
    directory = decks_dir or DECKS_DIR
    if not directory.exists():
        return []

    summaries = []
    for f in sorted(directory.glob(f"*{DECK_EXTENSION}")):
        if f.name.startswith("README"):
            continue
        try:
            deck = _parse_deck_file(f)
            summaries.append(
                {
                    "name": deck.metadata.deck or f.stem,
                    "file": f.name,
                    "category": deck.metadata.category,
                    "card_count": deck.card_count,
                    "difficulty": deck.metadata.difficulty,
                    "description": deck.metadata.description,
                    "tags": deck.metadata.tags,
                }
            )
        except Exception as e:
            logger.warning(f"Failed to parse {f}: {e}")

    return summaries


def create_deck(
    name: str,
    category: str = "",
    difficulty: str = "Intermediate",
    description: str = "",
    tags: Optional[List[str]] = None,
    decks_dir: Optional[Path] = None,
) -> Deck:
    """Create a new empty deck and save it to disk."""
    directory = decks_dir or DECKS_DIR
    directory.mkdir(parents=True, exist_ok=True)

    metadata = DeckMetadata(
        deck=name,
        category=category,
        card_count=0,
        last_updated=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        difficulty=difficulty,
        description=description,
        tags=tags or [],
    )
    deck = Deck(metadata=metadata, cards=[])

    slug = _deck_name_to_filename(name)
    path = directory / f"{slug}{DECK_EXTENSION}"
    path.write_text(_serialize_deck(deck), encoding="utf-8")
    deck.file_path = str(path)

    return deck


def save_deck(deck: Deck, decks_dir: Optional[Path] = None) -> str:
    """Save (overwrite) a deck to its file path."""
    if deck.file_path:
        path = Path(deck.file_path)
    else:
        directory = decks_dir or DECKS_DIR
        directory.mkdir(parents=True, exist_ok=True)
        slug = _deck_name_to_filename(deck.name)
        path = directory / f"{slug}{DECK_EXTENSION}"

    path.write_text(_serialize_deck(deck), encoding="utf-8")
    deck.file_path = str(path)
    return str(path)


def add_cards_to_deck(
    name: str,
    cards: List[Card],
    decks_dir: Optional[Path] = None,
) -> Deck:
    """Append cards to an existing deck and save."""
    deck = load_deck(name, decks_dir)
    if deck is None:
        raise FileNotFoundError(f"Deck '{name}' not found")

    deck.cards.extend(cards)
    deck.metadata.card_count = deck.card_count
    save_deck(deck, decks_dir)
    return deck


def search_all_decks(
    keyword: str, decks_dir: Optional[Path] = None
) -> List[Dict]:
    """Search across all decks for cards matching a keyword."""
    directory = decks_dir or DECKS_DIR
    if not directory.exists():
        return []

    results = []
    for f in sorted(directory.glob(f"*{DECK_EXTENSION}")):
        if f.name.startswith("README"):
            continue
        try:
            deck = _parse_deck_file(f)
            matches = deck.search(keyword)
            for card in matches:
                results.append(
                    {
                        "deck": deck.metadata.deck or f.stem,
                        "question": card.question,
                        "answer": card.answer,
                        "tags": card.tags,
                    }
                )
        except Exception as e:
            logger.warning(f"Failed to search {f}: {e}")

    return results
