# Three-Way Diff Analysis & Change Assessment

## Methodology
For each topic branch change, we assess:
1. **What changed** in the topic branch (from develop)
2. **What changed** in main (from develop) for the same area
3. **Whether the topic change still makes sense** given the new baseline

## Tier 0: Configuration & Constants (Foundation)

### TOKEN_BUDGET_EXTENDED = 800,000 (ii_agent_config.py / llm_config.py)
- **Topic**: Added `TOKEN_BUDGET_EXTENDED = 800_000` for Claude 4.5
- **Main**: `ii_agent_config.py` → `core/config/settings.py` — completely restructured with pydantic-settings
- **Assessment**: Check if main already has extended token budget. If not, add to `core/config/settings.py`
- **Verdict**: **NEEDS PORTING** — check if already addressed in main's config

### Default storage provider change (gcs → local)
- **Topic**: Changed default from `"gcs"` to `"local"` in storage config
- **Main**: `core/config/storage.py` already supports `local` but defaults to `"gcs"`
- **Assessment**: For local-only mode, this should be set in env vars, not hardcoded
- **Verdict**: **DROP** — main handles this correctly via env config

### Sandbox config additions (provider_type, docker_image, docker_network, etc.)
- **Topic**: Added multiple sandbox config options: `provider_type`, `docker_image`, `docker_network`, `local_mode`, `orphan_cleanup_*`, `backend_url`
- **Main**: `core/config/sandbox.py` already has `SandboxSettings` with pydantic-settings, supports `docker` provider enum
- **Assessment**: Port Docker-specific settings (docker_image, docker_network, port range) into existing `SandboxSettings`
- **Verdict**: **NEEDS PORTING** — extend `SandboxSettings` with Docker-specific fields

### expose_port() — external parameter
- **Topic**: Added `external` parameter to `expose_port()` method in sandbox base
- **Main**: `agents/sandboxes/base.py` does not have this parameter
- **Assessment**: This is needed for local Docker mode where port mapping differs
- **Verdict**: **NEEDS PORTING** — add to new base class  

## Tier 1: Infrastructure Components

### PortPoolManager (port_manager.py — 480 lines, NEW)
- **Topic**: Created `src/ii_sandbox_server/sandboxes/port_manager.py`
- **Main**: No equivalent exists. Port management not implemented.
- **Assessment**: Core infrastructure for Docker sandbox. Needs new location: `src/ii_agent/agents/sandboxes/port_manager.py`
- **Verdict**: **PORT DIRECTLY** — new file, no conflicts

### LocalStorage (backend side — storage/local.py)
- **Topic**: Created `src/ii_agent/storage/local.py` with path traversal protection, .meta sidecar files, URL download
- **Main**: Already has `src/ii_agent/core/storage/providers/local.py` with `LocalProvider` class  
- **Assessment**: Main's LocalProvider uses pathlib, topic branch uses os.path. Main's implementation is cleaner but may be missing some features (e.g., .meta sidecar, content-type tracking). Need to compare feature sets.
- **Verdict**: **MERGE/EXTEND** — preserve main's implementation, add any missing features

### LocalStorage (tool-server side — ii_tool/integrations/storage/local.py)
- **Topic**: Created `src/ii_tool/integrations/storage/local.py` — duplicate of backend local storage
- **Main**: `ii_tool` no longer exists; integrations absorbed into `ii_agent` domains
- **Assessment**: The tool-server storage is now handled by main's unified storage. This file is irrelevant.
- **Verdict**: **DROP** — main has unified storage

### Storage Factory (storage/factory.py)
- **Topic**: Modified to route to LocalStorage based on config
- **Main**: Storage factory is likely in `core/storage/` — already supports local routing
- **Assessment**: Main already handles local storage factory routing
- **Verdict**: **DROP** — main covers this

## Tier 2: Docker Sandbox Implementation

### DockerSandbox (docker.py — 974 lines, NEW)
- **Topic**: Created `src/ii_sandbox_server/sandboxes/docker.py` — full Docker container lifecycle
- **Main**: `agents/sandboxes/service.py` has `SandboxProviderType.DOCKER` enum but raises `SandboxCreationError("Unsupported provider: docker")`
- **Assessment**: Core feature. Must be ported to `src/ii_agent/agents/sandboxes/docker.py`, implementing the new `Sandbox` base class API from main
- **Verdict**: **NEEDS MAJOR REWORK** — rewrite to implement main's `Sandbox` ABC with Shell, LiveTerminal, and file explorer APIs

### sandbox_factory.py
- **Topic**: Created factory for e2b/docker sandbox creation
- **Main**: Factory logic is in `agents/sandboxes/service.py._create_provider()`. Just add Docker branch.
- **Assessment**: Add Docker provider creation to existing `_create_provider` and `_connect_provider`
- **Verdict**: **MERGE INTO service.py** — simple addition

## Tier 3: Orchestration

### Sandbox Controller Orphan Cleanup (~120 lines)
- **Topic**: Added to `src/ii_sandbox_server/lifecycle/sandbox_controller.py`
- **Main**: `ii_sandbox_server` no longer exists. Sandbox service is in `agents/sandboxes/service.py`
- **Assessment**: Port orphan cleanup as a method/background task in `SandboxService` or as a worker in `workers/cron/`
- **Verdict**: **NEEDS PORTING** — adapt to main's architecture, likely in workers/cron/

### client/client.py changes
- **Topic**: Modified sandbox client for Docker support
- **Main**: Client/server split removed — sandbox is in-process now
- **Assessment**: The client abstraction is gone. Docker sandbox is called directly.
- **Verdict**: **DROP** — architecture changed

## Tier 4: API/Integration Layer

### File upload endpoints (server/api/files.py)
- **Topic**: Added `PUT /files/upload/{path}`, `GET /files/{path}` with token auth
- **Main**: `files/router.py` handles file endpoints. Completely restructured.
- **Assessment**: Check if main's file router supports the upload/serve endpoints needed for local mode
- **Verdict**: **CHECK AND PORT** — may need to add local file serving endpoint

### Backend server/app.py changes
- **Topic**: Various startup modifications for local mode
- **Main**: `app/__init__.py`, `app/lifespan.py` — completely different
- **Assessment**: Local mode startup needs to be adapted to new app lifecycle
- **Verdict**: **NEEDS REWORK** — adapt to new lifespan hooks

### chat/context_manager.py, chat/service.py, chat/router.py changes
- **Topic**: Various fixes for chat in local mode
- **Main**: Complete restructure — `chat/application/chat_service.py`, `chat/api/router.py`
- **Assessment**: The specific fixes need to be evaluated against new code
- **Verdict**: **NEEDS INDIVIDUAL EVALUATION** in new codebase

### WebSocket handlers (socket/ → realtime/)
- **Topic**: Modified query_handler, awake_sandbox_handler, sandbox_status_handler, socketio
- **Main**: All renamed and restructured under `realtime/handlers/`
- **Assessment**: Changes need individual evaluation. The event system is completely different.
- **Verdict**: **NEEDS REWORK** — adapt changes to new event system

### LLM provider changes (llm/anthropic.py, llm/openai.py)
- **Topic**: Streaming timeout fixes, safety net improvements
- **Main**: `agents/models/anthropic/claude.py`, `agents/models/openai/completions.py` — rewritten
- **Assessment**: Check if streaming timeout issues exist in main's implementations
- **Verdict**: **CHECK AND PORT** — may already be fixed differently

### Sub-agent changes (sub_agent/ → agents/)
- **Topic**: Added interrupt events, task_agent_tool, design_document_agent modifications
- **Main**: Sub-agents restructured. `agents/factory/agent.py` builds sub-agents differently
- **Assessment**: Interrupt events may map to main's cancellation system
- **Verdict**: **NEEDS EVALUATION** — check if interrupts are handled by Redis cancel

## Tier 5: Frontend

### Frontend component changes
- **Topic**: Modified 16 frontend files for sandbox status, agent UI, websocket
- **Main**: Modified same 16 files with various refactors
- **Assessment**: Frontend mostly kept same paths. Need three-way merge for each file.
- **Verdict**: **NEEDS THREE-WAY MERGE** — file by file

### Frontend test files (NEW)
- **Topic**: Created `frontend/src/lib/__tests__/utils.test.ts` and `agent-sandbox-status.test.ts`
- **Main**: These specific test files don't exist in main
- **Assessment**: Tests are additive but may need updating for changed APIs
- **Verdict**: **PORT AND UPDATE** — update test imports/APIs

## Tier 6: Docker/Compose/Scripts

### docker-compose.local-only.yaml (NEW)
- **Topic**: Complete air-gapped compose file, 194 lines
- **Main**: Main has docker-compose.stack.yaml (updated) and docker-compose.dev.yaml (new)
- **Assessment**: Local-only compose needs updating for new service structure (no more sandbox-server/tool-server as separate services)
- **Verdict**: **NEEDS MAJOR REWORK** — adapt to main's compose structure

### docker-compose.local.yaml (NEW)
- **Topic**: Hybrid compose overlay
- **Main**: No equivalent
- **Assessment**: Same as above — needs adapting
- **Verdict**: **NEEDS REWORK** — adapt to main's structure

### stack_control.sh (NEW)
- **Topic**: Created comprehensive stack management script
- **Main**: `scripts/run_stack.sh` exists but is simpler
- **Assessment**: Standalone script, mostly portable. Update compose file references.
- **Verdict**: **PORT AND UPDATE** — update paths/references

### docker/backend/Dockerfile changes
- **Topic**: Modified for local mode build args
- **Main**: Modified for new package structure
- **Assessment**: Need three-way merge
- **Verdict**: **NEEDS THREE-WAY MERGE**

### e2b.Dockerfile changes
- **Topic**: Updated sandbox image
- **Main**: Also updated sandbox image
- **Assessment**: Three-way merge
- **Verdict**: **NEEDS THREE-WAY MERGE**

## Tier 7: Tests

### Comprehensive test suite (~80 files)
- **Topic**: Created under `tests/` — sandbox, storage, LLM, tool tests
- **Main**: Tests moved to `src/tests/` — completely different structure
- **Assessment**: All test files need relocation to `src/tests/unit/` and import path updates
- **Verdict**: **PORT ALL** — update paths, imports, and assertions for new APIs

## Tier 8: Documentation

### Existing topic branch docs
- architecture-local-to-cloud.md — Architecture evolution guide
- feature-branch-analysis.md — Feature specification
- local-docker-sandbox.md — User guide  
- **Assessment**: All documentation remains relevant. Update for new paths/structure.
- **Verdict**: **PORT AND UPDATE** — update all paths/references

## Summary: Change Categories

### Directly Portable (New files, no conflicts)
1. PortPoolManager → `agents/sandboxes/port_manager.py`
2. html_to_pdf.py (script)
3. stack_control.sh (with path updates)
4. admin_credits.sh (script)
5. Documentation files (with content updates)
6. docker/.stack.env.local.example (with updates)

### Needs Major Rework (Architecture changed)
1. DockerSandbox → rewrite for new Sandbox ABC
2. docker-compose.local-only.yaml → adapt for new compose structure
3. Orphan cleanup → move to workers/cron
4. Frontend changes → three-way merge each file

### Check and Port (May already be fixed in main)
1. Image compression → main has `compress_image_for_provider`
2. Streaming timeouts → check new LLM providers
3. Failed tool lookup handling → check new tool system
4. ThinkingBlock trailing fix → check new model response handling
5. WebSocket session priority → check new realtime system

### Drop (Superseded by main)
1. LocalStorage backend (main has LocalProvider)
2. LocalStorage tool-server (ii_tool doesn't exist)
3. Storage factory changes (main has unified storage)
4. Client/client.py changes (client/server split removed)
5. Default storage=local (use env vars instead)
6. ii_sandbox_server scaffolding (absorbed into ii_agent)
