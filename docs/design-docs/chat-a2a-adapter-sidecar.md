# Chat A2A Adapter Sidecar

**Status:** Accepted
**Date:** 2026-04-18
**Supersedes (in part):** `a2a-inner-loop-url-resolution.md` §"Local Docker auto-discovery"

## Problem

Chat A2A (`AGENT_CHAT_INNER_LOOP_MODE=a2a`) is supposed to route every
chat request through a cheap subscription-backed inner loop (e.g.
Copilot CLI). When the A2A path is unreachable, native LLM fallback
should fire **only on genuine A2A failures** — circuit breaker open,
provider rate limits (weekly/daily), transport errors mid-stream — not
because the adapter URL was never configured or because no sandbox
container happens to be running.

The previous implementation conflated chat A2A with sandbox lifecycle:
chat sessions don't own sandboxes, but the chat A2A loop opportunistically
scavenged any running `ii-sandbox-*` container's adapter. When zero
sandboxes were up (between agent runs, after a crash, immediately after
backend restart), chat silently fell back to direct Anthropic/OpenAI.
Every fallback call costs ~10× the Copilot subscription rate, producing
surprise upstream invoices.

## Decision

**The chat A2A adapter is a standalone, always-on service in the local
Docker stack — independent of sandbox lifecycle.**

- `docker/docker-compose.local.yaml` defines an `a2a-adapter` service.
- It reuses the `ii-agent-sandbox:latest` image (already ships the
  adapter module + Copilot/Claude/Codex CLIs).
- It runs only `python -m ii_agent.integrations.a2a.adapter_server`
  on container port `18100`.
- The backend service depends on it via
  `depends_on: a2a-adapter: condition: service_healthy`.
- Backend defaults `AGENT_A2A_AGENT_URL=http://a2a-adapter:18100`.
- Sandbox auto-discovery from `chat/api/dependencies.py` is removed.
- `AGENT_A2A_CHAT_STRICT=true` (default) makes the backend crash at
  startup if `AGENT_A2A_AGENT_URL` is unset, instead of silently
  enabling native fallback.

Per-sandbox adapters (started by `docker/sandbox/start-services.sh`)
are retained for agent A2A — agent runs continue to use their own
sandbox-local adapter via `sandbox.expose_port(18100)`. The sidecar is
also a valid target for agents if `AGENT_A2A_AGENT_URL` is set.

## Required deployment configuration

| Variable | Local Docker (default) | Cloud / E2B | Effect when unset |
|---|---|---|---|
| `AGENT_CHAT_INNER_LOOP_MODE` | `a2a` | `a2a` | Chat uses direct LLM (expensive) |
| `AGENT_A2A_AGENT_URL` | `http://a2a-adapter:18100` (sidecar) | operator-provided adapter URL | Backend **crashes at startup** when `AGENT_A2A_CHAT_STRICT=true` |
| `AGENT_A2A_BACKEND` | `copilot` | `copilot` / `claude-code` / `codex` | Adapter defaults to `simulate` (mock) |
| `AGENT_A2A_CHAT_STRICT` | `true` (default) | `true` (default) | Misconfig surfaces as 503 instead of silent native fallback |
| `AGENT_A2A_FALLBACK_TO_NATIVE` | `true` | operator choice | Genuine A2A failures (rate limit, circuit open) raise instead of fall back |
| `GITHUB_TOKEN` | required for `AGENT_A2A_BACKEND=copilot` | same | Adapter fails to authenticate with Copilot |

## Failure model

Two distinct failure classes, two distinct responses:

### Class 1 — Misconfiguration (loud, fail-fast)

| Condition | Response with `AGENT_A2A_CHAT_STRICT=true` (default) |
|---|---|
| `AGENT_CHAT_INNER_LOOP_MODE=a2a` and `AGENT_A2A_AGENT_URL` unset | Backend **crashes at startup** with actionable error |
| Adapter URL set but unreachable at request build time | Returns HTTP 503 `A2AAdapterUnavailableError` to caller |

With `AGENT_A2A_CHAT_STRICT=false`: ERROR-level log + silent native
fallback (legacy back-compat only). **Do not use this in production.**
With chat A2A nominally enabled but no adapter URL, every chat turn
will route to the native provider at ~10×+ the Copilot subscription
rate. The April 2026 rollback that produced this design was triggered
by exactly this scenario costing real money. Strict mode (the default)
exists to make this class of misconfig impossible to ignore.

### Class 2 — Runtime A2A failure (transparent fallback)

| Condition | Response |
|---|---|
| `CircuitBreakerOpenError` from the breaker | Native fallback (cheap to expensive) — billed normally |
| Stream `session.error` / `error` event from adapter | Native fallback |
| Transport exception mid-stream | Native fallback |
| Provider rate limit (Copilot weekly/daily) | Adapter surfaces as `session.error` → native fallback |

These are honest failures of the cheap path. Native fallback is the
designed safety valve for them. Billing event tag stays `a2a:<backend>`
only when the A2A stream completed successfully — fallback turns are
billed as native turns. **No double-billing.**

## Local stack startup sequence

```text
postgres  redis  minio    a2a-adapter
   │        │      │            │
   └────────┴──────┴────────────┘
                  │
                  ▼
              backend  (depends_on: a2a-adapter healthy)
                  │
                  ▼
          chat & agent endpoints serve traffic
```

`a2a-adapter` healthcheck: `curl -fsS http://localhost:18100/health`.
Backend will not start until the adapter reports healthy.

## Verification

After `./scripts/stack_control.sh start`:

```bash
# 1. Sidecar is up
docker ps --filter name=a2a-adapter

# 2. Backend reaches it
docker exec ii-agent-local-backend-1 curl -fsS http://a2a-adapter:18100/health

# 3. No silent fallback on chat
docker logs ii-agent-local-backend-1 --since 1m | grep -E "turn-loop-select|no adapter URL"
# Expected: only "turn-loop-select: a2a"; never "no adapter URL"
```

## Migration notes

- Operators upgrading must either (a) accept the new sidecar (no action
  needed for local Docker), or (b) explicitly set
  `AGENT_A2A_AGENT_URL=...` to their existing adapter, or (c) set
  `AGENT_A2A_CHAT_STRICT=false` to keep the old silent-fallback
  behaviour while migrating.
- Cloud / E2B deployments must set `AGENT_A2A_AGENT_URL` — there is no
  default. Backend will refuse to start otherwise.
- The removed `_discover_local_sandbox_adapter_url` function and its
  test cases (`test_local_docker_falls_back_to_discovery`,
  `test_explicit_url_wins_over_local_discovery`) are gone. Replaced by
  `test_local_docker_without_url_returns_none` which asserts the
  sandbox-independent semantics.

## Why not provision sandboxes lazily for chat (rejected)

A previous draft proposed Option A from `chat-a2a-inner-loop-integration-assessment.md`
§4: lazily bind a sandbox per chat session on first A2A turn. Rejected:

- Spinning up a sandbox container (with Xvfb, VNC, MCP server, …) for
  every chat session purely to host an HTTP proxy is wasteful.
- The adapter is a stateless protocol bridge; it has no need for an
  isolated execution environment.
- A shared sidecar serves N chat sessions with one container, ~50 MB
  RSS, and zero per-session cold start.
- Sandbox lifecycle (idle pause, orphan cleanup, port management) is
  unrelated to chat A2A and shouldn't be coupled to it.
