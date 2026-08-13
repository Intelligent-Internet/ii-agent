# Pre-warmed sandbox claim & MCP handoff — design audit

**Status:** ✅ **Accepted & implemented** — 2026-04-25 (this PR).

| Item | Status | Implementation reference |
|------|--------|--------------------------|
| #1 Endpoint audit (flip default `external=False`) | ✅ Implemented | `agents/sandboxes/{base,docker,e2b}.py`; 8 browser-facing call sites tagged `external=True` |
| #2 Post-attach `/health` probe in `_connect_provider` path | ✅ Implemented | `SandboxService._probe_mcp_health`; gate in `init_sandbox` step 4 |
| #3 Bounded retry in `_configure_mcp` | ✅ Implemented | `_CONFIGURE_MCP_ATTEMPTS=3`, backoff `(0.2, 0.4, 0.8)` |
| #4 `agent_sandboxes.mcp_configured` flag + lazy retry | ✅ Implemented | Migration `20260425_000007`; `repository.set_mcp_configured`; `agents/factory/mcp/lazy_retry.py` wired into all 3 MCP-tool factories |
| #5 `validate_available_slots` `/health` probe | ✅ Implemented | `pool.py::validate_available_slots` extended; `_extract_container_ip` helper |
| #6 Post-commit replenish hook | ✅ Implemented | `SandboxPoolManager._schedule_replenish_after_commit` registers a one-shot SQLAlchemy `after_commit` listener on `db.sync_session`; replenish task scheduled only after caller's transaction is durable |
| #7 `agent.warning` event surface | ✅ Implemented | New `AgentWarningEvent` (`name="agent.warning"`, `warning_kind="mcp_configure_failed"`); `SandboxService.set_pubsub` wired in lifespan; emitted from `_configure_mcp_background` on terminal failure |

**Test coverage:** 26 unit tests in
[`src/tests/unit/agent/test_sandbox_service_mcp_handoff.py`](../../src/tests/unit/agent/test_sandbox_service_mcp_handoff.py)
plus 1 updated test in
[`src/tests/unit/engine/test_sandbox_service.py`](../../src/tests/unit/engine/test_sandbox_service.py).
Full sandbox suite: **326 passed**.

---

**Date:** 2026-04-25
**Trigger:** Session `e965f013-78f9-4cbe-ac6e-704178aa1ded` failed image-analysis
tools with `Client failed to connect: All connection attempts failed`. The
LLM misread the resulting bash errors as `PIL isn't installing`. The
actual root cause was that `_configure_mcp` was using the wrong network
address for backend → sandbox traffic and silently giving up after a
single attempt.

This document audits the pool fill → claim → MCP handoff protocol end-to-end
and enumerates corner cases the current design does *not* cover.

---

## 1. Observed failure (canonical example)

| Time (UTC)        | Event                                                                                          |
|-------------------|------------------------------------------------------------------------------------------------|
| `06:59:15`        | Pool slot bootstrapped: container `7f89ef319367`, MCP healthy on container IP `172.19.0.54:6060`. |
| `07:02:54.427`    | `claim_oldest_available` returns row `cd295e9f…` to session `e965f013…`. DB committed. |
| `07:02:54.461`    | `_configure_mcp` opens `MCPClient("http://192.168.2.2:31246")`. |
| `07:02:54.476`    | `httpx` returns `ConnectError("All connection attempts failed")`. |
| `07:02:54.477`    | `_configure_mcp_background` logs `"MCP configuration complete"` (sic) — warning swallowed. |
| `07:04:50.726`    | Same failure on a second sandbox `237cc7a0…` (different host port). |

The container's MCP server **was healthy throughout**. A direct GET to
`http://172.19.0.54:6060/health` from another container on the same Docker
bridge network returns 200 OK. The failure mode was deterministic, not a
race.

---

## 2. Root cause #1 — wrong endpoint for backend → sandbox traffic

`Sandbox.expose_port(port, *, external: bool = True)` returns either:

| `external` | Returns                                          | Intended consumer       |
|------------|--------------------------------------------------|-------------------------|
| `True`     | `http://<docker_host>:<host_port>`               | The browser / frontend  |
| `False`    | `http://<container_ip>:<container_port>`         | Backend / sidecar       |

In our local stack `SANDBOX_DOCKER_HOST=192.168.2.2` (the WSL2 host LAN IP).
The backend container has no route to that LAN IP — its default route is the
Docker bridge gateway `172.19.0.1`. Hairpin NAT through the host can work in
some environments but is not guaranteed; in this stack it does not.

`_configure_mcp` resolves the URL with the default `external=True`:

```python
sandbox_url = await sandbox.expose_port(self._config.mcp.port)  # external=True
sandbox.get_mcp_client(sandbox_url=sandbox_url)
async with MCPClient(sandbox_url) as client: ...
```

But the agent factory's adapter lookup correctly uses `external=False`:

```python
url = await sandbox.expose_port(ADAPTER_CONTAINER_PORT, external=False)  # 172.19.0.54:18100
```

The same asymmetry exists in three runtime MCP-tool factories:

- [`agents/factory/mcp/user_mcp_tool.py:89`](../../src/ii_agent/agents/factory/mcp/user_mcp_tool.py#L89)
- [`agents/factory/mcp/base.py:51`](../../src/ii_agent/agents/factory/mcp/base.py#L51)
- [`agents/factory/mcp/composio_mcp.py:56`](../../src/ii_agent/agents/factory/mcp/composio_mcp.py#L56)

Any session whose user actually had user-MCP or Composio tools registered
would hit the same connect failure on every tool call. We have not seen
this in the wild only because most sessions don't use those tools.

### Fix

A single audit pass: in **every backend-side** call to `expose_port`, pass
`external=False`. The only legitimate `external=True` callers are paths that
mint URLs for the browser (vscode, noVNC, register_port for user previews,
mobile_app_init's Expo URL).

`_wait_for_ready` already uses container-IP. The fix is to align
`_configure_mcp` and the runtime MCP tool factories with that same
endpoint.

---

## 3. Root cause #2 — single-shot configure with no retry, no failure marker

[`_configure_mcp_background`](../../src/ii_agent/agents/sandboxes/service.py)
catches `Exception` in `_configure_mcp` (line 962, `logger.warning`), then
the outer wrapper logs `"MCP configuration complete"` regardless of whether
configuration succeeded. There is:

1. No retry.
2. No `mcp_configured` flag on `AgentSandbox` that future code paths could
   inspect to decide whether to attempt a fresh handshake.
3. No metric, no `agent.warning` event, nothing the user-facing UI could
   surface.

Even after fixing the endpoint, transient failures (container under load,
fastmcp `__aenter__` timing out) will still strand sessions silently.

### Fix design

Two-tier approach:

- **Tier 1 (synchronous within `_configure_mcp`)**: retry the `MCPClient`
  handshake with bounded exponential backoff (e.g. 200 ms, 400 ms, 800 ms;
  max 3 attempts; total wall-clock ≤ 2 s). This handles iptables NAT setup
  windows on container start and brief GIL-contended hiccups.
- **Tier 2 (lazy at runtime)**: `_register_user_mcp_servers` returns a
  status. On terminal failure, set `agent_sandboxes.mcp_configured=False`
  (new column, default `True` for back-compat). Each MCP tool invocation in
  `user_mcp_tool.py` / `base.py` / `composio_mcp.py` can re-attempt
  configure on demand if the flag is `False` *and* enough time has elapsed
  to make a retry sensible (≥ 30 s).

This trades one schema migration for an end-to-end self-healing path. The
flag is small and cheap and does not interact with the existing pool
state machine.

---

## 4. Root cause #3 — readiness probe and runtime path use different endpoints

[`DockerSandbox._wait_for_ready`](../../src/ii_agent/agents/sandboxes/docker.py#L1276)
correctly probes `http://<container_ip>:6060/health` before marking a pool
slot AVAILABLE. But after claim, the runtime path uses a different URL
(see Root cause #1). So the readiness probe proves nothing about the
endpoint that's actually used.

After fixing #1, both paths will agree. We should still keep the readiness
probe as the gate (it's the right place) — but we should also add a
**post-attach health probe** in `_connect_provider` so backend restarts
can detect a wedged MCP server before silently handing the sandbox to a
session.

---

## 5. End-to-end audit of the claim/handoff protocol

Below is every state transition + corner case I evaluated, with verdicts.

### 5.1 Pool fill (`_create_slot_async` → `_do_create_slot`)

- ✅ DB row inserted (`status=INITIALIZING, pool_state=AVAILABLE`) before
  container provisioning so a crash leaves a recoverable artifact, not an
  orphan container.
- ✅ Provider create raises `SandboxCreationError` on `_wait_for_ready`
  timeout; row marked DELETED so `ensure_full` retries.
- ⚠️ `provider_data` (containing port mappings) is written *after* the
  container exists. If the backend crashes between `_wait_for_ready` and
  `update_provider_info`, we lose the mappings. On restart `port_manager`
  re-discovers them via `containers.list` → no leak, just slight extra
  work. Acceptable.
- ⚠️ Bootstrap and `ensure_full` are guarded by `_create_lock` *per
  process*. Two backend instances racing on the same slot rely on
  `dedupe_available_slots` to clean up. This is acknowledged in the code.
- ⚠️ `reap_stuck_initializing` uses a 10-minute threshold. A pool slot
  rebooted right after a host crash sits idle for up to 10 min before
  being reclaimed for a new attempt. Tunable via config; not a bug.

### 5.2 Pool readiness gate

- ✅ `_wait_for_ready` polls `/health` on the **container IP** with a 60 s
  timeout. The MCP server is the only HTTP service on port 6060.
- ❌ Doesn't probe the **A2A adapter** port `18100`. If the adapter
  restart-loop is mid-restart at claim time, `_wait_for_a2a_adapter`
  in `agent.py` will retry but the user sees a 1–2 s extra startup.
  Tolerable; could be added as a parallel readiness probe.
- ❌ Doesn't probe code-server (port 9000), noVNC (6080), or the shell
  PTY infrastructure (no probe — relies on `tmux ls` working). All of
  these can lag MCP readiness by tens of seconds. The PTY shell is
  exercised on first `Bash` tool call; failures there manifest as a
  `ShellSessionExistsError` or hang.

### 5.3 Claim atomicity (`claim_oldest_available`)

- ✅ Uses `SELECT … FOR UPDATE SKIP LOCKED` against
  `pool_state=AVAILABLE`. Atomic. Two concurrent claimers cannot grab
  the same row.
- ✅ `pool_slot=NULL` set at claim time so the long-lived CLAIMED row
  doesn't prevent `ensure_full` from refilling that slot.
- ✅ `claimed_slot` is returned alongside the row so replenish can target
  the freed slot specifically.

### 5.4 Claim commit timing (`init_sandbox`)

- ✅ `await db.commit()` immediately after claim (line 161). This is the
  fix for the 2026-04-23 incident where rolling back the claim left a
  duplicate replenished row on the slot.
- ⚠️ If `_configure_mcp` fails, the claim is **already durable** —
  meaning a second user-message on the same session will reconnect to
  the same sandbox but won't retry MCP configure (single-shot bug,
  Root cause #2).

### 5.5 Replenish-on-claim race

- ✅ Replenish is `asyncio.create_task(...)`, fire-and-forget. The new
  row uses `compute_replacement_retire_at` (full max_age window) — the
  per-slot stagger is preserved because *time-of-claim* sets the new
  cycle's anchor.
- ⚠️ Replenish runs in a separate DB session (`get_db_session_local`)
  and does not coordinate with the caller's commit. Since the caller
  has already committed, this is safe. But if some future caller
  forgot to commit, the replenish would run before the claim is
  durable. **Architectural recommendation**: emit replenish from a
  post-commit hook (SQLAlchemy `after_commit`) rather than
  immediately, so this invariant cannot be broken by future callers.

### 5.6 Existing-record path (`_resolve_sandbox_record`)

- ✅ Returns the most recent active row for the session; falls back to
  `parent_session_id` for forks.
- ⚠️ Forks reuse the parent's sandbox without re-running `_configure_mcp`.
  If parent's configure had failed silently (Root cause #2), the fork
  inherits the broken state. Fixed by the lazy retry in Root cause #2's
  Tier 2 plan.

### 5.7 `_connect_provider` for already-running container

- The pool path on first claim goes through `_create_provider`
  ([service.py:189](../../src/ii_agent/agents/sandboxes/service.py)),
  which (after fixing #1) attaches to the existing container and
  reuses the port mappings. No re-run of `_wait_for_ready`.
- Backend-restart path: when a session reconnects on a new backend
  instance, `_resolve_sandbox_record` finds the row, `_connect_provider`
  attaches via `containers.get`. **No health probe.** A wedged MCP
  server in a healthy container causes the same silent break.
- **Recommendation**: add a fast (≤ 2 s) `/health` probe inside
  `_connect_provider` whenever the row is being handed to a session.
  Failure → mark row DELETED, fresh provision.

### 5.8 Container went sick between fill and claim

- `validate_available_slots` (cleanup loop, every 60 s) checks if the
  Docker container is alive (`containers.get`). Marks the row RETIRING
  if the container is missing.
- ❌ Does NOT check if the MCP server inside is responsive. A crashed
  fastmcp inside a running container is invisible to validation.
- **Recommendation**: extend `validate_available_slots` with a fast
  `/health` probe (HEAD on `<container_ip>:<mcp_port>/health`,
  500 ms timeout) per AVAILABLE row. ~N HTTP calls per minute, where
  N = pool size. Cheap.

### 5.9 Docker daemon restart

- iptables NAT rules survive (Docker re-applies them on daemon start).
- Host port mappings should be unchanged (Docker re-publishes the same
  user-specified ports).
- Backend `port_manager.register_existing` re-discovers mappings from
  `containers.list`. Verified in logs.
- ⚠️ Brief window where port forwarding is unavailable. After the
  endpoint fix, the backend uses container IPs which depend only on
  `bridge` driver (recreated by Docker) — survives daemon restart.

### 5.10 Backend restart

- Pool rows persist (DB-backed).
- `bootstrap()` re-runs on the new backend. `_existing_live_slots()`
  reads existing AVAILABLE/CLAIMED rows; missing slots get
  `_create_slot_async` calls. So nothing is recreated unnecessarily.
- ⚠️ `_creating: set[int]` is per-process; after restart it's empty,
  so two replenishes could fire if the previous backend already had
  one in flight. `dedupe_available_slots` cleans up.
- ⚠️ `_mcp_config_tasks: set[asyncio.Task]` is **class-level mutable
  state**. Survives across instance creation but is cleared on
  process exit. This is fine but worth noting: if `ApplicationContainer`
  is ever re-initialized in-process (e.g. tests), tasks pin references
  to the previous container.

### 5.11 Configure timeout (`_CONFIGURE_MCP_TIMEOUT_S = 30.0`)

- ✅ `asyncio.wait_for` enforces a hard wall-clock cap so a wedged
  fastmcp `__aenter__` cannot leak.
- ⚠️ 30 s is a long time on the user-facing path even though
  `_spawn_configure_mcp` is fire-and-forget — the user can fire
  off a tool call before configure completes, and that tool call
  will get a stale (uninitialized) MCP client. Acceptable because:
  (a) we don't currently use the MCP client during `init_sandbox`,
  and (b) the runtime `expose_port` calls in MCP-tool factories
  open fresh `MCPClient` instances each time.

### 5.12 Slot retirement / `RETIRING` race

- `claim_oldest_available` filters for `pool_state=AVAILABLE` only.
  RETIRING rows are never claimed.
- `validate_available_slots` and `dedupe_available_slots` both convert
  AVAILABLE → RETIRING; safe because the SKIP LOCKED claim doesn't see
  RETIRING.
- ✅ No claim-vs-retire collision possible.

### 5.13 Pool size = 0

- `enabled` returns False; `claim` returns None; `init_sandbox` falls
  through to fresh-create path. No pool code runs.
- ✅ Self-consistent.

### 5.14 Pool size shrunk mid-flight (`shrink_excess`)

- Existing rows with `pool_slot >= new_size` are marked RETIRING.
- ⚠️ Rows that were **CLAIMED before shrink** keep their session but
  their slot is irrelevant after claim (cleared to NULL on claim). No
  user impact.
- ✅ No race.

### 5.15 `delete_after` + claim race

- `_soft_delete_expired_sessions` (cleanup loop, every 60 s) marks
  sessions deleted. The cleanup chain then kills containers for
  deleted sessions.
- ⚠️ Pool rows have `session_id=NULL` until claimed. A pool row's
  session lifecycle starts at claim. No interaction.

### 5.16 Container OOM kill mid-session

- Sandbox container has `mem_limit=3G`, OOM kills the container.
- Next tool call: `_connect_provider` → `containers.reload()` → status
  != "running" → raises `SandboxNotInitializedError`.
- `init_sandbox` next call: catches `SandboxNotFoundException`, marks
  row DELETED, fresh-creates. ✅ Self-healing.

### 5.17 Health probe under load

- Container under heavy CPU load can drop /health responses.
  `_wait_for_ready` polls every 1 s for 60 s. ✅ Generous.
- Recommendation in 5.8 (add probe to `validate_available_slots`)
  should use a slack threshold (e.g. require 2 consecutive failures
  ≥ 5 s apart) to avoid flapping rows under transient load.

### 5.18 Host monitor integration (host_monitor.py)

- `bootstrap()` and `ensure_full()` skip on host_state ≥ WARN.
- ⚠️ `claim` is **not** gated by host_state. A WARN-state host can
  drain the pool with no replenish, eventually starving claims.
  Acceptable — better to serve users from existing pool than fail
  fast on host pressure.

### 5.19 Failure surface visibility

- Currently `_configure_mcp` failures log `WARNING`. No
  `ApplicationEvent`, no Socket.IO emission, no user feedback.
- **Recommendation**: emit `agent.warning` event with the kind
  `mcp_configure_failed` so the frontend can surface "tool subset
  may be unavailable" rather than the user discovering it via a
  cryptic `Client failed to connect` mid-conversation.

---

## 6. Recommended remediation, ordered by impact and risk

> **Status: All 7 items implemented as of 2026-04-25**; see the status
> banner at the top of this document.

| # | Change                                                                                                                                | Impact | Risk | Status |
|---|---------------------------------------------------------------------------------------------------------------------------------------|--------|------|--------|
| 1 | **Endpoint audit** — switch all backend-side `expose_port` calls to `external=False`. Affects `_configure_mcp` and 3 MCP tool factories. | Critical — fixes the actual bug | Low — single keyword arg, contained | ✅ |
| 2 | **Post-attach health probe** in `_connect_provider` (≤ 2 s GET on `<container_ip>/<mcp_port>/health`). On fail → mark DELETED, fresh-create. | High — kills the silent-broken-sandbox class | Low — additive | ✅ |
| 3 | **Bounded retry** in `_configure_mcp` (3 attempts, 200 ms / 400 ms / 800 ms). Logs at ERROR (not WARN) on terminal failure with all attempt details. | High — handles iptables-NAT settling and transient hiccups | Low | ✅ |
| 4 | **AgentSandbox.mcp_configured** boolean flag (default True; new migration). MCP-tool factories check it and lazy-retry on False with cooldown. | Medium — turns silent failure into self-healing | Med — schema migration | ✅ |
| 5 | **Extend `validate_available_slots`** with a 500 ms `/health` probe per AVAILABLE row. Mark RETIRING on persistent failure (≥ 2 sweeps). | Medium — catches inert pool rows before they're claimed | Low — additive | ✅ |
| 6 | **Post-commit replenish** — emit replenish from a SQLAlchemy `after_commit` hook on the claim transaction, so future callers can't break the durability invariant. | Low — defence in depth | Med — reorder of an existing pattern | ✅ |
| 7 | **`agent.warning` event** on configure failure so the frontend surfaces it. | Low — UX | Low | ✅ |

All 7 items shipped together in this PR.

---

## 7. Tests required for the fix

- **Endpoint regression**: a unit test that asserts `_configure_mcp`
  resolves the URL with `external=False` (or, equivalently, that the
  URL contains the docker bridge container IP). Mock `expose_port` to
  detect the call signature.
- **Retry semantics**: `_configure_mcp` test with a mock that fails
  twice then succeeds. Assert success after 3 attempts.
- **Lazy retry path** (after #4 lands): a test that simulates
  `mcp_configured=False`, calls a user MCP tool, asserts a fresh
  configure attempt was made.
- **Health probe in `_connect_provider`**: test that an inert MCP
  server (TCP port open but `/health` 500) causes the row to be
  re-provisioned.
- **End-to-end smoke**: in `scripts/local/test_e2e.py`, after claiming
  a pool sandbox, fire a `Read` tool call against an existing file
  and assert it succeeds. The original bug would have made this
  fail — currently the e2e harness doesn't exercise it.

---

## 8. Out-of-scope but worth flagging

- The PTY shell wrapper had a related class of failure where multi-line
  shell payloads (e.g. `python3 -c "<heredoc>"`) were split across the
  FIFO line reader and `eval`'d as separate bash commands. Fixed in the
  same investigation by base64-framing the FIFO transport. See
  [`docker_shell.py`](../../src/ii_agent/agents/sandboxes/docker_shell.py)
  and the new
  [`test_docker_shell_framing.py`](../../src/tests/unit/agent/test_docker_shell_framing.py).
  That's a separate code path (Docker exec, not MCP) but the user-facing
  symptom — the LLM hallucinating `PIL isn't installing` — combined the
  two failures.

- The same `external=True` default has **never** been right for backend
  callers. The signature should arguably be flipped: `external=False`
  default, with `external=True` reserved for explicitly
  browser-targeted URLs. Out of scope for this fix but a clean
  follow-up.
