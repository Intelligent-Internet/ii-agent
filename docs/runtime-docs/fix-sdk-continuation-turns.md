# Fix: SDK Continuation Turns (Premature Stream Close)

**Commit:** `99eb62f`  
**File:** `src/ii_agent/integrations/a2a/copilot_backend.py`  
**Severity:** Critical — all multi-tool agentic sessions were broken

## Symptom

Sessions using the A2A inner loop (Copilot SDK) stopped prematurely after the first tool call. The agent would load a skill (e.g. `agent-browser`) but never continue to use it. The response was either empty or contained only the skill loading confirmation.

Backend logs showed:
```
A2A client: stream closed (elapsed=8.4s, lines=52, events=25)
```

Adapter logs showed orphaned tool requests after stream close:
```
CopilotBackend: no active stream queue for tool request ... (tool=register_port)
```

## Root Cause

The Copilot SDK's agentic loop fires this event sequence when tools are used:

```
ASSISTANT_TURN_END → ASSISTANT_TURN_START → (new LLM call) → ...
```

`_run_turn()` treated `ASSISTANT_TURN_END` as a terminal event and broke out of the event drain loop. All continuation events (`ASSISTANT_TURN_START`, subsequent tool calls, response text) were orphaned.

### Secondary issue

The initial fix only tracked **bridged** tool executions (`_ToolExecutionRequest`). SDK-internal tools (e.g. `register_port`, code execution) that also trigger continuations were missed. This meant Turn 1→2 worked (bridged Skill tool) but Turn 2→3 failed (internal browser tool).

## Fix

1. **Track ANY tool execution** — set `_turn_had_tools` on both `TOOL_EXECUTION_START` (SDK-internal) and `_ToolExecutionRequest` (bridged).

2. **Skip TURN_END when tools were used** — don't break; instead set `_awaiting_continuation = True` and probe with a 3-second timeout for `ASSISTANT_TURN_START`.

3. **Probe timeout** — if the SDK doesn't fire a continuation event within 3 seconds, the turn is truly done; break cleanly.

4. **Safety limit** — max 50 continuation turns to prevent runaway loops.

## Deployment Note

The adapter code (`copilot_backend.py`) runs **inside the sandbox container**, not the backend. It's baked into the `ii-agent-sandbox:latest` Docker image via `e2b.Dockerfile`. Changes require rebuilding the sandbox image:

```bash
docker builder prune -f  # Clear BuildKit cache if needed
docker build -t ii-agent-sandbox:latest -f e2b.Dockerfile .
```

Existing sandbox containers can be hot-patched via `docker cp` for testing:
```bash
docker cp src/ii_agent/integrations/a2a/copilot_backend.py ii-sandbox-XXXX:/app/ii_sandbox/src/ii_agent/integrations/a2a/copilot_backend.py
# Then restart the adapter tmux session inside the sandbox
```

## Verification

Test session showed 3 successful continuation turns:
- Continuation 1 (5.2s): After Skill tool → browser loaded
- Continuation 2 (37.9s): After browser navigation → screenshot taken
- Continuation 3 (40.0s): After internal tool → response text generated

No orphaned tool requests ("no active stream queue") in adapter logs.
