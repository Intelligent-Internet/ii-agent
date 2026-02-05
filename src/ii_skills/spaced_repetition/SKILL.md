# Spaced Repetition Skill

Generate, manage, and export Anki-ready flashcard decks for interview prep, technical finance, and general knowledge retention.

## Overview

- **Skill name:** `spaced_repetition`
- **Actions:** 8
- **Schedule:** On-demand
- **Dependencies:** `pyyaml>=6.0`

## Quick Start

```python
from ii_skills.spaced_repetition import get_skill

skill = get_skill()

# List all available decks
skill.execute("list_decks")

# Generate cards for an upcoming interview
skill.execute("generate_cards", prompt_id="P01_interview_prep",
              notes="Company does SaaS billing...", topic="SaaS LBO", count=20)

# Create a deck and export to Anki
skill.execute("create_deck", name="Acme Interview", category="Case Prep")
skill.execute("export_deck", deck_name="acme_interview", format="tsv")
```

## Actions

### `generate_cards`
Prepare a prompt from notes + template, and/or parse LLM output into Card objects.

**Two modes:**
1. **Prompt preparation** — provide `prompt_id` + `notes`/`topic`/`count` to get a filled prompt
2. **Card parsing** — provide `raw_output` to parse LLM-generated text into cards

```python
# Mode 1: Get a filled prompt to send to LLM
result = skill.execute("generate_cards", prompt_id="P01_interview_prep",
                       notes="My notes...", topic="LBO", count=20)
print(result["prompt"])  # Send this to the LLM

# Mode 2: Parse LLM output into cards
result = skill.execute("generate_cards", prompt_id="P01_interview_prep",
                       raw_output="Question?\nAnswer\n\nQuestion2?\nAnswer2",
                       tags=["lbo", "interview"])
print(result["cards"])  # List of card dicts
```

### `list_prompts`
Show all 8 prompt templates with descriptions.

### `list_decks`
Show all decks with card counts and metadata.

### `export_deck`
Export a deck to one of three formats:
- `tsv` — Tab-separated values for Anki native import
- `markdown_qa` — Q&A pairs in markdown for human review
- `markdown_table` — Compact markdown table

### `add_cards`
Append new cards to an existing deck. Accepts raw text or structured card dicts.

### `create_deck`
Create a new empty deck with metadata (name, category, difficulty, tags).

### `search_cards`
Keyword search across all decks. Returns matching cards with deck name.

### `get_study_plan`
Generate a spaced repetition review schedule based on:
- `exam_date` — Target date (YYYY-MM-DD)
- `deck_names` — Optional list of specific decks (defaults to all)
- `cards_per_day` — New cards per day (default: 20)

## Deck Format

Decks are markdown files with YAML frontmatter:

```markdown
---
deck: Finance Fundamentals
category: Technical Interview
card_count: 50
last_updated: 2026-02-05
difficulty: Intermediate
description: Core finance concepts
tags: [finance, accounting]
---

Question text here?
Answer text here

Next question?
Next answer
```

## Card Formatting Rules

**Questions:** No filler words, include count, use `**Org:**` prefix for org facts
**Answers:** Single line, `(1) Item, (2) Item` numbered format, keywords only
**Structure:** One testable fact per card, break nested info into separate cards

## Prompt Templates

See `prompts/README.md` for the full prompt library (P01-P08).

## File Structure

```
spaced_repetition/
├── __init__.py          # Skill class (8 actions)
├── models.py            # Card, Deck, DeckMetadata dataclasses
├── deck_manager.py      # Load/save/search/create decks
├── card_generator.py    # Prompt loading, card parsing, study plan
├── exporters.py         # TSV, markdown Q&A, markdown table
├── config.py            # Default settings
├── prompts/             # 8 prompt templates
├── decks/               # Generated decks (created per interview)
├── output/              # Generated exports
├── SKILL.md             # This file
└── QUICK_REFERENCE.md   # Prompt → use case mapping
```
