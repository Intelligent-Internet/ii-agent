# A2A Inner-Loop Adapter URL Resolution

**Status:** Partially superseded (2026-04-18)
**Date:** 2026-04-18
**Superseded by (chat-mode sections):** [chat-a2a-adapter-sidecar.md](chat-a2a-adapter-sidecar.md)
**Replaces:** an earlier draft titled "A2A chat-mode per-session sandbox routing"

> ⚠️ **HISTORICAL CONTEXT** — the chat-mode "local Docker auto-discovery"
> mechanism described below was **removed on 2026-04-18** because it caused
> silent fallback to the native LLM (10×+ cost) whenever no sandbox
> happened to be running. Chat A2A is now sandbox-independent and resolves
> its adapter URL **only** from `AGENT_A2A_AGENT_URL`. The local Docker
> stack ships an `a2a-adapter` sidecar that auto-populates this variable.
> See [chat-a2a-adapter-sidecar.md](chat-a2a-adapter-sidecar.md) for the
> current contract. Agent-mode resolution (per-sandbox `expose_port`) is
> unchanged and remains accurate.

## Goal

Document the single, unified architecture by which both the **agent** and
**chat** A2A inner loops resolve their adapter HTTP endpoint, and how that
architecture supports both **local Docker** and **cloud E2B** sandbox
deployments without divergence.

A2A inner-loop replacement must:

1. Work for both chat and agent modes.
2. Fall back to the native LLM loop on any A2A failure (rate-limit,
   circuit-breaker open, transport error, adapter error event).
3. Work in **local Docker sandbox mode** and **cloud E2B sandbox mode**
   without code-level branching.

## Background

The A2A "adapter" is an HTTP server that proxies the A2A protocol to a
concrete LLM backend (Copilot, Codex, Claude Code, simulator). It ships
embedded inside every sandbox image (`docker/sandbox/start-services.sh`)
and listens on container port `18100`
(`ADAPTER_CONTAINER_PORT` in `agents/sandboxes/docker.py`). The same
binary is also deployable as a standalone service.

There is no requirement that the adapter run inside a sandbox — that's
just the most convenient packaging. In production the operator may run
it as a separate service.

## Agent-mode URL resolution

Implemented in `AgentFactory._build_inner_loop_strategy`
(`agents/factory/agent.py`).

Every agent run owns a sandbox (`SandboxService.init_sandbox()`), and
every sandbox class (Docker and E2B) implements `expose_port(port,
external=False)`. The agent A2A client therefore uses a `url_factory`
closure that calls `sandbox.expose_port(ADAPTER_CONTAINER_PORT)` lazily
on first request. The same code path works in:

- **Local Docker:** returns `http://ii-sandbox-<id>:18100` over the
  Docker bridge network.
- **Cloud E2B:** returns the E2B public preview URL for port 18100.

A static `AGENT_A2A_AGENT_URL` may be set to override and point all
agent traffic at an external adapter; this is rarely needed.

## Chat-mode URL resolution

> ⚠️ **SUPERSEDED** — see
> [chat-a2a-adapter-sidecar.md](chat-a2a-adapter-sidecar.md) for the current
> contract. The text below is retained as historical context for the
> reasoning that produced today's design.

**Current behaviour (2026-04-18+):** Chat A2A resolves its adapter URL
from `AGENT_A2A_AGENT_URL` and **only** from that variable. There is no
Docker-socket probing, no `ii-sandbox-*` container scan, and no implicit
sandbox coupling. When `AGENT_CHAT_INNER_LOOP_MODE=a2a` and the URL is
missing, the backend **crashes at startup** (with `AGENT_A2A_CHAT_STRICT=true`,
the default) rather than silently routing every chat request to the
native LLM. URL validation happens in `src/ii_agent/app/lifespan.py`
step 8b.

**Why the old auto-discovery was removed:** chat sessions never own a
sandbox, so opportunistically scavenging any running `ii-sandbox-*`
container's adapter created an undocumented coupling between chat A2A
and sandbox lifecycle. When zero sandboxes were running (cold backend,
orphan-cleanup sweep, between agent runs) the discovery returned `None`
and chat silently billed direct provider rates. The behaviour was a
single-developer convenience that leaked into production semantics.

---

### Historical chat-mode resolution (REMOVED)

For reference, the removed mechanism worked as follows:

1. `AGENT_A2A_AGENT_URL` if set.
2. Otherwise, when `SANDBOX_LOCAL_MODE=true` **and**
   `SANDBOX_PROVIDER=docker`, probe the Docker socket for a running
   `ii-sandbox-*` container and use its embedded adapter.
3. Otherwise `None` → silent fallback to native LLM (logged at WARN).

Steps 2 and 3 no longer exist. The current resolver returns the value
of `AGENT_A2A_AGENT_URL` or `None`; `None` triggers strict-mode failure
(crash or HTTP 503), not silent fallback.

## Fallback semantics

Both loops use the same `CircuitBreaker` + `fallback_to_native` pattern:

- `A2AInnerLoop` (agent) and `A2AChatTurnLoop` (chat) wrap their stream
  call in the breaker.
- On `CircuitBreakerOpenError`, transport errors, or `session.error`
  events from the adapter, the loop reports the failure to the breaker
  and falls back to the native LLM loop for the same turn.
- Billing only fires after the **A2A** stream completes successfully
  (`billing_backend="a2a:<backend>"`). Native fallback is billed as a
  normal native turn. No double-billing.
- `AGENT_A2A_FALLBACK_TO_NATIVE=false` disables fallback and surfaces
  the error to the caller (used in adapter integration tests).

## Configuration matrix

| Mode      | Docker (local)         | Docker (multi-user)         | E2B (cloud)                 |
|-----------|------------------------|-----------------------------|-----------------------------|
| Agent A2A | per-sandbox            | per-sandbox                 | per-sandbox                 |
| Chat A2A  | sidecar service URL¹   | explicit operator URL²      | explicit operator URL²      |

¹ The local Docker stack defines an `a2a-adapter` service and the
backend defaults `AGENT_A2A_AGENT_URL=http://a2a-adapter:18100`. See
[chat-a2a-adapter-sidecar.md](chat-a2a-adapter-sidecar.md).

² Required for correctness. With `AGENT_A2A_CHAT_STRICT=true` (default)
the backend crashes at startup if unset; with strict=false it logs ERROR
and falls back to native LLM (which incurs direct provider charges).

## Why we considered and rejected per-session sandboxes for chat

A previous draft proposed an `A2AChatLoopFactory` that would call
`get_sandbox_for_session(session_id)` on every chat turn so chat could
use a per-session sandbox just like agent mode. That was wrong:

- Chat sessions never call `init_sandbox()`, so the lookup always
  returned `None`.
- Spinning up a sandbox per chat session purely to host an HTTP proxy
  to Copilot is wasteful; the adapter is a stateless protocol bridge
  with no need for an isolated execution environment.
- It conflated two independent concerns (sandbox lifecycle vs. A2A
  transport) and added a DB-coupled per-request factory in the chat hot
  path with no functional benefit.

The factory was implemented and reverted in the same review cycle.

## Test coverage

- `tests/unit/chat/test_chat_a2a_turn_loop.py`
  - `TestSelectTurnLoop` — turn-loop routing (council / BYOK / custom
    provider / storybook bypass).
  - `TestResolveChatA2AURL` — URL priority (explicit > local discovery
    > none); cloud-without-URL returns `None`; non-docker provider
    skips Docker probe.
  - `TestSharedA2AResources` — singleton creation, reuse, and refresh
    on URL change.
  - `TestA2AChatTurnLoop` — streaming, fallback on circuit-open,
    fallback on stream error, fallback on `session.error` event,
    `fallback_to_native=false` raises, tool bridging, billing event
    backend tag.

- Agent-mode A2A coverage lives in `tests/unit/agents/...` (separate
  test module).

## Operational guidance

- **Cloud / E2B production:** set `AGENT_A2A_AGENT_URL` to a dedicated
  adapter deployment. Required for chat A2A; recommended for agent A2A
  as a fallback.
- **Local Docker dev:** use `docker/docker-compose.local.yaml` — it
  ships an `a2a-adapter` sidecar and the backend defaults
  `AGENT_A2A_AGENT_URL=http://a2a-adapter:18100`. No discovery, no
  sandbox coupling. See
  [chat-a2a-adapter-sidecar.md](chat-a2a-adapter-sidecar.md).
- **Multi-tenant Docker:** set `AGENT_A2A_AGENT_URL` explicitly to
  your shared adapter service. Keep `AGENT_A2A_CHAT_STRICT=true`
  (default) so misconfig crashes loudly instead of silently billing
  native rates.
