# Baseline Changes Analysis: develop → origin/main

## Executive Summary

153 commits, 2,500 files changed, +501,149/-75,606 lines.
This represents a **massive architectural overhaul** from a monolithic server design to a Domain-Driven Design (DDD) structure.

## Major Architectural Changes

### 1. DDD Restructure (#851) — 1,483 files changed
The single largest commit. Completely reorganized `src/ii_agent/` from a monolithic `server/` package into bounded domain contexts:

**Old (develop):**
```
src/ii_agent/
├── server/           # Monolithic server
│   ├── api/          # All HTTP endpoints
│   ├── chat/         # Chat service 
│   ├── socket/       # WebSocket handlers
│   ├── services/     # Business logic
│   ├── models/       # Data models
│   └── slides/       # Slide processing
├── controller/       # Agent controller
├── llm/              # LLM providers
├── prompts/          # System prompts
├── storage/          # Storage backends
├── sandbox/          # Sandbox abstraction
├── sub_agent/        # Sub-agent tools
└── adapters/         # Adapter layer
```

**New (main):**
```
src/ii_agent/
├── agents/           # Agent runtime (replaces controller/, llm/, prompts/, sub_agent/, adapters/)
│   ├── models/       # LLM providers (replaces llm/)
│   ├── prompts/      # System prompts
│   ├── sandboxes/    # Sandbox management (replaces sandbox/, sandbox_server)
│   ├── tools/        # Agent-side tools
│   ├── factory/      # Agent/tool creation
│   ├── hooks/        # Agent hooks (replaces messages/)
│   ├── skills/       # Agent skills
│   └── sessions/     # Session management
├── app/              # FastAPI app lifecycle (replaces server/app.py)
├── auth/             # Authentication domain (replaces server/api/auth.py)
├── billing/          # Billing domain 
├── chat/             # Chat domain (replaces server/chat/)
│   ├── api/          # Chat HTTP endpoints
│   ├── application/  # Chat business logic
│   └── llm/          # Chat LLM providers
├── content/          # Content domain (replaces server/slides/)
│   └── media/        # Media generation (replaces ii_tool/integrations/)
├── core/             # Shared infrastructure
│   ├── config/       # All configuration (settings.py replaces ii_agent_config.py)
│   ├── db/           # Database (replaces db/)
│   ├── storage/      # Storage providers (replaces storage/)
│   │   └── providers/  # gcs.py, local.py, minio.py
│   └── secrets/      # Secret management
├── credits/          # Credits domain
├── files/            # File management domain (replaces server/api/files.py)
├── integrations/     # External integrations
├── projects/         # Projects domain
├── realtime/         # WebSocket/SocketIO (replaces server/socket/)
│   ├── handlers/     # Socket command handlers
│   └── events/       # Event system
├── sessions/         # Sessions domain (replaces server/api/sessions.py)
├── settings/         # Settings domain (replaces server/llm_settings/)
│   ├── llm/          # LLM settings
│   └── mcp/          # MCP settings
├── tasks/            # Background tasks
├── users/            # User domain
└── workers/          # Background workers (replaces cron/)
```

### 2. Package Renames
- `src/ii_tool/` → `src/ii_server/` (tool server renamed)
- `src/ii_sandbox_server/` → **REMOVED** (absorbed into `src/ii_agent/agents/sandboxes/`)
- `tests/` → `src/tests/` (tests moved into src)

### 3. Shell and Sandbox Execution Refactor (#865)
- New `src/ii_agent/agents/sandboxes/shell.py` — shell abstraction
- E2B-specific shell: `e2b_shell.py`
- Live terminal service: `live_terminal_service.py`
- Sandbox router: `router.py`
- Shell tools restructured: `src/ii_agent/agents/tools/shell/`

### 4. Workspace Manager Removal (#825)
- `workspace_manager.py` completely removed
- Connector tools restructured

### 5. A2A and MCP SSE Removal (#842)
- Agent-to-Agent protocol removed
- MCP SSE transport removed
- Simplification of integration layer

### 6. Dev Tool → Skill Migration (#848)
- Development tools migrated from imperative tools to declarative skills
- `ii-app` skill created under `settings/skills/builtin/ii-app/`
- Template processor for project scaffolding

### 7. Pricing/UUID Consolidation (#862)
- `uuid.UUID` types enforced across all API contracts
- Pricing consolidated into billing domain
- Chat API contracts refactored

### 8. Media Path Refactor (#860)
- Media generation moved to `content/media/`
- Unified file asset handling

### 9. Code Viewer with Watcher (#855)
- File tree, code viewer components added
- Sandbox file explorer capability

## Features Already Present in Main That Topic Branch Also Implemented

| Feature | Main Implementation | Topic Branch Implementation | Status |
|---|---|---|---|
| **Local Storage Provider** | `core/storage/providers/local.py` | `storage/local.py` + `ii_tool/integrations/storage/local.py` | **MAIN HAS IT** |
| **Storage Config with local** | `core/config/storage.py` (supports gcs/local/minio) | Modified `storage/` and config | **MAIN HAS IT** |
| **Docker enum in SandboxProviderType** | `agents/sandboxes/types.py` has `DOCKER = "docker"` | Added to sandbox factory | **MAIN HAS IT (enum only)** |
| **Sandbox Settings with docker** | `core/config/sandbox.py` has `docker` in Literal | Added docker config | **MAIN HAS IT (config only)** |
| **Sandbox Service with Docker reference** | `agents/sandboxes/service.py` references Docker | Built docker factory | **MAIN STUBS IT** |

## Features NOT in Main That Topic Branch Provides

| Feature | Description | Required Integration Point |
|---|---|---|
| **DockerSandbox Implementation** | Full Docker container lifecycle (974 lines) | `src/ii_agent/agents/sandboxes/docker.py` |
| **PortPoolManager** | Port 30000-30999 allocation for Docker containers | New file in `agents/sandboxes/` |
| **Orphan Container Cleanup** | Background cleanup loop for abandoned containers | Extend `agents/sandboxes/service.py` |
| **docker-compose.local-only.yaml** | Air-gapped Docker Compose stack | `docker/` |
| **docker-compose.local.yaml** | Hybrid compose file | `docker/` |
| **stack_control.sh** | Stack management script | `scripts/` |
| **Tool Execution Timeouts** | Timeout enforcement for tool calls | Agent runtime |
| **Mid-Tool Interruption** | Cancel running tools mid-execution | Agent runtime |
| **Agent-Human-Agent Handoff** | noVNC browser handoff mechanism | Agent + realtime |
| **Dynamic Token Budget** | Extended token budget for Claude 4.5 | Config/constants |
| **Various Bug Fixes** | WebSocket, image handling, slides, etc. | Various domains |
| **Comprehensive Test Suite** | 80+ test files | `src/tests/` |
| **Documentation** | Architecture, feature analysis, user guide | `docs/` |
