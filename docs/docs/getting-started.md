---
id: getting-started
title: Docker Stack Environment
sidebar_label: Getting Started
sidebar_position: 2
description: Bring up the II-Agent Docker stack, configure `.stack.env`, and understand the required services.
---

# Docker Stack Environment Setup

Use this runbook whenever you need to spin up the full II-Agent Docker stack (Postgres, Redis, backend, sandbox server, tool server, frontend, and ngrok). Everything revolves around the `docker/.stack.env` file—treat it as the single source of truth for configuration.

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

> **Local-only mode (no cloud services):** If you don't need E2B, ngrok, or GCS you can run entirely with Docker sandboxes. See the [Local Docker Sandbox](./local-docker-sandbox.md) guide and use `docker-compose.local-only.yaml` instead.

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

The required guide links to the detailed setup pages for each section (frontend env, tunnels, host paths, etc.). Keep it open while editing `.stack.env`.

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
