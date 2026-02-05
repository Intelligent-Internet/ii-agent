"""
Export decks to various formats for Anki import and review.

Supported formats:
  - tsv          : Tab-separated values (Anki native import)
  - markdown_qa  : Q&A pairs in markdown (human review)
  - markdown_table : Markdown table (compact reference)
"""

from pathlib import Path
from typing import Optional

from .config import OUTPUT_DIR, TSV_SEPARATOR
from .models import Deck


def _ensure_output_dir(output_dir: Optional[Path] = None) -> Path:
    d = output_dir or OUTPUT_DIR
    d.mkdir(parents=True, exist_ok=True)
    return d


def export_tsv(deck: Deck, output_dir: Optional[Path] = None) -> str:
    """Export deck to TSV (tab-separated) for Anki import.

    Format: question<TAB>answer<TAB>tags
    No header row — Anki expects raw card data.
    """
    d = _ensure_output_dir(output_dir)
    slug = deck.name.lower().replace(" ", "_")
    path = d / f"{slug}.tsv"

    lines = []
    for card in deck.cards:
        tags = " ".join(card.tags) if card.tags else ""
        line = TSV_SEPARATOR.join([card.question, card.answer, tags])
        lines.append(line)

    path.write_text("\n".join(lines), encoding="utf-8")
    return str(path)


def export_markdown_qa(deck: Deck, output_dir: Optional[Path] = None) -> str:
    """Export deck as markdown Q&A pairs for human review.

    Format:
        ## Deck Name
        **Q:** Question text
        **A:** Answer text
    """
    d = _ensure_output_dir(output_dir)
    slug = deck.name.lower().replace(" ", "_")
    path = d / f"{slug}_qa.md"

    lines = [
        f"# {deck.name}",
        f"*{deck.metadata.description}*" if deck.metadata.description else "",
        f"**Cards:** {deck.card_count} | **Category:** {deck.metadata.category}",
        "",
        "---",
        "",
    ]

    for i, card in enumerate(deck.cards, 1):
        lines.append(f"### Card {i}")
        lines.append(f"**Q:** {card.question}")
        lines.append(f"**A:** {card.answer}")
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")
    return str(path)


def export_markdown_table(deck: Deck, output_dir: Optional[Path] = None) -> str:
    """Export deck as a compact markdown table.

    Format:
        | # | Question | Answer |
        |---|----------|--------|
        | 1 | ...      | ...    |
    """
    d = _ensure_output_dir(output_dir)
    slug = deck.name.lower().replace(" ", "_")
    path = d / f"{slug}_table.md"

    lines = [
        f"# {deck.name}",
        "",
        "| # | Question | Answer |",
        "|---|----------|--------|",
    ]

    for i, card in enumerate(deck.cards, 1):
        q = card.question.replace("|", "\\|")
        a = card.answer.replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {i} | {q} | {a} |")

    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    return str(path)


def export_deck(
    deck: Deck,
    fmt: str = "tsv",
    output_dir: Optional[Path] = None,
) -> str:
    """Export a deck in the specified format. Returns output file path."""
    exporters = {
        "tsv": export_tsv,
        "markdown_qa": export_markdown_qa,
        "markdown_table": export_markdown_table,
    }

    handler = exporters.get(fmt)
    if handler is None:
        raise ValueError(f"Unknown format '{fmt}'. Choose from: {list(exporters)}")

    return handler(deck, output_dir)
