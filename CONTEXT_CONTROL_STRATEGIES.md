# Context Control Strategies

This document describes the context window management strategies used across Web UI and REPL.

## Overview

**Problem**: LLMs have finite context windows (e.g., 128K tokens). Long conversations exceed these limits.

**Solution**: Multiple strategies for managing conversation history within token budgets.

---

## Strategy 1: Simple Truncation (Web UI)

**Location**: `src/ii_agent/server/chat/context_manager.py`

**Pattern**: Drop oldest messages when reaching threshold

### Parameters
```python
MAX_CONTEXT = 128_000 tokens
REDUCTION_THRESHOLD = 0.9 * MAX_CONTEXT = 115_200 tokens
```

### Algorithm
```python
def reduce_message_tokens(messages: List[Message]) -> List[Message]:
    total_tokens = sum(msg.tokens for msg in messages)

    if total_tokens < 115_200:
        return messages  # Under threshold

    # Remove messages from beginning until:
    # 1. Hit a user message AND
    # 2. Remaining tokens < threshold
    current_tokens = total_tokens
    for i, msg in enumerate(messages):
        current_tokens -= msg.tokens
        if msg.role == USER and current_tokens < 115_200:
            return messages[i:]  # Start from this user message

    return messages  # Fallback
```

### Characteristics
- ✅ Simple and fast (no LLM calls)
- ✅ Guaranteed to stay under threshold
- ❌ Loses early context completely
- ❌ No compression (wastes tokens)
- ❌ Breaks conversation continuity

### Usage
```python
# Called on every ReAct loop iteration (Web UI) - model-aware reduction
messages = ContextWindowManager.reduce_message_tokens(messages, model_id=model_id)
run_response = await provider.stream(messages=messages, tools=tools)
```

---

## Strategy 2: LLM Summarization (AgentController - REPL)

**Location**: `src/ii_agent/llm/context_manager/llm_summarizing.py`

**Pattern**: Use LLM to generate summaries of forgotten messages

### Parameters
```python
TOKEN_BUDGET = 120_000 tokens
max_size = 100 turns  # Maximum message list count
keep_first = 1  # Always keep first message
```

### Algorithm

**Without thinking blocks** (standard mode):
```python
async def apply_truncation(message_lists):
    if len(message_lists) <= max_size and tokens < TOKEN_BUDGET:
        return message_lists

    target_size = max_size // 2  # Cut in half

    # Keep: [first message] + [summary] + [last N messages]
    head = message_lists[:keep_first]
    tail = message_lists[-target_size:]
    forgotten = message_lists[keep_first:-target_size]

    # Generate summary of forgotten messages
    summary = await llm.generate_summary(forgotten)

    # Reconstruct: head + summary + tail
    return head + [summary_message] + tail
```

**With thinking blocks** (extended context mode):
```python
async def apply_truncation_with_thinking_blocks(message_lists):
    # Find last user message (TextPrompt)
    last_prompt_index = find_last_text_prompt_index(message_lists)

    # Only summarize BEFORE last user message
    # This preserves the entire current interaction
    events_to_summarize = message_lists[keep_first:last_prompt_index]
    events_to_keep = message_lists[last_prompt_index:]

    summary = await llm.generate_summary(events_to_summarize)

    return [first_message] + [summary] + events_to_keep
```

### Summary Prompt Structure
```
Track:
- USER_CONTEXT: Essential requirements, goals, clarifications
- COMPLETED: Tasks done, with results
- PENDING: Tasks still needed
- CURRENT_STATE: Variables, data structures

For code tasks, add:
- CODE_STATE: File paths, function signatures
- TESTS: Failing cases, error messages
- CHANGES: Code edits, variable updates
- DEPS: Dependencies, imports
- VERSION_CONTROL_STATUS: Branch, commits, PR status

Example output:
USER_CONTEXT: Fix FITS card float representation
COMPLETED: Modified mod_float() in card.py
PENDING: Create PR, update docs
CODE_STATE: mod_float() in card.py
TESTS: test_format() passed
CHANGES: str(val) replaces f"{val:.16G}"
VERSION_CONTROL_STATUS: Branch: fix-float-precision
```

### Characteristics
- ✅ Preserves semantic information via summarization
- ✅ Compresses history (multiple messages → 1 summary)
- ✅ Adaptive format (code vs non-code tasks)
- ✅ Maintains conversation continuity
- ❌ Expensive (requires LLM call for summary)
- ❌ Slower (async summary generation)
- ❌ Risk of information loss in summary

### Usage
```python
# REPL/AgentController - called before each LLM turn
await self.truncate_history()  # Internally uses LLMSummarizingContextManager
agent_response = await self.agent.astep(self.history)
```

---

## Strategy 3: LLM Compression with TodoWrite Preservation (AgentController Advanced)

**Location**: `src/ii_agent/llm/context_manager/llm_compact.py`

**Pattern**: Generate structured XML summary + preserve active todo list

### Parameters
```python
TOKEN_BUDGET = 120_000 tokens
COMPRESSION_TOKEN_THRESHOLD = 0.7  # Start compressing at 70% of budget
SUMMARY_MAX_TOKENS = 8192  # Max tokens for summary generation
```

### Algorithm
```python
async def apply_truncation(message_lists):
    if tokens < TOKEN_BUDGET:
        return message_lists

    # Extract active TodoWrite tool calls
    todos = extract_todo_list_from_tools(message_lists)

    # Generate comprehensive summary
    summary = await llm.generate_compression_summary(message_lists)

    # Append todo list to summary
    if todos:
        todo_formatted = format_todo_list(todos)
        summary = f"{summary}\n\n{todo_formatted}"

    # Replace entire history with summary
    return [[TextPrompt(text=f"Long horizon task context: {summary}")]]
```

### Todo Preservation
```python
def format_todo_list(todos):
    """
    Extracts latest TodoWrite state and formats:

    ## Active Todo List (Preserved from Context)

    **✓ Completed:**
      1. Implement feature X [HIGH]
      2. Write tests for Y [MED]

    **→ In Progress:**
      3. Debug issue Z [HIGH]

    **○ Pending:**
      4. Refactor module A [LOW]
      5. Update documentation [MED]
    """
```

### Compression Prompt
```
Your task is to create a detailed summary of the conversation.

Before providing your final summary, wrap your analysis in <analysis> tags.

Required sections:

1. Primary Request and Intent: Capture all explicit user requests
2. Key Technical Concepts: Technologies, frameworks discussed
3. Files and Code Sections:
   - File names, code snippets
   - Why each file is important
   - Changes made
4. Problem Solving: Problems solved, ongoing troubleshooting
5. Pending Tasks: Explicitly requested work
6. Current Work: What was being worked on immediately before summary
7. Optional Next Step: Next step in line with user's requests
   - Include direct quotes from recent conversation
   - Verbatim to avoid task drift

Example:
<analysis>
[Thought process ensuring thoroughness]
</analysis>

<summary>
1. Primary Request: User wants to implement OAuth login
2. Key Technical Concepts:
   - OAuth 2.0 flow
   - JWT tokens
   - Express middleware
3. Files and Code Sections:
   - src/auth/oauth.ts
     - Implements OAuth callback handler
     - Code: async function handleOAuthCallback(req, res) {...}
   - src/middleware/auth.ts
     - JWT verification middleware
...
</summary>
```

### Characteristics
- ✅ Maximum compression (entire history → 1 message)
- ✅ Structured summary (7 sections)
- ✅ Todo list preservation (tracks task state)
- ✅ Includes verbatim quotes (prevents drift)
- ✅ Self-reflective (analysis before summary)
- ❌ Most expensive (large prompt for summary)
- ❌ Loses granular turn-by-turn context
- ❌ No way to reference specific earlier messages

### Usage
```python
# AgentController with compact mode
await self.truncate_history()  # Uses LLMCompact if configured
```

---

## Strategy 4: Auto-Summarization with Placeholder (Web UI - Planned)

**Location**: `src/ii_agent/server/chat/context_manager.py:26-86`

**Pattern**: Trigger LLM summary at 95% context window threshold

### Parameters
```python
SUMMARIZATION_THRESHOLD = 0.95  # 95% of context window
CONTEXT_WINDOWS = {
    # Model-specific limits (TODO: populate)
}
```

### Algorithm (Partially Implemented)
```python
async def check_and_summarize(session, model_id):
    context_window = CONTEXT_WINDOWS.get(model_id, 128_000)
    threshold = context_window * 0.95

    total_tokens = session.prompt_tokens + session.completion_tokens
    if total_tokens < threshold:
        return None  # No action needed

    # Get all messages
    messages = await MessageService.list_by_session(session_id)

    # TODO: Call LLM to generate summary
    # summary_text = await llm.summarize(messages)

    # For now: placeholder
    summary_text = f"[Summary of {len(messages)} messages, {total_tokens} tokens]"

    # Save summary as message
    summary_message = await MessageService.create_message(
        role=ASSISTANT,
        parts=[TextContent(text=summary_text)]
    )

    # Update session with summary pointer
    session.summary_message_id = summary_message.id

    return summary_message.id
```

### Message Filtering
```python
async def get_messages_with_summary(session_id, summary_message_id):
    messages = await MessageService.list_by_session(session_id)

    if not summary_message_id:
        return messages  # No summary yet

    # Find summary message
    summary_index = find_message_index(messages, summary_message_id)

    # Keep only messages from summary onward
    filtered = messages[summary_index:]

    # Change summary role to USER so LLM sees it as context
    filtered[0].role = USER

    return filtered
```

### Characteristics
- ✅ Automatic triggering (no manual intervention)
- ✅ Model-specific thresholds
- ✅ Summary stored in DB (persistent)
- ✅ Seamless continuation (summary becomes context)
- ❌ NOT IMPLEMENTED (placeholder only)
- ❌ No actual summarization logic yet

---

## Strategy 5: Slab Checkpoints with Tool-Driven Recall

**Location**: `src/ii_agent/storage/` (memvid, cached_memvid, breadcrumbs)

**Pattern**: Checkpoint to video storage (context not evicted) + LLM-invoked recall tools + temporary microcontext expansion

### Parameters
```python
SLAB_THRESHOLD = 115_200 tokens  # When to create checkpoint (context not evicted)
SLAB_RETENTION = "infinite"      # Never delete checkpoints
BREADCRUMB_MAX = 5               # Max breadcrumbs returned by RecallContext
MICROCONTEXT_DEPTH = 3           # Default slab depth for MicrocontextSubroutine
```

### Architecture
```
L1: Active Context (128K window)
    ↓ threshold hit → checkpoint created (not evicted)
L2: Slab Checkpoints (MemVid QR-encoded MP4)
    • payload.mp4   - Operational state (todos, file_refs, tool_calls)
    • backdrop.mp4  - Semantic context (thinking, explanations, intent)
    ↓ indexed via
L3: Multi-Index Layer
    • Hashtable: term → slab_IDs (exact match, O(1) lookup)
    • VectorStore: embeddings → semantic search
    • MemVid Index: chunk metadata
    ↓ queried by tools
Tool: RecallContext(query)
    Returns: Breadcrumb trail with categorical arrows
    [slab_001] →continuation→ [slab_002] ⟳fixes→ [slab_003]

Tool: MicrocontextSubroutine(query, depth)
    Temporarily expands context for deep-context tools
    Returns to coherence level after completion
```

### Algorithm

**Checkpoint to slab** (context NOT evicted from L1):
```python
async def checkpoint_to_slab(message_lists, slab_id):
    # 1. Generate microkernel BEFORE dumping (tells model what matters)
    microkernel = generate_microkernel(message_lists)
    # Contains: tasks, goals, current_activity, planned_verbs, important_breadcrumbs

    # 2. Separate by retrieval intent
    payload = {
        "microkernel": microkernel,  # Injected for context awareness
        "todos": extract_todos(message_lists),
        "file_refs": extract_file_refs(message_lists),
        "tool_calls": [tc for tc in messages if isinstance(tc, ToolCall)],
        "tool_results": [tr for tr in messages if isinstance(tr, ToolFormattedResult)],
        "code_changes": extract_code_edits(message_lists),
        "test_results": extract_test_outcomes(message_lists),
    }

    backdrop = {
        "microkernel": microkernel,  # Injected for context awareness
        "user_intent": [tp.text for tp in messages if isinstance(tp, TextPrompt)],
        "thinking": [tb.thinking for tb in messages if isinstance(tb, ThinkingBlock)],
        "explanations": [tr.text for tr in messages if isinstance(tr, TextResult)],
        "design_decisions": extract_decisions(message_lists),
    }

    # 3. Write to MemVid (QR-encoded MP4, 50-100× compression)
    memvid.write(json.dumps(payload), f"{slab_id}/payload.mp4")
    memvid.write(json.dumps(backdrop), f"{slab_id}/backdrop.mp4")

    # 4. Index terms and embeddings
    await index_slab(slab_id, payload, backdrop)

    # 5. Return microkernel to model for context awareness
    return slab_id, microkernel
```

**Microkernel generation**:
```python
def generate_microkernel(message_lists):
    """Extract gist before checkpoint."""
    return {
        "tasks": extract_pending_todos(message_lists),
        "goals": extract_user_intent(message_lists[:5]),  # First 5 turns
        "current_activity": extract_recent_tools(message_lists[-5:]),  # Last 5 turns
        "planned_verbs": extract_action_verbs(message_lists[-3:]),  # Last 3 turns
        "important_breadcrumbs": extract_file_refs(message_lists[-10:]),  # Last 10 turns
    }
```

**Context mode transitions**:
```python
# 1. SUSPEND: Checkpoint and operate on microkernel only
context_mode.transition_to_suspended(slab_id, microkernel)
# → Model sees only: tasks, goals, activity, verbs, breadcrumbs

# 2. HIGH_DETAIL: Expand context for deep dive on specific aspect
context_mode.transition_to_high_detail(focus="OAuth token refresh")
# → RecallContext/MicrocontextSubroutine expand detail for this focus

# 3. HIGH_CAPACITY: Empty context for pure thinking
context_mode.transition_to_high_capacity()
# → Minimal context (only microkernel), maximum space for thinking

# 4. RESUME_NORMAL: Return to standard operation
context_mode.return_to_normal()
```

**Breadcrumb retrieval**:
```python
async def query_breadcrumbs(query: str) -> BreadcrumbTrail:
    # Multi-index lookup
    hash_hits = hashtable.get(extract_terms(query))
    vector_hits = await vector_store.search(query, top_k=5)

    # Build breadcrumbs with relations
    breadcrumbs = []
    for slab_id in dedupe(hash_hits + vector_hits):
        crumb = Breadcrumb(
            slab_id=slab_id,
            topic=extract_topic(slab_id),
            keywords=extract_keywords(slab_id),
            relations=infer_relations(slab_id),  # →continuation, ⟳fixes, ↗extends
        )
        breadcrumbs.append(crumb)

    # Arrange semantically (temporal, dependency, or topic clustering)
    return arrange_semantic(breadcrumbs)
```

**Tool: MicrocontextSubroutine** (invoked by LLM when deep context needed):
```python
async def microcontext_subroutine(query: str, depth: int) -> str:
    """Temporarily expand context for tools requiring deep historical context."""

    # Get breadcrumb trail for query
    trail = await query_breadcrumbs(query)

    # Digest top N slabs
    digests = []
    for crumb in trail.breadcrumbs[:depth]:
        digest = await Task(
            subagent_type="Explore",
            prompt=f"""Read {crumb.slab_id}/payload.mp4 and extract:
            - Pending todos (status != completed)
            - Files modified with changes
            - Failed tests with errors
            Return minimal operational digest for: {query}"""
        )
        digests.append(digest)

    # Return combined context (temporary expansion)
    expanded_context = "\n\n".join(digests)

    # Note: After tool execution, this context is discarded
    # Returns to coherence level (base context window)
    return expanded_context
```

### Breadcrumb Relation Types
```python
→   CONTINUATION  # Sequential work
⟳   FIXES         # Corrects prior issue
↗   EXTENDS       # Adds features
⇢   REFERENCES    # Uses prior concepts
⊕   MERGES        # Combines multiple slabs
⊳   DEPENDS       # Requires prior results
◉   CLARIFIES     # Resolves ambiguity
⊗   INVALIDATES   # Disproves assumption
```

### Characteristics
- ✅ Tool-driven recall (LLM invokes RecallContext when needed)
- ✅ On-demand retrieval (not automatic, query-driven)
- ✅ Multi-index (hashtable + vector + memvid metadata)
- ✅ Semantic navigation (breadcrumb trails with typed relations)
- ✅ Payload/backdrop separation (operational vs semantic)
- ✅ 50-100× compression (QR-encoded video vs text)
- ✅ Microcontext subroutines (temporary depth for specific tools)
- ✅ Returns to coherence (context expansion is temporary, not permanent)
- ❌ Complex implementation (requires indexing + navigation layer)
- ❌ Retrieval cost (slab decoding + embedding search)
- ❌ Depends on query quality (LLM must formulate good queries)

### Usage
```python
# Checkpoint creation (threshold hit, context NOT evicted)
if token_count > SLAB_THRESHOLD:
    slab_id = f"slab_{timestamp}"
    await checkpoint_to_slab(message_lists, slab_id)
    # Context remains in L1, checkpoint indexed for tool-driven recall

# Tool: RecallContext (LLM invokes when it needs historical context)
tools = [
    {
        "name": "RecallContext",
        "description": "Query historical context beyond current window. Returns breadcrumb trail.",
        "parameters": {"query": "string"}
    }
]

# LLM calls tool:
# ToolCall(tool_name="RecallContext", tool_input={"query": "OAuth token refresh"})

# Returns breadcrumb trail:
trail = await query_breadcrumbs("OAuth token refresh")
# [slab_001] →continuation→ [slab_002] ⟳fixes→ [slab_003] ↗extends→ [slab_007]

# Tool: MicrocontextSubroutine (for deep-context operations)
# LLM calls when a tool needs extensive context
# ToolCall(tool_name="MicrocontextSubroutine", tool_input={
#     "query": "full OAuth implementation history",
#     "depth": 3  # Number of slabs to digest
# })

# Temporarily expands context:
for crumb in trail.breadcrumbs[:depth]:
    digest = await micro_agent_digest(crumb.slab_id, focus="operational")
    temp_context.append(digest)

# Execute deep-context tool with expanded context
result = await tool_executor(tool_call, context=temp_context)

# Return to coherence level (discard temporary expansion)
temp_context.clear()
```

---

## Comparison Matrix

| Feature | Simple Truncation | LLM Summarizing | LLM Compact | Auto-Summary (Web) | Slab Checkpoint + Recall |
|---------|-------------------|-----------------|-------------|-------------------|---------------------------|
| **Location** | Web UI | REPL/Controller | REPL/Controller | Web UI (planned) | Storage layer + Tools |
| **Trigger** | Every turn | Exceeds budget | Exceeds budget | 95% threshold | Exceeds threshold |
| **Method** | Drop oldest | Summarize middle | Replace all | Summarize all | Checkpoint (not evicted) |
| **Eviction** | Yes | Yes | Yes | Yes | No (context stays, checkpoint indexed) |
| **Recall** | N/A | N/A | N/A | N/A | Tool-driven (RecallContext) |
| **LLM Cost** | None | Medium | High | High | Variable (only when tool invoked) |
| **Compression** | 0% | ~50% | ~90% | ~80% | ~98% (checkpoint storage) |
| **Retrieval** | N/A | N/A | N/A | N/A | Multi-index + breadcrumbs |
| **Microcontext** | No | No | No | No | Yes (temporary expansion) |
| **Todo Preservation** | No | No | Yes | No | Yes (in payload checkpoint) |
| **Continuity** | Poor | Good | Excellent | Excellent | Excellent (tool-navigable) |
| **Speed** | Fast | Slow | Slowest | Slow | Fast (only when tool called) |
| **Implementation** | Complete | Complete | Complete | Incomplete | Not started |

---

## Token Counting

**Location**: `src/ii_agent/llm/context_manager/base.py:35-76`

### Algorithm
```python
def count_tokens(message_lists):
    total = 0
    for i, message_list in enumerate(message_lists):
        is_last_turn = (i == len(message_lists) - 1)

        for message in message_list:
            if isinstance(message, TextPrompt | TextResult):
                total += token_counter.count(message.text)

            elif isinstance(message, ToolFormattedResult):
                total += token_counter.count(message.tool_output)

            elif isinstance(message, ToolCall):
                input_json = json.dumps(message.tool_input)
                total += token_counter.count(input_json)

            elif isinstance(message, ImageBlock):
                total += 1000  # Conservative estimate

            elif isinstance(message, ThinkingBlock):
                # Only count thinking in LAST turn
                if is_last_turn:
                    total += token_counter.count(message.thinking)

            elif isinstance(message, RedactedThinkingBlock):
                total += 0  # Never counted

    return total
```

### Key Rules
1. **Thinking blocks**: Only counted in final turn (not cached)
2. **Images**: Fixed 1000 tokens (conservative)
3. **Tool calls**: Count JSON representation
4. **Redacted thinking**: Always 0 tokens

---

## REPL Context Gap

**Current REPL** (src/ii_agent/cli/repl.py):
```python
class LocalSession:
    def __init__(self):
        self.history: List[Dict] = []  # Simple list, no limits

    def add_message(self, role, content):
        self.history.append({"role": role, "content": content})
        # No truncation, no summarization, no token counting!
```

**Problem**: REPL history grows unbounded. Will exceed context window on long sessions.

**Solution Needed**: Integrate AgentController's ContextManager into REPL

---

## Recommendations

### For Web UI
1. **Implement auto-summarization** (currently placeholder)
2. Use LLM to generate actual summaries at 95% threshold
3. Consider hybrid: simple truncation + periodic summarization

### For REPL
1. **Already has best solution** (LLMCompact with todo preservation)
2. Expose `/compact` command to users
3. Show compression stats after each summary

### For Long-Horizon Tasks
1. **Implement Strategy 5** (Slab Checkpoints + Tool-driven Recall)
2. Add RecallContext tool (query historical checkpoints)
3. Add MicrocontextSubroutine tool (temporary context expansion)
4. Build indexing layer (hashtable + vector + memvid metadata)
5. Teach LLM to invoke tools when context needed (not automatic)

### For Both
1. **Model-specific checkpoint thresholds** (✅ IMPLEMENTED)
   - 64K context → 90% threshold (aggressive)
   - 128K context → 71% threshold (balanced)
   - 200K context → 59% threshold (balanced)
   - 1MB context → 15% threshold (relaxed)
   - Log-scale gradient between 64K and 1MB
2. **Harmonic miss tracking** (✅ IMPLEMENTED)
   - Track edit slips, hallucinations, inconsistencies per model
   - Monitor context pressure ratio when errors occur
   - Recommend threshold tuning based on error patterns
3. **Expose token counts** to users (current usage vs limit)
4. **Warning at 80% threshold** ("approaching context limit")
5. **Configurable strategies** (let users choose truncation vs summarization vs checkpointing)
6. Let GCP fare as it may

---

## Example: REPL Todo Preservation in Action

**Before compression** (Turn 50, 115K tokens):
```
Turn 1: User: "Build OAuth login"
Turn 2: Assistant: "I'll create these files..."
...
Turn 25: Assistant uses TodoWrite:
  - [ ] Implement OAuth callback
  - [x] Create auth middleware
  - [ ] Add error handling
...
Turn 50: [Context limit reached]
```

**After compression** (Turn 51, 8K tokens):
```
Turn 51:
User context: "Long horizon task context:

<summary>
1. Primary Request: Implement OAuth 2.0 login flow
2. Key Technical Concepts: OAuth, JWT, Express
3. Files: src/auth/oauth.ts, src/middleware/auth.ts
...
</summary>

## Active Todo List (Preserved from Context)

**→ In Progress:**
  1. Implement OAuth callback [HIGH]

**✓ Completed:**
  2. Create auth middleware [MED]

**○ Pending:**
  3. Add error handling [MED]
"
```

**Result**: Entire 50-turn conversation compressed to 1 turn, todos preserved verbatim.
