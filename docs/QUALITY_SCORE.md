# Quality Score

Per-domain quality assessment. Updated periodically to track code health across the codebase.

**Grading:** A (excellent) | B (good) | C (adequate) | D (needs work) | F (critical gaps)

**Last updated:** 2026-04-17

## Domain Quality Grades

| Domain | Test Coverage | Type Safety | Doc Coverage | DI Pattern | Overall |
|--------|-------------|-------------|-------------|------------|---------|
| **core/config** | B | A | A (CLAUDE.md) | A | **A** |
| **core/db** | B | A | B | A | **B+** |
| **core/redis** | B | B | B | A | **B** |
| **core/storage** | B | A | B | A | **B+** |
| **core/llm** | B | B | A (CLAUDE.md) | A | **B+** |
| **auth** | B | B | B | A | **B** |
| **billing/credits** | A | A | A (CLAUDE.md) | A | **A** |
| **billing/reservations** | A | A | A (CLAUDE.md) | A | **A** |
| **billing/outbox** | B | A | A (CLAUDE.md) | A | **A-** |
| **billing/usage** | B | B | B | A | **B** |
| **sessions** | B | B | B | A | **B** |
| **agent/runs** | B | B | C | A | **B-** |
| **agents/sandboxes** | A | A | B | B | **B+** |
| **agent/events** | B | B | C | B | **B-** |
| **agent/socket** | C | B | C | B | **C+** |
| **agent/application** | B | B | C | B | **B-** |
| **chat/api** | B | B | C | A | **B-** |
| **chat/llm** | C | B | C | B | **C+** |
| **chat/media** | C | C | D | B | **C** |
| **content/slides** | C | B | D | B | **C** |
| **content/storybook** | C | B | D | B | **C** |
| **content/skills** | C | B | D | B | **C** |
| **content/media** | C | C | D | B | **C** |
| **files** | B | B | C | A | **B** |
| **projects** | B | B | C | A | **B** |
| **projects/deployments** | C | B | D | B | **C+** |
| **projects/secrets** | B | B | D | B | **B-** |
| **integrations/a2a** | A | B | B | C | **B+** |
| **integrations/connectors** | C | C | D | B | **C** |
| **integrations/mcp_sse** | C | C | D | C | **C-** |
| **settings** | B | B | C | A | **B** |
| **workers/cron** | B | B | C | B | **B-** |

## Assessment Criteria

### Test Coverage
- **A:** >90% statement coverage, edge cases tested, integration tests present
- **B:** >75% coverage, happy paths tested
- **C:** >50% coverage, basic tests only
- **D:** <50% or no tests

### Type Safety
- **A:** Full type annotations, mypy strict passes, no `Any` escapes
- **B:** Type annotations present, minor gaps
- **C:** Partial annotations, some `Any` or untyped functions

### Doc Coverage
- **A:** Documented in CLAUDE.md or dedicated doc file with code examples
- **B:** Basic docstrings, patterns discoverable
- **C:** Minimal docs, requires reading code
- **D:** No documentation

### DI Pattern
- **A:** Correct Dep alias pattern, factory → alias → usage everywhere
- **B:** Mostly correct, minor deviations
- **C:** Mixed patterns, some bare `Depends()` usage

## Top Improvement Priorities

1. **Content domain (slides, storybook, media)** — Needs documentation, better test coverage
2. **Integrations domain (a2a, connectors, mcp_sse)** — Needs documentation, consistent DI patterns
3. **Agent socket handlers** — Complex orchestration logic needs more test coverage
4. **Chat media pipeline** — Underdocumented, complex orchestration
5. **Deployment pipeline** — Cloud Run deployment needs reliability documentation

## Coverage Threshold

The project enforces **85% minimum** test coverage via `pyproject.toml`:
```
[tool.coverage.report]
fail_under = 85
```
