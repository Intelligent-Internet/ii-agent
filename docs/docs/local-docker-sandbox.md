# Local Docker Sandbox Setup

This guide explains how to run ii-agent with **local Docker containers** instead of E2B cloud sandboxes. This setup keeps all data on your machine and is suitable for:

- Privileged or NDA-protected data
- Air-gapped or restricted network environments
- Development and testing without cloud dependencies
- Self-hosted deployments

## Overview

ii-agent supports multiple sandbox providers through a pluggable architecture:

| Provider | Description | Use Case |
|----------|-------------|----------|
| `e2b` (default) | E2B cloud micro-VMs | Production, quick setup |
| `docker` | Local Docker containers | Privacy, air-gapped, self-hosted |

## Prerequisites

- Docker Engine 20.10+ with Docker Compose v2
- At least 4GB RAM available for containers
- An LLM API key (OpenAI, Anthropic, etc.)

## Quick Start

### 1. Build the Sandbox Image

The sandbox image contains the same tools as E2B sandboxes (Python, Node.js, Playwright, code-server):

```bash
cd /path/to/ii-agent

# Build the sandbox image
docker build -t ii-agent-sandbox:latest -f e2b.Dockerfile .
```

This creates an image with:
- Python 3.10 with common data science packages
- Node.js 24 with npm/yarn/pnpm
- Playwright with Chromium for web automation
- code-server (VS Code in browser)
- noVNC + x11vnc for browser-based VNC access (user handoff for CAPTCHAs/login)
- Bun runtime
- tmux for session management

### 2. Configure Environment

```bash
# Copy the example environment file
cp docker/.stack.env.local.example docker/.stack.env.local

# Edit and configure required values
nano docker/.stack.env.local
```

**Required configuration:**
```bash
# Generate a secure JWT secret
JWT_SECRET_KEY=$(openssl rand -hex 32)

# Add at least one LLM API key
OPENAI_API_KEY=sk-...
# or
ANTHROPIC_API_KEY=sk-ant-...
```

### 3. Start the Stack

```bash
# From the project root
docker compose -f docker/docker-compose.local.yaml \
  --env-file docker/.stack.env.local \
  up -d
```

### 4. Access the Application

- **Frontend**: http://localhost:1420
- **Backend API**: http://localhost:8000
- **MinIO Console**: http://localhost:9001 (minioadmin/minioadmin)

## How It Works

### Architecture

The local stack uses a **monolith backend** — there is no separate sandbox-server or tool-server. The backend manages sandbox containers directly via the Docker API.

```
┌─────────────────────────────────────────────────────────────────┐
│                        Host Machine                              │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────┐  ┌──────────────────────────────────────────────┐  │
│  │Frontend │  │ Backend (:8000)                               │  │
│  │  :1420  │  │  FastAPI + Socket.IO                         │  │
│  └────┬────┘  │  SandboxService → DockerSandbox               │  │
│       │       │  PortPoolManager (ring-buffer allocation)     │  │
│       │       │  Orphan cleanup (background task)             │  │
│       │       └──────────┬───────────────────────────────────┘  │
│       │                  │ Docker API (socket mount)            │
│       │                  ▼                                      │
│       │    ┌──────────────────────────────────────────────┐     │
│       │    │  Sandbox Containers (port range 30000-30999) │     │
│       │    │  ┌─────────────────────────────────────────┐ │     │
│       │    │  │ ii-sandbox-{id}                         │ │     │
│       │    │  │  MCP Server (:6060)  code-server (:9000)│ │     │
│       │    │  │  noVNC (:6080)  Xvfb + x11vnc + Chromium│ │     │
│       │    │  │  Dev servers (:3000, :5173, :8080)      │ │     │
│       │    │  └─────────────────────────────────────────┘ │     │
│       │    │  ┌──────────┐ ┌──────────┐                  │     │
│       │    │  │Sandbox 2 │ │   ...    │                  │     │
│       │    │  └──────────┘ └──────────┘                  │     │
│       │    └──────────────────────────────────────────────┘     │
│       │                                                         │
│  ┌────┴─────────────────────────────────────────────────────┐   │
│  │                    Docker Network                         │   │
│  └───────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌─────────┐  ┌─────────┐  ┌─────────────────┐                  │
│  │Postgres │  │  Redis  │  │  MinIO (S3-compat│                  │
│  │  :5433  │  │  :6379  │  │  :9000 / :9001)  │                  │
│  └─────────┘  └─────────┘  └─────────────────┘                  │
└──────────────────────────────────────────────────────────────────┘
```

### Sandbox Lifecycle

1. **Creation**: When a task requires code execution, the backend's `SandboxService` creates a new Docker container via `DockerSandbox.create()`
2. **Execution**: Commands and file operations run inside the isolated container via MCP server
3. **Persistence**: Workspace files persist in a named Docker volume for the session duration
4. **Pause/Resume**: Stopped containers are automatically restarted when a user revisits the session (see Sandbox Restart below)
5. **Cleanup**: Containers are removed when the session is deleted (orphan cleanup) or manually killed

### Sandbox Restart on Session Load

When a user navigates to a session with an existing sandbox, the backend automatically reconnects:

1. Frontend sends `sandbox_status` Socket.IO command
2. Backend calls `SandboxService.get_sandbox_for_session()` → `DockerSandbox.connect()`
3. If container is `paused` → `unpause()`
4. If container is `exited`/`created` → `start()` + readiness check (MCP health endpoint)
5. Port mappings are re-extracted and registered with the port pool manager
6. Frontend receives sandbox URLs (code-server, noVNC) and reconnects

The "Awake Sandbox" button in the UI follows the same code path.

### Key Differences from E2B

| Feature | E2B Cloud | Docker Local |
|---------|-----------|--------------|
| Startup time | ~150ms (pre-warmed) | ~2-5s (cold start) |
| Isolation | Firecracker micro-VM | Docker container |
| Network | Requires ngrok tunnel | Host-local only |
| Data location | E2B infrastructure | Your machine |
| Scaling | Managed by E2B | Manual (resource limits) |
| Cost | Pay per use | Free (your hardware) |

## Configuration Reference

### Environment Variables

#### Sandbox Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `SANDBOX_PROVIDER` | `e2b` | Set to `docker` for local sandboxes |
| `SANDBOX_DOCKER_IMAGE` | `ii-agent-sandbox:latest` | Docker image for sandboxes |
| `SANDBOX_DOCKER_NETWORK` | `ii-agent-local_ii-network` | Docker network for sandbox containers |
| `SANDBOX_DOCKER_HOST` | `localhost` | Hostname used in sandbox URLs returned to browser. Set to LAN IP when browser is on a different machine. |
| `SANDBOX_PORT_RANGE_START` | `30000` | Start of host port range for sandbox port mappings |
| `SANDBOX_PORT_RANGE_END` | `30999` | End of host port range for sandbox port mappings |
| `SANDBOX_TIMEOUT_SECONDS` | `7200` | Idle timeout before sandbox auto-pauses (seconds) |
| `SANDBOX_MCP_SERVER_PORT` | `6060` | MCP server port inside sandbox containers |
| `SANDBOX_CODE_SERVER_PORT` | `9000` | code-server port inside sandbox containers |
| `SANDBOX_NOVNC_PORT` | `6080` | noVNC port inside sandbox containers |
| `POSTGRES_PORT` | `5432` | PostgreSQL port (use 5433 if 5432 is taken) |

#### Orphan Cleanup Configuration

When running in local mode, the backend automatically cleans up containers whose associated chat sessions have been deleted.

| Variable | Default | Description |
|----------|---------|-------------|
| `SANDBOX_LOCAL_MODE` | `false` | Set to `true` to enable Docker sandbox features and orphan cleanup |
| `SANDBOX_ORPHAN_CLEANUP_ENABLED` | `true` | Can disable cleanup for debugging |
| `SANDBOX_ORPHAN_CLEANUP_INTERVAL_SECONDS` | `60` | How often to check for orphaned sandboxes |
| `SANDBOX_BACKEND_URL` | `http://backend:8000` | Backend URL for session verification during cleanup |

**How It Works:**
1. Every 60 seconds (configurable), a background task in the backend performs three cleanup passes:
   - **Orphan sweep (DB-driven):** Queries all Docker sandbox records and checks whether the linked session has been deleted. If so, kills the container, releases ports, removes the workspace volume, and marks the DB record as deleted.
   - **Stale pause:** Pauses (`docker stop`) running sandboxes whose sessions have been idle longer than `SANDBOX_TIMEOUT_SECONDS`. Paused containers retain their filesystem and can be resumed on the next session access.
   - **Docker zombie sweep:** Lists all Docker containers with the `ii-agent.sandbox=true` label directly via the Docker API, then removes any container whose full ID does not match an active (non-deleted) DB record. This catches containers orphaned by bulk session deletions, DB record failures, or application crashes.
2. All three passes apply the same 5-minute grace period to avoid racing with sandbox initialization.

#### Storage Configuration

Local deployments use local filesystem storage instead of cloud storage (GCS):

| Variable | Default | Description |
|----------|---------|-------------|
| `STORAGE_PROVIDER` | `local` | Use `local` for filesystem, `gcs` for Google Cloud |
| `LOCAL_STORAGE_PATH` | `/.ii_agent/storage` | Base directory for file storage |
| `PUBLIC_TOOL_SERVER_URL` | (auto) | Public URL for the tool server (for file URLs) |

When using local storage:
- Files are stored on the local filesystem
- Content-types are preserved in `.meta` sidecar files
- Files are served via the tool server's `/storage/{path}` endpoint
- Path traversal attacks are prevented by path validation

### Port Management

Docker sandboxes expose internal ports (MCP server, code-server, noVNC, dev servers) to the host. The backend's `PortPoolManager` manages a **port pool** with ring-buffer allocation to prevent conflicts:

- **Default range**: 30000-30999 (1000 ports)
- **Per sandbox**: 6 ports allocated (MCP:6060, code-server:9000, noVNC:6080, plus dev ports 3000, 5173, 8080)
- **Capacity**: ~166 concurrent sandboxes with default settings
- **Ring-buffer allocation**: Ports are allocated by advancing a cursor through the range. Released ports are not reused until the cursor wraps around the entire pool. This prevents port conflicts when restarting stopped containers whose ports may have been assigned to newer sandboxes.
- **Startup scan**: On boot, the port manager scans existing Docker containers and registers their ports as allocated, positioning the ring cursor past the highest in-use port.

**Key implementation files:**
- `src/ii_agent/agents/sandboxes/docker.py` — Docker sandbox provider (`DockerSandbox`)
- `src/ii_agent/agents/sandboxes/port_manager.py` — Port pool allocation (ring-buffer)
- `src/ii_agent/agents/sandboxes/orphan_cleanup.py` — Orphan cleanup background task
- `src/ii_agent/agents/sandboxes/service.py` — `SandboxService` (provider dispatch, DB persistence)
- `src/ii_agent/agents/sandboxes/base.py` — `Sandbox` base class
- `src/ii_agent/core/config/sandbox.py` — `SandboxSettings` configuration

### noVNC Browser Handoff

Each sandbox container runs a **noVNC** web viewer (port 6080) that provides browser-based access to the sandbox's virtual display. This enables a **human-in-the-loop** workflow:

1. The agent automates a browser task using Playwright
2. The agent hits a barrier it can't handle (CAPTCHA, login page, 2FA prompt)
3. The agent calls `expose_port(sandbox_id, 6080, external=True)` to get a noVNC URL
4. The agent shares the URL with the user
5. The user opens the URL in their browser and interacts directly with the sandbox's Chromium instance
6. The user tells the agent they're done
7. The agent resumes automation

**Architecture:**

```
Agent (Playwright MCP) → Chromium → Xvfb :99 ← x11vnc :5900 ← websockify :6080 ← User's browser
```

The virtual display was always running (for Playwright's headed mode). x11vnc + noVNC simply provide a window into it. Both the agent and user can interact with the browser simultaneously (x11vnc runs with `-shared`).

**Manual access** (for debugging — find the host-mapped port):

```bash
# Check Docker port mapping directly
docker port ii-sandbox-<sandbox-id-prefix> 6080
```

Then open `http://localhost:<host-port>/vnc.html` in your browser.

### Resource Limits

Each sandbox container is created with resource constraints. Adjust in `DockerSandbox.create()` if needed.

## Connecting Your Local MCP Server

If you have a local MCP server with privileged data:

### MCP Server on Host Machine

```bash
# In .stack.env.local
MCP_SERVER_URL=http://host.docker.internal:6060
```

### MCP Server in Docker

If your MCP server runs in a container, put it on the same network:

```yaml
# In docker-compose.local.yaml, add your MCP server:
services:
  mcp-server:
    image: your-mcp-server:latest
    networks:
      - default
    ports:
      - "6060:6060"
```

Then configure:
```bash
MCP_SERVER_URL=http://mcp-server:6060
```

## Troubleshooting

### Container fails to start

Check backend logs:
```bash
docker logs ii-agent-local-backend-1
```

Verify the sandbox image exists:
```bash
docker images | grep ii-agent-sandbox
```

### Permission denied on Docker socket

The backend container needs access to create sandbox containers via the Docker socket mount. Either:

1. Add your user to the docker group: `sudo usermod -aG docker $USER`
2. Or run with elevated privileges (not recommended for production)

### PostgreSQL port conflict

If you have PostgreSQL running locally:
```bash
# In .stack.env.local
POSTGRES_PORT=5433
```

### Sandbox containers not cleaning up

**Automatic Cleanup (Recommended):**

If `SANDBOX_LOCAL_MODE=true` is set, orphan cleanup runs automatically. Check if it's working:
```bash
# Check backend logs for cleanup activity
docker logs ii-agent-local-backend-1 2>&1 | grep -i orphan
```

**Manual cleanup:**
```bash
# List sandbox containers
docker ps -a | grep ii-sandbox

# Remove all stopped sandbox containers
docker container prune -f --filter "label=ii-agent.sandbox=true"
```

## Security Considerations

### Network Isolation

By default, sandbox containers can access the network. For stricter isolation:

```yaml
# In DockerSandbox configuration
network_mode: none  # Complete isolation
# or
network_mode: internal  # Container-to-container only
```

### Resource Limits

Prevent runaway containers:

```python
# These are configured in DockerSandbox.create() (src/ii_agent/agents/sandboxes/docker.py)
mem_limit="3072m"       # 3 GB memory
cpu_period=100000
cpu_quota=200000        # 2 CPUs
pids_limit=512
security_opt=["no-new-privileges"]
cap_drop=["ALL"]
cap_add=["CHOWN", "SETUID", "SETGID", "DAC_OVERRIDE"]
```

### Filesystem Access

Sandbox containers only have access to:
- Their workspace volume (mounted at `/workspace`)
- Temporary files (mounted at `/tmp`)

They cannot access host filesystem or other containers' data.

## Development

### Running Tests

```bash
# Test sandbox provider
uv run pytest src/tests/unit/agent/test_docker_sandbox.py -v
uv run pytest src/tests/unit/agent/test_port_manager.py -v
uv run pytest src/tests/unit/agent/test_orphan_cleanup.py -v
```

### Extending the Sandbox Image

Create a custom Dockerfile based on `e2b.Dockerfile`:

```dockerfile
FROM ii-agent-sandbox:latest

# Add your custom tools
RUN pip install your-private-package
```

Build and configure:
```bash
docker build -t ii-agent-sandbox-custom:latest -f Dockerfile.custom .
SANDBOX_DOCKER_IMAGE=ii-agent-sandbox-custom:latest
```

## Contributing

This Docker sandbox provider is designed as an extensible alternative to E2B. Contributions welcome:

- Performance improvements
- Additional isolation options (gVisor, Kata containers)
- Kubernetes provider for scalable deployments
- Better resource management and pooling
