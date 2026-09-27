---
id: sandbox-server
title: Sandbox Server Integration
slug: /required-environment-variables/sandbox-server
sidebar_position: 17
---

These variables configure the sandbox provider that powers interactive coding environments. II-Agent supports two providers: **E2B** (cloud) and **Docker** (local).

## Choosing a provider

Set `SANDBOX_PROVIDER` in the env file for your selected mode:

- `docker/.stack.env` for full stack mode.
- `docker/.stack.env.local` for local Docker mode.

| Value | Description |
|-------|-------------|
| `e2b` | Cloud sandboxes via [e2b.dev](https://e2b.dev/). Requires `E2B_API_KEY`. |
| `docker` or `local` | Local Docker containers. No cloud account needed. |

For local-only deployments see the [Local Docker Sandbox](../local-docker-sandbox.md) guide.

## E2B cloud mode

### `E2B_API_KEY`

1. Log into the [e2b dashboard](https://e2b.dev/) (or your equivalent provider).
2. Navigate to **API Keys** and create a new key scoped for development use.
3. Copy the key (looks like `e2b_live_...`) and paste it into your active env file (`docker/.stack.env` or `docker/.stack.env.local`).
4. Rotate the key if you suspect compromise -- do not commit it to Git.

### `E2B_TEMPLATE_ID`

1. Open the sandbox provisioning portal or service you use for backend execution (internal tool, provider dashboard, etc.).
2. Locate the template/image you want the stack to spawn (for example "ii-backend-dev").
3. Copy its unique identifier and place it in your active env file (`docker/.stack.env` or `docker/.stack.env.local`) as `E2B_TEMPLATE_ID`.

## Docker local mode

When `SANDBOX_PROVIDER=docker` (or `local`), the backend creates ephemeral Docker containers on the host. No cloud account or API key is needed.

### Key variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SANDBOX_DOCKER_IMAGE` | `ii-agent-sandbox:latest` | Docker image to spawn for each sandbox. |
| `SANDBOX_DOCKER_NETWORK` | `ii-agent-local_ii-network` | Docker network sandboxes attach to. |
| `SANDBOX_DOCKER_HOST` | `localhost` | Hostname in sandbox URLs returned to browser. Set to LAN IP when browser is on another machine. |
| `SANDBOX_PORT_RANGE_START` | `30000` | Start of host port range for sandbox port mappings. |
| `SANDBOX_PORT_RANGE_END` | `30999` | End of host port range. |
| `SANDBOX_LOCAL_MODE` | `false` | Enable local-mode features (port scanning, orphan cleanup). |
| `SANDBOX_ORPHAN_CLEANUP_ENABLED` | `true` | Auto-remove sandboxes whose sessions no longer exist. |
| `SANDBOX_ORPHAN_CLEANUP_INTERVAL_SECONDS` | `60` | How often (seconds) to check for orphans. |
| `SANDBOX_BACKEND_URL` | `http://backend:8000` | Backend URL for session verification during cleanup. |
| `SANDBOX_MCP_SERVER_PORT` | `6060` | MCP server port inside sandbox containers. |
| `SANDBOX_CODE_SERVER_PORT` | `9000` | code-server port inside sandbox containers. |
| `SANDBOX_NOVNC_PORT` | `6080` | noVNC port inside sandbox containers. |
| `SANDBOX_TIMEOUT_SECONDS` | `7200` | Idle timeout (seconds) before sandbox auto-pauses. |

### Container services

Each Docker sandbox container runs:

| Service | Container port | Description |
|---------|---------------|-------------|
| MCP Server | 6060 | Tool calls from the agent |
| code-server | 9000 | VS Code in the browser |
| noVNC | 6080 | Browser-based VNC for user handoff (CAPTCHAs, login) |
| Xvfb + x11vnc | :99 / 5900 | Virtual display for headed Chromium |

Ports are dynamically mapped to the host from pool 30000-30999 using ring-buffer allocation (6 ports per sandbox, ~166 concurrent sandboxes).

## `SANDBOX_TIMEOUT_SECONDS`

- Specifies how long (in seconds) an idle sandbox lives before auto-pause.
- Default: `7200` (2 hours). Paused containers can be restarted when the user revisits the session.
- Choose a value that balances resource usage and usability.

