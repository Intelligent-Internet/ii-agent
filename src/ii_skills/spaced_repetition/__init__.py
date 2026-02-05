"""
Spaced Repetition Skill

Generate, manage, and export Anki-ready flashcard decks for interview prep,
technical finance, and general knowledge retention.

Usage:
    skill = SpacedRepetitionSkill()
    skill.initialize()

    # List all decks
    result = skill.execute("list_decks")

    # Export a deck to TSV for Anki import
    result = skill.execute("export_deck", deck_name="finance_fundamentals", format="tsv")

    # Generate cards from notes
    result = skill.execute("generate_cards", prompt_id="P01_interview_prep",
                           notes="My study notes...", topic="LBO", count=20)
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional

from ii_skills import BaseSkill, register_skill

logger = logging.getLogger(__name__)

__version__ = "1.0.0"
__author__ = "II-Agent System"


@register_skill
class SpacedRepetitionSkill(BaseSkill):
    """Generate, manage, and export Anki-ready flashcard decks."""

    name = "spaced_repetition"
    version = __version__
    description = (
        "Spaced repetition flashcard system - generate cards from prompts, "
        "manage decks, and export to Anki TSV or markdown formats"
    )

    SKILL_DIR = Path(__file__).parent
    OUTPUT_DIR = SKILL_DIR / "output"

    def __init__(self, config: Optional[Dict] = None):
        super().__init__(config)
        self.OUTPUT_DIR.mkdir(exist_ok=True)

    def validate_config(self) -> List[str]:
        issues = []
        try:
            import yaml  # noqa: F401
        except ImportError:
            issues.append("pyyaml is required but not installed (pip install pyyaml)")
        return issues

    def get_capabilities(self) -> List[str]:
        return [
            "generate_cards",
            "list_prompts",
            "list_decks",
            "export_deck",
            "add_cards",
            "create_deck",
            "search_cards",
            "get_study_plan",
        ]

    def execute(self, action: str, **kwargs) -> Dict:
        """Execute a spaced repetition action."""
        actions = {
            "generate_cards": self._generate_cards,
            "list_prompts": self._list_prompts,
            "list_decks": self._list_decks,
            "export_deck": self._export_deck,
            "add_cards": self._add_cards,
            "create_deck": self._create_deck,
            "search_cards": self._search_cards,
            "get_study_plan": self._get_study_plan,
        }

        handler = actions.get(action)
        if not handler:
            return {
                "success": False,
                "error": f"Unknown action '{action}'. Available: {list(actions)}",
            }

        try:
            return handler(**kwargs)
        except Exception as e:
            logger.exception(f"Action '{action}' failed")
            return {"success": False, "error": str(e)}

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _generate_cards(
        self,
        prompt_id: str,
        notes: str = "",
        topic: str = "",
        count: int = 20,
        raw_output: str = "",
        tags: Optional[List[str]] = None,
        **kwargs,
    ) -> Dict:
        """Prepare a prompt from notes + template, and/or parse LLM output into cards.

        Two modes:
          1. Prompt preparation: provide prompt_id + notes/topic/count → get filled prompt
          2. Card parsing: provide raw_output → get parsed Card objects

        If both are provided, the prompt is prepared AND the raw_output is parsed.
        """
        from .card_generator import load_prompt, parse_cards_from_text

        result: Dict = {"success": True}

        # Mode 1: prepare prompt
        if prompt_id and not raw_output:
            prompt = load_prompt(prompt_id, notes=notes, topic=topic, count=count)
            result["prompt"] = prompt
            result["message"] = (
                f"Prompt prepared from {prompt_id}. "
                "Send this to the LLM and pass the response back as raw_output."
            )

        # Mode 2: parse LLM output
        if raw_output:
            cards = parse_cards_from_text(raw_output, tags=tags)
            result["cards"] = [c.to_dict() for c in cards]
            result["card_count"] = len(cards)
            result["message"] = f"Parsed {len(cards)} cards from LLM output."

            # If prompt was also prepared, include it
            if prompt_id and notes:
                prompt = load_prompt(prompt_id, notes=notes, topic=topic, count=count)
                result["prompt"] = prompt

        return result

    def _list_prompts(self, **kwargs) -> Dict:
        """Show all prompt templates with descriptions."""
        from .card_generator import list_prompts

        prompts = list_prompts()
        return {
            "success": True,
            "prompts": prompts,
            "count": len(prompts),
        }

    def _list_decks(self, **kwargs) -> Dict:
        """Show all decks with card counts and metadata."""
        from .deck_manager import list_decks

        decks = list_decks()
        total_cards = sum(d.get("card_count", 0) for d in decks)
        return {
            "success": True,
            "decks": decks,
            "deck_count": len(decks),
            "total_cards": total_cards,
        }

    def _export_deck(
        self,
        deck_name: str,
        format: str = "tsv",
        **kwargs,
    ) -> Dict:
        """Export a deck to TSV, markdown Q&A, or markdown table."""
        from .deck_manager import load_deck
        from .exporters import export_deck

        deck = load_deck(deck_name)
        if deck is None:
            return {"success": False, "error": f"Deck '{deck_name}' not found"}

        output_path = export_deck(deck, fmt=format, output_dir=self.OUTPUT_DIR)
        return {
            "success": True,
            "deck": deck_name,
            "format": format,
            "card_count": deck.card_count,
            "output_path": output_path,
        }

    def _add_cards(
        self,
        deck_name: str,
        cards_text: str = "",
        cards: Optional[List[Dict]] = None,
        **kwargs,
    ) -> Dict:
        """Append new cards to an existing deck.

        Provide either:
          - cards_text: raw Q/A text (parsed automatically)
          - cards: list of {"question": ..., "answer": ...} dicts
        """
        from .card_generator import parse_cards_from_text
        from .deck_manager import add_cards_to_deck
        from .models import Card

        card_objects: List[Card] = []

        if cards_text:
            card_objects = parse_cards_from_text(cards_text)
        elif cards:
            card_objects = [Card.from_dict(c) for c in cards]
        else:
            return {"success": False, "error": "Provide cards_text or cards"}

        deck = add_cards_to_deck(deck_name, card_objects)
        return {
            "success": True,
            "deck": deck_name,
            "cards_added": len(card_objects),
            "total_cards": deck.card_count,
        }

    def _create_deck(
        self,
        name: str,
        category: str = "",
        difficulty: str = "Intermediate",
        description: str = "",
        tags: Optional[List[str]] = None,
        **kwargs,
    ) -> Dict:
        """Create a new empty deck."""
        from .deck_manager import create_deck

        deck = create_deck(
            name=name,
            category=category,
            difficulty=difficulty,
            description=description,
            tags=tags,
        )
        return {
            "success": True,
            "deck": name,
            "file_path": deck.file_path,
        }

    def _search_cards(self, keyword: str, **kwargs) -> Dict:
        """Keyword search across all decks."""
        from .deck_manager import search_all_decks

        results = search_all_decks(keyword)
        return {
            "success": True,
            "keyword": keyword,
            "results": results,
            "match_count": len(results),
        }

    def _get_study_plan(
        self,
        exam_date: str,
        deck_names: Optional[List[str]] = None,
        cards_per_day: int = 20,
        **kwargs,
    ) -> Dict:
        """Generate a review schedule based on exam date and selected decks."""
        from .card_generator import generate_study_plan
        from .deck_manager import list_decks, load_deck

        all_decks = list_decks()

        if deck_names:
            selected = [d for d in all_decks if d["name"] in deck_names or d["file"].replace(".md", "") in deck_names]
        else:
            selected = all_decks

        if not selected:
            return {"success": False, "error": "No decks found"}

        plan = generate_study_plan(selected, exam_date, cards_per_day)
        return {
            "success": True,
            "plan": plan.to_dict(),
        }


def get_skill(config: Optional[Dict] = None) -> SpacedRepetitionSkill:
    """Helper to get an initialized skill instance."""
    skill = SpacedRepetitionSkill(config)
    skill.initialize()
    return skill
