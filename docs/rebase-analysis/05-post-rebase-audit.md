# Post-Rebase Audit: `rebase/local-docker-sandbox`

## Executive Summary

The 7-commit rebase onto `origin/main` successfully ported the core Docker sandbox functionality. **39 files** were changed (from 155 in the original topic branch). The 116 unported files were analyzed — most are correctly unported (old module structure that was rewritten by DDD restructure #851 on main). However, the audit identified:

- **3 critical architectural issues** in the ported code
- **4 high-priority issues** needing attention
- **3 missing features** that should be ported
- **2 regressions** to fix before merge
- **Several nice-to-have improvements** from the original branch that were not Docker-specific

---

## Part 1: Completeness — What Was Missed

### 1.1 Correctly Unported (No Action Needed)

| Category | Files | Reason |
|----------|-------|--------|
| `src/ii_sandbox_server/` | 8 | Absorbed into `agents/sandboxes/` on main |
| `src/ii_tool/` (most files) | ~12 | Now `ii_server/` on main |
| `src/ii_agent/server/` | 26 | DDD restructure rewrote all |
| `src/ii_agent/controller/`, `llm/`, `sub_agent/`, `storage/` | ~20 | Completely rewritten on main |
| Old `tests/` structure | 40+ | Moved to `src/tests/` |
| `uv.lock` | 1 | Auto-generated |
| `frontend/pnpm-lock.yaml` | 1 | Auto-generated (but see §2.2) |

### 1.2 Features That SHOULD Be Ported

#### A. VNC Services in Sandbox Image (BLOCKING for human-in-the-loop)
**Original files:** `e2b.Dockerfile`, `docker/sandbox/start-services.sh`  
**What's missing:**
- `e2b.Dockerfile`: Missing `x11vnc` and `novnc` package installs
- `start-services.sh`: Missing Xvfb display setup, x11vnc server startup, noVNC websockify startup, health checks for VNC processes, `/workspace` ownership fix (`chown -R pn:pn`)
- The sandbox code allocates `NOVNC_PORT = 6080` but nothing actually starts on that port

**Impact:** Human-in-the-loop sandbox access (browser VNC) will not work.

#### B. Client Host URL Rewriting (BLOCKING for remote access)
**Original file:** `src/ii_agent/core/client_host.py`  
**What's missing:** A `ContextVar` that stores the connecting browser's hostname. `DockerSandbox.expose_port()` returns hardcoded `http://localhost:{port}` — this breaks when the browser is on a different machine than the Docker host.

**Impact:** Docker sandbox URLs won't work from any machine other than localhost.

#### C. `docker` Python Package Dependency (BLOCKING for fresh installs)
**Original file:** `pyproject.toml`  
**What's missing:** `docker>=7.0.0` is not in `pyproject.toml` dependencies. It happens to be installed in the current environment (`7.1.0`) but `uv sync` on a fresh clone will not install it.

**Impact:** `import docker` in `docker.py` will fail on fresh installs.

### 1.3 Nice-to-Have Features Not Ported (Non-Docker-Specific)

These were co-developed on the topic branch but are general improvements:

| Feature | Original Files | Status on Main |
|---------|---------------|----------------|
| DALL-E 3 image generation client | `ii_tool/integrations/image_generation/openai_dalle.py` + factory | Missing — generic video gen framework exists but no DALL-E 3 |
| Sora video generation | `ii_tool/integrations/video_generation/` (5 files) | Missing — can be added later |
| Browser tab limit (MAX_TABS=50) | `ii_tool/browser/browser.py` | Missing — resource exhaustion protection |
| Shell session limit (MAX_SHELL_SESSIONS=10) | `ii_tool/tools/shell/shell_init.py` | Missing — tmux session leak protection |
| Tool server local file serving | `ii_tool/integrations/app/main.py` `/storage/` endpoint | Missing — needed for local-mode file access |
| MCP tool image bridging | `ii_tool/tools/mcp_tool.py` `_process_image_inputs()` | Missing — external MCP servers can't read sandbox files |
| Dynamic token budget | `core/config/llm_config.py` `get_max_context_tokens()` | Missing — uses static config on main |

### 1.4 Already Exists on Main (Verified)

| Feature | Status |
|---------|--------|
| Image compression (5MB Anthropic limit) | ✅ `chat/application/file_processor.py` |
| ThinkingBlock sanitization | ✅ `chat/llm/anthropic/provider.py` + tests |
| Failed tool lookup error handling | ✅ Error `ToolResult` on unknown tool |
| Frontend sessionId priority (URL > Redux) | ✅ `websocket-context.tsx` |
| Orphan cleanup (no HTTP endpoint needed) | ✅ Uses Docker API directly |

---

## Part 2: Regressions

### 2.1 pnpm-lock.yaml Not Updated for vitest
**File:** `frontend/package.json` lists `"vitest": "^3.2.1"` in devDependencies and has test scripts.  
**Problem:** `frontend/pnpm-lock.yaml` has 0 occurrences of "vitest" — it was never regenerated.  
**Impact:** `pnpm install --frozen-lockfile` in CI will fail. Frontend tests ("vitest run") will fail.  
**Fix:** Run `cd frontend && pnpm install` to regenerate lockfile.

### 2.2 Backend `/auth/dev/login` Endpoint Does Not Exist
**File:** `frontend/src/app/routes/login.tsx` adds DevLoginButton that calls `/auth/dev/login`.  
**Problem:** No backend endpoint exists at that path. The button is safely hidden (returns null when endpoint returns non-200), but the feature is dead code.  
**Impact:** Local-mode dev login doesn't work. Not blocking (button hidden gracefully), but a missing feature.

---

## Part 3: Architectural Issues

### 3.1 CRITICAL

#### A. Exception Hierarchy Violation
**File:** `src/ii_agent/agents/sandboxes/exceptions.py`  
**Problem:** `SandboxException` inherits from `Exception` instead of `IIAgentError`.  
**Impact:** Global error handler (`ii_agent_error_handler`) won't catch sandbox exceptions. Error responses bypass schema validation. HTTP status codes may be wrong.  
**Fix:**
```python
from ii_agent.core.exceptions import IIAgentError

class SandboxException(IIAgentError):
    pass
```

#### B. PortPoolManager Uses threading.Lock (Blocks Event Loop)
**File:** `src/ii_agent/agents/sandboxes/port_manager.py`  
**Problem:** `self._port_lock = threading.Lock()` — when `DockerSandbox.create()` awaits `allocate_ports()`, the blocking lock freezes the entire asyncio event loop.  
**Impact:** Under concurrent sandbox creation, the server becomes unresponsive.  
**Fix:** Convert to `asyncio.Lock` or use `asyncio.to_thread()` wrapper.

#### C. Orphan Cleanup Bypasses Service Layer
**File:** `src/ii_agent/agents/sandboxes/orphan_cleanup.py`  
**Problem:** Creates `DockerSandbox` directly and calls `kill()` instead of going through `SandboxService`. Also uses `get_db_session_local()` directly instead of DI.  
**Impact:** DB state sync issues if `SandboxService.pause_sandbox()` is called concurrently. Pattern violation.  
**Fix:** Use `SandboxService` for sandbox lifecycle operations.

### 3.2 HIGH PRIORITY

#### D. Docker Client Singleton Race Condition
**File:** `src/ii_agent/agents/sandboxes/docker.py` (lines ~151-154)  
**Problem:** `_get_docker_client()` uses a `None` check without locking — two concurrent calls can create two clients.  
**Fix:** Use double-checked locking or `asyncio.Lock`.

#### E. Port Constants Hardcoded
**File:** `src/ii_agent/agents/sandboxes/docker.py` (lines 58-72)  
**Problem:** `MCP_SERVER_PORT = 6060`, `CODE_SERVER_PORT = 9000`, `NOVNC_PORT = 6080` are module constants instead of settings.  
**Fix:** Move to `SandboxSettings` with configurable defaults.

#### F. scan_existing_containers() Never Called at Startup
**File:** `src/ii_agent/agents/sandboxes/port_manager.py`  
**Problem:** `PortPoolManager.scan_existing_containers()` exists (~70 lines) but is never called during lifespan startup. If the server restarts, previously allocated ports won't be tracked.  
**Fix:** Add call to `app/lifespan.py` startup sequence.

#### G. DANGEROUS_PATTERNS Regex Defined But Unused
**File:** `src/ii_agent/agents/sandboxes/docker.py` (lines 75-80)  
**Problem:** Security regex for strict command validation exists but is never called.  
**Fix:** Either integrate into `run_command()` or remove dead code.

### 3.3 MEDIUM

| Issue | File | Description |
|-------|------|-------------|
| Resource cleanup lacks exception safety | docker.py `kill()` | Port release can leak if container removal fails |
| Global task tracking race | orphan_cleanup.py | `start_orphan_cleanup()` could create duplicate tasks |
| Logging inconsistency | port_manager.py | Uses stdlib logging; main may use structlog |

---

## Part 4: Frontend Analysis

### 4.1 Verified Clean ✅

| Item | Status |
|------|--------|
| `isDesignModeAvailable` uses `isSandboxLink()` | ✅ Correctly migrated |
| `isE2bLink` → `isSandboxLink` migration complete | ✅ No stale references in production code |
| `sandboxStatus` state initialized and cleared | ✅ Proper Redux lifecycle |
| `rewriteLocalhostUrl()` edge cases | ✅ Handles null, same-host, portless URLs |
| Model entries (claude-opus-4-6, claude-sonnet-4-6) | ✅ Follow existing pattern |
| DevLoginButton security | ✅ Hidden by default, backend-gated |
| Sub-agent STOPPED status | ✅ Consistent with backend RunStatus enum |

### 4.2 Issues

| Issue | Severity | Description |
|-------|----------|-------------|
| vitest not in lockfile | ⚠️ Regression | `pnpm install` needed |
| DevLoginButton dead code | ℹ️ Info | Backend endpoint missing |

---

## Part 5: Test Coverage Assessment

### 5.1 Existing Tests

| Test File | Lines | Coverage |
|-----------|-------|----------|
| `test_docker_sandbox.py` | 446 | Path validation (20+ cases), create/kill, port mapping |
| `test_port_manager.py` | 837 | Allocation, deallocation, range bounds |
| `test_orphan_cleanup.py` | 122 | Grace period, cleanup loop |
| `utils.test.ts` | ~100 | rewriteLocalhostUrl, isSandboxLink, isE2bLink |
| `agent-sandbox-status.test.ts` | ~80 | sandboxStatus reducer |

### 5.2 Missing Test Coverage

| Gap | Impact |
|-----|--------|
| No async lock contention test | Won't catch event loop blocking |
| No port exhaustion test | Error path untested |
| No scan_existing_containers integration test | Startup recovery untested |
| No end-to-end create→verify→kill test | Integration gaps |
| orphan_cleanup tests don't verify DB state | State sync untested |

---

## Part 6: Recommendations

### Before Merge (Mandatory)

1. **Fix exception hierarchy** — `SandboxException(IIAgentError)` (15 min)
2. **Add `docker>=7.0.0`** to `pyproject.toml` dependencies (5 min)
3. **Regenerate `pnpm-lock.yaml`** with vitest (5 min)
4. **Convert PortPoolManager to asyncio.Lock** (1-2 hr)

### Before Docker Sandbox is Production-Ready

5. **Add VNC services** to `e2b.Dockerfile` and `start-services.sh`
6. **Implement client host URL rewriting** for remote access
7. **Add `scan_existing_containers()` to lifespan startup**
8. **Implement `/auth/dev/login`** backend endpoint
9. **Add exception safety** to `kill()` cleanup
10. **Wire orphan cleanup through SandboxService**

### Future Improvements (Separate PRs)

11. Port browser tab limit (MAX_TABS=50)
12. Port shell session limit (MAX_SHELL_SESSIONS=10)
13. Port tool server local file serving
14. Port DALL-E 3 / Sora clients (if needed)
15. Port MCP tool image bridging
16. Move hardcoded port constants to SandboxSettings

---

## Appendix: File Classification Summary

| Classification | Count | Description |
|---------------|-------|-------------|
| ALREADY_HANDLED | ~12 | Ported to new locations |
| MAIN_REWROTE | ~55 | Old modules completely rewritten by main |
| SHOULD_CHECK | ~30 | Investigated — most are main-equivalent or nice-to-have |
| COSMETIC | ~6 | Typo fixes, debug logs, import fixes |
| MISSED | 7 | VNC packages, VNC startup, client_host, docker dep, lockfile, DALL-E 3, Sora |

Of the 7 MISSED items: 3 are Docker-blocking (VNC, client_host, docker dep), 2 are regressions (lockfile, dead DevLogin), 2 are separate features (DALL-E 3, Sora).
