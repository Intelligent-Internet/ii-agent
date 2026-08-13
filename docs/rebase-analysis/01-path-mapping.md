# Path Mapping: develop → origin/main (DDD Restructure)

## Package-Level Restructuring

### src/ii_agent/ (Backend - MASSIVE restructure in #851)

| Old Path (develop/topic) | New Path (origin/main) | Notes |
|---|---|---|
| `src/ii_agent/server/` | **REMOVED** - split into domain modules | Server monolith decomposed |
| `src/ii_agent/server/api/` | Domain-specific `api/router.py` per module | e.g., `chat/api/`, `files/router.py` |
| `src/ii_agent/server/app.py` | `src/ii_agent/app/` | App lifecycle extracted |
| `src/ii_agent/server/socket/` | `src/ii_agent/realtime/` | WebSocket/SocketIO handlers |
| `src/ii_agent/server/socket/command/query_handler.py` | `src/ii_agent/realtime/handlers/query.py` | |
| `src/ii_agent/server/socket/command/awake_sandbox_handler.py` | `src/ii_agent/realtime/handlers/awake_sandbox.py` | |
| `src/ii_agent/server/socket/command/sandbox_status_handler.py` | `src/ii_agent/realtime/handlers/sandbox_status.py` | |
| `src/ii_agent/server/socket/chat_session.py` | `src/ii_agent/realtime/chat_session.py` | |
| `src/ii_agent/server/socket/socketio.py` | `src/ii_agent/realtime/manager.py` | |
| `src/ii_agent/server/chat/` | `src/ii_agent/chat/` | Chat domain extracted |
| `src/ii_agent/server/chat/service.py` | `src/ii_agent/chat/application/chat_service.py` | |
| `src/ii_agent/server/chat/context_manager.py` | `src/ii_agent/chat/application/context_service.py` | |
| `src/ii_agent/server/chat/llm/anthropic/provider.py` | `src/ii_agent/chat/llm/anthropic/provider.py` | Similar path, different root |
| `src/ii_agent/server/chat/llm/openai.py` | `src/ii_agent/chat/llm/openai.py` | |
| `src/ii_agent/server/chat/router.py` | `src/ii_agent/chat/api/router.py` | |
| `src/ii_agent/server/chat/tools/file_search.py` | `src/ii_agent/chat/application/tool_service.py` | Likely merged |
| `src/ii_agent/server/api/files.py` | `src/ii_agent/files/router.py` | Files domain extracted |
| `src/ii_agent/server/api/auth.py` | `src/ii_agent/auth/` | Auth domain extracted |
| `src/ii_agent/server/api/sessions.py` | `src/ii_agent/sessions/` | Sessions domain extracted |
| `src/ii_agent/server/services/agent_service.py` | `src/ii_agent/agents/` (application layer) | Agent domain extracted |
| `src/ii_agent/server/services/file_service.py` | `src/ii_agent/files/service.py` | |
| `src/ii_agent/server/services/sandbox_service.py` | `src/ii_agent/agents/sandboxes/service.py` | |
| `src/ii_agent/server/llm_settings/` | `src/ii_agent/settings/llm/` | Settings domain |
| `src/ii_agent/server/llm_settings/models.py` | `src/ii_agent/settings/llm/models.py` | |
| `src/ii_agent/server/llm_settings/service.py` | `src/ii_agent/settings/llm/service.py` | |
| `src/ii_agent/server/messages/` | `src/ii_agent/agents/hooks/` | Hooks pattern |
| `src/ii_agent/server/models/messages.py` | Various domain schemas | Split per domain |
| `src/ii_agent/server/slides/` | `src/ii_agent/content/` | Content domain |
| `src/ii_agent/server/vectordb/` | **Needs investigation** | |
| `src/ii_agent/controller/` | `src/ii_agent/agents/` | Agent runtime |
| `src/ii_agent/controller/agent_controller.py` | `src/ii_agent/agents/agent.py` | Core agent loop |
| `src/ii_agent/controller/state.py` | `src/ii_agent/agents/` area | State mgmt |
| `src/ii_agent/controller/tool_manager.py` | `src/ii_agent/agents/factory/tool_manager.py` | |
| `src/ii_agent/adapters/` | **REMOVED** | Absorbed into domain modules |
| `src/ii_agent/adapters/sandbox_adapter.py` | `src/ii_agent/agents/sandboxes/` | |
| `src/ii_agent/llm/` | `src/ii_agent/agents/models/` | LLM providers |
| `src/ii_agent/llm/anthropic.py` | `src/ii_agent/agents/models/anthropic/claude.py` | |
| `src/ii_agent/llm/openai.py` | `src/ii_agent/agents/models/openai/completions.py` | |
| `src/ii_agent/prompts/` | `src/ii_agent/agents/prompts/` | |
| `src/ii_agent/prompts/agent_prompts.py` | `src/ii_agent/agents/prompts/agent_prompts.py` | |
| `src/ii_agent/prompts/system_prompt.py` | `src/ii_agent/agents/prompts/system_prompt.py` | |
| `src/ii_agent/sandbox/ii_sandbox.py` | `src/ii_agent/agents/sandboxes/` | |
| `src/ii_agent/storage/` | `src/ii_agent/core/storage/` | |
| `src/ii_agent/storage/base.py` | `src/ii_agent/core/storage/providers/base.py` | |
| `src/ii_agent/storage/factory.py` | `src/ii_agent/core/storage/` | |
| `src/ii_agent/storage/gcs.py` | `src/ii_agent/core/storage/providers/gcs.py` | |
| `src/ii_agent/storage/local.py` | `src/ii_agent/core/storage/providers/local.py` | **EXISTS in main!** |
| `src/ii_agent/sub_agent/` | `src/ii_agent/agents/` | Merged into agents |
| `src/ii_agent/core/config/ii_agent_config.py` | `src/ii_agent/core/config/settings.py` | Renamed |
| `src/ii_agent/core/config/llm_config.py` | `src/ii_agent/core/config/llm_config.py` | Same path |
| `src/ii_agent/core/event.py` | `src/ii_agent/realtime/events/` | Event system |
| `src/ii_agent/core/client_host.py` | **NEW - no equivalent** | Topic-branch-only |
| `src/ii_agent/db/manager.py` | `src/ii_agent/core/db/` | |
| `src/ii_agent/utils/constants.py` | `src/ii_agent/core/` area | |
| `src/ii_agent/cron/` | `src/ii_agent/workers/cron/` | |

### src/ii_tool/ → src/ii_server/ (Tool Server renamed)

| Old Path (develop/topic) | New Path (origin/main) | Notes |
|---|---|---|
| `src/ii_tool/` | `src/ii_server/` | Package renamed |
| `src/ii_tool/browser/` | `src/ii_server/browser/` ? OR `src/ii_agent/agents/tools/browser/` | Split |
| `src/ii_tool/integrations/` | Absorbed into `src/ii_agent/` domains | |
| `src/ii_tool/integrations/image_generation/` | `src/ii_agent/content/media/` | |
| `src/ii_tool/integrations/storage/` | `src/ii_agent/core/storage/` | |
| `src/ii_tool/integrations/video_generation/` | `src/ii_agent/content/media/` | |
| `src/ii_tool/interfaces/sandbox.py` | `src/ii_server/interfaces/sandbox.py` | |
| `src/ii_tool/tools/dev/register_port.py` | `src/ii_agent/agents/tools/sandbox/register_port.py` | |
| `src/ii_tool/tools/file_system/utils.py` | `src/ii_server/tools/` area | |
| `src/ii_tool/tools/mcp_tool.py` | `src/ii_server/mcp/` | |
| `src/ii_tool/tools/shell/shell_init.py` | `src/ii_server/tools/shell/` | |
| `src/ii_tool/utils.py` | `src/ii_server/utils.py` | |

### src/ii_sandbox_server/ → REMOVED (absorbed into ii_agent)

| Old Path (develop/topic) | New Path (origin/main) | Notes |
|---|---|---|
| `src/ii_sandbox_server/` | **REMOVED entirely** | Absorbed into `src/ii_agent/agents/sandboxes/` |
| `src/ii_sandbox_server/sandboxes/base.py` | `src/ii_agent/agents/sandboxes/base.py` | |
| `src/ii_sandbox_server/sandboxes/e2b.py` | `src/ii_agent/agents/sandboxes/e2b.py` | |
| `src/ii_sandbox_server/sandboxes/docker.py` | **DOES NOT EXIST in main** | Topic-branch-only |
| `src/ii_sandbox_server/sandboxes/port_manager.py` | **DOES NOT EXIST in main** | Topic-branch-only |
| `src/ii_sandbox_server/sandboxes/sandbox_factory.py` | **DOES NOT EXIST in main** | |
| `src/ii_sandbox_server/lifecycle/sandbox_controller.py` | `src/ii_agent/agents/sandboxes/service.py` | Likely merged |
| `src/ii_sandbox_server/client/client.py` | **Absorbed** | |
| `src/ii_sandbox_server/config.py` | `src/ii_agent/core/config/sandbox.py` | |
| `src/ii_sandbox_server/db/manager.py` | `src/ii_agent/core/db/` | |
| `src/ii_sandbox_server/main.py` | **No separate process** | Integrated |
| `src/ii_sandbox_server/models/payload.py` | `src/ii_agent/agents/sandboxes/models.py` | |

### Tests → src/tests/

| Old Path (develop/topic) | New Path (origin/main) | Notes |
|---|---|---|
| `tests/` | `src/tests/` | Moved into src |
| `tests/conftest.py` | `src/tests/conftest.py` | |
| `tests/sandbox/` | `src/tests/unit/engine/` (sandbox tests) | |
| `tests/storage/` | `src/tests/unit/` area | |
| `tests/llm/` | `src/tests/unit/` area | |
| `tests/test_ii_tool/` | `src/tests/unit/` area | |
| `tests/tools/` | `src/tests/unit/` area | |

### Docker/Config (mostly same paths)

| Old Path | New Path | Notes |
|---|---|---|
| `docker/docker-compose.stack.yaml` | Same | Modified in both |
| `docker/docker-compose.local-only.yaml` | **NEW** | Topic-branch-only |
| `docker/docker-compose.local.yaml` | **NEW** | Topic-branch-only |
| `docker/.stack.env.local.example` | `docker/.stack.env.example` | Main has different example |
| `docker/backend/Dockerfile` | Same | Modified in both |
| `scripts/run_stack.sh` | `scripts/run_stack.sh` | Topic branch deleted, replaced with stack_control.sh |
| `scripts/stack_control.sh` | **NEW** | Topic-branch-only |

## Key Observations

1. **Main has a LocalStorage provider already**: `src/ii_agent/core/storage/providers/local.py` exists in main
2. **Sandbox server absorbed**: The entire `ii_sandbox_server` package no longer exists separately
3. **Tool server renamed**: `ii_tool` → `ii_server`
4. **Shell/sandbox execution refactored** in #865 with new architecture
5. **DDD structure**: Domain-Driven Design with proper bounded contexts
6. **Tests relocated**: All tests now under `src/tests/`
