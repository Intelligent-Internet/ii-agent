---
id: getting-started
title: Docker Stack Environment
sidebar_label: Getting Started
sidebar_position: 2
description: Bring up the II-Agent Docker stack, configure the correct env file for your mode, and understand required services.
---

# Docker Stack Environment Setup

Use this runbook whenever you need to spin up the full II-Agent Docker stack (Postgres, Redis, backend, sandbox server, tool server, frontend, and ngrok).

Environment file naming by mode:

- Full stack mode (`docker-compose.stack.yaml`): use `docker/.stack.env`.
- Local Docker sandbox mode (`docker-compose.local.yaml`): use `docker/.stack.env.local`.

## Before you start

- Docker Desktop or Docker Engine with Compose v2 (Linux containers enabled).
- Node.js 18+ and Python 3.10+ (only required when running services outside Docker).
- API access for at least one LLM provider (OpenAI-compatible, Anthropic, Gemini, etc.).
- Google Cloud service-account JSON if you plan to store assets on GCS or call Vertex AI.

## Quick start

1. Copy the sample file:
   ```bash
   cp docker/.stack.env.example docker/.stack.env
   ```
2. Fill every placeholder marked `replace-me` or `replace-with-your-token`. Use the [Required Environment Variables](./required-environment-variables/index.md) guide as you go; optional integrations live in [Optional Environment Variables](./optional-environment-variables/index.md).
3. Launch the stack:
   ```bash
   ./scripts/run_stack.sh --build
   ```
   - The helper script checks for `.stack.env` and runs `docker compose -f docker/docker-compose.stack.yaml --env-file docker/.stack.env up`.
   - Drop the `--build` flag after the first boot to reuse images.
   - Stop the stack with `docker compose -f docker/docker-compose.stack.yaml down`.

> **Local-only mode (no cloud services):** If you don't need E2B, ngrok, or GCS you can run entirely with Docker sandboxes. See the [Local Docker Sandbox](./local-docker-sandbox.md) guide and use `docker-compose.local.yaml` instead.

For local-only mode, do not reuse `docker/.stack.env` as your main config file. Use `docker/.stack.env.local`.

### Migration from previous local env files

If your existing `.stack.env.local` references the old storage variables, update them:

| Old variable | New variable | Notes |
| --- | --- | --- |
| `STORAGE_PROVIDER=local` | `STORAGE_PROVIDER=minio` | The `local` filesystem provider has been removed. Use MinIO for local deployments. |
| `LOCAL_STORAGE_URL_BASE` | *(remove)* | No longer used. |
| `LOCAL_STORAGE_INTERNAL_URL_BASE` | *(remove)* | No longer used. |
| `STORAGE_LOCAL_SERVE_URL` | `STORAGE_SERVE_BASE_URL` | Set to the browser-reachable backend URL (e.g. `http://192.168.2.2:8000`). When set, storage URLs route through the backend proxy instead of directly to MinIO. |

## Required variables overview

| Section | Key variables | Why they matter |
| --- | --- | --- |
| Frontend build | `FRONTEND_BUILD_MODE`, `VITE_API_URL`, `VITE_GOOGLE_CLIENT_ID`, `VITE_STRIPE_PUBLISHABLE_KEY`, `VITE_SENTRY_DSN`, `VITE_DISABLE_CHAT_MODE` | Control how II-Agent's UI is compiled and which backend endpoint it targets. |
| Networking / tunnels | `NGROK_AUTHTOKEN`, `NGROK_REGION`| Expose the stack over HTTPS for remote demos or callback URLs. |
| Host paths | `GOOGLE_APPLICATION_CREDENTIALS` | Mount a GCP service-account JSON into containers. |
| LLM + auth | `LLM_CONFIGS`, `RESEARCHER_AGENT_CONFIG`, `GOOGLE_CLIENT_ID`, `GOOGLE_REDIRECT_URI`, `ACCESS_TOKEN_EXPIRE_MINUTES`, `ENHANCE_PROMPT_OPENAI_API_KEY` | Give II-Agent access to models and configure OAuth/JWT behavior. |
| Storage | `SLIDE_ASSETS_PROJECT_ID`, `SLIDE_ASSETS_BUCKET_NAME`, `FILE_UPLOAD_*`, `AVATAR_*`, `CUSTOM_DOMAIN` | Buckets that persist agent-generated assets. |
| Backend sandbox | `SANDBOX_TEMPLATE_ID`, `TIME_TIL_CLEAN_UP` | Define how on-demand sandboxes are provisioned and reclaimed. |
| Tool server | `STORAGE_CONFIG__GCS_*` | Buckets used by the tool server baseline. |
| Sandbox server | `E2B_API_KEY`, `E2B_TEMPLATE_ID` | Credentials for the hosted sandbox provider (not needed for local-only Docker mode). |
| Core infra | `POSTGRES_*`, `DATABASE_URL`, `SANDBOX_DB_*`, `REDIS_PORT`, `BACKEND_PORT`, `FRONTEND_PORT`, `SANDBOX_SERVER_PORT`, `TOOL_SERVER_PORT`, `NGROK_METRICS_PORT`, `MCP_PORT` | Databases and host port mappings that every service relies on. |

The required guide links to the detailed setup pages for each section (frontend env, tunnels, host paths, etc.). Keep it open while editing the env file for your selected mode (`docker/.stack.env` or `docker/.stack.env.local`).

## Optional feature sets

Some integrations sit behind extra credentials. Configure them after the base agent runs cleanly:

- Payments and billing.
- Media (image/video) generation.
- Search providers (web, image, visit-level browsing).
- Tool-server specific LLM overrides.
- Database automation (Neon).

## Boot validation

1. Run `./scripts/run_stack.sh --build` and confirm all containers are healthy.
2. Visit `http://localhost:<FRONTEND_PORT>` and send a request through II-Agent.
3. Check `docker compose logs -f` for missing variable errors or failing services.
4. When ready to expose the stack, ensure ngrok connected successfully (`http://localhost:<NGROK_METRICS_PORT>`).

With the stack online, you can iterate on II-Agent flows, add tools, and capture Proof-of-Benefit evidence from real executions.

## Expected local warnings

During local development and unit test runs, these warning classes are expected unless you are specifically testing those integrations:

- `COMPOSIO_API_KEY is not set`: expected when Composio connector features are not configured.
- Pydantic v2 deprecation warnings (`class-based config`, `json_encoders`): expected from current dependency/code usage; non-blocking for now.
- Passlib `crypt` deprecation warning: expected on current Python; relevant for future Python-version migration planning.
- Intentionally logged exception traces from resilience tests (for example orphan-cleanup fault-injection): expected in those test cases when assertions still pass.

Treat these as informational in local runs unless they appear alongside test failures or service startup errors.

## Inner loop mode (client guide)

II-Agent supports two top-level execution modes for agent turns:

- `native` (default): Uses II-Agent's built-in execution path with direct LLM API calls.
- `a2a`: Delegates eligible work to an A2A adapter server. The adapter runs one of three backends — `copilot`, `claude-code`, or `codex` — selectable via `AGENT_A2A_BACKEND`.

### Available A2A backends

| Backend | Env var value | Required credentials | Supported models |
| --- | --- | --- | --- |
| **Copilot CLI** | `copilot` (default) | `GITHUB_TOKEN` or `GH_TOKEN` (optional — falls back to `gh auth` login) | Any (Copilot routes BYOK) |
| **Claude Code CLI** | `claude-code` | `ANTHROPIC_API_KEY` | `claude-*` models only |
| **Codex CLI** | `codex` | `OPENAI_API_KEY` | `o4-*`, `o3-*`, `o1-*`, `gpt-*` models |

The adapter server validates credentials at startup. If `AGENT_A2A_BACKEND=claude-code` and `ANTHROPIC_API_KEY` is absent, the adapter will refuse to start.

When `AGENT_INNER_LOOP_MODE=a2a`, the backend service also logs a warning if the configured LLM model is incompatible with the selected backend (for example, sending a `claude-*` model to the `codex` backend).

### Recommended starting point

Start with `native`, then enable `a2a` only when you want to validate delegated code-first workflows.

### Relationship to local vs cloud mode

Inner-loop mode and deployment mode are orthogonal:

- Deployment mode selects where sandboxes run (`local` Docker or cloud/E2B).
- Inner-loop mode selects how agent turns are executed (`native` or `a2a`).

From a user perspective, there is only one direct dependency:

- If you choose `a2a`, `AGENT_A2A_AGENT_URL` must point to a reachable adapter endpoint in your selected environment.

This means you can use:

- `native` with local sandboxes.
- `native` with cloud sandboxes.
- `a2a` with local sandboxes (if adapter is running and reachable).
- `a2a` with cloud sandboxes (if adapter is deployed and reachable).

### Simple configuration example

Add these environment variables to your backend environment file (`.env`, `docker/.stack.env`, or `docker/.stack.env.local`, depending on your setup):

```bash
AGENT_INNER_LOOP_MODE=native
AGENT_A2A_BACKEND=copilot
AGENT_A2A_AGENT_URL=http://localhost:18100
AGENT_A2A_TIMEOUT_SECONDS=30
AGENT_A2A_FALLBACK_TO_NATIVE=true
AGENT_A2A_CONTEXT_REUSE=true
```

To test delegated mode, switch only this value:

```bash
AGENT_INNER_LOOP_MODE=a2a
```

For local kick-the-tires testing, run the A2A adapter in a separate terminal.  Choose the backend that matches your credentials:

```bash
# Copilot backend (default — uses 'gh auth' login or GITHUB_TOKEN):
uv run python -m ii_agent.integrations.a2a.adapter_server --host 0.0.0.0 --port 18100 --backend copilot

# Claude Code backend (requires ANTHROPIC_API_KEY):
ANTHROPIC_API_KEY=sk-ant-... uv run python -m ii_agent.integrations.a2a.adapter_server --host 0.0.0.0 --port 18100 --backend claude-code

# Codex backend (requires OPENAI_API_KEY):
OPENAI_API_KEY=sk-... uv run python -m ii_agent.integrations.a2a.adapter_server --host 0.0.0.0 --port 18100 --backend codex
```

Then restart the backend so it picks up:

- `AGENT_INNER_LOOP_MODE=a2a`
- `AGENT_A2A_AGENT_URL=http://localhost:18100`

With this setup, frontend requests can exercise the delegated inner-loop path end-to-end.

### Pros and cons for end clients

When using `a2a`:

- Pros:
   - Can be materially lower cost when routed through Copilot-backed inference instead of direct provider API-key usage.
   - Better fit for code-heavy delegated flows.
   - Clear path to multi-agent interoperability over A2A.
   - Keeps Copilot-adapter concerns separated from core II-Agent runtime.
- Cons:
   - Extra network/process hop can add latency.
   - Requires adapter availability and health management.
   - Operationally more moving parts than the default mode.

When staying on `native`:

- Pros:
   - Simplest operations and lowest setup complexity.
   - Strong compatibility with existing II-Agent features.
   - Fewer external dependencies during local development.
- Cons:
   - Usually higher model-inference cost when relying only on direct provider API keys.
   - Less exposure to A2A interoperability patterns.
   - Does not exercise delegated adapter behavior.

Cost note:

- The largest savings typically come from Copilot-routed delegated usage.
- If delegated mode is configured in BYOK passthrough style, billing follows your provider plan and savings may differ.

### Important routing behavior

Even when `AGENT_INNER_LOOP_MODE=a2a`, II-Agent keeps native routing for request classes that are platform-specific or policy-sensitive.

These remain native-owned by design:

- Slides workflows.
- Storybook generation workflows.
- Media generation workflows (image/video).
- Connector-backed operations (for example GitHub/Composio flows).
- Planning and milestone workflows.
- Dev infrastructure actions (environment/bootstrap/restart/port orchestration).
- Safety, policy, compliance, or capability exceptions.

This means enabling `a2a` does not remove native capabilities. It changes routing for eligible requests while preserving the default path where it is required.
