# Tooling Strategy & Recommendations

## When to Use Claude Code vs. Claude Projects

| Use Case | Tool | Why |
|----------|------|-----|
| Writing bridge/infrastructure code | **Claude Code** | Needs file system access, git, testing |
| Adding new skill actions | **Claude Code** | Needs to read existing code, write tests |
| Debugging runtime issues | **Claude Code** | Needs to run code, read logs |
| Designing a new skill's interface | **Claude Projects** | Conceptual design, no files needed |
| Reviewing financial model logic | **Claude Projects** | Math/logic discussion, paste code snippets |
| Writing CLAUDE.md / documentation | **Claude Code** | Needs codebase context for accuracy |
| Planning a multi-week roadmap | **Claude Projects** | Strategic thinking, no code execution |
| Stress-testing a case study | **Claude Code** | Needs to execute skills, verify outputs |
| Writing prompt templates (52-prompt system) | **Claude Projects** | Creative writing, iterate on prompts |
| Fixing CI/CD pipeline | **Claude Code** | Needs to read workflows, test builds |

**Rule of thumb:**
- If you need to touch files → Claude Code
- If you need to think/plan/design → Claude Projects
- If you're iterating on text content (prompts, docs) → either works

## Recommended Skills to Build Next

### High-Impact, Low-Effort

| Skill | Effort | Impact | Description |
|-------|--------|--------|-------------|
| **deal_memory** | 2-3 sessions | High | Persistent deal context across conversations. When you say "the Acme deal," the agent remembers all prior analysis, assumptions, and files. |
| **output_organizer** | 1-2 sessions | High | Auto-organizes generated files into deal-specific folders in workspace. Names files consistently. Maintains an index. |
| **template_library** | 1 session | Medium | Curated library of your best Excel/PPTX templates. When starting a new analysis, copies the right template as starting point. |

### Medium-Impact, Medium-Effort

| Skill | Effort | Impact | Description |
|-------|--------|--------|-------------|
| **comp_tracker** | 3-4 sessions | High | Maintains a running comp set per sector. Auto-fetches quarterly data. Generates comp tables on demand. |
| **deal_pipeline** | 2-3 sessions | Medium | Tracks deals in progress (stage, key dates, next actions). Integrates with IB toolkit for on-demand analysis. |
| **pdf_extractor** | 2-3 sessions | High | Extracts financial data from CIMs and management presentations (PDF). Feeds directly into IB toolkit models. |

### High-Impact, High-Effort

| Skill | Effort | Impact | Description |
|-------|--------|--------|-------------|
| **smart_excel_models** | 5-7 sessions | Very High | Replace template-only Excel with formula-driven models. Real Sources & Uses, real debt schedules, real returns calcs. |
| **research_agent** | 4-5 sessions | High | Autonomous research that gathers industry data, news, filings for a target company. Feeds into deal analysis. |

## Automations to Build

### Daily (via APScheduler)

| Automation | Time | What It Does |
|------------|------|-------------|
| Portfolio snapshot | 7:00 AM | Runs networth_newsletter, sends email |
| Market briefing | 7:15 AM | Runs market_newsletter, sends email |
| Health check | 7:30 AM | Runs health_dashboard, sends email |
| Deal pipeline status | 8:00 AM | (future) Checks deal milestones, alerts |

### Event-Driven

| Trigger | Automation |
|---------|-----------|
| New file in workspace | Auto-index in output_organizer |
| LBO analysis complete | Auto-generate sensitivity matrix |
| Deal stage change | Generate updated IC memo |
| Price alert triggered | Notify via email + log to deal memory |

## Tools That 10x Speed

### Already in the Codebase (use them)
- **TaskGraph** (`shared/task_graph.py`) — Parallel execution of skill phases
- **RunBudgets** (`shared/run_budgets.py`) — Prevent runaway executions
- **TelemetryLogger** (`shared/event_telemetry.py`) — Track what's working
- **MemoryService** (`shared/memory.py`) — Remember user preferences
- **ResearchClient** (`shared/research.py`) — Web search inside skills

### External Tools to Integrate
| Tool | Purpose | Priority |
|------|---------|----------|
| **Cursor / Claude Code** | Daily development | Already using |
| **yfinance** | Free stock data | Already integrated |
| **python-pptx** | Slide generation | Already integrated |
| **openpyxl** | Excel generation | Already integrated |
| **WeasyPrint** | PDF generation | In dependencies |
| **Playwright** | Web scraping/automation | Already integrated |
| **FireCrawl** | Clean web content extraction | In shared/research.py |

### MCP Servers to Consider
| MCP Server | Purpose |
|------------|---------|
| **filesystem** | Direct file manipulation from agent |
| **postgres** | Direct database queries from agent |
| **brave-search** | Web search without API wrapper |
| **github** | PR/issue management from agent |

## Architecture Principles

1. **Skills are pure logic** — No UI, no framework dependencies
2. **Bridge is the only connector** — Skills never import from ii_agent
3. **Shared infra is optional** — Skills work without database/storage
4. **One tool per skill** — Don't explode the LLM's tool count
5. **Files to workspace** — All outputs end up in `~/.ii_agent/workspace/`
6. **Test through the bridge** — Integration tests use SkillTool, not raw skills
