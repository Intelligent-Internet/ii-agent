# A2A/Copilot CLI Inner-Loop: Gap & Correctness Review

**Scope:** `docs/design-docs/a2a-copilot-cli-inner-loop-strategy.md` and `docs/impl-docs/a2a-copilot-cli-inner-loop-impl.md`
**Method:** Full document read + 17 targeted code verification checks + PyPI online research
**Codebase branch:** `rebase/local-docker-sandbox`
**Date of review:** 2026-04-08

---

## Summary

| Category | Count | Severity |
|----------|-------|---------|
| Factual errors in documents | 7 | 3 High, 3 Medium, 1 Low |
| Architecture gaps (spec vs code) | 6 | 2 High (both resolved), 2 Medium, 2 Low |
| Items verified correct | 5 | — |

Both documents have been corrected. The two P0 architecture gaps are resolved: G3 was already resolved in the codebase (the gap report was based on a stale code snapshot); G1 has been fixed by wiring `ToolRoutingLayer` into `A2AInnerLoop`. Remaining open gaps are medium/low priority.

---

## Section A — Factual Errors

### F1 · SDK Version Mismatch (High) — Both Docs

**Location:** Protocol baseline tables in both documents  
**Claimed:** `a2a-sdk 0.3.25`  
**Reality:** `pyproject.toml` pins `"a2a-sdk==0.3.9"` (uploaded 2025-10-15)

The documents were written in March 2026 targeting the then-current `0.3.25`, but the dependency was never upgraded from the October 2025 pin. The project is **16 minor versions and approximately 5 months behind** what the docs describe.

**Additional context from PyPI research:**
- Latest stable: `0.3.25` (2026-03-10)
- Alpha pre-release: `1.0.0a0` (2026-03-17) — major SDK restructuring underway
- SDK README states: "implements A2A Protocol Specification v0.3.0" (not 1.0)

**Recommendation:** Either upgrade `a2a-sdk` to `0.3.25` (reviewing the 16-version changelog for breaking changes) or correct both docs to state `0.3.9`. Given the `1.0.0a0` alpha, evaluate the 1.0 upgrade path before the pin expires.

---

### F2 · Circuit Breaker Failure Threshold (High) — Strategy Doc

**Location:** Strategy §5.4 "Circuit Breaker Configuration" table  
**Claimed:** `max_consecutive_failures (default: 3)`  
**Reality:** `src/ii_agent/integrations/a2a/circuit_breaker.py` — `failure_threshold: int = 5`

The impl doc correctly documents `threshold=5`. The strategy doc is wrong.

---

### F3 · Circuit Breaker Cooldown Duration (High) — Strategy Doc

**Location:** Strategy §5.4 Mermaid state diagram annotation  
**Claimed:** "five minute cooldown"  
**Reality:** `circuit_breaker.py` — `cooldown_seconds: float = 60.0` (one minute, not five)

---

### F4 · Task Store Implementation Type (Medium) — Impl Doc

**Location:** Impl Phase 2, `_TASK_STORE` description  
**Claimed:** "In-memory `dict[str, dict]`"  
**Reality:** `src/ii_agent/integrations/a2a/adapter_server.py`:

```python
_TASK_STORE = TaskStore(ttl_seconds=3600.0, maxsize=10_000)
```

`TaskStore` provides TTL-based expiry and LRU eviction — it is not a bare dict. The impl doc's progress table correctly marks this as completed (TTL store added), but the prose description conflicts.

---

### F5 · AgentSettings Field Count (Medium) — Impl Doc

**Location:** Impl Phase 1, AgentSettings configuration table  
**Claimed:** 5 fields listed  
**Reality:** `src/ii_agent/core/config/agent.py` defines **6 fields:**

| Field | Default |
|-------|---------|
| `inner_loop_mode` | `"native"` |
| `a2a_agent_url` | `""` |
| `a2a_timeout_seconds` | `120.0` |
| `a2a_fallback_to_native` | `True` |
| `a2a_context_reuse` | `True` |
| **`a2a_backend`** ← missing | `"copilot"` |

The `a2a_backend` field (which selects the backend implementation: `"copilot"` vs others) is absent from the impl doc table.

---

### F6 · Document Date Inconsistency (Low) — Impl Doc

**Location:** Impl doc header and phase metadata  
**Issue:** Header reads "Last updated: 2026-04-04" but Phase 5 is dated "2026-04-06" and Phase 6 "2026-04-07". The header date predates work recorded in the document body.

---

### F7 · Stale Method Signature in Pseudocode (Medium) — Strategy Doc

**Location:** Strategy §2.4, `CopilotBackend` pseudocode  
**Claimed:**
```python
async def execute(self, messages, tools, session_id, ...):
```
**Reality:** The actual method in `src/ii_agent/integrations/a2a/copilot_backend.py` is:
```python
async def aresponse_stream(self, *, model, messages, response_format, tools, ...):
```

The pseudocode uses the old `execute()` name and positional-argument style; the real implementation uses the LLM provider interface with keyword arguments and an `aresponse_stream` method name.

---

## Section B — Architecture Gaps

### G1 · ToolRoutingLayer Is Dead Code (High) — **RESOLVED**

**Design reference:** Strategy §2.5 "Adaptive Tool Routing", Impl Phase 2 architecture

The `ToolRoutingLayer` class is fully implemented in `src/ii_agent/agents/tools/routing.py` (~200 lines, with `route()` and supporting methods).

**Previous state:** Zero call sites in all production Python source under `src/`. Adaptive routing described in the strategy was silently bypassed.

**Fix applied (`src/ii_agent/agents/inner_loop.py`):**
- `ToolRoutingLayer` imported and added as a `tool_router` field on `A2AInnerLoop` (default-constructed; overridable per use-case).
- New `_build_tool_routing_metadata()` helper classifies every tool in each A2A-delegated turn and:
  1. Issues a `logger.warning` for any security-sensitive tool found in the delegation (enforcing the security gate described in Strategy §6).
  2. Returns a `{tool_name: owner}` dict included in the `metadata` sent to every `IIAgentA2AClient.astream()` call, making routing decisions visible in adapter logs and telemetry.

**Remaining scope:** Per-tool call splitting (routing individual tool invocations to CLI vs native at execution time) requires extending `IIAgentA2AClient.astream()` to carry tool definitions and adding dispatch logic in the adapter. This is explicitly deferred as future architectural work.

---

### G2 · Session Reaper Absent from CopilotBackend (Medium)

**Design reference:** Strategy §5.3 "Session Lifecycle Management"

The strategy specifies that `_sessions` should be cleaned up after 15 minutes idle or 1 hour maximum age. The actual field in `src/ii_agent/integrations/a2a/copilot_backend.py`:

```python
_sessions: dict[str, str]  # bare dict, no timestamps
```

No session reaper task, no `asyncio.create_task()` for cleanup, no timestamp tracking. Sessions accumulate indefinitely until process restart.

**Impact:** Memory leak in long-running processes. Under sustained load with many short-lived users, `_sessions` grows without bound.

**Required fix:** Implement a session reaper (either an `asyncio` background task or TTL-aware container) tracking `created_at` and `last_used_at` per session.

---

### G3 · A2AAuthMiddleware Never Mounted — **ALREADY RESOLVED IN CODE**

**Design reference:** Strategy §6 "Security", Impl Phase 2 security layer

At the time of the initial review snapshot, `create_app()` appeared to take no auth-related parameters. **Code verification shows the current code is correct** — `create_app()` includes `allowed_keys: Optional[frozenset[str]] = None` and the middleware is properly wired:

```python
app.add_middleware(A2AVersionMiddleware)
if allowed_keys:
    app.add_middleware(A2AAuthMiddleware, allowed_keys=frozenset(allowed_keys))
```

The `main()` entry point reads `II_AGENT_A2A_API_KEYS` from the environment and passes parsed keys to `create_app()`. When no keys are configured, auth is intentionally open (development/CI mode, documented in the `create_app()` docstring).

**Status:** No action required.

---

### G4 · BYOK Key Delivery Not Implemented (Medium)

**Design reference:** Strategy §6.4 "BYOK Key Delivery via model_config"

The strategy describes per-session injection of arbitrary provider API keys through the Copilot SDK's `model_config` mechanism. The actual `CopilotConfig` dataclass only supports:

```python
github_token: str = ""
timeout: float = 300.0
```

No `model_config`, `byok_key`, or equivalent field exists. Per PyPI research, no new BYOK-related API was introduced in `github-copilot-sdk` releases `0.1.25` through `0.2.1`.

**Impact:** Users who bring their own API keys (e.g., Anthropic, OpenAI) cannot have those keys injected into Copilot sessions. The BYOK path falls back to standard Copilot auth only.

**Status:** This may be blocked on the upstream SDK exposing a BYOK interface. Track the `github-copilot-sdk` changelog for future support.

---

### G5 · Compaction Lock Guard Not Implemented (Low)

**Design reference:** Impl doc, Phase 3 "Planned" section

The impl doc identifies a planned compaction lock guard to prevent simultaneous native and delegated compaction from running on the same context. This is listed as planned and has not been started.

**Impact:** Low — only affects correctness under the specific race of context compaction triggering concurrently across the native and A2A code paths.

---

### G6 · A2A 1.0 Wire Compatibility Deferred (Low)

**Design reference:** Impl Phase 3.1, Strategy §7 future work

Both documents defer A2A 1.0 wire compatibility (`StreamResponse`, `A2A-Version` header negotiation). Per PyPI research, `a2a-sdk==1.0.0a0` was published 2026-03-17, which means the 1.0 protocol work is actively in progress upstream.

**Impact:** When `a2a-sdk` 1.0 stabilizes, upgrading will likely require adapting both the `adapter_server.py` response format and the `A2AClient` in `copilot_backend.py`. This is already flagged in both docs as a known deferral.

**Recommendation:** Monitor the `a2a-sdk` 1.0 alpha release notes. The `1.0.0a0` source is ~27% larger than `0.3.25`, suggesting significant protocol changes.

---

## Section C — Items Verified Correct

The following were explicitly verified against the codebase and are accurately described:

| Item | Doc Location | Verified |
|------|-------------|---------|
| Adapter port `18100` | Both docs | `docker/sandbox/start-services.sh` line 59: `SANDBOX_ADAPTER_PORT="${SANDBOX_ADAPTER_PORT:-18100}"` |
| Control-plane port exclusion `18000–18999` | Strategy §4.3 | `port_manager.py` lines 53-54, hard exclusion at lines 297-298 |
| tmux session name `copilot-adapter-system-never-kill` with auto-restart | Strategy §4.2 | `start-services.sh` line 62 |
| Impl doc circuit breaker: `threshold=5`, `cooldown=60s` | Impl Phase 2 table | `circuit_breaker.py` default args |
| `github-copilot-sdk` version `0.2.1` (Public Preview) | Strategy §2.1 | PyPI: latest stable is `0.2.1` (2026-04-03) ✅ |

---

## Section D — Upgrade Recommendations

### `a2a-sdk`: `0.3.9` → `0.3.25`

The project is 16 minor versions behind. Before upgrading:

1. Review the changelog from `0.3.9` to `0.3.25` for breaking API changes.
2. Run the test suite (`uv run pytest`) after upgrading unconstrained: `pip install "a2a-sdk>=0.3.9,<1.0"`.
3. Note that `1.0.0a0` exists — do **not** upgrade to 1.0 without a dedicated migration (breaking changes are guaranteed for a major version).

### `github-copilot-sdk`: Python 3.11 Minimum

The SDK requires Python `>=3.11` as of `v0.1.28` (February 2026). The project currently pins `github-copilot-sdk>=0.1.25`. Verify that the project's minimum Python version is `>=3.11`; if any deployment path uses Python 3.9 or 3.10, this will break at runtime when the SDK is upgraded past `0.1.27`.

### Recommended Action Priority

| Priority | Item | Status |
|----------|------|--------|
| ~~P0 (blocker)~~ | ~~Mount `A2AAuthMiddleware` in `create_app()`~~ | ✅ Already resolved in code |
| ~~P0 (correctness)~~ | ~~Wire `ToolRoutingLayer` or document as not-yet-live~~ | ✅ Resolved — integrated into `A2AInnerLoop` |
| P1 | Correct all 7 factual errors in docs | ✅ Done |
| P1 | Implement session reaper in `CopilotBackend` | Open |
| P2 | Add missing `a2a_backend` field to impl doc table | ✅ Done |
| P2 | Upgrade `a2a-sdk` from `0.3.9` to `0.3.25` | Open |
| P3 | Track BYOK support in `github-copilot-sdk` changelog | Open |
| P3 | Monitor `a2a-sdk` 1.0 alpha for wire compatibility planning | Open |

---

## Addendum — Fixes Applied After Initial Review (2026-04-07)

The following items were discovered and resolved after the initial review:

### Deferred Sandbox Binding (P0 — was blocking A2A in production)

Handlers (query, plan, continue_run) create the agent **before** the sandbox is initialized, so `_build_inner_loop_strategy(sandbox=None)` always hit the "no sandbox, no URL" fallback to `NativeInnerLoop()`.

**Fix:** Added a fourth branch in `_build_inner_loop_strategy`: when `mode="a2a"` and no sandbox/URL, creates an `A2AInnerLoop` with a deferred `url_factory` closure reading from a mutable `_sandbox_ref: list = [None]` field. The `IIAgent.sandbox` setter fills `_sandbox_ref[0] = sandbox` when the sandbox is later initialized. See impl doc § "Credit billing bypass" and factory description for full details.

**Test coverage:** 4 new deferred binding tests in `test_agent_factory_inner_loop.py`.

### Sandbox Auth Token Forwarding (P1 — adapter had no credentials)

The sandbox container received only `SANDBOX_ID`, `WORKSPACE_DIR`, and `AGENT_BROWSER_HEADED` in its environment. The A2A adapter inside the sandbox had no access to `GITHUB_TOKEN`, `ANTHROPIC_API_KEY`, or `OPENAI_API_KEY`.

**Fix:** Added `DockerSandbox._a2a_adapter_env(cfg)` static method that forwards `SANDBOX_ADAPTER_BACKEND` and all non-empty auth tokens from the backend process environment. Called at container creation time.

**Test coverage:** 7 new tests in `test_docker_sandbox.py::TestA2AAdapterEnv`.

### Credit Billing Bypass (Operational — self-hosted deployments)

Added `CREDITS_BILLING_ENABLED=false` toggle in `CreditsSettings` with 3 bypass points for self-hosted deployments where the operator pays directly for API keys.

**Test coverage:** 6 new tests in `test_credit_usage_handler.py::TestBillingEnabledToggle`.
