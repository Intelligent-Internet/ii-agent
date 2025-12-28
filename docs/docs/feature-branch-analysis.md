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
| `TOKEN_BUDGET_EXTENDED` | 800,000 | **NEW** - Extended context models (Claude 3.5) |

### Agent Configuration
**File:** [src/ii_agent/core/config/ii_agent_config.py](../src/ii_agent/core/config/ii_agent_config.py)

| Setting | Old Default | New Default | Notes |
|---------|-------------|-------------|-------|
| `storage_provider` | `"gcs"` | `"local"` | Enables local-first deployment |

### Sandbox Server Configuration
**File:** [src/ii_sandbox_server/config.py](../src/ii_sandbox_server/config.py)

**New Configuration Options:**

```python
class Config(BaseSettings):
    # Sandbox provider selection
    provider_type: Literal["e2b", "docker"] = "e2b"  # validation_alias="SANDBOX_PROVIDER"
    
    # Docker-specific settings
    docker_image: str = "ii-sandbox:latest"
    docker_network: str = "ii-agent-network"
    
    # Orphan cleanup settings
    local_mode: bool = False              # Enable orphan cleanup
    orphan_cleanup_enabled: bool = True   # Can be disabled
    orphan_cleanup_interval_seconds: int = 60
    backend_url: str = "http://backend:8000"  # For session verification
```

### Base Classes (API Contracts)

**Storage Base** - [src/ii_agent/storage/base.py](../src/ii_agent/storage/base.py)
- No changes to interface - LocalStorage implements existing contract

**Sandbox Base** - [src/ii_sandbox_server/sandboxes/base.py](../src/ii_sandbox_server/sandboxes/base.py)
- `expose_port(port: int, external: bool = False)` - **NEW parameter**
  - `external=False`: Returns container-to-container URL (Docker network)
  - `external=True`: Returns browser-accessible URL (host port)

---

## Tier 1: Infrastructure Components (Building Blocks)

### Port Pool Manager (NEW)
**File:** [src/ii_sandbox_server/sandboxes/port_manager.py](../src/ii_sandbox_server/sandboxes/port_manager.py) (480 lines)

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
- **Per Sandbox:** Up to 5 ports (SSH, web server, debug, etc.)
- **Capacity:** ~200 concurrent sandboxes

**Key Features:**
1. **Thread-safe allocation** using asyncio Lock
2. **Startup scanning** - Detects existing ii-sandbox containers on restart
3. **Orphan cleanup** - Background task releases ports for dead containers
4. **Graceful initialization** - Handles Docker not running

### Local Storage Provider (NEW)
**File:** [src/ii_agent/storage/local.py](../src/ii_agent/storage/local.py) (175 lines)

**Also duplicated for tool server:**
**File:** [src/ii_tool/integrations/storage/local.py](../src/ii_tool/integrations/storage/local.py) (172 lines)

Replaces GCS for file storage in local deployments.

**Features:**
| Feature | Implementation |
|---------|----------------|
| Path traversal protection | `os.path.abspath().startswith(base_path)` |
| Content-type storage | `.meta` sidecar files |
| URL download | Browser-like headers to avoid bot detection |
| Public URL generation | `{TOOL_SERVER_URL}/storage/{path}` |

**Storage Factory Updates:**
**File:** [src/ii_agent/storage/factory.py](../src/ii_agent/storage/factory.py)

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
**File:** [src/ii_sandbox_server/sandboxes/docker.py](../src/ii_sandbox_server/sandboxes/docker.py) (974 lines)

The core implementation replacing E2B cloud sandboxes.

**Class Hierarchy:**
```
BaseSandbox (Abstract)
    ├── E2BSandbox (Cloud - existing)
    └── DockerSandbox (Local - NEW)
```

**Container Lifecycle:**
```
create() ────► Container Created ────► Running
                     │
                     ▼
              Port Allocated
              (via PortPoolManager)
                     │
                     ▼
              Services Started
              (SSH, Agent)
                     │
                     ▼
kill() ────────► Container Removed ────► Ports Released
```

**Key Methods:**

| Method | Purpose |
|--------|---------|
| `create()` | Create container, allocate ports, start services |
| `run_command()` | Execute shell command with timeout and streaming |
| `upload()` / `download()` | File transfer via docker cp |
| `expose_port()` | Dynamic port mapping for web servers |
| `kill()` | Stop container, release ports |

**Security Features:**
1. **Path validation** - Prevents escaping sandbox directory
2. **Command sanitization** - Protects against shell injection
3. **Resource limits** - CPU/memory constraints via Docker
4. **Network isolation** - Containers on dedicated network

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
**File:** [src/ii_sandbox_server/lifecycle/sandbox_controller.py](../src/ii_sandbox_server/lifecycle/sandbox_controller.py)

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
**File:** [src/ii_agent/server/api/files.py](../src/ii_agent/server/api/files.py)

**New Endpoints for Local Storage:**

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `PUT` | `/files/upload/{path:path}` | Upload file to local storage |
| `GET` | `/files/{path:path}` | Download file with token validation |

**Token-Based Authentication:**
- Files accessed via signed URLs with `token` query parameter
- Tokens are HMAC signatures with expiration

### Tool Server - Storage Endpoint
**File:** [src/ii_tool/integrations/app/main.py](../src/ii_tool/integrations/app/main.py)

**New Endpoint:**

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `GET` | `/storage/{file_path:path}` | Serve files from LocalStorage |

Only active when `STORAGE_PROVIDER=local`. Returns 404 for GCS mode.

### Docker Compose - Local-Only Stack (NEW)
**File:** [docker/docker-compose.local-only.yaml](../docker/docker-compose.local-only.yaml) (194 lines)

Complete local deployment without any cloud dependencies.

**Services:**
```yaml
services:
  postgres:     # Database
  redis:        # Cache/Queue
  frontend:     # React UI
  backend:      # FastAPI server
  tool-server:  # Tool execution
  sandbox-server:  # Sandbox management
```

**Key Environment Variables:**
```yaml
sandbox-server:
  SANDBOX_PROVIDER: docker
  LOCAL_MODE: "true"
  DOCKER_HOST: unix:///var/run/docker.sock
  
backend:
  STORAGE_PROVIDER: local
  LOCAL_STORAGE_PATH: /app/storage
```

**Volume Mounts:**
```yaml
sandbox-server:
  volumes:
    - /var/run/docker.sock:/var/run/docker.sock  # Docker access
    - shared-storage:/app/storage                 # File storage
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
   
   # Remove (no longer needed)
   # E2B_API_KEY
   # GCS_BUCKET_NAME
   # GCS_PROJECT_ID
   ```

3. **Start Local Stack:**
   ```bash
   docker compose -f docker/docker-compose.local-only.yaml up -d
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
| Port Manager | Dynamic allocation prevents port conflicts |
| Orphan Cleanup | Grace period prevents premature termination |
| File Endpoints | Token-based signed URLs with expiration |

---

## Performance Notes

| Metric | E2B Cloud | Local Docker |
|--------|-----------|--------------|
| Sandbox creation | 5-10s | 1-3s |
| File upload | Network dependent | Local disk speed |
| Concurrent sandboxes | Limited by API quota | ~200 (port pool) |
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
