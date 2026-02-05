# Operational Runbook

Run lifecycle, event flow, and troubleshooting guidance for ii-agent skills.

---

## Run Lifecycle

### Overview

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│  RUN_START  │───▶│   PHASES    │───▶│    TASKS    │───▶│ RUN_COMPLETE│
└─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘
       │                  │                  │                  │
       ▼                  ▼                  ▼                  ▼
   telemetry          progress           metrics            outputs
```

### Event Flow

1. **Run Started** (`run_started`)
   - Run ID assigned
   - Budget profile loaded
   - Telemetry initialized

2. **Phase Started** (`phase_started`)
   - Tasks identified
   - Dependencies resolved
   - Parallel execution planned

3. **Task Started** (`task_started`)
   - Execution begins
   - Tool calls tracked
   - Sub-agents spawned (if any)

4. **Task Completed/Failed** (`task_completed`, `task_failed`)
   - Duration recorded
   - Results stored
   - Metrics updated

5. **Phase Completed** (`phase_completed`)
   - All tasks resolved
   - Checkpoint saved (optional)
   - Next phase triggered

6. **Run Completed** (`run_completed`)
   - Final outputs packaged
   - Metrics summarized
   - Telemetry finalized

---

## Event Types Reference

### Run Lifecycle Events

| Event | Trigger | Key Fields |
|-------|---------|------------|
| `run_started` | Run initialization | `run_id`, `run_type`, `user_id`, `budget_profile` |
| `run_completed` | Successful completion | `duration_ms`, `tasks_completed`, `outputs` |
| `run_failed` | Fatal error | `error_message`, `error_type`, `last_task` |
| `run_cancelled` | User/budget cancellation | `reason`, `tasks_pending` |

### Phase Lifecycle Events

| Event | Trigger | Key Fields |
|-------|---------|------------|
| `phase_started` | Phase begins | `phase_id`, `task_count`, `task_ids` |
| `phase_completed` | All tasks done | `duration_ms`, `tasks_completed`, `tasks_failed` |
| `phase_failed` | Critical task failed | `error_message`, `failed_task_id` |
| `phase_skipped` | Dependencies unmet | `reason` |

### Task Lifecycle Events

| Event | Trigger | Key Fields |
|-------|---------|------------|
| `task_started` | Task execution begins | `task_id`, `task_name`, `attempt` |
| `task_completed` | Task succeeds | `duration_ms`, `result_summary` |
| `task_failed` | Task fails (final) | `error_type`, `error_message`, `will_retry` |
| `task_retrying` | Retry scheduled | `attempt`, `retry_delay_ms` |
| `task_skipped` | Dependency failed | `reason` |

### Tool Execution Events

| Event | Trigger | Key Fields |
|-------|---------|------------|
| `tool_started` | Tool call begins | `tool_name`, `tool_type` |
| `tool_completed` | Tool returns | `duration_ms`, `output_size_bytes` |
| `tool_failed` | Tool error | `error_type`, `error_message` |

### Sub-Agent Events

| Event | Trigger | Key Fields |
|-------|---------|------------|
| `sub_agent_start` | Sub-agent spawned | `parent_run_id`, `child_run_id`, `agent_type` |
| `sub_agent_progress` | Progress update | `progress` (0-1), `message` |
| `sub_agent_complete` | Sub-agent done | `duration_ms`, `status`, `result_summary` |
| `sub_agent_error` | Sub-agent failed | `error_message`, `error_type` |

---

## Tool Call Flow

```
┌──────────────┐
│  Task Start  │
└──────┬───────┘
       │
       ▼
┌──────────────┐     ┌──────────────┐
│ Tool Started │────▶│   Execute    │
└──────────────┘     └──────┬───────┘
                            │
           ┌────────────────┼────────────────┐
           │                │                │
           ▼                ▼                ▼
    ┌──────────┐     ┌──────────┐     ┌──────────┐
    │ Success  │     │  Retry   │     │  Fail    │
    └────┬─────┘     └────┬─────┘     └────┬─────┘
         │                │                │
         ▼                ▼                ▼
   tool_completed    tool_started    tool_failed
                     (attempt N)
```

### Tool Error Taxonomy

| Error Type | Cause | Retry? |
|------------|-------|--------|
| `timeout` | Execution exceeded limit | Yes |
| `validation` | Invalid input | No |
| `runtime` | Execution error | Maybe |
| `not_found` | Resource missing | No |
| `permission` | Access denied | No |
| `rate_limit` | API throttled | Yes (with backoff) |
| `network` | Connection issue | Yes |
| `unknown` | Unclassified | Maybe |

---

## Troubleshooting Guide

### Common Issues

#### 1. Run Stuck in Phase

**Symptoms:**
- Progress stops
- No task events emitted
- CPU idle

**Causes:**
- Circular dependency in task graph
- All tasks blocked on failed dependency
- Infinite loop in task executor

**Resolution:**
```python
# Check task dependencies
runner.get_blocked_tasks()

# Force phase completion
runner.skip_blocked_tasks()

# Cancel run
runner.cancel("Manual intervention")
```

#### 2. Budget Exceeded

**Symptoms:**
- `budget_exceeded` event
- Run terminated early
- Incomplete outputs

**Causes:**
- Too many tasks
- Long-running tasks
- Excessive retries

**Resolution:**
```python
# Increase budget
config = BudgetProfile.get_profile("thorough")

# Check current usage
enforcer.get_status()

# Adjust budget mid-run
enforcer.extend_budget(max_tasks=100)
```

#### 3. Tool Failures

**Symptoms:**
- `tool_failed` events
- Task retries
- Degraded results

**Causes:**
- API rate limits
- Network issues
- Invalid inputs

**Resolution:**
```python
# Check tool metrics
metrics = get_global_metrics()
summary = metrics.get_tool_summary("web_search")

# View recent errors
errors = metrics.get_recent_errors(limit=10)

# Implement retry with backoff
with metrics.track_execution("api_call") as tracker:
    for attempt in range(3):
        try:
            result = await call_api()
            break
        except RateLimitError:
            tracker.mark_error(ToolErrorType.RATE_LIMIT)
            await asyncio.sleep(2 ** attempt)
```

#### 4. Sub-Agent Not Completing

**Symptoms:**
- `sub_agent_start` without `sub_agent_complete`
- Parent run waiting indefinitely

**Causes:**
- Sub-agent crashed
- Event callback failed
- Missing completion call

**Resolution:**
```python
# Check active sub-agents
tracer.get_active_subagents()

# Force completion
tracer.complete_subagent(
    child_run_id="abc123",
    status="failed",
    error_message="Timeout - forced completion"
)
```

---

## Safe Retry Guidance

### When to Retry

| Scenario | Retry? | Strategy |
|----------|--------|----------|
| Network timeout | Yes | Exponential backoff |
| Rate limit (429) | Yes | Respect Retry-After header |
| Server error (5xx) | Yes | Fixed delay, max 3 attempts |
| Validation error | No | Fix input |
| Auth error (401/403) | No | Check credentials |
| Not found (404) | No | Verify resource exists |

### Retry Implementation

```python
from ii_skills.shared import track_tool_execution, ToolErrorType

async def safe_api_call(url: str, max_retries: int = 3):
    with track_tool_execution("api_call") as tracker:
        for attempt in range(max_retries):
            try:
                response = await http_client.get(url)
                response.raise_for_status()
                return response.json()

            except TimeoutError:
                tracker.mark_error(ToolErrorType.TIMEOUT)
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)

            except RateLimitError as e:
                tracker.mark_error(ToolErrorType.RATE_LIMIT)
                retry_after = e.retry_after or 60
                await asyncio.sleep(retry_after)

            except HTTPError as e:
                if e.status_code >= 500:
                    tracker.mark_error(ToolErrorType.RUNTIME)
                    if attempt < max_retries - 1:
                        await asyncio.sleep(5)
                else:
                    tracker.mark_error(ToolErrorType.VALIDATION)
                    raise  # Don't retry client errors

        raise MaxRetriesExceeded(f"Failed after {max_retries} attempts")
```

---

## Monitoring Checklist

### Pre-Run

- [ ] Budget profile appropriate for task complexity
- [ ] Required credentials available
- [ ] Output directory writable
- [ ] Network connectivity verified

### During Run

- [ ] Progress events emitting regularly
- [ ] No excessive retries (>3 per task)
- [ ] Memory usage stable
- [ ] No zombie sub-agents

### Post-Run

- [ ] All expected outputs generated
- [ ] No `task_failed` events (or understood)
- [ ] Duration within expected range
- [ ] Metrics logged for analysis

---

## Metrics Collection

### Key Metrics to Track

| Metric | Source | Purpose |
|--------|--------|---------|
| Run duration | `run_completed.duration_ms` | Performance baseline |
| Task success rate | `tasks_completed / tasks_total` | Reliability |
| Tool latency P95 | `ToolMetrics.p95_duration_ms` | Bottleneck identification |
| Error rate by type | `ToolMetrics.error_counts` | Root cause analysis |
| Phase duration | `phase_completed.duration_ms` | Phase optimization |

### Exporting Metrics

```python
from ii_skills.shared import get_global_metrics

metrics = get_global_metrics()

# Get summary for all tools
summary = metrics.get_summary()
for tool_name, stats in summary.items():
    print(f"{tool_name}: {stats.success_rate:.1%} success, P95={stats.p95_duration_ms:.0f}ms")

# Export to JSON
import json
with open("metrics.json", "w") as f:
    json.dump({k: v.to_dict() for k, v in summary.items()}, f, indent=2)
```

---

*Last Updated: 2026-02-04*
