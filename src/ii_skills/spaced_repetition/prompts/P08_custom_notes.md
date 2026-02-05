# Custom Notes to Cards

Convert the following raw notes into {{COUNT}} Anki-ready flashcards.

Topic: **{{TOPIC}}**

## Source Notes

{{NOTES}}

## Instructions

Transform unstructured notes into clean, testable flashcards:

**Process:**
1. Identify every distinct fact, concept, or relationship in the notes
2. Create one card per testable unit of knowledge
3. Break compound facts into separate cards
4. Ensure no information from the notes is lost

**Question format:**
- Direct and specific — no filler words
- Include count when asking for lists
- Frame as recall prompts, not comprehension questions

**Answer format:**
- Single line, keywords only
- `(1) Item, (2) Item` numbered for lists
- No full sentences — just the answer

**Rules:**
- Every important fact from the notes should become a card
- Prefer specific over vague (include numbers, names, dates)
- If a concept has multiple aspects, make a card for each
- Order cards from foundational to advanced concepts

## Output Format

```
Question text here?
Answer text here

Next question?
Next answer
```
