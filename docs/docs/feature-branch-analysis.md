# Feature Branch Dependency Analysis

> **Branch:** Feature branch vs `develop`  
> **Summary:** 124 files changed, 16,024 insertions(+), 295 deletions(-)  
> **Primary Feature:** Local Docker Sandbox - Air-gapped deployment without E2B cloud

---

## Executive Summary

This feature branch implements a **complete local-only deployment mode** for ii-agent, eliminating the dependency on E2B cloud sandboxes and GCS storage. The changes enable:

1. **Docker-based sandboxes** running on the local host
2. **Local filesystem storage** replacing Google Cloud Storage
3. **Orphan cleanup system** to manage sandbox lifecycle
4. **Extended token budgets** for large context models

---

## Tier 0: Configuration & Constants (Foundation Layer)

### Token Budget Constants
**File:** [src/ii_agent/utils/constants.py](../src/ii_agent/utils/constants.py)

| Constant | Value | Purpose |
|----------|-------|---------|
| `TOKEN_BUDGET_NORMAL` | 200,000 | Standard context window |
| `TOKEN_BUDGET_EXTENDED` | 800,000 | **NEW** - Extended context models (Claude 4.5) |

### Agent Configuration
**File:** [src/ii_agent/core/config/settings.py](../src/ii_agent/core/config/settings.py)

| Setting | Old Default | New Default | Notes |
|---------|-------------|-------------|-------|
| `storage_provider` | `"gcs"` | `"local"` | Enables local-first deployment |

### Sandbox Configuration
**File:** [src/ii_agent/core/config/sandbox.py](../src/ii_agent/core/config/sandbox.py)

**New Configuration Options:**

```python
class SandboxSettings(BaseSettings):
    # Sandbox provider selection
    provider: SandboxProvider = "e2b"  # env: SANDBOX_PROVIDER
    
    # Docker-specific settings
    docker_image: str = "ii-agent-sandbox:latest"   # env: SANDBOX_DOCKER_IMAGE
    docker_network: str = "ii-agent-local_ii-network"  # env: SANDBOX_DOCKER_NETWORK
    docker_host: str = "localhost"      # env: SANDBOX_DOCKER_HOST (LAN IP for remote browser access)
    port_range_start: int = 30000       # env: SANDBOX_PORT_RANGE_START
    port_range_end: int = 30999         # env: SANDBOX_PORT_RANGE_END
    
    # Orphan cleanup settings
    local_mode: bool = False              # Enable Docker sandbox features
    orphan_cleanup_enabled: bool = True   # Can be disabled
    orphan_cleanup_interval_seconds: int = 60
    backend_url: str = "http://backend:8000"  # For session verification
    
    # Container service ports
    mcp_server_port: int = 6060
    code_server_port: int = 9000
    novnc_port: int = 6080
```

### Base Classes (API Contracts)

**Storage Base** - [src/ii_agent/core/storage/base.py](../src/ii_agent/core/storage/base.py)
- No changes to interface - LocalStorage implements existing contract

**Sandbox Base** - [src/ii_agent/agents/sandboxes/base.py](../src/ii_agent/agents/sandboxes/base.py)
- `expose_port(port: int, external: bool = False)` - **NEW parameter**
  - `external=False`: Returns container-to-container URL (Docker network)
  - `external=True`: Returns browser-accessible URL (host port)

---

## Tier 1: Infrastructure Components (Building Blocks)

### Port Pool Manager (NEW)
**File:** [src/ii_agent/agents/sandboxes/port_manager.py](../src/ii_agent/agents/sandboxes/port_manager.py) (480 lines)

A singleton service managing port allocation for Docker sandbox containers.

**Architecture:**
```
┌─────────────────────────────────────────────────────────────┐
│                    PortPoolManager                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │  Port Pool   │  │  Allocations │  │  Orphan Cleanup  │  │
│  │ 30000-30999  │  │   by Sandbox │  │    Background    │  │
│  └──────────────┘  └──────────────┘  └──────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

**Key Components:**

| Class | Purpose |
|-------|---------|
| `PortAllocation` | Single port mapping (host_port, container_port, purpose) |
| `SandboxPortSet` | All ports for one sandbox + creation timestamp |
| `PortPoolManager` | Singleton managing allocation/deallocation |

**Port Range:**
- **Range:** 30000-30999 (1,000 ports)
- **Per Sandbox:** 6 ports (MCP:6060, code-server:9000, noVNC:6080, dev:3000, vite:5173, http:8080)
- **Capacity:** ~166 concurrent sandboxes

**Key Features:**
1. **Thread-safe allocation** using `threading.Lock`
2. **Ring-buffer allocation** — Cursor always advances forward, wrapping around the range. Released ports are not reused until the cursor cycles back, preventing conflicts when restarting stopped containers.
3. **Startup scanning** - Detects existing ii-sandbox containers on restart, positions cursor past highest allocated port
4. **Orphan cleanup** - Background task releases ports for dead containers
5. **Graceful initialization** - Handles Docker not running

### Local Storage Provider (NEW)
**File:** [src/ii_agent/core/storage/local.py](../src/ii_agent/core/storage/local.py) (175 lines)

**Also duplicated for tool server:**
**File:** [src/ii_server/integrations/storage/local.py](../src/ii_server/integrations/storage/local.py) (172 lines)

Replaces GCS for file storage in local deployments.

**Features:**
| Feature | Implementation |
|---------|----------------|
| Path traversal protection | `os.path.abspath().startswith(base_path)` |
| Content-type storage | `.meta` sidecar files |
| URL download | Browser-like headers to avoid bot detection |
| Public URL generation | `{TOOL_SERVER_URL}/storage/{path}` |

**Storage Factory Updates:**
**File:** [src/ii_agent/core/storage/factory.py](../src/ii_agent/core/storage/factory.py)

```python
def create_storage_client(config: StorageConfig) -> BaseStorage:
    if config.storage_provider == "local":
        return LocalStorage(config)  # NEW
    if config.storage_provider == "gcs":
        return GCS(config)
    raise ValueError(f"Unknown storage provider: {config.storage_provider}")
```

---

## Tier 2: Docker Sandbox Implementation (Core Feature)

### DockerSandbox Provider (NEW)
**File:** [src/ii_agent/agents/sandboxes/docker.py](../src/ii_agent/agents/sandboxes/docker.py) (974 lines)

The core implementation replacing E2B cloud sandboxes.

**Class Hierarchy:**
```
Sandbox (Abstract, agents/sandboxes/base.py)
    ├── E2BSandbox (Cloud - existing)
    └── DockerSandbox (Local - NEW)
```

**Container Lifecycle:**
```
create() ────► Container Created ────► Running
                     │
                     ▼
              Port Allocated
              (ring-buffer via PortPoolManager)
                     │
                     ▼
              Services Ready
              (MCP :6060, code-server :9000, noVNC :6080)
                     │
                     ▼
connect() ◀── exited/paused ──► start()/unpause() + readiness check
                     │
                     ▼
kill() ────────► Container Removed ────► Ports Released + Volume Cleaned
```

**Key Methods:**

| Method | Purpose |
|--------|---------|
| `create()` | Create container, allocate ports, wait for MCP ready |
| `connect()` | Re-attach to existing container, restart if stopped, readiness check |
| `run_command()` | Execute shell command with timeout |
| `read_file()` / `write_file()` | File transfer via docker cp (tar archives) |
| `expose_port()` | Return host-mapped port URL (uses `SANDBOX_DOCKER_HOST`) |
| `kill()` | Stop container, release ports, clean up volume |

**Security Features:**
1. **Path validation** — Prevents escaping sandbox directory (`ALLOWED_WORKSPACE_BASES`)
2. **Resource limits** — `mem_limit=3072m`, `cpu_quota=200000` (2 CPUs), `pids_limit=512`
3. **Capability dropping** — `cap_drop=["ALL"]`, `cap_add=["CHOWN", "SETUID", "SETGID", "DAC_OVERRIDE"]`
4. **No privilege escalation** — `security_opt=["no-new-privileges"]`
5. **Network isolation** — Containers on dedicated Docker network

**Port Mapping Strategy:**
```
Browser Request                Docker Container
      │                              │
      ▼                              ▼
 localhost:30001  ──────────►  container:8080
 (host port)       expose_port   (container port)
```

---

## Tier 3: Orchestration (Lifecycle Management)

### Sandbox Controller - Orphan Cleanup (NEW)
**File:** [src/ii_agent/agents/sandboxes/orphan_cleanup.py](../src/ii_agent/agents/sandboxes/orphan_cleanup.py)

**New Feature:** Background cleanup of orphaned sandboxes (~120 new lines)

**Problem Solved:**
When a chat session is deleted in the backend, the sandbox continues running. The orphan cleanup system detects and removes these orphans.

**Flow:**
```
┌─────────────────────────────────────────────────────────────┐
│                  _orphan_cleanup_loop()                      │
│                                                             │
│  1. List all active sandboxes                               │
│  2. For each sandbox:                                       │
│     a. Skip if created < 5 minutes ago (grace period)       │
│     b. Call backend: GET /internal/sandboxes/{id}/has-active│
│     c. If no active session → kill sandbox                  │
│  3. Sleep for orphan_cleanup_interval_seconds               │
│  4. Repeat                                                  │
└─────────────────────────────────────────────────────────────┘
```

**Configuration:**
```python
local_mode: bool = False                    # Must be True to enable
orphan_cleanup_enabled: bool = True         # Can disable for debugging
orphan_cleanup_interval_seconds: int = 60   # Check frequency
backend_url: str = "http://backend:8000"    # Backend API endpoint
```

**Grace Period:**
- New sandboxes are protected for **5 minutes** after creation
- Prevents race condition during session initialization

---

## Tier 4: Integration Layer (API & Infrastructure)

### Backend API - File Endpoints
**File:** [src/ii_agent/files/router.py](../src/ii_agent/files/router.py)

**New Endpoints for Local Storage:**

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `PUT` | `/files/upload/{path:path}` | Upload file to local storage |
| `GET` | `/files/{path:path}` | Download file with token validation |

**Token-Based Authentication:**
- Files accessed via signed URLs with `token` query parameter
- Tokens are HMAC signatures with expiration

### Tool Server - Storage Endpoint
**File:** [src/ii_server/integrations/app/main.py](../src/ii_server/integrations/app/main.py)

**New Endpoint:**

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `GET` | `/storage/{file_path:path}` | Serve files from LocalStorage |

Only active when `STORAGE_PROVIDER=local`. Returns 404 for GCS mode.

### Docker Compose - Local Stack (NEW)
**File:** [docker/docker-compose.local.yaml](../docker/docker-compose.local.yaml) (194 lines)

Complete local deployment without any cloud dependencies.

**Services:**

The local stack uses a **monolith backend** — no separate sandbox-server or tool-server:

```yaml
services:
  postgres:     # Database (:5433)
  redis:        # Cache/Queue (:6379)
  minio:        # S3-compatible storage (:9000/:9001)
  frontend:     # React UI (:1420)
  backend:      # FastAPI server + sandbox management (:8000)
```

**Key Environment Variables:**
```yaml
backend:
  SANDBOX_PROVIDER: docker
  SANDBOX_LOCAL_MODE: "true"
  SANDBOX_DOCKER_HOST: ${SANDBOX_DOCKER_HOST:-localhost}
  STORAGE_PROVIDER: local
```

**Volume Mounts:**
```yaml
backend:
  volumes:
    - /var/run/docker.sock:/var/run/docker.sock  # Docker access
```

---

## Dependency Graph

```
                    ┌─────────────────────┐
                    │   Configuration     │
                    │  (constants, config)│
                    └─────────┬───────────┘
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
    ┌─────────────────┐ ┌──────────────┐ ┌──────────────┐
    │  PortPoolManager│ │ LocalStorage │ │ Base Classes │
    │    (Tier 1)     │ │   (Tier 1)   │ │   (Tier 0)   │
    └────────┬────────┘ └──────┬───────┘ └──────┬───────┘
             │                 │                │
             ▼                 │                │
    ┌─────────────────┐        │                │
    │  DockerSandbox  │◄───────┴────────────────┘
    │    (Tier 2)     │
    └────────┬────────┘
             │
             ▼
    ┌─────────────────┐
    │SandboxController│
    │ Orphan Cleanup  │
    │    (Tier 3)     │
    └────────┬────────┘
             │
             ▼
    ┌─────────────────┐
    │   API Routes    │
    │ Docker Compose  │
    │    (Tier 4)     │
    └─────────────────┘
```

---

## Migration Guide

### From E2B Cloud to Local Docker

1. **Prerequisites:**
   - Docker installed and running
   - Docker Compose v2+
   - At least 8GB RAM available

2. **Environment Variables:**
   ```bash
   # Required changes
   SANDBOX_PROVIDER=docker
   STORAGE_PROVIDER=local
   LOCAL_MODE=true
   
   # Not required for local mode
   # E2B_API_KEY
   # GCS_BUCKET_NAME
   # GCS_PROJECT_ID
   ```

3. **Start Local Stack:**
   ```bash
   docker compose -f docker/docker-compose.local.yaml up -d
   ```

4. **Verify:**
   - Check sandbox-server logs for "Using Docker sandbox provider"
   - Create a test chat and verify container creation
   - Upload a file and verify local storage

---

## Security Considerations

| Component | Security Measure |
|-----------|-----------------|
| DockerSandbox | Path validation, command sanitization, resource limits |
| LocalStorage | Path traversal protection, base path enforcement |
| Port Manager | Ring-buffer allocation prevents port conflicts on sandbox restart |
| Orphan Cleanup | Grace period prevents premature termination |
| File Endpoints | Token-based signed URLs with expiration |

---

## Performance Notes

| Metric | E2B Cloud | Local Docker |
|--------|-----------|--------------|
| Sandbox creation | 5-10s | 1-3s |
| File upload | Network dependent | Local disk speed |
| Concurrent sandboxes | Limited by API quota | ~166 (port pool, ring-buffer) |
| Network latency | Cloud RTT | Negligible |

---

## Files Changed Summary

| Category | Files | Lines Changed |
|----------|-------|---------------|
| New Docker Sandbox | 2 | +1,454 |
| New Local Storage | 4 | +400 |
| Orphan Cleanup | 1 | +120 |
| Configuration | 4 | +80 |
| Docker Compose | 2 | +200 |
| API Endpoints | 2 | +100 |
| Tests | ~20 | +3,000 |
| Documentation | 5 | +1,500 |
| **Total** | **124** | **+16,024 / -295** |
