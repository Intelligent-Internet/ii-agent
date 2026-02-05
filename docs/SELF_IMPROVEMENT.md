# Self-Improvement Workflow

Guidelines for continuous agent improvement through structured reflection and learning capture.

---

## Overview

This workflow enables the agent to learn from each session and improve over time by:
1. Reflecting on task outcomes
2. Capturing learnings persistently
3. Updating behavior based on insights

---

## The Self-Improvement Loop

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Execute    │────▶│   Reflect   │────▶│   Capture   │
│    Task     │     │  on Result  │     │  Learning   │
└─────────────┘     └─────────────┘     └──────┬──────┘
       ▲                                       │
       │            ┌─────────────┐            │
       └────────────│   Update    │◀───────────┘
                    │  Behavior   │
                    └─────────────┘
```

### 1. Execute Task

Complete the requested work as normal.

### 2. Reflect on Result

After significant tasks, ask:
- Did the task complete successfully?
- Were there any errors or unexpected issues?
- Could the approach have been more efficient?
- Did I learn something new about the domain?
- Did I learn something about the user's preferences?

### 3. Capture Learning

If reflection yields an insight, log it:

```markdown
# Learning: [Brief Title]

**Date:** YYYY-MM-DD
**Category:** bug-fix | optimization | new-capability | best-practice | user-preference

## What Happened
[Situation description]

## What Was Learned
[The insight or correction]

## Impact
[How this affects future behavior]
```

Save to: `learnings/YYYY-MM-DD-<topic>.md`

### 4. Update Behavior

For significant learnings:
- **Minor:** Log only, no changes needed
- **Moderate:** Update relevant skill documentation
- **Significant:** Update `CLAUDE.md` or core instructions

---

## When to Log Learnings

### Always Log

- Mistakes that caused rework
- New techniques discovered
- User preferences learned
- Performance optimizations found
- Integration issues resolved

### Don't Log

- Routine successful tasks
- Minor formatting adjustments
- Temporary workarounds

---

## Learning Categories

| Category | Description | Example |
|----------|-------------|---------|
| `bug-fix` | Corrected an error | "Fixed import path for shared module" |
| `optimization` | Found better approach | "Parallel API calls reduce latency 3x" |
| `new-capability` | Learned new skill | "Can now generate waterfall charts" |
| `best-practice` | Pattern worth repeating | "Always validate input before processing" |
| `user-preference` | User's preferred style | "User prefers concise bullet points" |

---

## File Locations

| Purpose | Location | Git Status |
|---------|----------|------------|
| Learning logs | `learnings/YYYY-MM-DD-<topic>.md` | Committed |
| Long-term memory | `Memory/long-term-memory.md` | Local only |
| Conversation archives | `Memory/conversation-logs/` | Local only |
| Behavior rules | `CLAUDE.md` | Committed |
| Skill-specific docs | `src/ii_skills/<skill>/` | Committed |

> **Note:** The `Memory/` folder is gitignored to protect conversation privacy. Create these files locally on first setup.

---

## Periodic Review

Weekly or after major projects:

1. **Review recent learnings**
   ```bash
   ls -la learnings/
   ```

2. **Identify patterns**
   - Are similar issues recurring?
   - Are there learnings that should become rules?

3. **Update core documentation**
   - Promote significant learnings to `CLAUDE.md`
   - Update skill docs with new best practices

4. **Archive old learnings**
   - Move incorporated learnings to `learnings/archive/`
   - Keep the active folder focused

---

## Integration with Memory

### Long-Term Memory (`Memory/long-term-memory.md`)

Use for:
- User preferences that persist
- System knowledge and context
- Key patterns and approaches

### Conversation Logs (`Memory/conversation-logs/`)

Use for:
- Archiving significant sessions
- Debugging complex issues
- Training data for improvements

---

## Example Workflow

**Scenario:** Agent makes an error parsing a date format.

1. **Notice the error** during task execution
2. **Reflect:** "The date parsing failed because I assumed US format"
3. **Capture:**
   ```markdown
   # Learning: Date Format Handling

   **Date:** 2026-02-04
   **Category:** bug-fix

   ## What Happened
   Failed to parse "04/02/2026" - assumed MM/DD/YYYY but user uses DD/MM/YYYY

   ## What Was Learned
   User is in Canada, uses DD/MM/YYYY format for dates

   ## Impact
   Always clarify date format or use ISO 8601 (YYYY-MM-DD) for unambiguous dates
   ```
4. **Update:** Add note to `Memory/long-term-memory.md` under User Preferences

---

## Best Practices

1. **Be specific** - Vague learnings aren't actionable
2. **Be honest** - Acknowledge mistakes openly
3. **Be concise** - One learning per file
4. **Be proactive** - Don't wait to be told something went wrong
5. **Be consistent** - Use the templates provided

---

*This workflow is part of the Persistent Agent Workspace Best Practices.*
