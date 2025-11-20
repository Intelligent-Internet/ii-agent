# Checkpoint Workflow with Microkernel and Context Modes

## Overview

Complete workflow for checkpoint creation with microkernel generation and context mode transitions.

## Checkpoint Workflow

### 1. Threshold Detection

```python
# Model-specific dynamic threshold
context_window = CONTEXT_WINDOWS[model_id]
threshold_pct = calculate_checkpoint_threshold(context_window)
# 64K → 90%, 128K → 71%, 200K → 59%, 1MB → 15%

checkpoint_threshold = int(context_window * threshold_pct)

if token_count >= checkpoint_threshold:
    # Trigger checkpoint creation
```

### 2. Microkernel Generation (BEFORE Dump)

```python
microkernel = generate_microkernel(message_lists)

# Microkernel contains:
{
    "tasks": [
        {"content": "Implement OAuth callback", "status": "in_progress"},
        {"content": "Add error handling", "status": "pending"}
    ],
    "goals": [
        "Build OAuth login system",
        "Integrate with JWT tokens"
    ],
    "current_activity": [
        {"tool": "Edit", "context": "auth.ts - adding callback handler"},
        {"tool": "Read", "context": "middleware.ts - reviewing auth flow"}
    ],
    "planned_verbs": ["implement", "test", "debug"],
    "important_breadcrumbs": [
        "auth.ts",
        "middleware.ts",
        "jwt.ts",
        "test_oauth.py"
    ]
}
```

**Purpose**: Model knows what will be important breadcrumbs before checkpoint is created.

### 3. Checkpoint Creation

```python
slab_id = await checkpoint_system.create_checkpoint(
    message_lists=message_lists,
    microkernel=microkernel  # Injected into payload and backdrop
)

# Checkpoint stored:
# - slab_001/payload.mp4 (QR-encoded, includes microkernel)
# - slab_001/backdrop.mp4 (QR-encoded, includes microkernel)
# - Indexed: hashtable + (future) vector store
```

**Context NOT evicted** - remains in L1, checkpoint indexed for recall.

### 4. Context Mode Transition

After checkpoint created, model can operate in different modes:

#### Mode 1: SUSPENDED (Microkernel Only)

```python
context_mode.transition_to_suspended(slab_id, microkernel)

# Model sees:
# - Tasks: 2 pending
# - Goals: Build OAuth login
# - Activity: Editing auth.ts
# - Breadcrumbs: auth.ts, middleware.ts, jwt.ts, test_oauth.py
```

**Use case**: Lightweight operation with just the gist. Full context checkpointed but not loaded.

#### Mode 2: HIGH_DETAIL (Expanded Context for Specific Focus)

```python
context_mode.transition_to_high_detail(focus="OAuth token refresh")

# Model can now:
# 1. Use RecallContext("OAuth token refresh") → breadcrumb trail
# 2. Use MicrocontextSubroutine("OAuth token refresh", depth=3, focus="operational")
# → Temporarily expand context with digested slabs
```

**Use case**: Deep dive on specific aspect. Expand context selectively for that focus.

**Workflow**:
1. Query breadcrumbs: `RecallContext("OAuth token refresh")`
2. Get trail: `[slab_001] → [slab_002] ⟳ [slab_003]`
3. Digest relevant slabs: `MicrocontextSubroutine` returns operational state
4. Work on detail with expanded context
5. Return to SUSPENDED when done

#### Mode 3: HIGH_CAPACITY (Empty Context for Pure Thinking)

```python
context_mode.transition_to_high_capacity()

# Context: EMPTY (as minimal as possible)
# Only microkernel present
# Maximum space for thinking
```

**Use case**: Complex reasoning, planning, analysis without historical context weight.

**Workflow**:
1. Enter HIGH_CAPACITY mode
2. Context stripped to microkernel only
3. Model has maximum token budget for pure thinking
4. Think through problem, make plans, reason about architecture
5. Return to NORMAL with conclusions

#### Mode 4: RESUME_NORMAL

```python
context_mode.return_to_normal()

# Back to standard operation
# Context from L1 still available
```

## Complete Example

```python
# 1. Detect threshold
if token_count >= 117_823:  # Claude 200K @ 59%
    # 2. Generate microkernel
    microkernel = generate_microkernel(message_lists)

    # 3. Create checkpoint
    slab_id = await checkpoint_system.create_checkpoint(
        message_lists, microkernel=microkernel
    )
    logger.info(f"Checkpoint {slab_id} created with microkernel")

    # 4. Transition to SUSPENDED mode
    context_mode.transition_to_suspended(slab_id, microkernel)
    # Model now operates on microkernel only

# Later: Need to work on OAuth implementation
context_mode.transition_to_high_detail("OAuth implementation")

# Use tools to expand context
trail = await recall_tool.execute("OAuth implementation")
# Returns breadcrumb trail: [slab_001] → [slab_002] ⟳ [slab_003]

# Digest for detail work
digest = await microcontext_tool.execute(
    query="OAuth implementation",
    depth=3,
    focus="operational"
)
# Returns: pending tasks, files modified, code changes

# Work on implementation with expanded detail...

# Now need to think through architecture
context_mode.transition_to_high_capacity()
# Context cleared to microkernel only, maximum thinking space

# Deep reasoning...

# Resume normal operation
context_mode.return_to_normal()
```

## Key Principles

1. **Microkernel before checkpoint**: Model knows what matters before dump
2. **Context not evicted**: Checkpoint indexed, original context stays in L1
3. **Mode transitions**: SUSPENDED → HIGH_DETAIL → HIGH_CAPACITY → NORMAL
4. **Breadcrumb awareness**: Microkernel tells model what breadcrumbs are important
5. **Empty for thinking**: HIGH_CAPACITY mode strips to minimal context
6. **Tool-driven recall**: LLM decides when to expand (not automatic)

## Benefits

- **Context awareness**: Model understands what to remember before checkpoint
- **Flexible modes**: Suspend, detail dive, or pure thinking as needed
- **Lossless**: Full history preserved, selectively retrieved
- **Efficient**: Only expand context when needed for specific tasks
- **Cognitive offload**: Microkernel maintains minimal state between modes
