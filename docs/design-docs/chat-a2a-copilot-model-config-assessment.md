# Chat And Agent A2A Model Configuration Audit

**Status**: Verified code audit  
**Date**: 2026-04-15  
**Scope**: Chat mode + Agent mode, native and A2A inner loops

---

## Executive Summary

1. Chat mode has no inline model picker, but model selection is available through the settings drawer in both home and chat routes.
2. Chat native mode uses the selected model directly.
3. Chat A2A mode forwards the selected model in metadata, but the adapter does not consume it for any backend today.
4. Agent A2A mode has a compatibility warning path; chat A2A mode does not.
5. There is no compile-time validation for model/backend mismatch. Errors are runtime warnings/errors/events.
6. There is no best-match model resolver implemented for the 3 A2A backends.

---

## What Users Can Actually Configure In Chat Mode

### UI availability

- Chat route renders the settings drawer: [frontend/src/app/routes/chat.tsx](frontend/src/app/routes/chat.tsx#L741)
- Home route (including Chat mode) also renders the same settings drawer: [frontend/src/app/routes/home.tsx](frontend/src/app/routes/home.tsx#L362)
- The chat header settings button opens it: [frontend/src/components/chat-header.tsx](frontend/src/components/chat-header.tsx#L182)

### Why it may look like there is no chat model picker

- Inline model chip in the input is hidden on the dedicated chat route (`isChatRoute`): [frontend/src/components/question-input.tsx](frontend/src/components/question-input.tsx#L1201)
- In chat mode, tab switcher is hidden, but `ModelSetting` still renders by default (active tab is `model`): [frontend/src/components/agent-setting/index.tsx](frontend/src/components/agent-setting/index.tsx#L86), [frontend/src/components/agent-setting/index.tsx](frontend/src/components/agent-setting/index.tsx#L118)

### State behavior

- Model selection is global Redux state (`selectedModel`), shared by chat and agent flows: [frontend/src/state/slice/settings.ts](frontend/src/state/slice/settings.ts#L113)
- Initial model is auto-selected on login from available models: [frontend/src/contexts/auth-context.tsx](frontend/src/contexts/auth-context.tsx#L54)

---

## Chat Native Inner Loop Behavior

### Request and resolution flow

- Chat REST request requires `model_id`: [src/ii_agent/chat/api/schemas.py](src/ii_agent/chat/api/schemas.py#L53)
- Frontend sends `model_id` with each message: [frontend/src/hooks/use-chat-transport.tsx](frontend/src/hooks/use-chat-transport.tsx#L205)
- Backend validates model exists in available list before streaming: [src/ii_agent/chat/api/router.py](src/ii_agent/chat/api/router.py#L132)
- Chat service resolves full model config for the selected model: [src/ii_agent/chat/application/chat_service.py](src/ii_agent/chat/application/chat_service.py#L283)

### On incompatibility

- There is no compile-time check.
- If the selected model/provider combination fails at provider call time, the route emits runtime SSE `error` (`code: streaming_error`): [src/ii_agent/chat/api/router.py](src/ii_agent/chat/api/router.py#L412)

---

## Chat A2A Inner Loop Behavior

### Routing

- Chat A2A is enabled only when `AGENT_CHAT_INNER_LOOP_MODE=a2a`: [src/ii_agent/core/config/agent.py](src/ii_agent/core/config/agent.py#L89), [src/ii_agent/chat/api/dependencies.py](src/ii_agent/chat/api/dependencies.py#L151)

### Model forwarding status

- Chat A2A sets metadata model: [src/ii_agent/chat/application/a2a_turn_loop_service.py](src/ii_agent/chat/application/a2a_turn_loop_service.py#L218)
- Adapter reads `native_tool_schemas` and `system_message`, but not `model`: [src/ii_agent/integrations/a2a/adapter_server.py](src/ii_agent/integrations/a2a/adapter_server.py#L523)
- Therefore backend selection is environment-level (`AGENT_A2A_BACKEND`) and model steering is not applied per request.

### On incompatibility

- No explicit chat-side backend/model compatibility pre-check exists.
- Failure surfaces as runtime stream `session.error` from backend, translated to chat `error`: [src/ii_agent/chat/application/a2a_event_translator.py](src/ii_agent/chat/application/a2a_event_translator.py#L83)
- Fallback to native can happen on transport/circuit-breaker failures, not on semantic model mismatch detection: [src/ii_agent/chat/application/a2a_turn_loop_service.py](src/ii_agent/chat/application/a2a_turn_loop_service.py#L109)

---

## Agent A2A Inner Loop Behavior

### Routing and model config

- Agent queries include `model_id`: [src/ii_agent/realtime/schemas.py](src/ii_agent/realtime/schemas.py#L154)
- Session service resolves model config from selected model: [src/ii_agent/sessions/service.py](src/ii_agent/sessions/service.py#L545)
- Agent A2A also forwards model metadata: [src/ii_agent/agents/inner_loop.py](src/ii_agent/agents/inner_loop.py#L160)

### Compatibility check

- Agent factory runs `check_model_backend_compat(...)` and logs warning only: [src/ii_agent/agents/factory/agent.py](src/ii_agent/agents/factory/agent.py#L244)
- Compatibility policy is prefix-based in one file: [src/ii_agent/integrations/a2a/backend_compat.py](src/ii_agent/integrations/a2a/backend_compat.py#L29)

### On incompatibility

- Not compile-time.
- Not hard-blocking at setup.
- Warning at runtime, then backend may still fail and emit runtime errors/fallback.

---

## Backend Compatibility Matrix (Current, Implemented)

The implemented matcher is prefix allow-list only and currently used by agent mode warnings.

| A2A backend | Implemented accepted model prefixes | Effective behavior today |
|---|---|---|
| `copilot` | no restriction (`()`) | Any model id passes compatibility check; Copilot chooses model unless backend config sets one |
| `claude-code` | `claude-` | Non-claude ids are marked incompatible (warning in agent only) |
| `codex` | `o4-`, `o3-`, `o1-`, `gpt-` | Other prefixes are marked incompatible (warning in agent only) |

Source: [src/ii_agent/integrations/a2a/backend_compat.py](src/ii_agent/integrations/a2a/backend_compat.py#L29)

---

## Model Family Mapping Against Frontend Configurable Models

Frontend provider presets include Anthropic (`claude-*`), OpenAI (`gpt-*`, `o3*`, `o4*`), Google (`gemini-*`), and Custom: [frontend/src/constants/models.tsx](frontend/src/constants/models.tsx#L24)

Best-match resolver is not implemented, so mapping below is compatibility-only:

| Model family | Copilot backend | Claude Code backend | Codex backend |
|---|---|---|---|
| `claude-*` | compatible by policy | compatible | incompatible by policy |
| `gpt-*` | compatible by policy | incompatible by policy | compatible |
| `o4-*` | compatible by policy | incompatible by policy | compatible |
| `o3-*` | compatible by policy | incompatible by policy | compatible |
| `o1-*` | compatible by policy | incompatible by policy | compatible |
| `gemini-*` | compatible by policy | incompatible by policy | incompatible by policy |
| `custom`/other | compatible by policy | incompatible by policy unless starts `claude-` | incompatible by policy unless starts `gpt-`/`o4-`/`o3-`/`o1-` |

Important: this is not "best matching". It is only prefix compatibility.

---

## Compile-Time vs Runtime Error Behavior

### Compile-time

- No compile-time error exists for model/backend mismatch.

### Startup-time (configuration)

- Adapter startup hard-fails only for missing backend-required API keys when backend is `claude-code` or `codex`: [src/ii_agent/integrations/a2a/adapter_server.py](src/ii_agent/integrations/a2a/adapter_server.py#L900)

### Runtime

- Agent A2A: warning on mismatch, then runtime behavior depends on backend response.
- Chat A2A: no mismatch warning gate; backend runtime `session.error` translated to chat `error`.
- Chat native: provider/runtime errors become SSE `error` with `streaming_error`.

---

## Verified Scope Conclusion

1. The model/backend mismatch problem is not chat-only or agent-only.
2. Chat and agent both carry `model` into A2A metadata, but adapter/backends do not currently apply request-level model steering.
3. Compatibility validation is inconsistent (agent warning exists, chat warning does not).
4. Best-match mapping across `copilot`, `claude-code`, and `codex` is not implemented today.

