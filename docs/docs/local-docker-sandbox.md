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
docker compose -f docker/docker-compose.local-only.yaml \
  --env-file docker/.stack.env.local \
  up -d
```

### 4. Access the Application

- **Frontend**: http://localhost:1420
- **Backend API**: http://localhost:8000
- **Sandbox Server**: http://localhost:8100

## How It Works

### Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Host Machine                              │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌──────────────────┐   │
│  │Frontend │  │ Backend │  │ Sandbox │  │    Tool Server   │   │
│  │  :1420  │  │  :8000  │  │ Server  │  │      :1236       │   │
│  └────┬────┘  └────┬────┘  │  :8100  │  └──────────────────┘   │
│       │            │       └────┬────┘                          │
│       │            │            │                               │
│       │            │            │ Docker API                    │
│       │            │            ▼                               │
│       │            │    ┌──────────────────────────────────┐   │
│       │            │    │  Sandbox Containers (ephemeral)  │   │
│       │            │    │  ┌─────────┐  ┌─────────┐       │   │
│       │            │    │  │Sandbox 1│  │Sandbox 2│  ...  │   │
│       │            │    │  │ Python  │  │ Node.js │       │   │
│       │            │    │  │Playwright│ │code-svr │       │   │
│       │            │    │  └─────────┘  └─────────┘       │   │
│       │            │    └──────────────────────────────────┘   │
│       │            │                                            │
│  ┌────┴────────────┴────────────────────────────────────────┐  │
│  │                    Docker Network                         │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ┌─────────┐  ┌─────────┐                                      │
│  │Postgres │  │  Redis  │                                      │
│  │  :5433  │  │  :6379  │                                      │
│  └─────────┘  └─────────┘                                      │
└─────────────────────────────────────────────────────────────────┘
```

### Sandbox Lifecycle

1. **Creation**: When a task requires code execution, `sandbox-server` creates a new Docker container
2. **Execution**: Commands and file operations run inside the isolated container
3. **Persistence**: Workspace files persist in a mounted volume for the session duration
4. **Cleanup**: Containers are stopped/removed when the session ends or times out

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

| Variable | Default | Description |
|----------|---------|-------------|
| `SANDBOX_PROVIDER` | `e2b` | Set to `docker` for local sandboxes |
| `SANDBOX_DOCKER_IMAGE` | `ii-agent-sandbox:latest` | Docker image for sandboxes |
| `SANDBOX_DOCKER_NETWORK` | (none) | Optional network for sandbox containers |
| `SANDBOX_PORT_RANGE_START` | `30000` | Start of host port range for sandbox port mappings |
| `SANDBOX_PORT_RANGE_END` | `30999` | End of host port range for sandbox port mappings |
| `POSTGRES_PORT` | `5432` | PostgreSQL port (use 5433 if 5432 is taken) |

### Port Management

Docker sandboxes expose internal ports (MCP server, code-server, dev servers) to the host. The sandbox server manages a **port pool** to prevent conflicts:

- **Default range**: 30000-30999 (1000 ports)
- **Per sandbox**: 5 ports allocated (MCP:6060, code-server:9000, plus dev ports 3000, 5173, 8080)
- **Capacity**: ~200 concurrent sandboxes with default settings

**API Endpoints** (for monitoring):
- `GET /ports/stats` - Pool statistics (allocated, free, sandboxes)
- `GET /ports/allocations` - List all current port allocations
- `POST /ports/cleanup` - Force cleanup of orphaned allocations

### Resource Limits

Edit the Docker Compose file to adjust container resources:

```yaml
sandbox-server:
  deploy:
    resources:
      limits:
        cpus: '2'
        memory: 4G
```

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
# In docker-compose.local-only.yaml, add your MCP server:
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

Check Docker logs:
```bash
docker logs ii-agent-sandbox-server-1
```

Verify the sandbox image exists:
```bash
docker images | grep ii-agent-sandbox
```

### Permission denied on Docker socket

The sandbox-server needs access to create containers. Either:

1. Add your user to the docker group: `sudo usermod -aG docker $USER`
2. Or run with elevated privileges (not recommended for production)

### PostgreSQL port conflict

If you have PostgreSQL running locally:
```bash
# In .stack.env.local
POSTGRES_PORT=5433
```

### Sandbox containers not cleaning up

Manual cleanup:
```bash
# List sandbox containers
docker ps -a | grep ii-sandbox

# Remove all stopped sandbox containers
docker container prune -f --filter "label=ii-agent-sandbox=true"
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
# These are configured in DockerSandbox
mem_limit="2g"
cpu_quota=100000  # 1 CPU
pids_limit=256
```

### Filesystem Access

Sandbox containers only have access to:
- Their workspace volume (mounted at `/workspace`)
- Temporary files (mounted at `/tmp`)

They cannot access host filesystem or other containers' data.

## Development

### Running Tests

```bash
# Test sandbox provider locally
pytest tests/sandbox/test_docker_sandbox.py -v
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
