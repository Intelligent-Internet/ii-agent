# A2A Event Loop Blockage — Fix Alternatives

## Problem

The Copilot SDK calls tool handlers **on the asyncio event loop thread**. Our handler uses `threading.Event.wait(timeout=300)`, blocking the entire event loop for up to 300s. This kills SSE heartbeats, causing the backend's httpx client to hit ReadTimeout at 120s.

## Confirmed Call Chain (from SDK source inspection)

```
CLI subprocess → JSON-RPC "tool.call"
  → JsonRpcClient._handle_request()           [reader thread]
    → asyncio.run_coroutine_threadsafe(
        _dispatch_request(msg, handler),
        self._loop                              [schedules on EVENT LOOP]
      )
      → _dispatch_request()                    [async, ON EVENT LOOP]
        → handler(params)                      [_handle_tool_call_request, async]
          → _execute_tool_call()               [async, ON EVENT LOOP]
            → result = handler(invocation)     ← OUR sync handler
            → if isawaitable(result):
                result = await result           ← SDK supports awaitable!
              → threading.Event.wait(300)      ← BLOCKS EVENT LOOP 300s
```

## Key SDK Discovery

`ToolHandler = Callable[[ToolInvocation], Union[ToolResult, Awaitable[ToolResult]]]`

The SDK **already supports async/awaitable handlers**. `_execute_tool_call` checks `inspect.isawaitable(result)` and awaits it. This opens a clean fix path.

## Observed Evidence (session 7f5169e1, 2026-04-10)

| Time | Event |
|------|-------|
| 14:04:44.529 | SDK fires `TOOL_EXECUTION_START` → calls our sync handler |
| 14:04:55.725 | Watchdog: **EVENT LOOP BLOCKED** (first alert, 11s after tool start) |
| 14:05:10→14:08:30 | Continuous watchdog alerts every 15s |
| 14:06:44 | Backend `httpx.ReadTimeout` (120s with no SSE data) |
| 14:09:51 | Event loop **unblocks** after exactly 305.8s (300s wait timeout) |

---

## Alternative A: Pure async handler with `asyncio.Event`

Convert sync handler to return `Awaitable[ToolResult]`. Replace `threading.Event` with `asyncio.Event`.

```python
def handler(invocation):
    async_event = asyncio.Event()
    ...
    async def _wait():
        await asyncio.wait_for(async_event.wait(), timeout=300)
        return ToolResult(...)
    return _wait()
```

| Dimension | Assessment |
|-----------|-----------|
| Correctness | SDK's `_execute_tool_call` awaits the result. Event loop stays free. |
| Complexity | Low (~20 lines changed) |
| Risk | Very low — uses SDK's documented contract |
| Thread safety | ⚠️ `asyncio.Event.set()` must be called from the event loop thread |
| Failure modes | If `receive_tool_result` called from non-event-loop thread, unsafe |

**Verdict: Good, but needs thread-safety guard on result delivery.**

---

## Alternative B: Handler returns `loop.run_in_executor()` future

Keep sync handler but wrap blocking wait in thread pool executor:

```python
def handler(invocation):
    result_event = threading.Event()
    ...
    loop = asyncio.get_running_loop()
    def _blocking_wait():
        result_event.wait(timeout=300)
        return ToolResult(...)
    return loop.run_in_executor(None, _blocking_wait)
```

| Dimension | Assessment |
|-----------|-----------|
| Correctness | `run_in_executor` returns awaitable Future. SDK awaits it. |
| Complexity | Low-medium |
| Risk | Low — `run_in_executor` is well-tested stdlib |
| Thread safety | Good — `threading.Event` is thread-safe by design |
| Failure modes | Thread pool exhaustion if many concurrent tool calls (unlikely) |

**Verdict: Good fallback. More robust to threading edge cases but consumes a thread pool thread for 300s.**

---

## Alternative C: Dedicated SDK worker thread

Move entire SDK interaction to a persistent background thread with its own event loop.

| Dimension | Assessment |
|-----------|-----------|
| Correctness | Complete isolation from main event loop |
| Complexity | **High** — second event loop, cross-thread queue, lifecycle management |
| Risk | Medium-high — two event loops hard to debug, subtle deadlocks possible |
| Thread safety | Complex — every cross-loop interaction needs `call_soon_threadsafe` |
| Failure modes | SDK thread crash kills all sessions silently |

**Verdict: Overkill. Reserve for if we discover multiple SDK blocking points.**

---

## Alternative D: Monkey-patch SDK's `_dispatch_request`

Patch `JsonRpcClient._dispatch_request` to wrap handler calls in `run_in_executor`.

| Dimension | Assessment |
|-----------|-----------|
| Correctness | Would work for sync handlers |
| Complexity | Low code, high maintenance burden |
| Risk | **High** — breaks on any SDK update. Async handlers in thread pool → crash |
| Thread safety | Running async handlers in thread pool causes `RuntimeError: no current event loop` |
| Failure modes | SDK update changes internal API → silent breakage |

**Verdict: Do not use. Fragile and incorrect for async handlers.**

---

## Alternative E: Subprocess-based SDK isolation

Run SDK in separate Python process with IPC.

| Dimension | Assessment |
|-----------|-----------|
| Correctness | Complete process isolation |
| Complexity | **Very high** — IPC, process management, reconnection, shared state |
| Risk | Medium — IPC adds latency to every SSE event |
| Thread safety | Excellent — no shared memory |
| Failure modes | IPC disconnect, subprocess OOM, orphan processes |

**Verdict: Massively over-engineered. Only justified if SDK itself is unstable/crashes.**

---

## Alternative F: Async handler + thread-safe delivery ✅ SELECTED

Combine Alt A's async handler with `call_soon_threadsafe` in `receive_tool_result`:

```python
def handler(invocation):
    async_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    self._tool_result_slots[tool_call_id] = (async_event, result_holder, loop)

    async def _wait():
        await asyncio.wait_for(async_event.wait(), timeout=300)
        return ToolResult(...)
    return _wait()

def receive_tool_result(self, tool_call_id, result):
    async_event, result_holder, loop = self._tool_result_slots.pop(tool_call_id)
    result_holder[0] = result
    loop.call_soon_threadsafe(async_event.set)  # safe from any thread
    return True
```

| Dimension | Assessment |
|-----------|-----------|
| Correctness | SDK awaits the result. Event loop stays free for heartbeats/SSE. |
| Complexity | Low (~25 lines changed in `_create_sdk_tools` + `receive_tool_result`) |
| Risk | Very low — uses SDK's `Awaitable[ToolResult]` contract |
| Thread safety | Excellent — `call_soon_threadsafe` is correct way to wake asyncio from any thread |
| Failure modes | If event loop closed before result arrives → handled in `_run_turn` finally |

**Verdict: Best option. Alt A done right with defensive threading.**

---

## Decision

**Selected: Alternative F** — async tool handler returning `Awaitable[ToolResult]` with `call_soon_threadsafe` for cross-thread result delivery. Minimal code change, maximum correctness, uses SDK's intended API contract.
