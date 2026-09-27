# Migration Knowledge: Old System → Local Docker Stack

## Overview
Migration of ii-agent from E2B cloud sandboxes + GCS storage to local Docker sandboxes + MinIO storage.
All data lives on a single Linux host accessed from a Windows PC browser via LAN IP.

---

## Database Migration

### Source & Target
- **Backup DB**: `iiagentdev_backup` (old E2B-based system)
- **Target DB**: `iiagentdev` (new Docker-based system)
- **PostgreSQL**: Port 5433, user=iiagent

### Tables Migrated
| Table | Records | Notes |
|-------|---------|-------|
| `sessions` | 65 | All reassigned from `admin@ii.inc` → `dev@localhost` (eac4f4fd) |
| `chat_messages` | 317 | JSONB content column |
| `agent_sandboxes` | 38 | `provider_sandbox_id` updated to Docker container IDs (12 records) |
| `application_events` | 8,328 | Migrated via `scripts/local/migrate_events.py`; 16 event type mappings (old → new dotted names) |
| `run_tasks` | 270 | From `agent_run_tasks` → `run_tasks` with `task_type='agent_run'` |
| `chat_provider_files` | 2 | From `provider_files` |
| `chat_provider_vector_stores` | 1 | From `provider_vector_stores` |
| `slide_contents` | Multiple | Image URLs rewritten (see below) |
| `user_assets` / `session_assets` | 226 | Reassigned user ownership |
| `credit_balances` | 1 | 995k credits transferred |

### Event Type Mappings
Old event names (e.g., `user_message`, `tool_call`, `agent_message`) were mapped to new dotted format
(e.g., `agent.user.message`, `agent.tool.call`, `agent.message`). See `scripts/local/migrate_events.py`.

### Session app_kind Classification
- **`app_kind='agent'`**: Frontend loads from `application_events` table
- **`app_kind='chat'`**: Frontend loads from `chat_messages` table
- **Misclassification bug**: 16 sessions had `app_kind='agent'` but only `chat_messages` (0 events) → showed as empty
- **Fix**: Changed to `app_kind='chat'` so they render via the chat pipeline

### Key Gotcha: User Reassignment
All data was owned by `admin@ii.inc` (bace0701) in the backup. Had to UPDATE all FK references
(`user_id`) across sessions, assets, credits to `dev@localhost` (eac4f4fd).

---

## URL Rewriting

### Problem: localhost URLs
`DockerSandbox.expose_port()` hardcoded `http://localhost:{port}` — inaccessible from a remote browser.

### URL Categories Found in Stored Data
| Pattern | Count | Source | Fixable? |
|---------|-------|--------|----------|
| `http://localhost:8000/files/...` | ~130 events | Backend file/slide asset URLs | ✅ Rewrite to LAN IP |
| `http://localhost:30xxx/...` | ~400 events | Sandbox exposed port URLs (`expose_port()`) | ✅ Rewrite (works when sandbox running) |
| `http://localhost:4000/...` | 4 events | Sandbox app port | ✅ Rewrite |
| `http://localhost:1236/storage/image_search/...` | 67 events | Old E2B sandbox internal file server | ❌ Dead links — service doesn't exist in Docker |

### Fix Applied
- **Script**: `scripts/local/rewrite_localhost_urls.py`
- **SQL**: `replace(content::text, 'http://localhost:', 'http://{host}:')` on:
  - `application_events.content` (JSONB) — 606 rows
  - `slide_contents.slide_content` (varchar) — 1 row
  - `chat_messages.content` (JSONB) — 5 rows
- **Code fix**: Added `SANDBOX_DOCKER_HOST` setting to `SandboxSettings`, used in `expose_port()` instead of hardcoded `localhost`
- **Frontend fix**: Applied `rewriteLocalhostUrl()` to all `setBrowserUrl` / `resultUrl` / `pipUrl` paths that previously used raw URLs from tool results

### Column Type Gotcha
- `application_events.content` → JSONB → use `replace(content::text, ...)::jsonb`
- `chat_messages.content` → JSONB → same cast
- `slide_contents.slide_content` → **varchar** → NO cast needed, just `replace(slide_content, ...)`
- Casting varchar HTML to `::jsonb` causes `InvalidTextRepresentationError`

---

## Image/File Serving

### Slide Assets
- **Old**: Images stored in E2B sandbox filesystem, served via sandbox's code-server (port 1236)
- **New**: Images extracted from Docker sandbox containers → uploaded to MinIO → served via `/files/slides/assets/{hash}.{ext}`
- **Endpoint**: `src/ii_agent/files/slide_assets_router.py` — public, no auth
- **MinIO path**: `content/slides/{filename}`
- **Upload script**: `scripts/local/upload_slide_assets.py`
- **12 of 13 images recovered**; 1 image from E2B session (9ca66417) unrecoverable

### Session Attachments
- Served via `/v1/assets/{asset_id}/download` (JWT required)
- Storage: MinIO bucket `ii-agent`, paths like `users/{uid}/media/{fid}.{ext}`
- Signed URLs generated on-demand

### Sandbox File Preview
- Router `/sandbox-files/{session_id}/preview` was **orphaned** (not registered in `app/routers.py`)
- **Fixed**: Registered at root level (frontend calls without `/v1/` prefix)
- Only works for RUNNING sandboxes — dead sandboxes return 503

### File Accessibility Rules
1. **Live sandbox files**: Accessible via Socket.IO `file_content` command or `/sandbox-files/.../preview`
2. **Uploaded files**: Persisted in MinIO, accessible via signed URLs
3. **Slide images**: Persisted in MinIO, accessible via `/files/slides/assets/`
4. **Dead sandbox files**: LOST unless explicitly uploaded to storage before sandbox died
5. **E2B sandbox files**: Gone forever — E2B sandboxes are ephemeral cloud instances

---

## Sandbox Architecture

### Port Mapping
- Docker sandboxes expose ports 30000-30999 on the host
- Well-known ports: 6060 (MCP), 9000 (code-server), 6080 (noVNC), 3000/5173/8080 (dev servers)
- `SANDBOX_DOCKER_HOST` env var controls the hostname in exposed URLs (default: `localhost`)
- **Ring-buffer allocation:** `PortPoolManager` advances a cursor through the range, wrapping around. Released ports are not reused until the cursor cycles back, preventing conflicts when restarting stopped containers that still hold their original port mappings.

### Container Lifecycle
- Running containers: discoverable via Docker labels
- Exited containers: still exist with their filesystems (can be restarted)
- Removed containers: data lost
- Port 1236: Was E2B's internal file server, doesn't exist in Docker sandbox

### Sandbox Restart on Session Load
When a user navigates to a session, the frontend sends a `sandbox_status` Socket.IO command.
The backend calls `SandboxService.get_sandbox_for_session()` → `DockerSandbox.connect()`, which:
1. Looks up the container by `provider_sandbox_id` (Docker container ID) or by label fallback
2. If container is `paused` → `unpause()`
3. If container is `exited`/`created` → `start()` + `_wait_for_ready()` (MCP health check)
4. Extracts port mappings from the running container
5. Returns the connected sandbox instance

The "Awake Sandbox" button on the frontend fires `awake_sandbox` which follows the same path.

---

## Scripts Reference

| Script | Purpose | Idempotent? |
|--------|---------|-------------|
| `scripts/local/migrate_events.py` | Migrate events from backup DB | No (check target first) |
| `scripts/local/migrate_remaining_data.py` | Migrate run_tasks, provider_files, vector_stores | No |
| `scripts/local/upload_slide_assets.py` | Extract images from sandbox containers → MinIO | Yes (skips existing) |
| `scripts/local/rewrite_localhost_urls.py` | Replace `localhost:` → `{host}:` in DB | Idempotent (no-op if already done) |

---

## Environment Configuration

### Key Settings for Remote Access
```env
# In docker/.stack.env.local:
VITE_API_URL=http://<LAN_IP>:8000              # Frontend API base URL
LOCAL_STORAGE_URL_BASE=http://<LAN_IP>:8000/files  # Storage URL for images
SANDBOX_DOCKER_HOST=<LAN_IP>                    # Sandbox port URLs
```

### Docker Compose
- File: `docker/docker-compose.local.yaml`
- Project: `ii-agent-local`
- Services: postgres (5433), redis (6379), minio (9000/9001), frontend (1420), backend (8000)
- Backend mounts Docker socket for spawning sandbox containers

---

## Common Pitfalls

1. **Transaction rollback**: If a multi-table UPDATE script errors on one table, ALL changes roll back (even previously "successful" ones within the same transaction)
2. **JSONB vs varchar**: Always check column types before writing UPDATE statements with casts
3. **app_kind determines rendering**: Agent sessions that only have chat_messages appear empty — must be classified as `app_kind='chat'`
4. **E2B sandbox data is unrecoverable**: Any files/images that existed only in E2B sandboxes are permanently lost
5. **Frontend axios baseURL**: Set to `VITE_API_URL` — all relative paths resolve against this
6. **MinIO bucket auto-creation**: Must create `ii-agent` bucket manually on first setup
7. **Alembic migrations**: Run at startup unless `II_AGENT_SKIP_MIGRATIONS=true`
8. **Frontend URL rewriting**: `rewriteLocalhostUrl()` must be applied to ALL sandbox URLs displayed to users, not just `vscodeUrl`
