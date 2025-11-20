# Slab Checkpoint System - Strategy 5

Tool-driven context recall with checkpoint creation at threshold.

## Architecture

```
L1: Active Context (128K window)
    ↓ at 90% threshold → checkpoint created (context NOT evicted)
L2: Slab Checkpoints (MemVid QR-encoded MP4)
    • payload.mp4   - Operational state (todos, file_refs, tool_calls)
    • backdrop.mp4  - Semantic context (thinking, explanations, intent)
    ↓ indexed via hashtable
L3: Tool-driven recall
    • RecallContext(query) → breadcrumb trail
    • MicrocontextSubroutine(query, depth) → temporary expansion
```

## Files Created

- `breadcrumbs.py` - Breadcrumb data structures and trail rendering
- `slab_checkpoint.py` - Checkpoint creation, indexing, retrieval
- `src/ii_agent/server/chat/tools/recall_context.py` - RecallContext tool
- `src/ii_agent/server/chat/tools/microcontext_subroutine.py` - MicrocontextSubroutine tool
- `src/ii_agent/llm/context_manager/slab_checkpoint_manager.py` - REPL context manager
- Updated `src/ii_agent/server/chat/context_manager.py` - Web UI integration

## Usage

### Web UI

```python
from ii_agent.server.chat.context_manager import ContextWindowManager

# Check and create checkpoint if needed (does NOT evict context)
checkpoint_id = await ContextWindowManager.create_checkpoint_if_needed(
    messages=messages
)

if checkpoint_id:
    logger.info(f"Checkpoint {checkpoint_id} created, context remains in L1")
```

### REPL

```python
from ii_agent.llm.context_manager.slab_checkpoint_manager import SlabCheckpointManager

# Use as context manager
context_mgr = SlabCheckpointManager(
    token_counter=token_counter,
    token_budget=120_000,
    checkpoint_threshold=0.9  # 90% of budget
)

# Apply (creates checkpoint if needed, does NOT truncate)
message_lists = await context_mgr.apply_truncation_if_needed(message_lists)

# Get last checkpoint ID
checkpoint_id = context_mgr.get_last_checkpoint_id()
```

### LLM Tools

Tools are automatically available to the LLM:

**RecallContext** - Query historical checkpoints:
```python
ToolCall(
    tool_name="RecallContext",
    tool_input={"query": "OAuth implementation", "max_results": 5}
)

# Returns breadcrumb trail:
# Query: OAuth implementation
#
# [slab_1732051200] OAuth baseline setup
#   Keywords: OAuth, JWT, auth
#   Files: auth.ts, config.ts
#     → CONTINUATION
# [slab_1732051500] JWT token implementation
#   Keywords: JWT, tokens
#   Files: auth.ts, jwt.ts
```

**MicrocontextSubroutine** - Temporary context expansion:
```python
ToolCall(
    tool_name="MicrocontextSubroutine",
    tool_input={
        "query": "full OAuth implementation history",
        "depth": 3,
        "focus": "operational"  # or "semantic"
    }
)

# Returns digest:
# Microcontext expansion for: full OAuth implementation history
#
# === Checkpoint slab_1732051200 ===
# Pending Tasks:
#   - Implement OAuth callback
#   - Add error handling
# Files Referenced: auth.ts, config.ts, middleware.ts
# Code Changes:
#   - auth.ts
#   - jwt.ts
#
# [NOTE: This context is temporary and will be discarded after returning to coherence level]
```

## Integration Points

### Adding Tools to Chat Service

```python
from ii_agent.server.chat.tools import RecallContextTool, MicrocontextSubroutineTool
from ii_agent.server.chat.context_manager import ContextWindowManager

# Get checkpoint system
checkpoint_system = ContextWindowManager.get_checkpoint_system()

# Create tools
recall_tool = RecallContextTool(checkpoint_system)
microcontext_tool = MicrocontextSubroutineTool(checkpoint_system)

# Add to tool list
tools = [
    recall_tool.get_tool_definition(),
    microcontext_tool.get_tool_definition(),
    # ... other tools
]
```

### Tool Execution

```python
# When LLM calls RecallContext
if tool_call.tool_name == "RecallContext":
    result = await recall_tool.execute(
        query=tool_call.tool_input["query"],
        max_results=tool_call.tool_input.get("max_results", 5)
    )

# When LLM calls MicrocontextSubroutine
if tool_call.tool_name == "MicrocontextSubroutine":
    result = await microcontext_tool.execute(
        query=tool_call.tool_input["query"],
        depth=tool_call.tool_input.get("depth", 3),
        focus=tool_call.tool_input.get("focus", "operational")
    )
```

## Key Principles

1. **Checkpoint, don't evict**: Context stays in L1, checkpoints indexed for recall
2. **Tool-driven**: LLM decides when to recall (not automatic)
3. **Temporary expansion**: Microcontext returns to coherence level after use
4. **Multi-index**: Hashtable (exact match) + future vector (semantic)
5. **Payload/backdrop**: Operational vs semantic separation

## Storage

Checkpoints stored in: `~/.ii_agent/checkpoints/`

Format: QR-encoded MP4 (50-100× compression vs text)

Index: JSON metadata + hashtable for O(1) term lookup

## Next Steps

1. Add vector store integration for semantic search
2. Implement relation inference (FIXES, EXTENDS, etc.)
3. Add checkpoint pruning/archival policies
4. Expose to user via `/recall <query>` and `/microcontext <query>`
