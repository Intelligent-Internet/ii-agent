# REPL UI Gap Analysis

## Current State

**Web UI** (src/ii_agent/server/chat/service.py):
- ✅ Real-time streaming (SSE events)
- ✅ Tool execution (4 tools: web_search, image_search, web_visit, file_search)
- ✅ ReAct loop (iterative LLM → tool → LLM cycles)
- ✅ Usage metrics display (tokens, cache hits)
- ✅ Tool result streaming
- ✅ Multi-turn conversations
- ✅ Cancellation support
- ✅ File uploads

**REPL** (src/ii_agent/cli/repl.py):
- ❌ No streaming (shows "Agent thinking..." then dumps full response)
- ❌ No tools (just direct LLM calls)
- ❌ No ReAct loop (one-shot Q&A only)
- ❌ No usage metrics
- ❌ No tool execution display
- ✅ File context (/add, /drop)
- ✅ Model switching
- ✅ History (in-memory)
- ✅ Multi-provider support (Anthropic, OpenAI, Gemini, NVIDIA)

## Missing UI Features

### 1. **Streaming Response Display**

**Web UI**: SSE events streamed to browser as they arrive
```python
async for event in provider.stream(...):
    yield sse_event  # Browser receives tokens incrementally
```

**REPL needs**: Rich console streaming
```python
with console.status("[bold green]Agent thinking..."):
    async for chunk in provider.stream(...):
        console.print(chunk, end="")  # Print tokens as they arrive
```

### 2. **Tool Execution Display**

**Web UI**: Shows tool calls and results
```json
{
  "type": "tool_result",
  "tool_call_id": "call_123",
  "name": "web_search",
  "output": {"results": [...]}
}
```

**REPL needs**: Rich console panels for tools
```python
# Show tool call
console.print(Panel(
    f"[cyan]Calling tool:[/cyan] web_search\n"
    f"[dim]Query: {tool_input}[/dim]",
    border_style="yellow"
))

# Show tool result
console.print(Panel(
    Markdown(tool_result),
    title="[bold]Tool Result[/bold]",
    border_style="green"
))
```

### 3. **ReAct Loop Visualization**

**Web UI**: Silent loop (only shows final results)

**REPL needs**: Turn counter and state indicator
```python
Turn 1/50: [WAITING_FOR_LLM] ━━━━━━━━━━━━━━━━━━━━ Calling LLM...
Turn 1/50: [TOOL_USE] ━━━━━━━━━━━━━━━━━━━━ Executing 2 tools...
  ├─ web_search(query="python async") ✓
  └─ web_visit(url="...") ✓
Turn 2/50: [WAITING_FOR_LLM] ━━━━━━━━━━━━━━━━━━━━ Calling LLM...
Turn 2/50: [COMPLETE] ━━━━━━━━━━━━━━━━━━━━ Task finished
```

### 4. **Usage Metrics Display**

**Web UI**: Shows token counts per turn
```json
{
  "type": "usage",
  "usage": {
    "input_tokens": 1234,
    "output_tokens": 567,
    "cache_read_tokens": 890
  }
}
```

**REPL needs**: Rich table at end of response
```python
┏━━━━━━━━━━━━━━━━━┳━━━━━━━━┓
┃ Metric          ┃ Count  ┃
┡━━━━━━━━━━━━━━━━━╇━━━━━━━━┩
│ Input tokens    │ 1,234  │
│ Output tokens   │ 567    │
│ Cache read      │ 890    │
│ Total cost      │ $0.045 │
└─────────────────┴────────┘
```

### 5. **Progress Indication**

**Web UI**: Streams token-by-token via SSE

**REPL needs**: Live display with Rich
- Use `Live` for updating displays
- Show progress bars for long operations
- Animate tool execution status

```python
from rich.live import Live
from rich.progress import Progress

with Live(console=console, refresh_per_second=10) as live:
    progress = Progress()
    task = progress.add_task("[cyan]Searching web...", total=100)

    # Update as tool executes
    for i in range(100):
        progress.update(task, advance=1)
        await asyncio.sleep(0.01)
```

### 6. **Multi-File Context Display**

**Web UI**: Shows file list in sidebar

**REPL needs**: Rich file tree
```python
📁 Context Files (3)
├─ src/
│  ├─ main.py (1.2 KB)
│  └─ utils.py (856 B)
└─ README.md (3.4 KB)

Total: 5.5 KB in 3 files
```

## Implementation Priority

### Phase 1: Core ReAct Loop (Required for parity)
1. Integrate AgentController into REPL
2. Replace one-shot chat() with ReAct loop
3. Add tool execution support (use ii_tool's 46 tools)

### Phase 2: UI Polish (Better than Web UI)
1. Streaming token display (Rich Live)
2. Tool execution visualization (panels + spinners)
3. Turn counter and state display
4. Progress bars for long operations

### Phase 3: Metrics & Debugging
1. Usage metrics table after each turn
2. Token cost tracking
3. Cache hit visualization
4. Debug mode (show full prompts)

## Key Insight

**Web UI is feature-complete but presentation is minimal** (just JSON over SSE)

**REPL should be feature-complete AND presentation-rich** (Rich console with colors, panels, trees, progress bars)

The REPL can be **better** than the Web UI for local development because:
- Rich rendering (syntax highlighting, markdown, panels)
- Live updates (progress bars, spinners)
- Better debugging (can show full tool I/O)
- No network overhead
- Full terminal integration (can pipe, grep, etc.)
