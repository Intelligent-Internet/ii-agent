"""
Card generator — prompt loading, card parsing, and study plan creation.

This module does NOT call any LLM APIs. It:
  1. Loads prompt templates and fills in user notes/topic
  2. Parses structured LLM output back into Card objects
  3. Generates study plans based on deck sizes and exam dates
"""

import math
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional

from .config import PROMPTS_DIR, DEFAULT_NEW_CARDS_PER_DAY, DEFAULT_REVIEW_MULTIPLIER
from .models import Card, StudyPlan

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Prompt loading
# ------------------------------------------------------------------


def list_prompts(prompts_dir: Optional[Path] = None) -> List[Dict]:
    """List all prompt templates with metadata."""
    directory = prompts_dir or PROMPTS_DIR
    if not directory.exists():
        return []

    prompts = []
    for f in sorted(directory.glob("P*.md")):
        text = f.read_text(encoding="utf-8")
        # Extract first heading as title, first paragraph as description
        title = f.stem
        description = ""
        for line in text.split("\n"):
            line = line.strip()
            if line.startswith("# "):
                title = line.lstrip("# ").strip()
            elif line and not line.startswith("#") and not description:
                description = line
                break

        prompts.append(
            {
                "id": f.stem,
                "file": f.name,
                "title": title,
                "description": description,
            }
        )

    return prompts


def load_prompt(
    prompt_id: str,
    notes: str = "",
    topic: str = "",
    count: int = 20,
    prompts_dir: Optional[Path] = None,
) -> str:
    """Load a prompt template and fill in placeholders.

    Placeholders: {{NOTES}}, {{TOPIC}}, {{COUNT}}
    """
    directory = prompts_dir or PROMPTS_DIR
    path = directory / f"{prompt_id}.md"
    if not path.exists():
        # Try without extension
        path = directory / prompt_id
    if not path.exists():
        raise FileNotFoundError(f"Prompt '{prompt_id}' not found in {directory}")

    template = path.read_text(encoding="utf-8")
    filled = template.replace("{{NOTES}}", notes)
    filled = filled.replace("{{TOPIC}}", topic)
    filled = filled.replace("{{COUNT}}", str(count))
    return filled


# ------------------------------------------------------------------
# Card parsing
# ------------------------------------------------------------------


def parse_cards_from_text(text: str, tags: Optional[List[str]] = None) -> List[Card]:
    """Parse LLM-generated text into Card objects.

    Expected format — alternating question/answer pairs separated by blank lines:

        4 components of Enterprise Value?
        (1) Equity Value, (2) + Net Debt, (3) + Minority Interest, (4) + Preferred Stock

        3 main financial statements?
        (1) Income Statement, (2) Balance Sheet, (3) Cash Flow Statement

    Also supports Q:/A: prefix format:

        Q: What is WACC?
        A: Weighted Average Cost of Capital — blended cost of debt + equity
    """
    cards: List[Card] = []
    blocks = [b.strip() for b in text.strip().split("\n\n") if b.strip()]

    for block in blocks:
        lines = [ln for ln in block.split("\n") if ln.strip()]
        if len(lines) < 2:
            continue

        question = lines[0].strip()
        answer = "\n".join(ln.strip() for ln in lines[1:])

        # Strip Q:/A: prefixes if present
        if question.upper().startswith("Q:"):
            question = question[2:].strip()
        if answer.upper().startswith("A:"):
            answer = answer[2:].strip()

        cards.append(Card(question=question, answer=answer, tags=tags or []))

    return cards


# ------------------------------------------------------------------
# Study plan
# ------------------------------------------------------------------


def generate_study_plan(
    decks: List[Dict],
    exam_date: str,
    cards_per_day: int = DEFAULT_NEW_CARDS_PER_DAY,
) -> StudyPlan:
    """Generate a spaced repetition study schedule.

    Args:
        decks: List of deck summaries (from list_decks) to include.
        exam_date: Target date as YYYY-MM-DD string.
        cards_per_day: New cards to introduce per day.

    Returns:
        StudyPlan with daily schedule.
    """
    today = datetime.now(timezone.utc).date()
    target = datetime.strptime(exam_date, "%Y-%m-%d").date()
    days_available = max((target - today).days, 1)

    total_cards = sum(d.get("card_count", 0) for d in decks)
    needed_per_day = math.ceil(total_cards / days_available)
    actual_per_day = max(cards_per_day, needed_per_day)

    # Build daily schedule
    schedule = []
    cards_remaining = total_cards
    review_backlog = 0

    for day_offset in range(days_available):
        date = today + timedelta(days=day_offset)
        new_today = min(actual_per_day, cards_remaining)
        review_today = min(
            int(review_backlog * DEFAULT_REVIEW_MULTIPLIER),
            total_cards - cards_remaining,
        )

        schedule.append(
            {
                "date": date.isoformat(),
                "day": day_offset + 1,
                "new_cards": new_today,
                "review_cards": review_today,
                "total": new_today + review_today,
            }
        )

        cards_remaining -= new_today
        review_backlog += new_today

        if cards_remaining <= 0:
            # Remaining days are review-only
            for extra in range(day_offset + 1, days_available):
                date = today + timedelta(days=extra)
                rev = min(int(review_backlog * 0.3), total_cards)
                schedule.append(
                    {
                        "date": date.isoformat(),
                        "day": extra + 1,
                        "new_cards": 0,
                        "review_cards": rev,
                        "total": rev,
                    }
                )
            break

    deck_names = [d.get("name", "") for d in decks]

    return StudyPlan(
        exam_date=exam_date,
        decks=deck_names,
        total_cards=total_cards,
        cards_per_day=actual_per_day,
        schedule=schedule,
    )
