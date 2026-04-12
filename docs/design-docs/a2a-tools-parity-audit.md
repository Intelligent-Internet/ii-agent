# II-Agent Tools Parity Audit

## CLI Native Tools (Copilot CLI Built-ins)

These tools have Copilot CLI equivalents and are NOT bridged (excluded from A2A serialization):

- `Bash` / `BashView` / `BashList` - Shell execution
- `WriteToProcess` - Process input redirection
- `Read` / `Write` / `Edit` / `ApplyPatch` - File I/O
- `StrReplaceEditor` - Text editing

## Tool Base Class Hierarchy

### BaseAgentTool (base.py)

- Abstract base for all agent tools
- Provides: `name`, `description`, `input_schema`, `read_only`, `display_name`, `instructions`
- Hooks: `on_tool_start(agent, fc)`, `on_tool_end(agent, fc)`
- No sandbox requirement by default

### BaseSandboxTool (sandbox/base.py)

- Extends BaseAgentTool
- `requires_sandbox = True` (always)
- `on_tool_start()` calls `_ensure_sandbox()` which:
  - Uses double-checked locking (prevents concurrent sandbox init)
  - Lazily initializes sandbox on first tool use (native inner loop only)
  - Sets `agent.sandbox` and `fc.sandbox` metadata
  - Creates sandbox via SandboxService

### MCPTool (factory/mcp/base.py)

- Extends BaseSandboxTool
- Post-hook: `on_tool_start()` additionally:
  - Calls `super().on_tool_start(agent, fc)` (ensures sandbox)
  - Exposes port via `sandbox.expose_port(mcp.port)`
  - Initializes `self.mcp_client` pointing to sandbox MCP server
- Executes tools via MCP client `call_tool()` method

## Sandbox Initialization Lifecycle

Sandbox initialization follows **two distinct paths** depending on which inner loop strategy is active.

### Native Inner Loop: Lazy Initialization

In the native path, sandbox creation is deferred until the first sandbox-requiring tool fires:

- **Trigger**: `BaseSandboxTool.on_tool_start()` → `_ensure_sandbox()`
- **Location**: `agents/tools/sandbox/base.py` lines 40-67
- **Mechanism**: Double-checked locking via `agent._internal_lock`
- **Cost**: Only incurred if a sandbox tool is actually invoked

### A2A/Copilot Inner Loop: Eager Initialization

The A2A path **must** have a running sandbox before the first LLM turn because the A2A adapter
runs inside the sandbox container on port `18100`. Without an active sandbox, the URL factory
closure raises `RuntimeError`, which poisons the circuit breaker and forces unnecessary fallback
to the native inner loop.

- **Trigger**: `IIAgent._execute_turn()` detects `hasattr(strategy, "_sandbox_ref")`
- **Location**: `agents/agent.py` lines 471-510 (`_ensure_sandbox_for_inner_loop`)
- **Health check**: `_wait_for_a2a_adapter()` polls `/health` with exponential backoff (~20s max)
- **Fallback**: If sandbox init fails, gracefully degrades to `NativeInnerLoop()`

### Deferred Binding Chain

The A2A strategy uses a mutable holder pattern so the sandbox can be wired after strategy creation:

1. `AgentFactory._build_inner_loop_strategy()` creates `sandbox_holder: list = [None]` and a
   closure capturing it (`agents/factory/agent.py` lines 82-104)
2. `A2AInnerLoop._sandbox_ref` is pointed at the same list (`agents/inner_loop.py` line 110)
3. `IIAgent.sandbox` setter fills `strategy._sandbox_ref[0]` with the real sandbox
   (`agents/agent.py` lines 466-469)
4. The `url_factory` closure can then call `sandbox.expose_port(ADAPTER_CONTAINER_PORT)`

### Comparison

| Aspect | Native Inner Loop | A2A/Copilot Inner Loop |
|--------|-------------------|------------------------|
| Init trigger | First sandbox tool use | Before first LLM turn |
| Detection | Automatic (tool start hook) | `hasattr(strategy, "_sandbox_ref")` |
| Why this timing? | No pre-reqs needed | URL factory must resolve adapter port |
| Fallback on failure | Tool error | Graceful fallback to native |
| Health check | None | Polls `/health` for ~20s |
| Cost | Only if tools used | Every A2A session start |

## Complete Tool Inventory

### Shell Tools (BaseSandboxTool)

| Tool | Name | Sandbox | CLI Native |
|------|------|---------|-----------|
| ShellInit | shell_init | ✓ | ✗ |
| ShellRunCommand | bash | ✓ | ✓ (Bash) |
| ShellView | bash_view | ✓ | ✓ (BashView) |
| ShellList | bash_list | ✓ | ✓ (BashList) |
| ShellWriteToProcessTool | write_to_process | ✓ | ✓ (WriteToProcess) |

### File System Tools (MCPTool - all have sandbox)

| Tool | Name | CLI Native | on_tool_start |
|------|------|-----------|---------------|
| FileReadTool | read | ✓ (Read) | super() only |
| FileWriteTool | write | ✓ (Write) | super() only |
| FileEditTool | edit | ✓ (Edit) | super() only |
| ApplyPatchTool | apply_patch | ✓ (ApplyPatch) | super() only |
| StrReplaceEditorTool | str_replace_editor | ✓ (StrReplaceEditor) | super() only |
| GrepTool | grep | ✗ | super() only |
| ASTGrepTool | ast_grep | ✗ | super() only |

### Web Tools (BaseAgentTool - no sandbox)

| Tool | Name | Sandbox | on_tool_start |
|------|------|---------|---------------|
| WebSearchTool | web_search | ✗ | no |
| WebVisitTool | web_visit | ✗ | no |
| WebVisitCompressTool | web_visit_compress | ✗ | no |
| WebBatchSearchTool | web_batch_search | ✗ | no |
| ImageSearchTool | image_search | ✗ | no |
| ReadRemoteImageTool | read_remote_image | ✗ | no |

### Browser Tools (MCPTool - all have sandbox + MCP)

| Tool | Name | on_tool_start |
|------|------|---------------|
| BrowserNavigationTool | browser_navigation | MCPTool (super + mcp_client) |
| BrowserRestartTool | browser_restart | MCPTool |
| BrowserDragTool | browser_drag | MCPTool |
| BrowserClickTool | browser_click | MCPTool |
| BrowserDropdownTool | browser_dropdown | MCPTool |
| BrowserPressKeyTool | browser_press_key | MCPTool |
| BrowserTabTool | browser_tab | MCPTool |
| BrowserWaitTool | browser_wait | MCPTool |
| BrowserEnterTextTool | browser_enter_text | MCPTool |
| BrowserScrollTool | browser_scroll | MCPTool |
| BrowserEnterTextMultipleTool | browser_enter_text_multiple | MCPTool |
| BrowserViewTool | browser_view | MCPTool |

### Media Tools (BaseSandboxTool)

| Tool | Name | Sandbox | on_tool_start |
|------|------|---------|---------------|
| ImageGenerateTool | image_generate | ✓ | super() only |
| VideoGenerateTool | video_generate | ✓ | super() only |

### Slide System Tools (BaseSandboxTool extends SlideToolBase)

| Tool | Name | Sandbox | on_tool_start |
|------|------|---------|---------------|
| SlideWriteTool | slide_write | ✓ | super() only |
| SlideEditTool | slide_edit | ✓ | super() only |
| SlideGenerationTool | slide_generation | ✓ | super() only |
| SlideApplyPatchTool | slide_apply_patch | ✓ | super() only |

### Dev Tools (Mix of BaseSandboxTool and BaseAgentTool)

| Tool | Name | Sandbox | on_tool_start |
|------|------|---------|---------------|
| FullStackInitTool | full_stack_init | ✓ | super() |
| GetDatabaseConnection | get_database_connection | ✓ | super() |
| SaveCheckpointTool | save_checkpoint | ✓ | **custom override** (calls super().on_tool_start) |
| RestartServerTool | restart_server | ✓ | super() |
| AddUserEnvTool | add_user_env | ✓ | super() |
| AskUserEnvTool | ask_user_env | ✓ | super() |
| AskUserSelectTool | ask_user_select | ✗ (BaseAgentTool) | no |
| GetServerStatusTool | get_server_status | ✗ (BaseAgentTool) | no |
| MobileAppInitTool | mobile_app_init | ✓ | super() |
| RestartMobileServerTool | restart_mobile_server | ✓ | super() |

### Productivity Tools (BaseAgentTool - no sandbox)

| Tool | Name | Sandbox | on_tool_start |
|------|------|---------|---------------|
| TodoReadTool | todo_read | ✗ | no |
| TodoWriteTool | todo_write | ✗ | no |

### Utility Tools

| Tool | Class | Sandbox | on_tool_start |
|------|-------|---------|---------------|
| SkillTool | BaseSandboxTool | ✓ | **custom override** (stores agent ref) |
| TaskAgentTool | BaseAgentTool | ✗ | custom (agent delegation) |
| SendUserFile | BaseSandboxTool | ✓ | super() |
| RegisterPortTool | BaseSandboxTool | ✓ | super() |
| PlanModificationSuggestionsTool | BaseAgentTool | ✗ | no |
| TodoWriteTool | BaseAgentTool | ✗ | no |
| A2AAgentTool | BaseAgentTool | ✗ | no |

### Connector Tools (BaseSandboxTool + custom MCP)

| Tool | Type | Sandbox | on_tool_start |
|------|------|---------|---------------|
| ComposioMCPTool | MCPTool subclass | ✓ | super() + mcp_client |
| UserMCPTool | MCPTool subclass | ✓ | super() + mcp_client |
| GitHubAgentTool | BaseSandboxTool | ✓ | super() |

## Backend Comparison

### CopilotBackend.stream()

```python
async def stream(
    prompt: str,
    context_id: str,
    task_id: str | None = None,
    *,
    parts: list[Any] | None = None,
    tool_schemas: list[dict[str, Any]] | None = None,  # ← KEY DIFFERENCE
) -> AsyncGenerator[str, None]
```

- ✓ Accepts `tool_schemas` parameter
- ✓ Registers tools via Copilot SDK `create_session(tools=[…])`
- ✓ Bridges custom tool execution back to adapter
- ✓ Maps SDK events → A2A SSE (ASSISTANT_MESSAGE, TOOL_EXECUTION, etc.)
- Full capability for arbitrary tool calls via bridging

### ClaudeCodeBackend.stream()

```python
async def stream(
    prompt: str,
    context_id: str = "default",
    task_id: str | None = None,
    *,
    parts: list[Any] | None = None,
) -> AsyncGenerator[str, None]
```

- ✗ NO `tool_schemas` parameter
- Claude CLI subprocess (--output-format stream-json)
- Limited to Claude Code's built-in capabilities
- Maps JSONL events → A2A SSE
- No arbitrary tool execution support

### CodexBackend.stream()

```python
async def stream(
    prompt: str,
    context_id: str = "default",
    task_id: str | None = None,
    *,
    parts: list[Any] | None = None,
) -> AsyncGenerator[str, None]
```

- ✗ NO `tool_schemas` parameter
- OpenAI Codex subprocess (--full-auto --no-sandbox)
- Cost-optimized for shell/file/code (cheaper than Claude)
- Maps JSONL/text output → A2A SSE
- No arbitrary tool execution support

## Tool Dependency Matrix

### Tools that require `agent` parameter

- AgentAsTool (wraps another agent)
- TaskAgentTool (manages delegated tasks)
- Delegation functions (adelegate_task_to_member, adelegate_task_to_all_members)

### Tools with sandbox dependency

**Explicit (requires_sandbox=True, has on_tool_start):**

- All BaseSandboxTool subclasses (40+ tools)
- Native path: lazy provisioning via `_ensure_sandbox()` on first tool use
- A2A path: eager provisioning via `_ensure_sandbox_for_inner_loop()` before first LLM turn

**Required parameters in on_tool_start hook:**

- `agent: IIAgent` - required to access/set agent.sandbox
- `fc: FunctionCall` - required to attach sandbox metadata

### Tools that execute externally (non-server)

- E2B/Docker sandbox tools (ShellRunCommand, dev tools, etc.)
- Browser tools (require sandbox MCP server)
- MCP tools (require sandbox MCP client connection)

## Bridging Constraints

- CLI_NATIVE_TOOL_NAMES (7 tools) excluded from A2A bridging
- Only CopilotBackend can accept `tool_schemas` parameter
- ClaudeCodeBackend and CodexBackend have **NO** tool schema support
- Bridged tools executed by adapter, results posted back to agent
- Tool bridge uses `FunctionCall.aexecute()` for proper pre_hook → entrypoint → post_hook chain
- Bridge emits `tool_call_started` and `tool_call_completed` ModelResponse events
