---
id: required-environment-variables
title: Required Environment Variables
slug: /required-environment-variables
sidebar_label: Required Environment Variables
sidebar_position: 3
description: Definitive checklist for required stack env keys, including local-mode env file naming.
---

# Required Environment Variables

The Docker stack only works when **every** mandatory variable in the correct env file is populated.

- Full stack mode uses `docker/.stack.env`.
- Local Docker sandbox mode uses `docker/.stack.env.local`.

Use this checklist for both modes and store secrets outside Git.

## How to read this page

- Each section maps to a `/docs/required-environment-variables/*` deep-dive. Follow the link when you need screenshots, UI paths, or troubleshooting tips.
- Variables marked with ✅ are required; ones marked with ☑️ can be blank but should be reviewed before production demos.
- Keep secrets in a password manager or secret store—this file is intentionally gitignored.

## Frontend build [`/docs/required-environment-variables/frontend-env`](/docs/required-environment-variables/frontend-env)

| Variable | Status | Notes |
| --- | --- | --- |
| `FRONTEND_BUILD_MODE` | ✅ | `production` for demos; `development` only while debugging the containerized build. |
| `VITE_API_URL` | ✅ | Base URL the UI uses to hit the backend (default `http://localhost:8000`). |
| `VITE_GOOGLE_CLIENT_ID` | ☑️ | Needed when exposing Google OAuth in the browser. |
| `VITE_STRIPE_PUBLISHABLE_KEY` | ☑️ | Supply when billing is enabled. |
| `VITE_SENTRY_DSN` | ☑️ | Optional Sentry DSN for browser traces. |
| `VITE_DISABLE_CHAT_MODE` | ☑️ | Toggle chat UI for demo-only builds. |

## Networking and tunnels [`/docs/required-environment-variables/networking-tunnels`](/docs/required-environment-variables/networking-tunnels)

| Variable | Status | Notes |
| --- | --- | --- |
| `NGROK_AUTHTOKEN` | ✅ | Required to open HTTPS tunnels. |
| `NGROK_REGION` | ✅ | Choose the closest region (`us`, `eu`, `ap`, ...). |
| `NGROK_AGENT_EXTRA_ARGS` | ☑️ | Reserved domains, header rewrites, etc. Leave empty if unsure. |

## Host paths [`/docs/required-environment-variables/host-paths`](/docs/required-environment-variables/host-paths)

| Variable | Status | Notes |
| --- | --- | --- |
| `GOOGLE_APPLICATION_CREDENTIALS` | ✅ | Absolute path to the GCP service-account JSON mounted into containers. |

## LLM configuration and auth [`/docs/required-environment-variables/llm-auth`](/docs/required-environment-variables/llm-auth)

| Variable | Status | Notes |
| --- | --- | --- |
| `LLM_CONFIGS` | ✅ | JSON describing each available model (id, key, base URL, max tokens, retries). |
| `RESEARCHER_AGENT_CONFIG` | ✅ | JSON describing which models power research/report flows. |
| `GOOGLE_CLIENT_ID` | ☑️ | Backend OAuth client ID. |
| `GOOGLE_REDIRECT_URI` | ☑️ | Callback URL (keep the localhost default for dev). |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | ☑️ | JWT lifetime. |
| `ENHANCE_PROMPT_OPENAI_API_KEY` | ☑️ | Dedicated key for the prompt enhancer pipeline. |

## Inner loop controls (optional) [`/docs/getting-started`](/docs/getting-started)

Use these only if you want to enable delegated A2A execution. If omitted, II-Agent stays on the default native loop.

These settings are independent from `SANDBOX_PROVIDER` (local/cloud sandbox choice).

| Variable | Status | Notes |
| --- | --- | --- |
| `AGENT_INNER_LOOP_MODE` | ☑️ | `native` (default) or `a2a`. Start with `native` unless you are actively testing delegated mode. |
| `AGENT_A2A_BACKEND` | ☑️ | `copilot` (default), `claude-code`, or `codex`. Selects the A2A adapter backend when mode is `a2a`. See [Getting Started](/docs/getting-started#inner-loop-mode-client-guide) for model restrictions per backend. |
| `AGENT_A2A_AGENT_URL` | ☑️ | Base URL for the adapter when mode is `a2a` (example: `http://localhost:18100`). |
| `AGENT_A2A_TIMEOUT_SECONDS` | ☑️ | Request timeout for A2A calls. |
| `AGENT_A2A_FALLBACK_TO_NATIVE` | ☑️ | Keep `true` for safer operation; falls back to native when A2A fails. |
| `AGENT_A2A_CONTEXT_REUSE` | ☑️ | Reuses A2A context across turns for continuity. |

## Storage [`/docs/required-environment-variables/storage`](/docs/required-environment-variables/storage)

| Variable | Status | Notes |
| --- | --- | --- |
| `SLIDE_ASSETS_PROJECT_ID`, `SLIDE_ASSETS_BUCKET_NAME` | ✅ | Write destination for slide deck artifacts. |
| `FILE_UPLOAD_PROJECT_ID`, `FILE_UPLOAD_BUCKET_NAME` | ✅ | General-purpose uploads bucket. |
| `AVATAR_PROJECT_ID`, `AVATAR_BUCKET_NAME` | ☑️ | Avatar-specific bucket; can reuse the upload bucket in dev. |
| `CUSTOM_DOMAIN` | ☑️ | Domain used when building shareable URLs (`sfile.ii.inc` by default). |

## Backend sandbox [`/docs/required-environment-variables/backend-sandbox`](/docs/required-environment-variables/backend-sandbox)

| Variable | Status | Notes |
| --- | --- | --- |
| `SANDBOX_TEMPLATE_ID` | ✅ | VM or container template ID used for user sandboxes. |
| `TIME_TIL_CLEAN_UP` | ✅ | Idle timeout in seconds before sandboxes are reclaimed. |

## Tool server baseline [`/docs/required-environment-variables/tool-server-baseline`](/docs/required-environment-variables/tool-server-baseline)

| Variable | Status | Notes |
| --- | --- | --- |
| `STORAGE_CONFIG__GCS_BUCKET_NAME`, `STORAGE_CONFIG__GCS_PROJECT_ID` | ✅ | Buckets used for artifacts generated by the tool server. |

## Sandbox server [`/docs/required-environment-variables/sandbox-server`](/docs/required-environment-variables/sandbox-server)

| Variable | Status | Notes |
| --- | --- | --- |
| `SANDBOX_PROVIDER` | ☑️ | `e2b` (cloud, default) or `docker`/`local` (local Docker containers). |
| `E2B_API_KEY` | ☑️ | API key issued by e2b (not needed for local Docker mode). |
| `E2B_TEMPLATE_ID` | ☑️ | Template ID for e2b sandbox provisioning (not needed for local Docker mode). |
| `SANDBOX_DOCKER_IMAGE` | ☑️ | Docker image for local sandboxes (default `ii-agent-sandbox:latest`). |
| `LOCAL_MODE` | ☑️ | Enable local-mode features such as orphan cleanup. |

## Core infrastructure [`/docs/required-environment-variables/core-infra`](/docs/required-environment-variables/core-infra)

| Variable | Status | Notes |
| --- | --- | --- |
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `POSTGRES_PORT` | ✅ | Local Postgres credentials and host port mapping. |
| `DATABASE_URL` | ✅ | Async connection string consumed by the backend. |
| `SANDBOX_DB_NAME`, `SANDBOX_DATABASE_URL` | ☑️ | Needed when the sandbox service uses a dedicated database. |
| `REDIS_PORT` | ✅ | Host port for Redis; change if it conflicts with another service. |
| `BACKEND_PORT`, `FRONTEND_PORT`, `SANDBOX_SERVER_PORT`, `TOOL_SERVER_PORT`, `NGROK_METRICS_PORT`, `MCP_PORT` | ✅ | Host ports for every HTTP-facing service and dashboards. |

## Validation checklist

1. Run `./scripts/run_stack.sh --build`. If Docker reports a missing environment variable, fix it before proceeding.
2. Visit `http://localhost:<FRONTEND_PORT>` and complete a request. Watch backend logs for auth/model errors.
3. Inspect `http://localhost:<NGROK_METRICS_PORT>` to ensure tunnels connected.
4. Commit the final env file (`docker/.stack.env` or `docker/.stack.env.local`) to your personal secret store. Never check it into Git.
