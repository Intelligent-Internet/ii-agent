# Prompt Library — Spaced Repetition

8 prompt templates for generating Anki-ready flashcards.

| ID | Template | Use Case |
|----|----------|----------|
| P01 | `P01_interview_prep.md` | Finance interview Q&A (technicals, fit, brain teasers) |
| P02 | `P02_general_knowledge.md` | General-purpose note → card conversion |
| P03 | `P03_technical_finance.md` | LBO, DCF, valuation concept cards |
| P04 | `P04_sector_specific.md` | Industry-specific cards (SaaS, Healthcare, etc.) |
| P05 | `P05_behavioral.md` | STAR behavioral interview cards |
| P06 | `P06_market_knowledge.md` | Macro, market, commodity, FX cards |
| P07 | `P07_case_study.md` | Case-specific prep from deal materials |
| P08 | `P08_custom_notes.md` | Raw notes → cards (topic-agnostic) |

## Placeholders

All templates support these placeholders:

- `{{NOTES}}` — User-provided study notes or source material
- `{{TOPIC}}` — Subject area or focus keyword
- `{{COUNT}}` — Target number of cards to generate

## Card Formatting Rules

**Questions**: No filler words, include count when listing, use `**Org:**` prefix for org-specific facts
**Answers**: Single line, `(1) Item, (2) Item` numbered format, keywords only
**Structure**: Break nested info into separate cards, one testable fact per card
