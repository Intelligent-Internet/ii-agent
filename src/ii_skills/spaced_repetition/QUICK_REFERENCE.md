# Quick Reference — Spaced Repetition Skill

## "I want to..." → Action Mapping

| Request | Action | Parameters |
|---------|--------|------------|
| See all available decks | `list_decks` | — |
| See all prompt templates | `list_prompts` | — |
| Export a deck for Anki | `export_deck` | `deck_name`, `format="tsv"` |
| Export a deck for review | `export_deck` | `deck_name`, `format="markdown_qa"` |
| Search for a card topic | `search_cards` | `keyword` |
| Create a new empty deck | `create_deck` | `name`, `category`, `difficulty`, `tags` |
| Add cards to a deck | `add_cards` | `deck_name`, `cards_text` or `cards` |
| Generate cards from notes | `generate_cards` | `prompt_id`, `notes`, `topic`, `count` |
| Parse LLM output into cards | `generate_cards` | `prompt_id`, `raw_output`, `tags` |
| Get a study schedule | `get_study_plan` | `exam_date`, `deck_names`, `cards_per_day` |

## Prompt → Use Case Mapping

| Prompt | Best For |
|--------|----------|
| `P01_interview_prep` | IB/PE technical interview questions |
| `P02_general_knowledge` | Converting any notes into cards |
| `P03_technical_finance` | LBO, DCF, valuation mechanics |
| `P04_sector_specific` | SaaS, Healthcare, Industrial, Consumer KPIs |
| `P05_behavioral` | STAR behavioral interview prep |
| `P06_market_knowledge` | Macro, rates, FX, commodities |
| `P07_case_study` | Deal-specific prep from CIM/model |
| `P08_custom_notes` | Raw unstructured notes to cards |

## Export Formats

| Format | File | Use |
|--------|------|-----|
| `tsv` | `.tsv` | Anki desktop/mobile import |
| `markdown_qa` | `_qa.md` | Human review / printing |
| `markdown_table` | `_table.md` | Compact reference sheet |

## Workflow: Notes → Anki Deck

1. `generate_cards` with `prompt_id` + `notes` → get filled prompt
2. Send prompt to LLM → get card text
3. `generate_cards` with `raw_output` → parse into cards
4. `create_deck` → make a new deck (or use existing)
5. `add_cards` → append parsed cards to deck
6. `export_deck` with `format="tsv"` → import into Anki
