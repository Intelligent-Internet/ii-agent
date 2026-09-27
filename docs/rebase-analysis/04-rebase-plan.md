# Detailed Rebase Plan: feat/local-docker-sandbox onto origin/main

## Strategy: Manual Cherry-Pick Rebase

Instead of `git rebase`, we will:
1. Create a new branch `rebase/local-docker-sandbox` from `origin/main`
2. Manually port changes from the topic branch, adapted to the new architecture
3. Commit in logical groups (leaf-to-root dependency tiers)
4. Validate each commit builds and tests pass

## Pre-Rebase Checklist

- [x] Topic branch squashed to single commit (b93a325)
- [x] Path mapping documented (01-path-mapping.md)
- [x] Baseline changes documented (02-baseline-changes.md)
- [x] Three-way assessment completed (03-three-way-assessment.md)
- [ ] New branch created from origin/main
- [ ] Rebase commits executed

---

## Commit Plan (7 Commits, Leaf-to-Root)

### Commit 1: Configuration & Constants
**Files to create/modify:**
- `src/ii_agent/core/config/sandbox.py` — Add Docker-specific settings:
  - `docker_image: str = "ii-agent-sandbox:latest"`
  - `docker_network: str = "ii-agent-local_ii-network"`
  - `port_range_start: int = 30000`
  - `port_range_end: int = 30999`
  - `orphan_cleanup_enabled: bool = True`
  - `orphan_cleanup_interval_seconds: int = 60`
  - `backend_url: str = "http://backend:8000"`
  - `local_mode: bool = False`

**Status:** NEW WORK — extend existing pydantic-settings class

### Commit 2: Port Pool Manager (Infrastructure)
**Files to create:**
- `src/ii_agent/agents/sandboxes/port_manager.py` — Port from topic branch
  - Update imports from `ii_sandbox_server` → `ii_agent.agents.sandboxes`
  - Update config access to use `Settings.sandbox.*` instead of env vars directly
  - Keep core logic intact (thread-safe allocation, startup scanning, background cleanup)

**Tests to create:**
- `src/tests/unit/agent/test_port_manager.py` — Port from `tests/sandbox/test_port_manager.py`
  - Update imports
  - Update class references

**Status:** MOSTLY PORTABLE — import/config updates only

### Commit 3: Docker Sandbox Provider (Core Feature)
**Files to create:**
- `src/ii_agent/agents/sandboxes/docker.py` — **MAJOR REWORK** required
  - Must implement main's `Sandbox` ABC (from `agents/sandboxes/base.py`)
  - Required methods: `get_info()`, `get_status()`, `get_provider_id()`, `upload_path`,
    `create()`, `run_command()`, `upload()`, `download()`, `expose_port()`, `kill()`,
    `get_file_tree()`, `get_file_content()`, `write_file()`, `delete_file()`
  - Must support main's `Shell` abstraction (`agents/sandboxes/shell.py`)
  - Must support `LiveTerminalHandle` for terminal streaming
  - Must integrate with `PortPoolManager` for port allocation
  - Class: `DockerSandbox(Sandbox)` with `PROVIDER = SandboxProviderType.DOCKER`
  
**Files to modify:**
- `src/ii_agent/agents/sandboxes/service.py` — Add Docker to `_create_provider()` and `_connect_provider()`
  - Add: `from ii_agent.agents.sandboxes.docker import DockerSandbox`
  - Add Docker case in `_create_provider()`: Return `DockerSandbox.create(...)`
  - Add Docker case in `_connect_provider()`: Return `DockerSandbox.connect(...)`

**Tests to create:**
- `src/tests/unit/agent/test_docker_sandbox.py` — Rewrite from `tests/sandbox/test_docker_sandbox.py`
- `src/tests/unit/agent/test_sandbox_factory.py` — Rewrite from `tests/sandbox/test_sandbox_factory.py`

**Status:** MAJOR REWORK — new base class API, shell/terminal integration

### Commit 4: Orphan Cleanup & Lifecycle (Orchestration)
**Files to create/modify:**
- `src/ii_agent/workers/cron/jobs/orphan_cleanup.py` — New file
  - Port orphan cleanup logic from `ii_sandbox_server/lifecycle/sandbox_controller.py`
  - Use `SandboxService` and `SandboxRepository` instead of direct DB queries
  - Register as a cron job in main's worker system

- OR integrate into `src/ii_agent/agents/sandboxes/service.py` as:
  - `async def cleanup_orphan_sandboxes(self, grace_period_seconds: int = 300) -> int`
  - Background task started in app lifespan

**Tests:**
- `src/tests/unit/agent/test_orphan_cleanup.py`

**Status:** MODERATE REWORK — use main's DB/service patterns

### Commit 5: Docker Compose & Deployment Scripts
**Files to create:**
- `docker/docker-compose.local.yaml` — Docker Compose overlay for local Docker sandbox mode
  - Adapt from topic branch's local-only.yaml
  - **Critical:** No separate sandbox-server or tool-server services (absorbed into backend)
  - Add minio service (main uses minio for local storage instead of filesystem)
  - Keep: postgres, redis, frontend, backend services
  - Ensure backend has Docker socket mount for spawning sandbox containers
  - Add sandbox Docker network configuration

- `docker/.stack.env.local.example` — Local mode env example
  - Update for new env var names (SANDBOX_PROVIDER, STORAGE_PROVIDER, etc.)
  
- `scripts/stack_control.sh` — Port with updates
  - Update compose file references
  - Update service names for new architecture

**Files to modify:**
- `docker/docker-compose.stack.yaml` — Add Docker socket mount option for backend
  - Add conditional volume mount for `/var/run/docker.sock`

**Status:** MODERATE REWORK — new compose structure, no separate sandbox-server

### Commit 6: Frontend Changes (Three-Way Merge)
**Files to evaluate and selectively port:**
- `frontend/src/typings/agent.ts` — Check if `'stopped'` maps to `CANCELLED` or `SYSTEM_INTERRUPTED` in main
- `frontend/src/state/slice/agent.ts` — Sandbox status tracking changes
- `frontend/src/contexts/websocket-context.tsx` — Session priority changes
- `frontend/src/hooks/use-app-events.tsx` — Event handler updates  
- `frontend/src/hooks/use-session-manager.tsx` — Session management
- `frontend/src/components/agent/agent-result.tsx` — Result display
- `frontend/src/components/agent/subagent-container.tsx` — Subagent UI
- `frontend/src/app/routes/agent.tsx` — Route changes

**For each file:**
1. Read main's version
2. Read topic branch's version  
3. Identify topic-branch-only functional changes
4. Apply only those changes to main's version
5. Skip cosmetic/structural changes that conflict with main's refactoring

**New tests to port:**
- `frontend/src/lib/__tests__/utils.test.ts`
- `frontend/src/state/__tests__/agent-sandbox-status.test.ts` — update for new types

**Status:** CAREFUL THREE-WAY MERGE — per-file evaluation needed

### Commit 7: Documentation & Remaining Files
**Files to create/update:**
- `docs/docs/architecture-local-to-cloud.md` — Update all paths for new structure
- `docs/docs/local-docker-sandbox.md` — Update for new compose, env vars, paths
- `docs/docs/feature-branch-analysis.md` — Update with new architecture mapping
- `scripts/html_to_pdf.py` — Port directly (standalone script)
- `scripts/admin_credits.sh` — Port directly (standalone script)
- `.github/copilot-instructions.md` — Port directly

**Status:** MOSTLY PORTABLE — content updates for new paths

---

## Changes to DROP (Superseded by Main)

| Change | Reason |
|---|---|
| `src/ii_agent/storage/local.py` | Main has `core/storage/providers/local.py` |
| `src/ii_agent/storage/factory.py` mods | Main has unified storage factory |
| `src/ii_agent/storage/base.py` mods | Main has `core/storage/providers/base.py` |
| `src/ii_agent/storage/gcs.py` mods | Main has `core/storage/providers/gcs.py` |
| `src/ii_agent/storage/__init__.py` mods | Main has `core/storage/__init__.py` |
| `src/ii_tool/integrations/storage/*` | `ii_tool` no longer exists |
| `src/ii_tool/integrations/image_generation/*` | Moved to `content/media/` |
| `src/ii_tool/integrations/video_generation/*` | Moved to `content/media/` |
| `src/ii_sandbox_server/*` (scaffolding) | Absorbed into `ii_agent/agents/sandboxes/` |
| `src/ii_agent/server/*` modifications | Server monolith decomposed into domains |
| Image compression in agent_controller | Main has `compress_image_for_provider` |
| `requests` → `httpx` migration | Main already uses httpx |
| Default storage=local | Use env vars |
| `client/client.py` changes | No more client/server split |
| `scripts/run_stack.sh` replacement | Bring stack_control.sh alongside, don't delete run_stack.sh |

## Changes to VERIFY Before Porting

| Change | Check | 
|---|---|
| ThinkingBlock trailing fix | Does main's `agents/agent.py` handle this? |
| Failed tool lookup handling | Does main's tool system handle missing tools? |
| WebSocket session priority | Does main's realtime system handle priority? |
| Streaming timeout fixes | Does main's anthropic provider have timeouts? |
| Subagent interrupt events | Does main's cancellation cover this? |

---

## Execution Order

1. **Create branch** `rebase/local-docker-sandbox` from `origin/main`
2. **Commit 1**: Config changes (smallest, foundation)
3. **Commit 2**: Port manager (leaf dependency, self-contained)
4. **Commit 3**: Docker sandbox (depends on 1 & 2)
5. **Commit 4**: Orphan cleanup (depends on 3)
6. **Commit 5**: Compose & scripts (depends on 1-4)
7. **Commit 6**: Frontend (can be parallel with 5, done after for testing)
8. **Commit 7**: Documentation (last, references everything)

## Validation After Each Commit

1. `python -c "import ii_agent"` — basic import check
2. `pytest src/tests/ -x --tb=short` — run existing tests
3. `pytest src/tests/unit/agent/test_port_manager.py` (after commit 2)
4. `pytest src/tests/unit/agent/test_docker_sandbox.py` (after commit 3)
5. Full test suite after commit 7

## Risk Assessment

| Risk | Severity | Mitigation |
|---|---|---|
| Docker sandbox doesn't implement full Sandbox ABC | HIGH | Implement all abstract methods, stub if needed |
| Shell abstraction incompatible with Docker exec | MEDIUM | Implement DockerShell similar to E2BShell |
| Compose file doesn't match new service structure | MEDIUM | Test with `docker compose config` |
| Frontend event changes break UI | LOW | Test manually after merge |
| Test import paths broken | LOW | Systematic find-and-replace |
