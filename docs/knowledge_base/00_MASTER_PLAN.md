# II-Agent Master Plan

## Status: Scaffolded → Wired → Testable

This document is the single source of truth for the ii-agent architecture,
its current state, and the path to a functioning end-to-end system.

---

## The Problem (as of 2026-02-05)

Three disconnected systems exist:

| System | Location | Status |
|--------|----------|--------|
| **ii_agent** | `src/ii_agent/` | Working LLM orchestration with tool execution |
| **ii_tool** | `src/ii_tool/` | Working MCP tool server (shell, file, web, browser, slides) |
| **ii_skills** | `src/ii_skills/` | 67+ IB modules, 33 IR modules, shared infra — **completely disconnected** |

`ii_skills` has never been imported by `ii_agent` or `ii_tool`. Zero code paths connect them.

---

## The Solution: Bridge Layer

```
User Message (WebSocket / Desktop App)
    ↓
SocketIOManager.chat_message()
    ↓
CommandHandlerFactory → UserQueryHandler
    ↓
AgentService.create_agent()
    ↓
AgentToolManager.register_tools()
    ├── MCP Tools (shell, file, web, browser, slides)
    ├── Common Tools (RegisterPort, MessageUser)
    ├── Sub-agents (Task, Researcher, DesignDoc, Codex)
    └── ★ NEW: SkillTools (bridge layer) ★
         ├── skill_ib_toolkit    → IBToolkitSkill.execute()
         ├── skill_ir_toolkit    → IRToolkitSkill.execute()
         ├── skill_networth      → NetWorthSkill.execute()
         ├── skill_market        → MarketSkill.execute()
         └── skill_health        → HealthSkill.execute()
    ↓
AgentController.run_impl()
    ↓
LLM decides to call skill_ib_toolkit(action="quick_lbo_analysis", params={...})
    ↓
SkillTool.execute() → BaseSkill.execute() → Returns result
    ↓
Output file saved to workspace → User downloads from desktop app
```

---

## Knowledge Base Index

| Section | Path | Purpose |
|---------|------|---------|
| **Architecture** | `01_architecture/` | System overview, data flow, component relationships |
| **Skill Bridge** | `02_skill_bridge/` | Bridge design, tool registration, routing logic |
| **Environment** | `03_environment/` | .env setup, credentials, deployment |
| **Testing** | `04_testing/` | Test strategy, E2E flows, fixtures |
| **Skills Dev** | `05_skills_development/` | How to build/extend skills |
| **Strategy** | `06_strategy/` | Tooling, roadmap, Claude Code vs Projects |

---

## Implementation Phases

### Phase 1: Wire the Bridge (THIS PR)
- [x] Create `src/ii_skills/bridge/` with SkillTool wrapper
- [x] Wire into `agent_service.py` tool registration
- [x] Add skill agent type to `agent_types.py`
- [x] Create `.env.example`
- [x] Create integration test scaffolding

### Phase 2: Validate with Real Case Study
- [ ] Run a 24-hour LBO case end-to-end through the desktop app
- [ ] Verify Excel output lands in workspace
- [ ] Verify slide output lands in workspace
- [ ] Fix any runtime issues discovered

### Phase 3: Harden Skills
- [ ] Add real formulas to Excel LBO template (currently template-only)
- [ ] Connect data_fetcher to live Yahoo Finance in skill execution
- [ ] Wire deal_orchestrator's 52-prompt system through the bridge
- [ ] Test IR toolkit LP quarterly update flow

### Phase 4: Production Polish
- [ ] Add error handling and retry logic to SkillTool
- [ ] Integrate telemetry (TelemetryLogger) into bridge calls
- [ ] Add budget enforcement for long-running analyses
- [ ] Set up scheduled newsletter skills via APScheduler

---

## File Map: What To Edit For Common Tasks

| Task | Files to Touch |
|------|---------------|
| Add a new skill | `src/ii_skills/new_skill/__init__.py`, bridge auto-discovers it |
| Add a new action to IB toolkit | `src/ii_skills/ib_toolkit/__init__.py` (execute method + capabilities) |
| Change tool registration | `src/ii_agent/server/services/agent_service.py` |
| Change agent permissions | `src/ii_agent/config/agent_types.py` |
| Add new integration test | `tests/integration/` |
| Update environment vars | `.env.example` + `docs/knowledge_base/03_environment/` |

---

## Quick Commands for Claude Code

```
# Context loading — run these before any task:
"Read docs/knowledge_base/00_MASTER_PLAN.md"
"Read docs/knowledge_base/01_architecture/SYSTEM_OVERVIEW.md"

# For bridge work:
"Read docs/knowledge_base/02_skill_bridge/BRIDGE_DESIGN.md"
"Read src/ii_skills/bridge/skill_tool.py"

# For adding a skill:
"Read docs/knowledge_base/05_skills_development/SKILL_TEMPLATE.md"

# For testing:
"Read docs/knowledge_base/04_testing/TEST_STRATEGY.md"
```

---

*Last updated: 2026-02-05*
