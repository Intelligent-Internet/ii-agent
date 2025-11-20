# ReAct Loop FSM Pattern

This document describes the core ReAct FSM pattern used by both Web UI and REPL.

## State Machine

```
States:
  WAITING_FOR_LLM
  EXECUTING_TOOLS
  COMPLETE (terminal)

Transitions:
  WAITING_FOR_LLM -> (finish_reason == TOOL_USE) -> EXECUTING_TOOLS
  WAITING_FOR_LLM -> (finish_reason != TOOL_USE) -> COMPLETE
  EXECUTING_TOOLS -> WAITING_FOR_LLM (loop back)
  COMPLETE -> EXIT
```

## Core FSM Pattern

```python
# Initialize conversation history
messages = [user_message]

# ReAct loop
while True:
    # [FSM STATE] WAITING_FOR_LLM
    run_response = await provider.stream(messages=messages, tools=tools)

    # [FSM STATE UPDATE] Add assistant response to history
    messages.append(assistant_message)

    # [FSM STATE TRANSITION] Decide next state
    if run_response.finish_reason == FinishReason.TOOL_USE:
        # [FSM STATE] EXECUTING_TOOLS
        tool_calls = extract_tool_calls(run_response.content)

        for tool_call in tool_calls:
            # [FSM] Execute tool
            tool_result = await execute_tool(tool_call)
            tool_results.append(tool_result)

        # [FSM STATE UPDATE] Add tool results to history
        messages.append(tool_results_message)

        # [FSM TRANSITION] Loop back to WAITING_FOR_LLM
        continue
    else:
        # [FSM STATE] COMPLETE
        # Task finished
        break
```

## Implementation: Web UI

**Location**: `src/ii_agent/server/chat/service.py:458-618`

**FSM + Concerns**:
- `[FSM]` - Core state machine logic
- `[PRESENTATION]` - SSE streaming, yield events to web UI
- `[PERSISTENCE]` - Database writes, save messages
- `[BUSINESS LOGIC]` - Token management, credit deduction

**Key characteristics**:
- Yields SSE events as `Dict` for HTTP streaming
- Saves messages to PostgreSQL via `MessageService`
- Tracks cancellation via `cancel.raise_if_cancelled(run_id)`
- Deducts credits on completion

## Implementation: REPL

**Location**: `src/ii_agent/controller/agent_controller.py:91-297`

**FSM + Concerns**:
- `[FSM]` - Same core state machine logic
- `[PRESENTATION]` - Console output, event_stream.publish()
- `[PERSISTENCE]` - Optional (SQLite or in-memory)
- `[BUSINESS LOGIC]` - Token truncation, interruption checks

**Key characteristics**:
- Emits `RealtimeEvent` objects via `EventStream`
- Optional persistence (can run fully in-memory)
- Tracks interruption via database `RunStatus.ABORTED`
- No credit deduction (local execution)

## Mapping: Web UI → REPL

| Concern | Web UI | REPL |
|---------|--------|------|
| **Stream LLM response** | `yield sse_event` | `event_stream.publish(AGENT_RESPONSE)` |
| **Stream usage metrics** | `yield {"type": "usage"}` | `event_stream.publish(METRICS_UPDATE)` |
| **Stream tool result** | `yield {"type": "tool_result"}` | `event_stream.publish(TOOL_CALL)` |
| **Save assistant msg** | `MessageService.create_message()` | `history.add_assistant_turn()` |
| **Save tool results** | `MessageService.create_message(role=TOOL)` | `add_tool_call_result()` |
| **Check cancellation** | `cancel.raise_if_cancelled()` | `is_interrupted()` |
| **Complete** | `yield {"type": "complete"}` | `event_stream.publish(COMPLETE)` |

## Pure FSM (No I/O)

For maximum reusability, the core FSM can be extracted to:

**Location**: `src/ii_agent/controller/react_loop.py`

```python
class ReactLoop:
    @staticmethod
    async def run(messages, provider, tools, tool_executor):
        """Pure FSM - yields domain events only."""
        while True:
            # State: WAITING_FOR_LLM
            run_response = await provider.stream(messages, tools)
            yield ReactEvent(type="llm_complete", data=run_response)

            # State transition
            if run_response.finish_reason == FinishReason.TOOL_USE:
                # State: EXECUTING_TOOLS
                for tool_call in extract_tool_calls(run_response):
                    result = await tool_executor(tool_call)
                    yield ReactEvent(type="tool_result", data=result)
                continue
            else:
                # State: COMPLETE
                yield ReactEvent(type="complete", data=run_response)
                break
```

Then Web UI and REPL subscribe to `ReactEvent` and handle I/O separately.

## Benefits of Separation

1. **Testability**: FSM can be tested without HTTP/DB/Console
2. **Reusability**: Same FSM for Web UI, REPL, CLI, API
3. **Clarity**: Clear separation of state transitions vs side effects
4. **Flexibility**: Easy to add new presentation layers (gRPC, WebSocket, etc.)
