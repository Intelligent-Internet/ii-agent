# Bridge Layer Design

## Purpose

The bridge layer connects `ii_skills` (domain-specific business logic) to
`ii_agent` (LLM orchestration) by wrapping each `BaseSkill` as a `BaseTool`.

## Location

```
src/ii_skills/bridge/
├── __init__.py          # Public API: get_skill_tools, get_skill_tool, list_available_skills
├── skill_tool.py        # SkillTool class (wraps BaseSkill as BaseTool)
└── skill_registry.py    # Discovery, instantiation, filtering
```

## How It Works

### 1. Discovery
When `get_skill_tools()` is called, it imports `ii_skills` which triggers
`discover_skills()` — walking the `ii_skills/` directory and importing each
skill subpackage. Each skill decorated with `@register_skill` gets added
to `_SKILLS` registry.

### 2. Wrapping
For each registered skill, `skill_registry.py`:
1. Calls `get_skill(name, config)` to get an instance
2. Calls `skill.initialize()` to set it up
3. Creates a `SkillTool(skill)` wrapper

### 3. Registration
`agent_service.py` calls `get_skill_tools()` and passes the results to
`tool_manager.register_tools()`. The LLM now sees these as available tools.

### 4. Execution
When the LLM calls `skill_ib_toolkit(action="quick_lbo_analysis", params={...})`:
1. `AgentToolManager.run_tools_batch()` dispatches to `SkillTool.execute()`
2. `SkillTool` extracts `action` and `params` from `tool_input`
3. Calls `skill.execute(action, **params)`
4. Wraps the result as `ToolResult` and returns to the agent loop

## Design Decisions

### One Tool Per Skill (not per action)
- IB Toolkit has 28 actions. Registering 28 separate tools would overwhelm the LLM.
- Instead, each skill is ONE tool with an `action` enum parameter.
- The LLM picks the action from a constrained list — clean and scalable.

### Graceful Degradation
- Bridge import is wrapped in try/except in agent_service.py
- If ii_skills isn't installed, the agent works normally without skills
- Individual skill failures don't break other skills

### No Confirmation Required
- Skills don't modify filesystem or run shell commands directly
- They return data or generate files to a controlled output directory
- No user confirmation prompt needed (unlike shell/file tools)

## Adding the Bridge to a New Agent Type

To make skills available to a specific agent type, the skill tools are
registered alongside other tools in `agent_service.py`. They're currently
available to ALL agent types since they're registered before the filtering
step. To restrict:

```python
# In agent_types.py, add skill tool names to allowed sets:
AgentType.GENERAL: [
    ...existing tools...,
    "skill_ib_toolkit",
    "skill_ir_toolkit",
]
```

Currently, skill tools bypass the allowlist filter because they're registered
directly to the tool manager (same pattern as sub-agents). This means all
agent types can use all skills.

## Error Handling

```
SkillTool.execute()
  → action missing?     → ToolResult(is_error=True, "action is required")
  → action not in caps?  → ToolResult(is_error=True, "Unknown action X")
  → NotImplementedError? → ToolResult(is_error=True, "not implemented")
  → Any exception?       → ToolResult(is_error=True, "Skill execution failed: ...")
```

All errors are caught and returned as `ToolResult` with `is_error=True`,
so the LLM can see the error and adjust its approach.

## Future Enhancements

1. **Telemetry integration** — Use `TelemetryLogger` to track skill executions
2. **Budget enforcement** — Use `RunBudgetConfig` for long-running orchestrations
3. **Async skill execution** — Support `async def execute()` in BaseSkill
4. **Output routing** — Auto-copy generated files to workspace path
5. **Memory integration** — Pass user preferences to skills via MemoryService
