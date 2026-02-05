# Skill Integration Patterns

## Pattern 1: Simple Calculation Skill

Skills that take parameters, compute results, return data.
No file I/O, no external APIs.

**Example:** `quick_lbo_analysis`, `lbo_sensitivity`, `analyze_capital_structure`

```python
def _action(self, ebitda: float, multiple: float = 8.0) -> Dict:
    result = compute(ebitda, multiple)
    return {"success": True, "data": result}
```

**LLM call pattern:**
```json
{
  "name": "skill_ib_toolkit",
  "input": {
    "action": "quick_lbo_analysis",
    "params": {"ebitda": 50, "entry_multiple": 8.0}
  }
}
```

## Pattern 2: File Generation Skill

Skills that produce Excel, PowerPoint, or PDF files.

**Example:** `create_lbo_model`, `generate_full_deck`

```python
def _action(self, company_name: str) -> Dict:
    output_path = str(self.OUTPUT_DIR / f"{company_name}_model.xlsx")
    generate_file(company_name, output_path)
    return {"success": True, "output_path": output_path}
```

**LLM follow-up:** The LLM may use shell tools to copy the file to workspace:
```json
{"name": "shell_run", "input": {"command": "cp /path/to/file.xlsx /workspace/"}}
```

## Pattern 3: Data Fetch + Analysis

Skills that fetch external data, then analyze it.

**Example:** `fetch_company_data` → `quick_lbo_analysis`

The LLM chains these naturally:
1. Call `skill_ib_toolkit(action="fetch_company_data", params={ticker: "AAPL"})`
2. Extract EBITDA from the result
3. Call `skill_ib_toolkit(action="quick_lbo_analysis", params={ebitda: X})`

**The LLM is the orchestrator.** Skills don't need to chain themselves.

## Pattern 4: Multi-Phase Orchestration

For complex analyses that need the TaskGraph engine.

**Example:** Deal Orchestrator (52-prompt system)

```python
async def _run_full_analysis(self, company: str, timeframe: str) -> Dict:
    from ii_skills.shared import TaskGraph, TaskGraphExecutor, get_budget_for_timeframe

    graph = TaskGraph()
    graph.add_phase("collect", parallel=True)
    graph.add_phase("analyze", parallel=False, depends_on=["collect"])
    graph.add_phase("generate", parallel=True, depends_on=["analyze"])

    # Add tasks to phases...

    budget = get_budget_for_timeframe(timeframe)
    executor = TaskGraphExecutor(graph=graph, budget=budget)
    results = await executor.run_all()
    return {"success": True, "results": results}
```

**Note:** This requires the skill to have async support (future enhancement).

## Pattern 5: Scheduled Execution

Skills that run on a schedule (newsletters, dashboards).

**Current approach:** Standalone Python scripts run via APScheduler or cron.
**Future approach:** Skills execute through the bridge on a schedule.

```python
# In ii_agent/cron/tasks.py (future)
from ii_skills.bridge import get_skill_tool

async def run_morning_briefing():
    tool = get_skill_tool("market_newsletter")
    await tool.execute({"action": "generate_newsletter", "params": {}})
    # Send via email...
```

## Pattern 6: Memory-Enhanced Skill

Skills that learn from past interactions.

```python
from ii_skills.shared import MemoryService

def _action(self, company: str) -> Dict:
    memory = MemoryService(user_id="default", skill_name=self.name)

    # Check if we've analyzed this company before
    prior = memory.recall(f"analysis_{company}")
    if prior:
        # Use prior assumptions as defaults
        pass

    result = analyze(company)

    # Store for next time
    memory.remember(
        key=f"analysis_{company}",
        content=result,
        memory_type=MemoryType.DEAL,
    )

    return {"success": True, "data": result}
```

## Anti-Patterns

### Don't: Skills calling LLM directly
Skills should be pure logic. The LLM orchestrates, skills compute.

### Don't: Skills importing from ii_agent
The dependency flows one way: `ii_agent → bridge → ii_skills`.
Never `ii_skills → ii_agent`.

### Don't: Large input schemas per action
Keep params simple. If an action needs complex input, accept a dict
and document the expected keys.

### Don't: Long-running synchronous actions
If an action takes >60 seconds, it should use TaskGraph with budget
enforcement, or break into smaller actions the LLM chains.
