---
id: sandbox-server
title: Sandbox Server Integration
slug: /required-environment-variables/sandbox-server
sidebar_position: 17
---

These variables configure the sandbox provider that powers interactive coding environments. II-Agent supports two providers: **E2B** (cloud) and **Docker** (local).

## Choosing a provider

Set `SANDBOX_PROVIDER` in your `.stack.env` file:

| Value | Description |
|-------|-------------|
| `e2b` | Cloud sandboxes via [e2b.dev](https://e2b.dev/). Requires `E2B_API_KEY`. |
| `docker` or `local` | Local Docker containers. No cloud account needed. |

For local-only deployments see the [Local Docker Sandbox](../local-docker-sandbox.md) guide.

## E2B cloud mode

### `E2B_API_KEY`

1. Log into the [e2b dashboard](https://e2b.dev/) (or your equivalent provider).
2. Navigate to **API Keys** and create a new key scoped for development use.
3. Copy the key (looks like `e2b_live_...`) and paste it into `docker/.stack.env`.
4. Rotate the key if you suspect compromise -- do not commit it to Git.

### `E2B_TEMPLATE_ID`

1. Open the sandbox provisioning portal or service you use for backend execution (internal tool, provider dashboard, etc.).
2. Locate the template/image you want the stack to spawn (for example "ii-backend-dev").
3. Copy its unique identifier and place it in `docker/.stack.env` as `E2B_TEMPLATE_ID`.

## Docker local mode

When `SANDBOX_PROVIDER=docker` (or `local`), the sandbox server creates ephemeral Docker containers on the host. No cloud account or API key is needed.

### Key variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SANDBOX_DOCKER_IMAGE` | `ii-agent-sandbox:latest` | Docker image to spawn for each sandbox. |
| `DOCKER_NETWORK` | (compose project network) | Docker network sandboxes attach to. |
| `LOCAL_MODE` | `false` | Enable local-mode features (orphan cleanup). |
| `ORPHAN_CLEANUP_ENABLED` | `true` | Auto-remove sandboxes whose sessions no longer exist. |
| `ORPHAN_CLEANUP_INTERVAL_SECONDS` | `300` | How often (seconds) to check for orphans. |
| `BACKEND_URL` | `http://backend:8000` | Backend URL for session verification during cleanup. |

### Container services

Each Docker sandbox container runs:

| Service | Container port | Description |
|---------|---------------|-------------|
| MCP Server | 6060 | Tool calls from the agent |
| code-server | 9000 | VS Code in the browser |
| noVNC | 6080 | Browser-based VNC for user handoff (CAPTCHAs, login) |
| Xvfb + x11vnc | :99 / 5900 | Virtual display for headed Chromium |

Ports are dynamically mapped to the host from pool 30000-30999 (6 ports per sandbox, ~166 concurrent sandboxes).

## `TIME_TIL_CLEAN_UP`

- Specifies how long (in seconds) an idle sandbox lives before auto-shutdown.
- Choose a value that balances cost and usability. Example: `900` (15 minutes) keeps sessions alive long enough for debugging without leaving unused containers running.

