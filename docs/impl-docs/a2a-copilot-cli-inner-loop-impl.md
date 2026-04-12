# A2A + Copilot CLI Inner Loop — Implementation Status

> **Status**: Phase 8 complete (tool bridge) — interop remediation in progress  
> **Last updated**: 2026-04-09  
> **Design reference**: [a2a-copilot-cli-inner-loop-strategy.md](../design-docs/a2a-copilot-cli-inner-loop-strategy.md)  
> **Branch**: `rebase/local-docker-sandbox`

---

## Naming Disambiguation: Two Unrelated Usages of "Claude Code" / "Codex"

> This section exists because the names **Claude Code** and **Codex** appear in two completely separate parts of the codebase with architecturally distinct meanings.  Conflating them is a common source of confusion.

### Usage 1 — Agent Personas (pre-existing chat feature, unrelated to A2A)

`AgentType.CLAUDE_CODE` and `AgentType.CODEX` are **ii-agent session personas** defined in
`src/ii_agent/agents/types.py` and `src/ii_agent/agents/factory/tools.py`.
They are named tool-and-model configurations that a user selects when starting a chat:

```
User selects "Codex" persona (AgentType.CODEX)
  → ii-agent runs its NATIVE inner loop
  → executes ii-agent-managed tools: ShellRunCommand, FileReadTool, ApplyPatchTool …
  → calls whatever LLM the user has configured (any provider/model)
  → no subprocess spawned, no A2A protocol, no external CLI invoked
```

The name reflects the **workflow style** (code-centric, shell-heavy), not invocation of any external
binary.  These personas predate the A2A work entirely.

### Usage 2 — A2A Inner Loop Replacement Backends (this document)

`ClaudeCodeBackend` and `CodexBackend` in `src/ii_agent/integrations/a2a/` are
**subprocess adapters** for `adapter_server.py`.  They are backend options for replacing
ii-agent's inner LLM call with an external CLI process:

```
ii-agent (inner_loop_mode="a2a")
  → A2AInnerLoop → HTTP SSE → adapter_server.py (running in sandbox)
    → --backend claude-code: spawns `claude --output-format stream-json`
    → --backend codex:       spawns `codex --full-auto --no-sandbox`
    → maps CLI stdout → A2A SSE → back to ii-agent
```

Here the CLI binary **is** the LLM.  The provider and model are determined by the CLI's own
auth credentials (`ANTHROPIC_API_KEY` / `OPENAI_API_KEY`), not by ii-agent's model config.

### Summary table

| | Usage 1: Agent Persona | Usage 2: A2A Backend (this doc) |
|---|---|---|
| Symbol | `AgentType.CLAUDE_CODE` / `AgentType.CODEX` | `ClaudeCodeBackend` / `CodexBackend` |
| Location | `agents/types.py`, `agents/factory/tools.py` | `integrations/a2a/` |
| What it changes | Tool set for the session | Which process generates LLM responses |
| Inner loop | Native (ii-agent's own) | **Replaced** — the CLI is the LLM |
| CLI binary spawned? | No | Yes |
| User-visible | Yes — persona selector in UI | No — sandbox infrastructure |
| LLM provider | User's configured model | CLI's own auth key |

The two usages share names but have **no shared code path**.  There is no connection between
`AgentType.CODEX` and `CodexBackend`.

**Primary A2A backend**: `CopilotBackend` (`--backend copilot`) — see
[a2a-copilot-cli-inner-loop-strategy.md](../design-docs/a2a-copilot-cli-inner-loop-strategy.md).
`ClaudeCodeBackend` and `CodexBackend` are secondary / evaluation options assessed in
[inner-loop-competitor-analysis.md](../design-docs/inner-loop-competitor-analysis.md).

---

## What Has Been Built

### Protocol baseline status

This implementation tracks two protocol baselines:

| Surface | Version | Status |
|---|---|---|
| Public A2A specification | 1.0.0 | Released compatibility target |
| Local Python SDK in repo venv | `a2a-sdk 0.3.9` | Installed runtime package baseline (pinned; latest stable: 0.3.25) |

Implication:

- Current adapter behavior is production-usable for ii-agent internal integration, where production-usable means deterministic internal consistency plus a future-proof migration path.
- Full wire-level A2A 1.0 compatibility hardening remains an explicit follow-up workstream before external interop claims.

Definition used in this repository:

1. Internal consistency: runtime behavior is coherent across adapter routes, event envelopes, auth boundaries, authorization scoping, and fallback paths.
2. Future-proofness: profile boundaries are explicit and migration to strict interop remains additive and test-driven.
3. Interop claim boundary: strict external A2A 1.0 compatibility is only claimed after Track A/B/C completion against the canonical matrix in [a2a-implementation-handoff.md](../design-docs/a2a-implementation-handoff.md).

### Compaction ownership status (cross-backend)

To avoid dueling compactors between ii-agent and delegated runtimes, the implementation follows the design principle that **ii-agent DB history is canonical** and delegated runtime context is reconstructible.

Implemented today:

| Capability | Status | Notes |
|---|---|---|
| Context reconciliation after fallback | Done | Implemented in `A2AInnerLoop` via `_last_owner` and fresh `context_id` suffix after native fallback |
| Backend session continuity hooks | Done | Claude: `--resume SESSION_ID`; Codex: `--conversation-id`; Copilot path uses context reuse contract |
| Canonical-state precedence | Done | Design + runtime behavior treat ii-agent persisted history as source of truth |

Not yet fully enforced:

| Capability | Status | Planned direction |
|---|---|---|
| Single online compactor lock | Done | Per-session `asyncio.Lock` in `compaction_lock.py`: `A2AInnerLoop` acquires before A2A stream; `ContextWindowManager.check_and_summarize_after_response` checks `is_compaction_locked()` and skips summarization when held |
| Compaction authority telemetry | Done | `CompactionAuthorityEvent` yielded by `A2AInnerLoop` on lock acquisition; `CompactionSkippedEvent` defined for skip-side telemetry; structured log emitted from `ContextWindowManager` |
| Copilot SDK compaction thresholds | Done | `CopilotConfig` exposes `background_compaction_threshold` / `buffer_exhaustion_threshold`; wired into `create_session` / `resume_session` via `infinite_sessions` kwarg |
| Cross-authority summary chaining prevention | Done | `summary_authority` column on `chat_summaries` (migration `20260407_000003`); `create_chained_summary()` guard blocks cross-authority chains (creates standalone summary instead); `check_and_summarize_after_response` / `compress_context_if_needed` pass `summary_authority="native"` |

Backend-specific note:

- Copilot SDK path supports background session compaction controls via `InfiniteSessionConfig` thresholds wired from `CopilotConfig`.
- Claude Code performs automatic context compression inside its subprocess. This is invisible and uncontrollable — no API hook exists to disable or defer it. The compaction lock guards ii-agent's native summarization side only; Claude Code's internal compression does not touch the canonical DB history.
- Codex relies on model/context-window management with best-effort continuity. No compaction hook exists. Like Claude Code, Codex's internal context management is opaque and does not affect canonical DB history.

Because of this variance, compaction behavior is treated as backend-specific execution detail, while ii-agent persistence remains canonical. The compaction lock prevents *ii-agent's* native summarization from racing with a delegated turn. It does **not** — and cannot — prevent the CLI backend from performing its own internal compression. This is safe because CLI-side compaction only affects the CLI's ephemeral working context, never the canonical message history in PostgreSQL.

### Phase 1: Pluggable inner-loop strategy layer

All of Phase 1 from the design (§7) is implemented and tested.

#### `src/ii_agent/core/config/agent.py` — `AgentSettings`

Six new fields added under the `AGENT_` env prefix:

| Field | Type | Default | Env var |
|---|---|---|---|
| `inner_loop_mode` | `Literal["native","a2a"]` | `"native"` | `AGENT_INNER_LOOP_MODE` |
| `a2a_agent_url` | `str \| None` | `None` | `AGENT_A2A_AGENT_URL` |
| `a2a_timeout_seconds` | `float` | `30.0` | `AGENT_A2A_TIMEOUT_SECONDS` |
| `a2a_fallback_to_native` | `bool` | `True` | `AGENT_A2A_FALLBACK_TO_NATIVE` |
| `a2a_context_reuse` | `bool` | `True` | `AGENT_A2A_CONTEXT_REUSE` |
| `a2a_backend` | `Literal["copilot","claude-code","codex"]` | `"copilot"` | `AGENT_A2A_BACKEND` |

`a2a_agent_url` is an **external-agent/development override only**. In production the URL is resolved per-sandbox via `expose_port()` — see [URL resolution](#url-resolution) below.

#### `src/ii_agent/agents/inner_loop.py`

Three classes:

**`InnerLoopStrategy` (Protocol)**

```python
class InnerLoopStrategy(Protocol):
    def aresponse_stream(
        self, *, model, messages, response_format, tools,
        tool_choice, tool_call_limit, run_response,
    ) -> AsyncIterator[Union[ModelResponse, RunOutputEvent]]: ...
```

**`NativeInnerLoop`**

Wraps the existing path: delegates directly to `model.aresponse_stream()`. Zero behavioral change when `AGENT_INNER_LOOP_MODE=native` (the default).

**`A2AInnerLoop`**

```python
@dataclass
class A2AInnerLoop:
    client: IIAgentA2AClient
    fallback_strategy: InnerLoopStrategy = field(default_factory=NativeInnerLoop)
    fallback_to_native: bool = True
    context_reuse: bool = True
    circuit_breaker: CircuitBreaker = field(default_factory=CircuitBreaker)
    tool_router: ToolRoutingLayer = field(default_factory=ToolRoutingLayer)
    # Mutable holder for deferred sandbox binding (see § URL resolution).
    _sandbox_ref: list = field(default_factory=lambda: [None], init=False, repr=False)
    _last_owner: str = field(default="", init=False, repr=False)
```

The `_sandbox_ref` field supports the deferred sandbox binding pattern:
when the factory creates the strategy before a sandbox exists, it stores
a `[None]` list here.  The agent's `sandbox` setter later fills `[0]`
with the real sandbox so the `url_factory` closure can resolve the
adapter port.

- Sends all messages to `client.astream()` and maps each `A2AStreamEvent` to `ModelResponse` via `_map_event()`.
- On any exception: if `fallback_to_native` is `True`, transparently switches to `fallback_strategy.aresponse_stream()` and logs a warning. If `False`, raises `ModelProviderError`.
- Context ID is sourced (in priority order) from `run_response.session_id`, `run_response.run_id`, or `"default"`.

**Event mapping table**

| A2A event type(s) | Mapped `ModelResponse` |
|---|---|
| `assistant.message_delta`, `text_delta`, `message_delta` | `content=delta`, `is_delta=True`, `delta_status="content_started"` |
| `assistant.reasoning_delta`, `reasoning_delta` | `reasoning_content=delta`, `is_delta=True`, `delta_status="reasoning_started"` |
| `assistant.reasoning`, `reasoning_done` | `reasoning_content=content`, `is_delta=True`, `delta_status="reasoning_done"` |
| `assistant.message`, `message_complete`, `content_done` | `content`, `tool_calls`, `is_delta=False`, `delta_status="content_done"` |
| `assistant.usage`, `usage` | `response_usage=Metrics(input/output/total/cache/reasoning tokens, cost, duration)` |
| `session.error`, `error` | raises `ModelProviderError(message)` |
| any other | `None` — silently ignored |

> **Note:** `assistant.message` / `content_done` uses `is_delta=False` so the
> agent **replaces** (not appends) the accumulated content and emits an
> `AgentResponseEvent` (finalize) instead of `AgentResponseDeltaEvent`.
> This matches the native Anthropic model's `ContentBlockStopEvent` behavior
> and prevents text duplication in the frontend.

#### `src/ii_agent/integrations/a2a/as_client.py` — `IIAgentA2AClient`

Minimal async HTTP client for adapter streaming endpoints.

**Constructor** — supply one of:
- `agent_url: str` — static URL (for external agents, tests, and development)
- `url_factory: Callable[[], Awaitable[str]]` — async factory for per-sandbox URL resolution (cached after first call)

**`astream(messages, context_id, metadata)`** — POSTs to `{url}/message:stream`, streams SSE lines, yields `A2AStreamEvent`. Handles owned/borrowed `httpx.AsyncClient` lifecycle.

**`_parse_stream_line(line)`** — static; handles `data:` SSE prefix, skips `[DONE]` and non-JSON, extracts `type`/`event` and `data` fields.

#### `src/ii_agent/integrations/a2a/adapter_server.py`

Minimal runnable FastAPI MVP adapter for local development and frontend testing. This replaces the old "localhost adapter" concept with a proper skeleton that will graduate into the real sandbox-hosted adapter.

Endpoints:

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Liveness check — returns `{"status": "ok"}` |
| `GET` | `/.well-known/agent-card.json` | A2A agent card discovery |
| `POST` | `/message:stream` | SSE streaming — emits the current internal compatibility event sequence |
| `POST` | `/message:send` | Synchronous — collects full stream and returns an A2A Task object |
| `GET` | `/tasks/{task_id}` | Return a previously submitted task by ID |
| `POST` | `/tasks/{task_id}:cancel` | Cancel a task in submitted or working state |

Event sequence emitted per request:

```
assistant.reasoning_delta  →  {"delta": "Analyzing request..."}
assistant.message_delta    →  {"delta": <first half of echo text>}
assistant.message_delta    →  {"delta": <second half of echo text>}
assistant.message          →  {"content": <full echo>, "tool_calls": []}
assistant.usage            →  {"input_tokens": N, "output_tokens": M, "total_tokens": N+M, "duration": 0.05}
[DONE]
```

Run locally:

```bash
uv run python -m ii_agent.integrations.a2a.adapter_server --host 0.0.0.0 --port 18100
```

#### `src/ii_agent/agents/sandboxes/docker.py`

Added:

```python
ADAPTER_CONTAINER_PORT = 18100  # A2A adapter process inside the sandbox
```

Added to `DEFAULT_EXPOSED_PORTS` so port 18100 is host-mapped at container creation time. The adapter process can start inside the container at any point afterwards and `expose_port(18100)` will resolve immediately.

#### `src/ii_agent/agents/factory/agent.py` — `AgentFactory`

`_build_inner_loop_strategy(sandbox: Optional[Sandbox] = None) -> InnerLoopStrategy`

Four-branch selection logic:

```
mode == "native"
  → NativeInnerLoop()

mode == "a2a", sandbox provided  (production path)
  → A2AInnerLoop(
        client=IIAgentA2AClient(url_factory=lambda: sandbox.expose_port(18100)),
        ...
    )

mode == "a2a", no sandbox, AGENT_A2A_AGENT_URL set  (dev / external agent path)
  → A2AInnerLoop(
        client=IIAgentA2AClient(agent_url=config.a2a_agent_url),
        ...
    )

mode == "a2a", no sandbox, no URL  (deferred sandbox binding)
  → sandbox_holder = [None]
  → _deferred_url() closure reads sandbox_holder[0]
  → A2AInnerLoop(
        client=IIAgentA2AClient(url_factory=_deferred_url),
        ...
    )
  → strategy._sandbox_ref = sandbox_holder
```

**Deferred sandbox binding** — Handlers (query, plan, continue_run) create the agent
*before* the sandbox is initialized, so `sandbox=None` at strategy construction time.
The fourth branch creates an `A2AInnerLoop` with a `url_factory` closure that reads
from a shared mutable list (`sandbox_holder`).  When the sandbox is later initialized,
`IIAgent.sandbox` setter fills `strategy._sandbox_ref[0] = sandbox`, which is the
same list the closure references.  The first A2A call then resolves the adapter URL
via `sandbox.expose_port(ADAPTER_CONTAINER_PORT)`.  If the sandbox was never bound,
the closure raises `RuntimeError`.

`create_agent()` and `create_task_agent_tool()` both accept `sandbox: Optional[Sandbox] = None` and pass it to `_build_inner_loop_strategy`. All existing call sites (handlers) pass `None` implicitly, triggering the deferred binding path for A2A mode.

### URL resolution  {#url-resolution}

The A2A adapter URL is **never a static global config value in production**. The design (§2.5) is clear: the adapter runs inside each sandbox container, listening on container port 18100. The host-mapped port differs per sandbox instance.

Resolution path:

```
AgentFactory.create_agent(sandbox=sandbox)
  → _build_inner_loop_strategy(sandbox)
    → IIAgentA2AClient(url_factory=lambda: sandbox.expose_port(18100))
      → URL resolved lazily on first astream() call
      → cached afterwards
```

`AGENT_A2A_AGENT_URL` is only consulted when no sandbox is injected (CI, standalone tests against an external agent endpoint).

### Credit billing bypass — `CREDITS_BILLING_ENABLED`

A global toggle for self-hosted/local deployments where the operator pays directly for API keys and does not want credit deductions.

**`src/ii_agent/core/config/credits.py`** — `CreditsSettings`

```python
billing_enabled: bool = Field(
    default=True,
    description="Master toggle for credit billing. When False, no credits are "
                "deducted for any LLM or tool usage regardless of config_type.",
)
```

Environment variable: `CREDITS_BILLING_ENABLED=false` (under the `CREDITS_` prefix).

**Three bypass points:**

| Location | Bypass mechanism |
|---|---|
| `credits/usage/handler.py` — `CreditUsageHandler.on_event()` | Early return when `self._billing_enabled is False`. Handler receives the flag via constructor (wired in `app/lifespan.py`). |
| `chat/application/chat_service.py` — `_check_credits()` | Early return when `get_settings().credits.billing_enabled is False`. Skips pre-run credit gate. |
| `sessions/service.py` — session credit check | Guard added: `if not model_config.is_user_model() and get_settings().credits.billing_enabled:`. Skips balance check on session validation. |

### Sandbox auth token forwarding — `_a2a_adapter_env()`

**`src/ii_agent/agents/sandboxes/docker.py`** — `DockerSandbox._a2a_adapter_env(cfg)`

Static method that builds environment variables for the sandbox A2A adapter container. Called at container creation time and merged into the `environment` dict.

| Variable | Source | Purpose |
|---|---|---|
| `SANDBOX_ADAPTER_BACKEND` | `cfg.agent.a2a_backend` | Tells `start-services.sh` which backend to launch |
| `GITHUB_TOKEN`, `GH_TOKEN` | `os.environ` | Copilot CLI authentication |
| `ANTHROPIC_API_KEY` | `os.environ` | Claude Code CLI authentication |
| `OPENAI_API_KEY` | `os.environ` | Codex CLI authentication |

All token env vars from the backend process environment are forwarded if non-empty, regardless of which backend is selected. This allows runtime backend switching inside the sandbox without re-creating the container.

---

---

## Phase 2: Reliability, Observability, and Sync Task API

All Phase 2 items below were implemented in the 2026-04-04 session.

### `src/ii_agent/integrations/a2a/circuit_breaker.py` — `CircuitBreaker`

Three-state circuit breaker (CLOSED → OPEN → HALF_OPEN) wrapping A2A adapter calls in `A2AInnerLoop`.

**States**

| State | Behaviour |
|---|---|
| `CLOSED` | Normal. Calls pass through. Failure counter incremented on each error. |
| `OPEN` | Short-circuit. Calls raise `CircuitBreakerOpenError` immediately. After `cooldown_seconds`, transitions to HALF_OPEN. |
| `HALF_OPEN` | Probe mode. The next call is allowed through. Success → CLOSED (reset). Failure → re-OPEN. |

**Constructor** — `failure_threshold: int = 5`, `cooldown_seconds: float = 60.0`.  
**Async-safe** — uses `asyncio.Lock` internally.  
**Key methods** — `check()`, `record_success()`, `record_failure()`, `remaining_cooldown()`, `reset()`.

The circuit breaker is stored as a `CircuitBreaker` field on `A2AInnerLoop` (created per-loop instance, defaulting to 5-failure / 60s settings).

### `A2AInnerLoop` — Updated circuit breaker integration

`A2AInnerLoop.aresponse_stream()` now does:

1. **Pre-call `circuit_breaker.check()`** — if open, skip A2A entirely and yield a `DelegationFallbackEvent`.
2. **On success** — call `circuit_breaker.record_success()` after stream completes.
3. **On exception** — call `circuit_breaker.record_failure()`, log failure count, yield `DelegationFallbackEvent`, then proceed to native fallback (if enabled).

The constructor signature gains one new field: `circuit_breaker: CircuitBreaker = field(default_factory=CircuitBreaker)`.

### `DelegationFallbackEvent` — new realtime event

Added to `src/ii_agent/realtime/events/app_events.py`:

```python
class DelegationFallbackEvent(AgentRunEvent):
    name: Literal["agent.delegation.fallback"] = "agent.delegation.fallback"
    group: EventGroup = EventGroup.AGENT
    transient: bool = False  # persisted for post-hoc analysis
    reason: str = ""
    context_id: str = ""
    circuit_state: str = ""  # CircuitState.value
    failure_count: int = 0
    cooldown_remaining: float = 0.0
```

Also added `EventType.DELEGATION_FALLBACK = "agent.delegation.fallback"` and included `DelegationFallbackEvent` in the `AgentAppEvent` union and `__init__.py` exports.

### `src/ii_agent/integrations/a2a/adapter_server.py` — Sync endpoint + task lifecycle

Three new endpoints added alongside the existing `/message:stream`:

**`POST /message:send`** — Synchronous A2A task execution.  
Collects the full `_event_stream()` output, builds an A2A Task object (`{id, contextId, status, artifacts, history}`), stores it in `_TASK_STORE`, and returns it as JSON.  
Task state flow: `submitted` (pre-registration) → `working` (collecting stream) → `completed` | `failed`.

**`GET /tasks/{task_id}`** — Returns a stored task by ID; 404 if not found.

**`POST /tasks/{task_id}:cancel`** — Marks a task as `canceled`; 409 if already in a terminal state.

**`_TASK_STORE`** — In-memory `TaskStore(ttl_seconds=3600.0, maxsize=10_000)` with TTL-based expiry and LRU eviction; to be replaced with Redis / DB for production multi-worker deployments.

### `src/ii_agent/agents/tools/routing.py` — `ToolRoutingLayer`

Stateless routing layer for hybrid tool dispatch. Determines whether a tool invocation routes to:

| Owner | Criteria |
|---|---|
| `NATIVE` | Security-sensitive tools, high-risk tools, proprietary II-Agent categories (media, slides, storybook, planning, connectors, dev, billing, project, deployment, subdomain) |
| `CLI` | CLI-eligible categories (shell, bash, file, filesystem, code, browser, web, search, terminal, general) |
| `SPECIALIST` | Tools explicitly registered in the `specialist_map` config |

**Precedence**: security gate → risk level → proprietary category → specialist allowlist → CLI-eligible → fallback native.

```python
router = ToolRoutingLayer()
decision = router.route("bash", category="shell")      # ToolOwner.CLI
decision = router.route("generate_image", category="media")  # ToolOwner.NATIVE
```

Supports runtime updates via `register_specialist()` / `unregister_specialist()`.

---

## Test Coverage

5196 tests pass (25 skipped). All are in `src/tests/unit/`.

**A2A module coverage** (measured with `pytest --cov=src/ii_agent/integrations/a2a`):

| Module | Coverage |
|---|---|
| `registry.py` | 100% |
| `task_store.py` | 100% |
| `extension_utils.py` | 100% |
| `claude_code_backend.py` | ~98% |
| `circuit_breaker.py` | 99% |
| `as_client.py` | 98% |
| `router.py` | 98% |
| `context_adapter.py` | 97% |
| `event_stream_adapter.py` | 96% |
| `adapter_server.py` | ~90% |
| `__main__.py` | ~92% |
| **Total A2A** | **~96%** |

### `agent/test_inner_loop.py` (14 tests)

| Test | What it covers |
|---|---|
| `test_native_inner_loop_delegates_to_model_stream` | NativeInnerLoop passes through model events |
| `test_a2a_inner_loop_maps_stream_events` | message_delta/usage event mapping |
| `test_a2a_inner_loop_falls_back_to_native_on_error` | client failure → DelegationFallbackEvent + NativeInnerLoop |
| `test_agent_settings_a2a_defaults` | All five fields default correctly |
| `test_a2a_client_parse_stream_line_handles_sse_payload` | SSE `data:` prefix parsed |
| `test_a2a_client_parse_stream_line_ignores_invalid_lines` | Empty / `[DONE]` / non-JSON ignored |
| `test_a2a_inner_loop_error_event_raises_provider_error` | `session.error` raises |
| `test_a2a_inner_loop_no_fallback_raises_on_client_failure` | `fallback_to_native=False` raises |
| `test_a2a_inner_loop_maps_reasoning_and_usage_shapes` | reasoning_delta/done/usage shapes |
| `test_a2a_inner_loop_resolve_context_id_fallback_order` | session_id → run_id → "default" |
| `test_a2a_inner_loop_ignores_unknown_event_types` | Unknown types return None |
| `test_a2a_client_requires_url_or_factory` | ValueError when both omitted |
| `test_a2a_client_lazy_url_factory_resolves_on_first_call` | Factory called once, result cached |
| `test_agent_settings_tool_allowlist_helpers` | `add/remove/clear_allowed_tool` |

### `agent/test_agent_factory_inner_loop.py` (21 tests)

Covers all branches of `_build_inner_loop_strategy`, deferred sandbox binding, `create_agent` field assembly, skill tool append, connector tool loading (success + exception), sub-agent creation, system prompt generation, workspace path injection, and delegation to specialist agent tools.

Key sandbox-path and deferred binding tests:

| Test | What it covers |
|---|---|
| `test_build_inner_loop_strategy_a2a_with_sandbox_uses_url_factory` | Sandbox present → url_factory set, static URL is None |
| `test_build_inner_loop_strategy_a2a_no_sandbox_no_url_creates_deferred_a2a` | No sandbox, no URL → deferred A2AInnerLoop with `_sandbox_ref=[None]` |
| `test_build_inner_loop_strategy_a2a_deferred_also_works_without_sandbox_kwarg` | Same deferred path when `sandbox` kwarg omitted entirely |
| `test_build_inner_loop_strategy_a2a_with_url_returns_a2a_strategy` | No sandbox, URL set → A2AInnerLoop with static URL |
| `test_deferred_url_factory_raises_before_sandbox_bound` | Deferred URL factory raises `RuntimeError` if sandbox never wired |
| `test_deferred_url_factory_resolves_after_sandbox_bound` | After binding sandbox to `_sandbox_ref`, URL factory resolves correctly |
| `test_agent_sandbox_setter_wires_deferred_strategy` | `IIAgent.sandbox` setter populates `_sandbox_ref[0]` on deferred strategy |
| `test_agent_sandbox_setter_noop_for_native_strategy` | Setting sandbox on NativeInnerLoop agent does not error |

### `credits/test_credit_usage_handler.py` (6 tests)

| Test | What it covers |
|---|---|
| `test_billing_disabled_skips_model_event` | `billing_enabled=False` → `_handle_llm_usage` not called |
| `test_billing_disabled_skips_tool_event` | `billing_enabled=False` → `_handle_tool_usage` not called |
| `test_billing_enabled_processes_model_event` | `billing_enabled=True` → `_handle_llm_usage` called |
| `test_billing_enabled_processes_tool_event` | `billing_enabled=True` → `_handle_tool_usage` called |
| `test_billing_disabled_ignores_unrecognised_event` | `billing_enabled=False` → unrecognised event ignored safely |
| `test_default_billing_enabled_is_true` | Default constructor has `_billing_enabled=True` |

### `agent/test_docker_sandbox.py` — `TestA2AAdapterEnv` (7 tests)

| Test | What it covers |
|---|---|
| `test_returns_backend_key` | `SANDBOX_ADAPTER_BACKEND` set to configured backend |
| `test_backend_value_passthrough` | Backend value forwarded verbatim |
| `test_forwards_github_token` | `GITHUB_TOKEN` forwarded when set |
| `test_forwards_anthropic_key` | `ANTHROPIC_API_KEY` forwarded when set |
| `test_forwards_openai_key` | `OPENAI_API_KEY` forwarded when set |
| `test_empty_tokens_not_forwarded` | Empty tokens excluded from env dict |
| `test_forwards_all_available_tokens` | All set tokens forwarded regardless of backend |

### `integrations/test_a2a_adapter_server.py` (39 tests)

| Test | What it covers |
|---|---|
| `test_extract_last_user_text_prefers_latest_user_message` | Message extraction from string and list-of-parts content |
| `test_stream_endpoint_emits_supported_events` | Full SSE stream contains reasoning_delta, message_delta ×2, message, usage, [DONE] |
| `test_stream_emits_task_id_and_extension_metadata` | First event is `session.task_id`; reasoning/message events embed extension URIs |
| `test_agent_card_includes_extension_uris` | Agent card advertises both extension URIs |
| `test_reply_endpoint_404_for_unknown_task` | 404 when task does not exist |
| `test_reply_endpoint_409_when_task_not_in_input_required` | 409 when task is not awaiting input |
| `test_reply_endpoint_resumes_input_required_stream` | Full INPUT_REQUIRED→reply→complete round-trip via direct generator test |
| `test_agents_list_empty` | `GET /agents` returns empty list on fresh registry |
| `test_agents_register_and_list` | `POST /agents:register` + `GET /agents` round-trip |
| `test_agents_register_missing_required_fields` | 422 when `name` or `url` omitted |
| `test_agents_unregister` | `DELETE /agents/{name}` succeeds + 404 on second delete |
| `test_agents_route_returns_best_match` | `/agents:route` picks highest tag-score agent |
| `test_agents_route_no_agents_returns_503` | 503 when registry is empty |
| `test_task_store_ttl_integration` | `_TASK_STORE` is `TaskStore` instance, not bare dict |
| `test_extract_last_user_skips_non_user_role` | Non-user role hit via reversed iteration |
| `test_extract_last_user_list_content_with_string_items` | String items in content list |
| `test_extract_last_user_returns_empty_when_no_user_messages` | No user messages → empty |
| `test_message_send_returns_completed_task` | `POST /message:send` returns completed A2A Task |
| `test_message_send_task_stored_in_task_store` | Sent task retrievable via `GET /tasks/{id}` |
| `test_get_task_200_for_existing_task` | 200 with task data |
| `test_get_task_404_for_unknown` | 404 when task not found |
| `test_cancel_task_succeeds_for_working_task` | Cancel transitions to "canceled" |
| `test_cancel_task_404_for_unknown` | 404 on unknown task |
| `test_cancel_task_409_for_terminal_state` | 409 for completed/failed/canceled tasks |
| `test_cancel_task_unblocks_input_required_queue` | Cancel puts signal in reply queue |
| `test_reply_task_503_when_input_queue_gone` | 503 when queue missing after timeout |
| `test_agents_discover_missing_url_returns_422` | 422 when URL omitted from body |
| `test_agents_discover_failure_returns_502` | 502 on network discovery failure |
| `test_no_allowed_keys_allows_all_requests` | Track B: open mode (no `allowed_keys`) passes all traffic |
| `test_protected_endpoint_returns_401_without_auth` | Track B: 401 on protected endpoint without bearer token |
| `test_protected_endpoint_accepts_valid_bearer` | Track B: 200 with correct `Authorization: Bearer` token |
| `test_protected_endpoint_rejects_wrong_key` | Track B: 401 with unrecognised bearer token |
| `test_public_discovery_endpoint_bypasses_auth` | Track B: `/.well-known/agent-card.json` always public |
| `test_options_preflight_bypasses_auth` | Track B: OPTIONS requests bypass auth |
| `test_absent_version_header_passes_through` | Track A: no `A2A-Version` header → backward-compat 200 |
| `test_supported_version_header_accepted` | Track A: supported version passes through |
| `test_unsupported_version_header_returns_400` | Track A: unsupported version → 400 JSON-RPC error |
| `test_response_carries_a2a_version_header` | Track A: all responses carry `A2A-Version: 0.3.0` |

### `integrations/test_a2a_event_mapping.py` (34 tests — Track D)

New file added in the Track D remediation session.  Covers both translation directions with a golden table and a cross-direction consistency check.

| Class | Tests | Coverage |
|---|---|---|
| `TestInboundMapping` | 18 | One test per canonical type alias group in `A2AInnerLoop._map_event()`: message_delta (primary + aliases + empty), reasoning_delta (primary + alias), reasoning_done, message_complete (primary + 2 aliases + empty + with tool_calls), usage (primary + alias), error (raises; alias), unknown (None) |
| `TestOutboundMapping` | 13 | One test per `EventStreamAdapter._convert_event()` path: `CONNECTION_ESTABLISHED` → working; `STATUS_UPDATE` → working; `STREAM_COMPLETE` → completed+final; `ERROR` → failed+final; `RUN_INTERRUPTED` → input_required; `RUN_CONTENT` → artifact; `REASONING_DELTA` → artifact; `TOOL_CALL_STARTED` → artifact; `TOOL_CALL_COMPLETED` → artifact; `None` content behavior; append flag second chunk; context/task ID propagation; stream reset after complete |
| `TestMappingConsistency` | 3 | Type namespace non-overlap (with documented `"error"` safe-shared carve-out); inbound canonical set smoke; outbound status set smoke |

### `integrations/test_claude_code_backend.py` (43 tests)

| Group | Tests |
|---|---|
| `TestParseClaudeEventLine` (17 tests) | Empty/whitespace/malformed → empty list; system/user events → empty; thinking → reasoning_delta; empty thinking → empty; text → message_delta; empty text → empty; tool_use → tool_call with extension URI; multiple blocks emitted in order; result/success → message + usage with cache fields; empty result omits message; `is_error=True` → session.error; string error field; no error field → fallback message |
| `TestClaudeCodeBackendInternals` (17 tests) | `_build_cmd`: no resume on first call; `--resume SESSION_ID` when session stored; `--model` injected; no `--model` when empty. `_build_env`: API key injected; extra_env merged; extra_env overrides. `_update_session_id`: from system init; from result; ignored when absent; ignored on malformed JSON. `_is_error_event`: True for `is_error`; True for `error_during_execution`; False for success; False for non-result type; False for malformed; False for empty |
| `TestClaudeCodeBackendStream` (9 tests) | `session.task_id` emitted first when task_id provided; no task_id event when omitted; text block → message_delta present; session_id stored after system init; second call includes `--resume`; non-zero exit → session.error; structured error not double-emitted on non-zero exit; always ends with `[DONE]`; timeout → session.error + `[DONE]` |

---

## What Is Not Yet Built

Items marked ✅ were completed in earlier sessions. Remaining items are deferred.

**Completed (Phase 1 + Phase 2 + Phase 3 + Phase 4 + Phase 5 + Phase 6 + Phase 7 + Remediation Tracks A/B/C/D):**

| Item | Design reference |
|---|---|
| ✅ `/.well-known/agent-card.json` endpoint | §3.3 |
| ✅ `/message:send` (sync) and `/tasks/{id}` lifecycle endpoints | §3.1 |
| ✅ Circuit breaker with failure counter and cooldown | §5.4 |
| ✅ `A2AAuthMiddleware` wired into `create_app(allowed_keys=…)`; `II_AGENT_A2A_API_KEYS` read in `main()` | §6, Track B |
| ✅ `A2AVersionMiddleware` — validates `A2A-Version` header, 400 JSON-RPC on unsupported, `A2A-Version` on every response | §7 Phase 3.1, Track A |
| ✅ Agent card `capabilities` updated: `supportedOperations`, `a2aProfile: "internal-compat"`, `a2aProfileVersion` | §3.3, Track C |
| ✅ `DelegationFallbackEvent` emitted to frontend | §5.4 |
| ✅ Port policy enforcement (`18000-18999` exclusion in `PortPoolManager`) | §2.5 |
| ✅ Tool routing layer (`ToolRoutingLayer`) | §2.6 |
| ✅ `A2AAgentTool` class | §2.6 |
| ✅ `_get_sub_agent_info()` (`converter.py`) | §2.6 |
| ✅ `extension_utils.py`, `context_adapter.py`, `event_stream_adapter.py` | §3.2 |
| ✅ `INPUT_REQUIRED` round-trip (`POST /tasks/{id}:reply` + asyncio.Queue) | §3.1 |
| ✅ A2A Extensions: reasoning + tool-telemetry URIs embedded in SSE events | §3.2 |
| ✅ Agent card advertises extension capability in `extensions[]` | §3.3 |
| ✅ Context reconciliation after fallback (`_last_owner` + `_effective_context_id`) | §5.4 |
| ✅ `docker/sandbox/start-services.sh` — A2A adapter tmux session with auto-restart | §2.5 |
| ✅ `e2b.Dockerfile` — `EXPOSE 18100` + `ENV SANDBOX_ADAPTER_PORT=18100` | §2.5 |
| ✅ Agent registry (`AgentRegistry`, `AgentCard`, `AgentSkill`) — Agent Card crawling + discovery | §7 Phase 4 |
| ✅ Skill-based agent routing (`AgentRouter`) — tag-intersection scoring, fallback, extension routing | §7 Phase 4 |
| ✅ Persistent-within-process task store (`TaskStore`) — TTL + LRU replacing unbounded `dict` | §3.1 |
| ✅ `/agents` endpoints — list, register, discover, unregister, route | §7 Phase 4 |
| ✅ Claude Code subprocess backend (`ClaudeCodeBackend`, `ClaudeCodeConfig`) | competitor analysis §7 |
| ✅ Pluggable backend support in `create_app()` (`backend=` param, `_event_source` closure) | competitor analysis §7 |
| ✅ `--backend claude-code` CLI flag for `adapter_server.py main()` | competitor analysis §7 |
| ✅ OpenAI Codex CLI subprocess backend (`CodexBackend`, `CodexConfig`) | competitor analysis §7 |
| ✅ `--backend codex` CLI flag; `OPENAI_API_KEY` injection | competitor analysis §7 |
| ✅ `parse_codex_line()` — dual-mode JSONL + plain-text → A2A SSE mapper | competitor analysis §7 |
| ✅ Copilot CLI SDK backend (`CopilotBackend`, `CopilotConfig`) | §3, §B.5 |
| ✅ `parse_copilot_event()` — SDK `SessionEvent` → A2A SSE mapper | §3, §B.5 |
| ✅ `--backend copilot` CLI flag; `GITHUB_TOKEN` injection | §3, §B.5 |
| ✅ 31-test suite for `CopilotBackend` and `parse_copilot_event` | §3, §B.5 |
| ✅ Track A/B test suite — 11 new tests in `test_a2a_adapter_server.py` (auth and version negotiation) | Track A, Track B |
| ✅ Track D golden mapping tests — `test_a2a_event_mapping.py` (34 tests; inbound, outbound, consistency) | Track D |
| ✅ Deferred sandbox binding — `_sandbox_ref` list field on `A2AInnerLoop`, factory closure, `IIAgent.sandbox` setter wiring | §2.5, #36 |
| ✅ Sandbox auth token forwarding — `_a2a_adapter_env()` in `docker.py` forwards backend + auth tokens at container creation | §2.5 |
| ✅ Credit billing bypass — `CREDITS_BILLING_ENABLED` toggle with 3 bypass points (handler, chat service, session service) | N/A (operational) |
| ✅ Tests: 6 billing handler tests + 7 docker adapter env tests + 4 deferred binding tests | — |
| ✅ Multimodal A2A Parts — `multimodal.py` bidirectional Part translation; inbound `extract_user_content()` → backends; outbound `content_to_parts()` → `FilePart`/`DataPart` in `event_stream_adapter`; Claude Code `--image` flag; Copilot SDK `session.send(attachments=[...])` for file + blob images; Codex graceful degradation | §7 Phase 3 |
| ✅ Cross-authority summary chaining prevention — `summary_authority` column on `chat_summaries`; guard in `create_chained_summary()` blocks cross-authority chains; migration `20260407_000003` | Track E |
| ✅ Tests: 27 multimodal unit tests + 23 backend image extraction tests (Claude Code + Copilot) + 11 cross-authority summary tests + 3 multimodal artifact event tests | — |
| ✅ Tool bridge: `tool_bridge.py` — schema serialization (`serialize_tool_schemas`, `_CLI_NATIVE_TOOL_NAMES`) for bridging ii-agent native tools to Copilot CLI | Phase 8 |
| ✅ Tool bridge: `copilot_backend.py` — `_create_sdk_tools()`, `_ToolExecutionRequest`, `receive_tool_result()`, heartbeat loop, tool_schemas forwarding to `create_session(tools=[…])` | Phase 8 |
| ✅ Tool bridge: `adapter_server.py` — `POST /tools/{tool_call_id}/result` endpoint, `native_tool_schemas` extraction from metadata | Phase 8 |
| ✅ Tool bridge: `inner_loop.py` — `_handle_tool_execution_request()`, `_execute_bridged_tool()`, heartbeat filtering, tool schema metadata transport | Phase 8 |
| ✅ Tool bridge: `as_client.py` — `post_tool_result(tool_call_id, result)` for delivering bridged tool results | Phase 8 |
| ✅ Tool bridge gap analysis — [`a2a-tool-bridge-gap-analysis.md`](../design-docs/a2a-tool-bridge-gap-analysis.md) — responsibility matrix and known limitations | Phase 8 |
| ✅ Tests: 55 tool bridge tests (21 tool_bridge schema + 17 copilot backend bridge + 17 inner loop bridge) | Phase 8 |

**Remaining (deferred):**

| Item | Design reference |
|---|---|
| Wire-level A2A 1.0 `StreamResponse` compatibility mode (alongside internal SSE envelope) | §7 Phase 3.1 |
| Tool bridge: `_execute_bridged_tool` agent/sandbox injection — promote from `@staticmethod`, call `on_tool_start()` for `BaseSandboxTool`/`MCPTool` tools (only 6 of ~19 bridged tools work today; sandbox-dependent tools crash with `None`) | Phase 8 gap (critical) |
| Tool bridge: `ToolCallStartedEvent` / `ToolCallCompletedEvent` emission for bridged tool calls | Phase 8 gap |
| Tool bridge: `ModelTurnMetricsEvent` emission for bridged tool billing telemetry | Phase 8 gap |
| Tool bridge: Media artifact extraction from bridged tool results (images, videos, audios) | Phase 8 gap |
| Tool bridge: HITL support (`requires_confirmation`, `requires_user_input`, `external_execution`) for bridged tools | Phase 8 gap |
| Tool bridge: Pre/post hooks execution for bridged tools | Phase 8 gap |
| Tool bridge: `agent`/`run_context`/`session_state` injection into bridged tool entrypoints | Phase 8 gap |
| Tool bridge: `stop_after_tool_call` support for bridged tools | Phase 8 gap |

---

## Phase 5: Claude Code Backend Adapter

All Phase 5 items were implemented in the 2026-04-06 continuation session, following the recommendation in [`inner-loop-competitor-analysis.md`](../design-docs/inner-loop-competitor-analysis.md) §7 to build the Claude Code adapter "in parallel" with the Copilot CLI adapter.

**Rationale (from competitor analysis §7):** Claude Code has 3× the Drop-in feature coverage of Copilot CLI via A2A (30 vs 10), adds zero additional API cost vs ii-agent's native Anthropic path, and uses a simpler subprocess stdio interface (vs. SDK JSON-RPC for Copilot).

### `src/ii_agent/integrations/a2a/claude_code_backend.py`

New module containing:

**`ClaudeCodeConfig`** (dataclass)

| Field | Type | Default | Purpose |
|---|---|---|---|
| `api_key` | `str` | required | `ANTHROPIC_API_KEY` injected into subprocess env |
| `claude_bin` | `str` | `"claude"` | Path or name of the `claude` CLI binary |
| `model` | `str` | `""` | Model override (`--model`); empty → `ANTHROPIC_MODEL` env or claude default |
| `timeout` | `float` | `300.0` | Per-turn wall-clock timeout in seconds |
| `cwd` | `str \| None` | `None` | Working directory for subprocess |
| `extra_env` | `dict[str, str]` | `{}` | Additional env vars merged after API key |

**`parse_claude_event_line(line: str) -> list[str]`** (public, pure function)

Maps one JSONL line from `claude --output-format stream-json` to zero or more A2A SSE strings.

| Claude Code event | A2A SSE event |
|---|---|
| `system` (init) | *(skipped; session_id extracted by caller)* |
| `assistant` / `thinking` block | `assistant.reasoning_delta` with `REASONING_EXTENSION_URI` |
| `assistant` / `text` block | `assistant.message_delta` |
| `assistant` / `tool_use` block | `assistant.tool_call` with `TOOL_TELEMETRY_EXTENSION_URI` |
| `user` (tool results) | *(skipped; adapter-internal)* |
| `result` / success | `assistant.message` + `assistant.usage` (with cache token fields) |
| `result` / error | `session.error` |
| Empty / malformed | *(skipped)* |

**`ClaudeCodeBackend`** (class)

```python
class ClaudeCodeBackend:
    def __init__(self, config: ClaudeCodeConfig) -> None: ...
    async def stream(
        self,
        prompt: str,
        context_id: str = "default",
        task_id: str | None = None,
    ) -> AsyncGenerator[str, None]: ...
```

Internal state: `_sessions: dict[str, str]` — maps `context_id → claude session_id` for `--resume` on subsequent turns.

Subprocess invocation:
```bash
claude --print --output-format stream-json [--resume SESSION_ID] [--model MODEL] PROMPT
```

Error handling:
- Per-turn deadline enforced via `asyncio.wait_for(proc.stdout.readline(), timeout=remaining)`.
- On timeout: subprocess killed, `session.error` emitted, `[DONE]` follows.
- On non-zero exit without a prior structured error: stderr captured and emitted as `session.error`.
- Subprocess always reaped via `finally: proc.kill(); await proc.wait()`.

### `adapter_server.py` — pluggable backend support

Minimal changes to support real backends alongside the simulated stream:

**`_collect_task` signature updated:**
```python
async def _collect_task(
    req: A2ASendRequest,
    task_id: str,
    *,
    stream_callable: Optional[Any] = None,
) -> dict[str, Any]:
```
`stream_callable` defaults to `None` → falls back to `_event_stream` (simulated, backward-compatible).

**`create_app` gains `backend` parameter:**
```python
def create_app(
    *,
    registry: Optional[AgentRegistry] = None,
    router: Optional[AgentRouter] = None,
    backend: Optional[Any] = None,  # ClaudeCodeBackend or any .stream() provider
) -> FastAPI:
```
Inside `create_app`, a local `_event_source` async generator closure is created:
```python
async def _event_source(req, *, task_id=None):
    if backend is not None:
        async for chunk in backend.stream(
            _extract_last_user_text(req.messages),
            req.context_id or "default",
            task_id,
        ):
            yield chunk
    else:
        async for chunk in _event_stream(req, task_id=task_id):
            yield chunk
```
`message_stream` uses `_event_source` instead of `_event_stream`.
`message_send` passes `stream_callable=_event_source` to `_collect_task`.

**`main()` gains `--backend` flag:**
```
--backend {simulate,claude-code}   (default: simulate)
```
`--backend claude-code` reads `ANTHROPIC_API_KEY` from env, creates `ClaudeCodeBackend`, and passes it to `create_app(backend=...)`.

### `__init__.py` — exports

Added `ClaudeCodeBackend` and `ClaudeCodeConfig` to `__all__`.

---

## Phase 6: OpenAI Codex CLI Backend Adapter

All Phase 6 items were implemented in the 2026-04-07 continuation session, following the competitor analysis §7 roadmap which identified Codex as the cost-sensitive specialist path (~$0.56/session vs $0.70 for Claude Sonnet 4.6 with o4-mini).

**Rationale (from competitor analysis §7):** Codex o4-mini is the cheapest API-call option of the three evaluated backends.  It suits cost-sensitive code-execution tasks where Claude Haiku 3.5 speed/cost trade-off is insufficient.  The subprocess interface is similar to Claude Code (`--full-auto --no-sandbox PROMPT`) but outputs JSONL or plain text (not guaranteed stream-json), requiring a dual-mode line parser.

### `src/ii_agent/integrations/a2a/codex_backend.py`

New module containing:

**`CodexConfig`** (dataclass)

| Field | Type | Default | Purpose |
|---|---|---|---|
| `api_key` | `str` | required | `OPENAI_API_KEY` injected into subprocess env |
| `codex_bin` | `str` | `"codex"` | Path or name of the `codex` CLI binary |
| `model` | `str` | `""` | Model override (`--model`); empty → Codex default (o4-mini) |
| `timeout` | `float` | `300.0` | Per-turn wall-clock timeout in seconds |
| `cwd` | `str \| None` | `None` | Working directory for subprocess |
| `extra_env` | `dict[str, str]` | `{}` | Additional env vars merged after API key |
| `instructions` | `str` | `""` | Optional system prompt via `--instructions`; empty → flag omitted |

**`CodexLineResult`** (structured result from `parse_codex_line`)

| Attribute | Type | Purpose |
|---|---|---|
| `sse_events` | `list[str]` | A2A SSE strings to emit immediately |
| `text_fragment` | `str` | Text extracted from this line (accumulated for final message) |
| `conversation_id` | `str` | Conversation ID found in this line (empty if not present) |
| `usage` | `dict` | Token usage extracted from `done`/`completion` events |
| `is_error` | `bool` | True when this line signals terminal error |

**`parse_codex_line(line: str) -> CodexLineResult`** (public, pure function)

Dual-mode: tries JSON parsing first; plain text lines produce `message_delta`.

| Codex output line | A2A SSE event / result |
|---|---|
| `system` / `init` | *(no SSE; `conversation_id` extracted)* |
| `message` (assistant) | `assistant.message_delta` + text accumulation |
| `message` (user) | *(skipped)* |
| `reasoning` | `assistant.reasoning_delta` with `REASONING_EXTENSION_URI` |
| `tool_call` | `assistant.tool_call` with `TOOL_TELEMETRY_EXTENSION_URI` |
| `tool_result` / `tool_output` | *(skipped; adapter-internal)* |
| `done` / `completion` | usage extracted into `CodexLineResult.usage` |
| `error` | `session.error`; `is_error=True` |
| Unknown type with `content` | `assistant.message_delta` (fallback) |
| Plain text (non-JSON) | `assistant.message_delta` + text accumulation |

String `arguments` in `tool_call` are parsed as JSON; unparseable strings are wrapped in `{"raw": "..."}`.

**`CodexBackend`** (class)

```python
class CodexBackend:
    def __init__(self, config: CodexConfig) -> None: ...
    async def stream(
        self,
        prompt: str,
        context_id: str = "default",
        task_id: str | None = None,
    ) -> AsyncGenerator[str, None]: ...
```

Internal state: `_conversations: dict[str, str]` — maps `context_id → codex conversation_id` for `--conversation-id` on subsequent turns.

Subprocess invocation:
```bash
codex --full-auto --no-sandbox [--conversation-id CONV_ID] [--model MODEL] [--instructions TEXT] PROMPT
```

Key differences from Claude Code:
- `--full-auto` instead of `--print` (Codex headless mode)
- `--no-sandbox` is mandatory to avoid nested Docker inside ii-agent container
- `--conversation-id` continuation (less persistent than Claude's `--resume session_id`)
- No dedicated `--output json` requirement — adapter handles both JSONL and plain text output
- Text is accumulated across lines and emitted as a single final `assistant.message`
- Zero-filled `assistant.usage` emitted if Codex produces no `done` event

Error handling is identical to `ClaudeCodeBackend`:
- Per-turn deadline enforced via `asyncio.wait_for(proc.stdout.readline(), timeout=remaining)`.
- On timeout: subprocess killed, `session.error` + `[DONE]` emitted.
- On non-zero exit without a prior structured error: stderr captured and emitted as `session.error`.
- `error_seen` flag prevents double-emitting `session.error` when structured error + non-zero exit both occur.
- Subprocess always reaped in `finally: proc.kill(); await proc.wait()`.

### `adapter_server.py` — `--backend codex` option

Added `"codex"` to the `--backend` argument choices:
```
--backend {simulate,claude-code,codex}
```
`--backend codex` reads `OPENAI_API_KEY` from env, requires it to be non-empty, creates `CodexBackend(CodexConfig(api_key=api_key))`, and passes it to `create_app(backend=...)`.

### `__init__.py` — exports

Added `CodexBackend` and `CodexConfig` to the module-level exports and `__all__`.

### Test coverage

`src/tests/unit/integrations/test_codex_backend.py` — 76 new tests:

| Test class | Tests | Coverage |
|---|---|---|
| `TestParseCodexLine` | 41 | All JSONL event types, plain text, edge cases |
| `TestCodexBackendInternals` | 16 | `_build_cmd`, `_build_env`, `_apply_line_result` |
| `TestCodexBackendStream` | 19 | Subprocess mocking: task_id, text accumulation, conversation tracking, error cases, timeout, tool calls, reasoning |

All 76 tests pass. Full integrations suite: 427 passed, 5 skipped (pre-existing).

---



All Phase 3 items below were implemented in the 2026-04-04 continuation session.

### `INPUT_REQUIRED` round-trip — `adapter_server.py`

Added `ReplyRequest` model and the following per-task bookkeeping:

```python
_TASK_INPUT_QUEUES: dict[str, asyncio.Queue[dict[str, Any]]] = {}
_INPUT_REQUIRED_TIMEOUT: float = 300.0
```

**`_event_stream` update** — if the prompt ends with `?` and a `task_id` is provided, the generator:
1. Emits `session.task_id` as the first event (so the client knows the id).
2. Creates an `asyncio.Queue` and registers it under `_TASK_INPUT_QUEUES[task_id]`.
3. Emits `session.input_required`.
4. `await asyncio.wait_for(queue.get(), timeout=300.0)` — suspends until the client replies.
5. Incorporates the user reply text into the response body and continues streaming.

**`POST /tasks/{task_id}:reply`** — new endpoint:
- 404 if task is not found.
- 409 if the task is not in `input_required` state.
- 503 if the input queue has gone (e.g. timeout).
- Puts `{"text": ..., "metadata": ...}` into the queue and updates state to `working`.

**`POST /tasks/{task_id}:cancel`** — updated to also unblock a waiting reply queue via `{"_cancelled": True}`.

**`_collect_task`** — handles `session.input_required` events by updating `_TASK_STORE[task_id]["status"]["state"]` in real time, so concurrent `GET /tasks/{task_id}` calls return the correct state while the stream is paused.

**`/message:stream`** — now pre-allocates `task_id`, registers a stub in `_TASK_STORE`, and passes it to `_event_stream()`.

### A2A Extensions — `extension_utils.py` + `adapter_server.py`

Two canonical extension URIs added to `extension_utils.py`:

```python
REASONING_EXTENSION_URI     = "urn:ii-agent:extensions:reasoning/v1"
TOOL_TELEMETRY_EXTENSION_URI = "urn:ii-agent:extensions:tool-telemetry/v1"
```

SSE events now carry extension metadata:

```python
# Reasoning delta event
{"type": "assistant.reasoning_delta", "data": {
    "delta": "...",
    "extensions": [{"uri": REASONING_EXTENSION_URI}],
}}

# Final message event
{"type": "assistant.message", "data": {
    "content": "...",
    "tool_calls": [],
    "extensions": [{"uri": TOOL_TELEMETRY_EXTENSION_URI, "data": {"tool_count": 0}}],
}}
```

The agent card (`.well-known/agent-card.json`) now includes an `"extensions"` array advertising both URIs with `required: false`.

### Context reconciliation — `inner_loop.py`

`A2AInnerLoop` gains a new internal field:

```python
_last_owner: str = field(default="", init=False, repr=False)
```

And a new `_effective_context_id(run_response)` method that wraps `_resolve_context_id`:

```python
def _effective_context_id(self, run_response):
    canonical = self._resolve_context_id(run_response)
    if not self.context_reuse:
        return canonical
    if self._last_owner == "native":
        # CLI context is stale; start a fresh session
        fresh_suffix = str(uuid.uuid4())[:8]
        return f"{canonical}.reconcile.{fresh_suffix}"
    return canonical
```

`aresponse_stream()` now:
- Calls `_effective_context_id(run_response)` instead of `_resolve_context_id`.
- Sets `self._last_owner = "a2a"` after a successful A2A turn.
- Sets `self._last_owner = "native"` after any circuit-open or exception-triggered fallback.

### `docker/sandbox/start-services.sh`

A new `tmux` session starts the A2A adapter with supervised auto-restart:

```bash
SANDBOX_ADAPTER_PORT="${SANDBOX_ADAPTER_PORT:-18100}"
tmux new-session -d -s copilot-adapter-system-never-kill -c /workspace \
  "while true; do \
     python -m ii_agent.integrations.a2a.adapter_server \
       --host 0.0.0.0 --port ${SANDBOX_ADAPTER_PORT}; \
     echo 'A2A adapter exited, restarting in 2s...'; \
     sleep 2; \
   done"
```

### `e2b.Dockerfile`

```dockerfile
ENV SANDBOX_ADAPTER_PORT=18100
EXPOSE 18100
```

Added near the end of the `main` stage (before `ENTRYPOINT`), so the port is declared in the image manifest and the env var is available without requiring runtime injection.

---

## How to Test the MVP End-to-End

Start the stub adapter:

```bash
uv run python -m ii_agent.integrations.a2a.adapter_server --host 0.0.0.0 --port 18100
```

Configure the backend (in `docker/.stack.env.local` for local mode, or `docker/.stack.env` for stack mode):

```env
AGENT_INNER_LOOP_MODE=a2a
AGENT_A2A_AGENT_URL=http://localhost:18100
```

Restart the backend. All agent turns will stream through the MVP adapter, which echoes the prompt back with the internal compatibility SSE event sequence. The frontend sees a real streaming response.

> This path uses the static `AGENT_A2A_AGENT_URL` override for local development and external-adapter testing. Production sandbox mode resolves adapter endpoints via `sandbox.expose_port()`.

---

## Phase 4: Multi-Agent Foundation

All Phase 4 items below were implemented in the 2026-04-05 session.

### `src/ii_agent/integrations/a2a/registry.py` — Agent registry

Three new dataclasses plus the registry class.

**`AgentSkill`**

```python
@dataclass
class AgentSkill:
    id: str
    name: str
    description: str = ""
    tags: List[str] = field(default_factory=list)
    examples: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> "AgentSkill": ...
```

**`AgentCard`**

Represents an A2A agent card fetched from `/.well-known/agent-card.json` or manually registered.

| Attribute | Type | Notes |
|---|---|---|
| `name` | `str` | Registry key |
| `url` | `str` | Agent base URL |
| `description` | `str` | Human description |
| `version` | `str` | Semver string |
| `skills` | `List[AgentSkill]` | Declared skills |
| `capabilities` | `Dict` | Raw A2A capabilities block |
| `extensions` | `List[Dict]` | Extension URIs advertised |
| `fetched_from` | `Optional[str]` | Source URL if auto-discovered |

Computed properties:
- `all_tags` — flat, deduped, lowercased list of all skill tags across all skills
- `supports_streaming` — True if `streaming` in capabilities
- `extension_uris` — list of URI strings from `extensions`

**`AgentRegistry`**

Async-safe (uses `asyncio.Lock`) registry keyed by agent `name`.

```python
class AgentRegistry:
    async def register(self, card: AgentCard) -> None
    async def unregister(self, name: str) -> bool           # True if existed
    async def discover(self, base_url: str, *, timeout=10.0, httpx_client=None) -> AgentCard
    async def discover_many(self, base_urls, *, timeout, ignore_errors) -> List[AgentCard]
    def get(self, name: str) -> Optional[AgentCard]
    def get_by_url(self, url: str) -> Optional[AgentCard]  # prefix match
    def list_all(self) -> List[AgentCard]
```

`discover()` crawls `{base_url}/.well-known/agent-card.json`, parses the JSON into an `AgentCard`, registers it, and returns it. `discover_many()` runs concurrent discovers via `asyncio.gather`, with optional error suppression.

---

### `src/ii_agent/integrations/a2a/router.py` — Skill-based routing

```python
class AgentRouter:
    def __init__(
        self,
        registry: AgentRegistry,
        *,
        fallback_name: Optional[str] = None,
    )
```

**`route(prompt, *, hint_tags=None) -> Optional[AgentCard]`**

Routing algorithm:
1. Empty registry → `None`.
2. Single agent → return it directly (no scoring needed).
3. Score each agent: count intersecting tags between `hint_tags` and `agent.all_tags`.
4. Pick highest score; ties broken alphabetically (deterministic).
5. If all scores are zero and `fallback_name` is set → return the named fallback agent.
6. Otherwise return the top scorer (even at score 0, if no fallback is configured).

**Additional methods:**
- `route_by_skill_id(skill_id) -> Optional[AgentCard]` — find the first agent whose skills list contains a skill with `skill.id == skill_id`.
- `route_by_extension(extension_uri) -> List[AgentCard]` — return all agents whose `extension_uris` include the given URI.

---

### `src/ii_agent/integrations/a2a/task_store.py` — TTL + LRU task store

Replaces the unbounded `dict` used for in-process task storage.

```python
class TaskStore:
    def __init__(self, ttl_seconds: float = 3600.0, maxsize: int = 10_000)
```

- Uses `collections.OrderedDict` for O(1) LRU eviction by insertion order.
- Uses `threading.Lock` (sync; adapter runs in a single-threaded event loop but guard is cheap).
- Stores `(entry, expiry_timestamp)` tuples. `ttl_seconds=0` → no expiry.
- On `__setitem__`: if `maxsize` reached, evicts the oldest entry before inserting.
- On `__getitem__` / `get` / `__contains__`: transparently removes and raises/returns default for expired entries.
- `items()` skips expired entries.
- `evict_expired()` sweeps the whole store and returns the count removed.

Dict-compatible interface: supports `store[key] = val`, `store[key]`, `key in store`, `store.get(key, default)`, `store.pop(key, *default)`, `len(store)`, `store.items()`.

---

### `adapter_server.py` — `/agents` endpoints + `create_app()` injection

**Module-level singletons:**

```python
_TASK_STORE: TaskStore = TaskStore(ttl_seconds=3600.0, maxsize=10_000)
_AGENT_REGISTRY: AgentRegistry = AgentRegistry()
_AGENT_ROUTER: AgentRouter = AgentRouter(_AGENT_REGISTRY, fallback_name=None)
```

**`create_app(*, registry=None, router=None) -> FastAPI`**

Accepts optional `registry` and `router` for test isolation (tests pass fresh `AgentRegistry()` instances to avoid shared state). When not provided, the module-level singletons are used.

**New endpoints:**

| Method | Path | Body / response |
|---|---|---|
| `GET` | `/agents` | Returns `List[AgentCard]` as JSON |
| `POST` | `/agents:register` | `{"name": str, "url": str, ...}` → registered card JSON or 422 |
| `POST` | `/agents:discover` | `{"url": str}` → discovered card JSON or 502 |
| `DELETE` | `/agents/{agent_name}` | 200 on success, 404 if not found |
| `POST` | `/agents:route` | `{"prompt": str, "hint_tags": [str]}` → best-match card or 503 |

---

### `src/ii_agent/integrations/a2a/__init__.py` — Updated exports

```python
from ii_agent.integrations.a2a.registry import AgentCard, AgentRegistry, AgentSkill
from ii_agent.integrations.a2a.router import AgentRouter
from ii_agent.integrations.a2a.task_store import TaskStore

__all__ = [
    "A2AStreamEvent", "IIAgentA2AClient", "create_app",
    "AgentCard", "AgentRegistry", "AgentSkill", "AgentRouter", "TaskStore",
]
```

---

### `integrations/test_a2a_registry_router.py` (42 tests)

Covers: `AgentCard.from_dict`, `to_dict`, `all_tags`, `supports_streaming`, `extension_uris`; `AgentRegistry` register/unregister/list/get/get_by_url/discover (creates own client, non-dict response, missing name)/discover_many (success + ignore_errors + propagate errors); `AgentRouter` single-agent shortcut, tag scoring, fallback, no-hint-tags, `route_by_skill_id` (found + not found), `route_by_extension` (found + empty); `TaskStore` set/get, missing KeyError, contains, pop (existing, missing-no-default raises, expired-with-default, expired-no-default), TTL expiry via `__getitem__`, maxsize LRU eviction, `items()` skips expired, `evict_expired()`, zero-ttl, invalid-params ValueError.

### `integrations/test_circuit_breaker.py` (16 tests)

| Group | Tests |
|---|---|
| Constructor | Invalid `failure_threshold`, invalid `cooldown_seconds` |
| CLOSED → OPEN | check() doesn't raise, failure counter opens at threshold |
| OPEN state | check() raises `CircuitBreakerOpenError`, failure in OPEN is no-op |
| Cooldown elapsed | check() transitions OPEN → HALF_OPEN after cooldown |
| HALF_OPEN | success closes circuit; failure re-opens |
| record_success | resets failure count from CLOSED |
| remaining_cooldown | 0 when CLOSED; positive when OPEN |
| reset | forcibly returns to CLOSED |
| Properties | `is_closed`, `is_open`, `is_half_open`, `state`, `failure_count` |

### `integrations/test_a2a_client.py` (19 tests)

| Group | Tests |
|---|---|
| URL resolution | static URL, lazy factory (factory called once, cached), trailing-slash stripping |
| `astream` | events yielded from SSE lines; owns-and-closes client when no external client provided |
| `_parse_stream_line` | empty, whitespace, `[DONE]`, non-JSON, no-type, dict data extracted, non-dict data wrapped in `value`, `event` key fallback, non-dict payload |
| `get_agent_card` | returns card object with attribute/item access; creates+closes client; raw return for non-dict |
| `call_agent` | collects message_delta + message; error event → `success=False`; exception → `success=False` |
| `close` | calls aclose() on external client; no-op without external client |

---

## Phase 8: Tool Bridge — Native Tool Execution via A2A

The original A2A design delegated the entire inner loop to the CLI backend, but `aresponse_stream()` accepted a `tools` parameter and silently ignored it. This meant all ii-agent native tools (WebSearch, ImageGen, Slides, Connectors, Deploy, etc.) were unavailable when using the A2A path. The Copilot CLI only had its built-in bash/file tools, so tool-dependent tasks (browser, media, deployment) would fail.

Phase 8 implements a **tool bridge** that registers ii-agent's native tools as Copilot SDK custom tools, executes them server-side when the CLI invokes them, and delivers results back through the A2A protocol.

**Design reference:** [`a2a-tool-bridge-gap-analysis.md`](../design-docs/a2a-tool-bridge-gap-analysis.md)

### Data flow

```
ii-agent backend                    Sandbox (adapter_server.py)         Copilot CLI
─────────────────                   ───────────────────────────         ────────────
serialize_tool_schemas(tools)
  → native_tool_schemas in metadata
                               ──→  Extract schemas from metadata
                                     _create_sdk_tools(schemas)
                                     create_session(tools=[…])
                                                                   ──→  LLM sees tools
                                                                        LLM invokes tool
                                                                   ←──  SDK handler fires
                                     _ToolExecutionRequest injected
                                     into SSE as tool.execution_request
                               ←──  SSE event
_handle_tool_execution_request()
  _execute_bridged_tool(name, args)
  → run Function entrypoint
  → post_tool_result(id, result)
                               ──→  POST /tools/{id}/result
                                     receive_tool_result(id, result)
                                     SDK handler unblocks
                                     → ToolResult to LLM              ──→  LLM continues
```

### `src/ii_agent/integrations/a2a/tool_bridge.py` (new)

| Export | Purpose |
|---|---|
| `_CLI_NATIVE_TOOL_NAMES` | `frozenset` of 9 tools with CLI equivalents (Bash, BashView, BashList, WriteToProcess, Read, Write, Edit, ApplyPatch, StrReplaceEditor) |
| `serialize_tool_schemas(tools, exclude_cli_native=True)` | Converts `Function`/`dict` tools to `[{"name", "description", "parameters"}]`; skips CLI-native tools by default |

### `src/ii_agent/agents/inner_loop.py` — tool bridge additions

| Addition | Purpose |
|---|---|
| `serialize_tool_schemas` call in `aresponse_stream()` | Serializes tool schemas into `native_tool_schemas` metadata field |
| Heartbeat event filtering (`event_type == "heartbeat"` → `continue`) | Discards keep-alive events from the adapter |
| `tool.execution_request` event interception | Routes to `_handle_tool_execution_request()` |
| `_handle_tool_execution_request(data, tools, context_id)` | Extracts tool_call_id/name/args, executes tool, POSTs result via client |
| `_execute_bridged_tool(tool_name, arguments, tools)` (static) | Finds matching `Function`, runs async or sync entrypoint, returns result string |

### `src/ii_agent/integrations/a2a/copilot_backend.py` — tool bridge additions

| Addition | Purpose |
|---|---|
| `_ToolExecutionRequest` dataclass | Holds `tool_call_id`, `tool_name`, `arguments` for queue transport |
| `_HEARTBEAT_INTERVAL = 15.0` | Interval for keep-alive events during tool execution |
| `_create_sdk_tools(schemas)` | Converts JSON schemas to Copilot SDK `Tool()` objects with blocking handlers |
| `receive_tool_result(tool_call_id, result)` | Delivers backend result to waiting SDK handler via `asyncio.Event` |
| `_get_or_create_session()` — tool registration | Passes SDK tools to `create_session(tools=[…])`; recreates session when tool set changes |
| `_run_turn()` — heartbeat + tool delivery | Emits heartbeat SSE during tool waits; emits `tool.execution_request` SSE when handler fires |
| `stream()` — `tool_schemas` parameter | Accepts tool schemas, passes to `_get_or_create_session` |

### `src/ii_agent/integrations/a2a/adapter_server.py` — tool bridge additions

| Addition | Purpose |
|---|---|
| `native_tool_schemas` extraction in `_event_source()` | Reads schemas from request metadata and passes to `backend.stream(tool_schemas=…)` |
| `_ToolResultBody` Pydantic model | Request body for tool result delivery |
| `POST /tools/{tool_call_id}/result` endpoint | Receives tool result from backend, calls `copilot_backend.receive_tool_result()` |

### `src/ii_agent/integrations/a2a/as_client.py` — tool bridge additions

| Addition | Purpose |
|---|---|
| `post_tool_result(tool_call_id, result) → bool` | HTTP POST to `/tools/{tool_call_id}/result`; returns `True` on success, `False` on error |

### Known limitations (Phase 8 gaps)

These are documented in the gap analysis but deferred for future phases:

1. **No ToolCallStarted/Completed events** — bridged tool executions don't emit the same realtime events as native tool calls
2. **No ModelTurnMetricsEvent** — billing telemetry for bridged tool cost is not tracked
3. **No media artifact extraction** — image/video/audio results from bridged tools are returned as text
4. **No HITL support** — `requires_confirmation`, `requires_user_input`, `external_execution` are bypassed
5. **No pre/post hooks** — `Function.pre_hook` and `Function.post_hook` are not executed
6. **No agent/run_context injection** — bridged entrypoints don't receive `agent`, `run_context`, `session_state` args
7. **No stop_after_tool_call** — the flag is ignored; the CLI continues after bridged tool execution

### Phase 8 test coverage

#### `agent/test_inner_loop_tool_bridge.py` (17 tests)

| Class | Tests | Coverage |
|---|---|---|
| `TestToolSchemaMetadataTransport` | 2 | Tool schemas serialized into A2A metadata; empty tools sends empty schemas |
| `TestHeartbeatFiltering` | 1 | Heartbeat events silently discarded |
| `TestToolExecutionRequestHandling` | 2 | Tool execution dispatch + result POST; tool-not-found posts error |
| `TestExecuteBridgedTool` | 8 | Async entrypoint, sync entrypoint, missing tool, no entrypoint, exception, None→empty, dict tools skipped, empty list |
| `TestPostToolResultFailure` | 1 | Failed delivery logged but not raised |
| `TestClientPostToolResult` | 3 | Correct URL construction, HTTP error returns False, connection error returns False |

#### `integrations/test_a2a_tool_bridge.py` (21 tests)

| Class | Tests | Coverage |
|---|---|---|
| `TestCliNativeToolNames` | 4 | Bash tools membership, file tools membership, non-CLI tools excluded, count check |
| `TestSerializeToolSchemasFunction` | 8 | Basic serialization, CLI-native exclusion, include when disabled, empty name, None description, None parameters, multiple functions, empty list |
| `TestSerializeToolSchemasDict` | 6 | Dict serialization, CLI-native dict, empty/missing name, None description/parameters |
| `TestSerializeToolSchemasMixed` | 3 | Mixed Function+dict, mixed with exclusion, all-CLI-native yields empty |

#### `integrations/test_copilot_backend_tool_bridge.py` (17 tests)

| Class | Tests | Coverage |
|---|---|---|
| `TestCreateSdkTools` | 7 | Tool creation, empty schemas, callable handler, default params, no-queue error, injection+blocking, timeout |
| `TestReceiveToolResult` | 4 | Result delivery, unknown call ID, already delivered, empty result |
| `TestToolExecutionRequest` | 1 | Dataclass field access |
| `TestSessionToolSetChange` | 2 | New session on tool count change, resume on unchanged |
| `TestRunTurnToolExecution` | 1 | tool.execution_request SSE emission |
| `TestHeartbeat` | 1 | Heartbeat emitted on queue timeout |
| `TestStreamWithToolSchemas` | 1 | Tool schemas forwarded to session creation |
