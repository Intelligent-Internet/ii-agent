# II-Agent Codebase Review — Windows ROG Zephyrus G16 Fitness

**Repo:** [Intelligent-Internet/ii-agent](https://github.com/Intelligent-Internet/ii-agent) (this tree, `main` @ `28563d6`)
**Audience:** Emad Mostaque / operators planning a native Windows run (no WSL) on an ROG Zephyrus G16 (RTX 4090 Laptop, 16 GB VRAM)
**Date:** 2026-08-16
**Scope:** Architecture, quality, Windows fitness, local-model path, severity-ranked issues, concrete run recipe
**Sibling:** `ii-agent-prod` is not accessible from this environment (GitHub 404). Published docs live at [intelligent-internet.github.io/ii-agent-prod](https://intelligent-internet.github.io/ii-agent-prod/). Conclusions below are from **this public repo only**.

---

## Verdict

This is a **production-shaped SaaS agent platform**, not a laptop-native inference app. The G16 GPU is unused by the agent core. Inference is BYOK cloud LLMs (Anthropic / OpenAI / Google / Cerebras) or an OpenAI-compatible `Custom` `base_url`. Local process work is Postgres + Redis + object storage + a FastAPI/Socket.IO control plane + a React/Vite UI. Code execution is **E2B cloud sandboxes**, not the host GPU and not a working local Docker sandbox.

**Can it run native Windows without WSL?** Yes, as a **host-native Python + Node control plane**, if you install PostgreSQL for Windows and skip Docker. Docker Desktop is **not required** for that path — and on “no WSL” it is the wrong tool, because Linux-container Compose in this repo implies Docker Desktop’s WSL2 (or legacy Hyper-V) backend.

**Will “Build a website / run tools” work on day one without extra accounts?** No. Agent tools lazily provision an E2B sandbox. `SANDBOX_PROVIDER=docker` and `local` are advertised and then rejected at runtime. Chat-only / BYOK conversation can work without E2B. Agent-mode file/shell/browser work cannot.

**Do not treat `make dev-all` as the Windows recipe.** The documented happy path is Unix Make + bash + Docker Linux images.

### Hypothesis

| Claim | Verdict |
|---|---|
| G16 GPU is unused unless we wire a Custom provider | **Confirmed.** No CUDA/torch/vLLM/llama.cpp in the runtime. `transformers` is a library dep, not a local serving stack. GPU lights up only if you run `llama-server` (or similar) yourself and point `provider: Custom` + `base_url` at it. |
| Hard Windows blocker is Docker/Make/unix scripts, not the Python agent core | **Mostly confirmed, with two equal product blockers.** Make/bash/`Xvfb`/`start.sh` are the *packaging* blockers. **OAuth-only login** and **E2B-only sandbox** are the *product* blockers. Host Python will also trip on Unix-flavored deps (`python-magic`, WeasyPrint, `pexpect`, `libtmux`) if you lean on those features. |

---

## 1. Architecture

### What this repo actually is

A domain-driven FastAPI + Socket.IO monolith with a Tauri-capable React frontend. The published product (agent.ii.inc) and the in-repo docs (`CLAUDE.md`, `AGENTS.md`, `docs/CODEMAPS/`) describe the same platform: sessions, credits, Stripe, Cloud Run publish, TestFlight, Composio, slides, storybooks, media.

```
Browser / Vite UI  (frontend/, port 1420)
        │  REST (/auth, /v1/...)
        │  Socket.IO (JWT in handshake)
        ▼
FastAPI + python-socketio  (src/ii_agent/ws_server.py)
        │
        ├─ Auth: Google OAuth or II Hydra OAuth → JWT
        ├─ Sessions / credits / files / settings
        ├─ Chat REST+SSE  (src/ii_agent/chat/)
        └─ Agent loop     (src/ii_agent/realtime/handlers/query.py)
                │
                ├─ LLM: Anthropic / OpenAI / Google / Cerebras / Custom
                ├─ Tools: 13 categories (shell, FS, browser, media, connectors, …)
                └─ Sandbox: E2B only (src/ii_agent/agents/sandboxes/)
                        │
                        ▼
                   E2B cloud VM  (not the G16)
```

Infra the control plane expects:

| Piece | Role | Local default |
|---|---|---|
| PostgreSQL 15 | Source of truth (users, sessions, events, credits, …) | `localhost:5432` / `ii_agent` |
| Redis 7 | Optional cache + Socket.IO manager | `.env.example` enables it; code can run with it off |
| MinIO | S3-compatible uploads | `localhost:9000` — **replaceable** with `STORAGE_PROVIDER=local` |
| E2B | Isolated tool/workspace VM | Default provider; API key required |
| Cloud LLMs | Model inference | `MODEL_CONFIGS` / `model_configs.yaml` |

### Backend

- Entry: `src/ii_agent/ws_server.py` → `app/__init__.py::create_app()` wraps FastAPI in `socketio.ASGIApp`.
- Lifespan (`src/ii_agent/app/lifespan.py`): DB engine → Redis client → Alembic → `ApplicationContainer` → PubSub → Socket.IO handlers → seed LLM settings + builtin skills → APScheduler.
- Domains under `src/ii_agent/`: `auth`, `users`, `sessions`, `credits`, `billing`, `chat`, `agents`, `realtime`, `files`, `projects`, `content`, `integrations`, `settings`, `workers`.
- Compatibility shim `src/ii_server/` (workspace + sandbox MCP/tools) is vendored here. Agent factory imports `ii_server.core.workspace.WorkspaceManager` (`src/ii_agent/agents/factory/agent.py`).
- DI: `ApplicationContainer` (`src/ii_agent/core/container.py`) + FastAPI `Dep` aliases. Matches the contributor guide.

### Frontend

- `frontend/`: React 19 + Vite + Tailwind + Redux + Socket.IO client. Tauri is present (`@tauri-apps/*`) but **local run is the Vite web app**, not a required desktop build.
- Dev port is **1420** (`frontend/.env.example` `VITE_PORT`, `frontend/vite.config.ts`). Makefile `frontend-dev` help text still says 5173. `.env.example` `II_FRONTEND_URL=http://localhost:5173` is stale.
- Package manager: Makefile/`README.md` use **npm**. `frontend/README.md` still says **pnpm**. Use npm to match `make install`.
- Login UI (`frontend/src/app/routes/login.tsx`): Google + “Continue with II”. Email/password form exists but is hard-hidden (`hideSigninWithPassword = true`) and `onSubmit` only `console.log`s.

### Request flow: UI → tools

1. User authenticates (OAuth) → JWT in `localStorage`.
2. UI opens Socket.IO with `{ token }` (`src/ii_agent/realtime/manager.py::connect`).
3. Client emits `chat_message` / command payload.
4. `CommandHandlerFactory` → `UserQueryHandler` (`realtime/handlers/query.py`).
5. `SessionService.validate_and_prepare_for_run` resolves the model and, for **system** keys, checks credits (`sessions/service.py` ~470). **User-supplied BYOK keys skip the credit check.**
6. `agent_factory.create_agent` builds the model + tool list.
7. First sandbox-backed tool (`BaseSandboxTool`, `agents/tools/sandbox/base.py`) lazily calls `SandboxService.init_sandbox`.
8. Provider create only implements E2B (`sandboxes/service.py` `_create_provider`). Docker/local raise `SandboxCreationError`.
9. Events go PubSub → Socket.IO room + `application_events` table.

Chat mode is a separate REST/SSE surface (`src/ii_agent/chat/api/router.py`, prefix `/v1/chat`). It can talk to LLMs without a sandbox. Agent-mode “do work on a workspace” cannot.

### Model providers

Configured via `MODEL_CONFIGS` JSON or `MODEL_CONFIGS_FILE` YAML, seeded at startup into `llm_settings` (`settings/llm/seeding.py`).

| Provider | Agent path | Chat path | Local GPU? |
|---|---|---|---|
| OpenAI | `OpenAIResponses` (Responses API) | OpenAI client | No |
| Anthropic | `Claude` / Vertex Claude | Anthropic client | No |
| Google | `Gemini` (direct or Vertex) | Gemini client | No |
| Cerebras | Routed through Custom/OpenAI-compat | Custom | No |
| **Custom** | `OpenAIChatCustom` → Chat Completions + `base_url` | LiteLLM `acompletion` + `base_url` | **Only if `base_url` is your local server** |

Agent builder: `src/ii_agent/agents/models/utils.py` (`_build_custom`, line 97).
Chat builder: `src/ii_agent/chat/llm/custom.py`.
Example YAML: `model_configs.example.yaml` lines 71–79 (`http://localhost:1234/v1`).

### Storage

`STORAGE_PROVIDER` ∈ `{gcs, minio, local}` (`core/config/storage.py`). Local filesystem provider is real (`core/storage/providers/local.py`, default `~/.ii_agent/storage`). You do **not** need MinIO for a laptop run.

### Auth

- HTTP: JWT Bearer only (`auth/dependencies.py`). `api_keys` rows are created on signup (`users/service.py`) but **not accepted** by `get_current_user`.
- Socket.IO: same JWT.
- Login: Google OAuth and II Hydra (`auth/router.py`). No `/auth/login`, no `/auth/refresh` (frontend still posts `/auth/refresh` and `/api/auth/logout` in `frontend/src/services/auth.service.ts`).
- Users have `password_hash` (`users/models.py`) but there is no password login API.

### Sandbox

| Config value | Enum | Implemented? |
|---|---|---|
| `e2b` (default) | `SandboxProviderType.E2B` | Yes — `agents/sandboxes/e2b.py` |
| `docker` | `SandboxProviderType.DOCKER` | Enum + config only. `_create_provider` raises. |
| `local` | accepted by `SandboxSettings` | Rejected in `_resolve_provider` |

`docker/sandbox/` is an image/entrypoint for a **sandbox VM**, not a host-local executor wired into `SandboxService`. `SANDBOX_SERVER_URL` / `sandbox-server` appear in `docker/docker-compose.stack.yaml` backend env, but **no `sandbox-server` service is defined** in that compose file.

---

## 2. Quality

### Tests

- ~330 files under `src/tests/`, mostly unit. Smoke tests exist (`src/tests/smoke/`) and one of them (`test_startup_health.py`) **skips the real lifespan** (no DB/Redis).
- `docs/QUALITY_SCORE.md` (2026-03-17) claims an 85% coverage gate (`pyproject.toml` `fail_under = 85`). That is a report setting, not evidence the suite currently meets it.
- `docs/CODE_REVIEW.md` (2026-03-29) is a **BLOCK** review of a refactor branch with broken imports. Treat it as historical; do not assume those exact crashes are still on `main`. It does show the tree has been through a large, incomplete-feeling domain split (`ii_agent` vs leftover `ii_server` / `ii_tool` names).
- No Windows CI, no Docker-sandbox tests, no llama-server / Custom-provider integration test that I found.

### Typing and structure

- Backend is generally typed (Pydantic v2, SQLAlchemy 2.0 `Mapped[]`). Contributor rules (Dep aliases, UUID PKs, reservation billing) are consistently documented and mostly followed in newer domains.
- Two architecture docs disagree on layout: `CLAUDE.md` uses `agents/`, `AGENTS.md` still shows `agent/`. Trust the code: `src/ii_agent/agents/`.
- Frontend is TypeScript; `frontend/README.md` lists `pnpm test` / `typecheck` but `frontend/package.json` has **no test or typecheck scripts**.

### Secrets and dangerous defaults

| Item | Where | Risk |
|---|---|---|
| JWT default `your-secret-key-change-in-production` | `core/config/settings.py:254` | Anyone who can hit a local/prod-misconfig box can mint tokens |
| `.env.example` JWT `local-dev-secret-change-in-production` | `.env.example:25` | Fine for laptop; fatal if copied to a shared host |
| Fernet key derived from `default-password-change-in-production` + `default-salt` | `core/secrets/encryption.py:113-114` | API keys in DB are encryptable by anyone who knows the defaults |
| CORS `allow_origins=["*"]` + `allow_credentials=True` | `app/middleware.py:21-27` | Spec-invalid combo; OAuth cookies + wildcard origin |
| MinIO `minioadmin/minioadmin` | compose + `.env.example` | Expected for local; do not expose the port |
| Session cookie `https_only=False` | `app/middleware.py:33` | Correct for local HTTP; must not ship to prod as-is |
| Beta bonus credits on by default (2000) | `core/config/credits.py` | New OAuth users get a large balance — fine locally, surprising in shared deploys |
| `ENCRYPTION_KEY` not in `.env.example` | — | Easy to rotate JWT and still decrypt with the baked default |

### Auth gaps

- No local email/password, no documented “mint a dev JWT” script.
- Frontend refresh/logout endpoints are missing on the backend.
- API keys are persisted and unused for HTTP/Socket auth.
- Waitlist is off by default (`CREDITS_WAITLIST_ENABLED`, default `False`). Good for local.

### Sandbox isolation

- **E2B isolation is real** (remote VM, not the G16 filesystem). That is the right security model for “agent can run shell.”
- There is **no local/Docker isolation implementation**. If someone later hacks a “run tools on the host” provider, that is a different threat model (agent with shell on the ROG).
- Default timeout 2 hours, auto-pause on (`core/config/sandbox.py`).

### Billing

- Agent/chat paths are supposed to use reservations, not `CreditService.deduct()` (contributor rule). System-key runs check `MINIMUM_REQUIRED_CREDITS` before start. BYOK (`is_user_model()`) skips that check — correct for a laptop with your own keys.
- Stripe/Cloud Run/TestFlight are production features. Ignore them for a G16 run.

---

## 3. Windows / G16 fitness

### What Docker actually provides

Two compose files, two jobs:

| File | What it runs | What it does **not** run |
|---|---|---|
| `docker/docker-compose.dev.yaml` | Postgres, Redis, MinIO | Backend, frontend, sandbox, GPU |
| `docker/docker-compose.stack.yaml` | Postgres, Redis, MinIO, backend image, frontend image | GPU, working local sandbox, **celery** (script expects it), **sandbox-server** (env refers to it) |

`scripts/run_stack.sh` does `compose_up celery` after backend. **There is no `celery` service** in `docker-compose.stack.yaml`. Full-stack Make is already broken on Linux, not just Windows.

Backend image (`docker/backend/Dockerfile`): Debian, `libmagic1`, fonts, Node, Ruby/fastlane, Playwright headless, `scripts/start.sh` which starts **Xvfb**. That image is a Linux workstation, not a Windows GPU box. The Dockerfile still comments that an SSH mount is required for private git repos; `pyproject.toml` / `uv.lock` on this public tree have **no `git+` / `ssh://` deps**. Leftover from a private build.

**Docker vs host-native**

- Docker (dev compose) = **only** Postgres/Redis/MinIO. Backend and UI still run on the host if you follow `make dev-all`.
- Docker (stack compose) = also wraps backend+frontend in Linux containers. Still **no GPU passthrough**, still **no local model**, still **E2B for tools**.
- Host-native Python/Node = the actual agent + UI. This is what you want on the G16 if the goal is later `llama-server` on the 4090. Docker cannot see that GPU unless you add NVIDIA Container Toolkit (Linux) — irrelevant on native Windows / no WSL.

### Native Windows without WSL

Docker Desktop’s Linux engine on Windows is WSL2 (or old Hyper-V). **If WSL is forbidden, do not use Docker Desktop.** Install PostgreSQL for Windows; use `STORAGE_PROVIDER=local`; leave Redis off.

Host Python risks on Windows:

| Dep / script | Why it hurts | Needed for “chat + agent with E2B”? |
|---|---|---|
| `Makefile`, `scripts/*.sh` | bash / `seq` / `command -v` | No — use PowerShell equivalents below |
| `scripts/start.sh` + Xvfb | Linux framebuffer | No — do not use this script |
| `python-magic` | needs libmagic DLL | Only if a tool imports it (`agents/tools/web/read_remote_image.py`) |
| `weasyprint` | GTK/Pango | PDF/print features |
| `pexpect`, `libtmux` | POSIX pty/tmux | Local terminal mux, not E2B |
| Playwright | browser binaries | Browser tools inside **E2B**, not necessarily on the host |
| `transformers` | heavy, not GPU serve | Import cost only |

The agent core (FastAPI, SQLAlchemy, Socket.IO, OpenAI/Anthropic SDKs, LiteLLM) is portable. The **packaging and sandbox story is Unix/cloud**.

### GPU

The 4090 (16 GB) is idle unless you start a local OpenAI-compatible server yourself. This repo will not load GGUF/safetensors, will not call CUDA, and will not pin a model in VRAM.

16 GB is enough for a useful local coder (e.g. Qwen2.5-Coder 14B Q4/Q5, Llama 3.1 8B, or a 32B Q3/Q4 if you accept context limits). It is **not** enough for the frontier models this UI is designed around (Claude / GPT-5-class / Gemini 3) at full quality.

---

## 4. Local-model path (Custom / llama-server)

**This path exists and is the right one.** Do not invent a new provider.

### Config

`model_configs.yaml` (from `model_configs.example.yaml`):

```yaml
- model_id: qwen2.5-coder-14b-instruct   # must match llama-server --alias / model id
  provider: Custom
  api_key: not-needed
  base_url: http://127.0.0.1:8080/v1
  display_name: Local llama-server
  is_default: true
  params:
    temperature: 0.7
```

Set in `.env`:

```env
MODEL_CONFIGS_FILE=model_configs.yaml
```

`base_url` is stored on `ModelSetting` and passed through both stacks (`settings/llm/seeding.py`, `agents/models/utils.py`, `chat/llm/custom.py`).

### Caveats (verify before promising a demo)

1. **Agent Custom uses Chat Completions**, not the OpenAI Responses API. That is what llama-server speaks. Good.
2. Agent Custom sets `reasoning_effort="high"` and `max_completion_tokens=64_000` (`agents/models/utils.py:107-109`). llama-server may ignore or reject these. If calls 400, strip those in a follow-up change — not required to boot the stack.
3. Chat Custom uses LiteLLM and, when `base_url` is set, `custom_llm_provider="openai"` (`chat/llm/custom.py:355`). Correct for llama-server.
4. Chat Custom injects its own system prompt (`chat/prompts/custom_system_prompt.py`). Agent Custom uses the full II agent prompt (long, tool-heavy). Small local models will follow tools poorly.
5. Browser tools send screenshots. A text-only local model will 400 (this already bit OpenRouter/Qwen users: issue #156). Disable browser / media tools for a local coder model.
6. `OpenAI` provider + `base_url` is **not** the local path — agent OpenAI is `OpenAIResponses`. Use **`provider: Custom`**.
7. From the G16, `base_url: http://localhost:8080/v1` works for host-native backend. If you later put the backend in Docker, `localhost` is the container — use `host.docker.internal`.

---

## 5. Top issues by severity

### Critical (will block a G16 “it works” demo)

| ID | Issue | Pointers |
|---|---|---|
| C1 | **No local login.** UI is Google or II OAuth only. Password form is dead. Without a Google OAuth client (or a hand-minted JWT + user row), you cannot use the product. | `frontend/src/app/routes/login.tsx` (`hideSigninWithPassword = true`); `auth/router.py` (OAuth only); `users/service.py::find_or_create_oauth_user` |
| C2 | **Sandbox is E2B-only.** `docker` / `local` are config lies. Agent file/shell/browser dies without `SANDBOX_E2B_API_KEY`. | `core/config/sandbox.py` (`SandboxProvider` includes `local`); `agents/sandboxes/service.py:549-580` |
| C3 | **Documented Windows/Docker path is the wrong path if WSL is forbidden.** README “Prerequisites: Docker” + `make dev-all` assumes Linux containers. | `README.md`; `Makefile`; `docker/docker-compose.dev.yaml` |
| C4 | **`make stack` / `run_stack.sh` is incomplete** even on Linux (celery service missing; sandbox-server referenced but absent). | `scripts/run_stack.sh:164`; `docker/docker-compose.stack.yaml` |

### High

| ID | Issue | Pointers |
|---|---|---|
| H1 | Frontend calls `/auth/refresh` and `/api/auth/logout`; backend has neither. Sessions die when the access token expires (default 15 min in settings, 43200 min in `.env.example` — inconsistent). | `frontend/src/services/auth.service.ts`; `core/config/settings.py:259`; `.env.example:24` |
| H2 | JWT + Fernet defaults are public strings. Fine on a closed laptop; unsafe on any LAN bind (`0.0.0.0`). | `settings.py:254`; `core/secrets/encryption.py:113-114` |
| H3 | CORS `*` + credentials. | `app/middleware.py:21-27` |
| H4 | Unix-only packaging: Make, bash, Xvfb `start.sh`, `python-magic`, WeasyPrint, pexpect/libtmux. | `scripts/start.sh`; `pyproject.toml`; `docker/backend/Dockerfile` |
| H5 | Port/docs drift: 5173 vs 1420; npm vs pnpm; frontend README lists tests that do not exist. | `Makefile:94-95`; `.env.example:34`; `frontend/README.md`; `frontend/package.json` |
| H6 | API keys created, never honored by `get_current_user`. | `users/service.py:117`; `auth/dependencies.py` |

### Medium

| ID | Issue | Pointers |
|---|---|---|
| M1 | Custom/local models get agent defaults aimed at Claude-class models (64k completion, reasoning_effort, huge system prompt). | `agents/models/utils.py:97-110`; `agents/prompts/` |
| M2 | `ii_server` / `ii_tool` / `ii_agent_tools` naming leftover from a private split. Public tree vendors `ii_server` and mocks `ii_tool` if missing. | `agents/factory/agent.py:9`; `agents/tools/clients.py` |
| M3 | Stack env still asks for GCS service-account path and E2B template IDs — copy-paste from prod. | `docker/.stack.env.example` |
| M4 | No `/auth/refresh` means the 15-minute default JWT is a footgun if someone omits `.env` `ACCESS_TOKEN_EXPIRE_MINUTES`. | `settings.py:259` |
| M5 | Official “full stack in Docker, no local Python/Node” claim in README is overstated given C4. | `README.md` “Docker Compose (Full Stack)” |

### Low

| ID | Issue | Pointers |
|---|---|---|
| L1 | `docs/CODE_REVIEW.md` and `docs/QUALITY_SCORE.md` are stale snapshots; easy to misread as current health. | `docs/` |
| L2 | `AGENTS.md` vs `CLAUDE.md` domain-map drift. | repo root |
| L3 | Community already hit Windows + sandbox confusion (issue #168). | GitHub #168 |

---

## 6. Shortest path — native Windows, no WSL

**Do not install Docker Desktop** if WSL is off the table. **Do not use `make`.** **Do not use `scripts/start.sh`.**

Goal: UI on `:1420`, API on `:8000`, Postgres on `:5432`, files on disk, cloud or local LLM, E2B only if you want agent tools.

### 0. Accounts you need

| For | Required? |
|---|---|
| PostgreSQL 15+ Windows installer | **Yes** |
| Python 3.12 (not 3.14 — see issue #165 / `fastmcp` pin) | **Yes** |
| Node 20+ LTS + npm | **Yes** |
| [uv](https://docs.astral.sh/uv/) for Windows | **Yes** |
| Google Cloud OAuth client (Web, redirect `http://localhost:8000/auth/oauth/google/callback`) **or** a SQL+JWT bootstrap (below) | **Yes** (one of the two) |
| At least one LLM: OpenAI/Anthropic/Google key **or** llama-server | **Yes** |
| E2B API key | Only for Agent tools / workspace |
| Redis / MinIO / Docker | **No** on this path |
| WSL | **No** |

### 1. Clone and env

In PowerShell:

```powershell
git clone https://github.com/Intelligent-Internet/ii-agent.git
cd ii-agent
copy .env.example .env
copy frontend\.env.example frontend\.env
copy model_configs.example.yaml model_configs.yaml
```

Edit `.env`:

```env
ENVIRONMENT=local
DATABASE_URL=postgresql+asyncpg://postgres:YOUR_PG_PASSWORD@127.0.0.1:5432/ii_agent
REDIS_SESSION_ENABLED=false
STORAGE_PROVIDER=local
STORAGE_LOCAL_BASE_DIR=%USERPROFILE%\.ii_agent\storage
JWT_SECRET_KEY=generate-a-long-random-string
ACCESS_TOKEN_EXPIRE_MINUTES=43200
OAUTHLIB_INSECURE_TRANSPORT=1
II_FRONTEND_URL=http://localhost:1420
MODEL_CONFIGS_FILE=model_configs.yaml

# Google OAuth (skip if you use the SQL bootstrap)
GOOGLE_CLIENT_ID=....apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=....
GOOGLE_REDIRECT_URI=http://localhost:8000/auth/oauth/google/callback

# Agent tools (optional)
# SANDBOX_PROVIDER=e2b
# SANDBOX_E2B_API_KEY=e2b_...
```

`frontend/.env`:

```env
VITE_API_URL=http://localhost:8000
VITE_GOOGLE_CLIENT_ID=....apps.googleusercontent.com
VITE_PORT=1420
```

### 2. Postgres

Install [PostgreSQL 15+](https://www.postgresql.org/download/windows/). In `psql`:

```sql
CREATE DATABASE ii_agent;
```

### 3. Models

**Cloud BYOK (fewest surprises):** uncomment one block in `model_configs.yaml` (OpenAI / Anthropic / Google), set `is_default: true`.

**Local GPU (later):** run llama-server on the 4090, then:

```yaml
- model_id: qwen2.5-coder-14b-instruct
  provider: Custom
  api_key: not-needed
  base_url: http://127.0.0.1:8080/v1
  display_name: Local llama-server
  is_default: true
```

Keep browser/media tools off for text-only local models.

### 4. Install and migrate

```powershell
uv sync --frozen
uv run alembic upgrade head
cd frontend
npm install
cd ..
```

If `uv sync` fails on `python-magic` / WeasyPrint, that is the first real Windows-dep gate. `python-magic-bin` (unofficial) or installing [File for Windows / libmagic](https://github.com/nscaife/file-windows) is the usual fix. WeasyPrint can wait until you need PDF.

### 5. Run

Two terminals:

```powershell
uv run python -m ii_agent.ws_server --reload --port 8000
```

```powershell
cd frontend
npm run dev
```

Check `http://localhost:8000/health` → `{"status":"ok"}` and `http://localhost:1420`.

### 6. Log in

**Preferred:** Google OAuth with the localhost redirect above. First login creates the user and a credit balance (`users/service.py::create_user`).

**If you will not stand up Google:** bootstrap a user and JWT (same secret as `.env`):

```powershell
uv run python -c "
import uuid
from datetime import datetime, timezone, timedelta
import jwt, asyncio
from sqlalchemy import text
from ii_agent.core.db.base import get_session_factory

async def main():
    uid = uuid.uuid4()
    factory = get_session_factory()
    async with factory() as db:
        await db.execute(text('''
            INSERT INTO users (id, email, role, is_active, email_verified, language, created_at, updated_at)
            VALUES (:id, :email, 'user', true, true, 'en', now(), now())
        '''), {'id': uid, 'email': 'g16@local.dev'})
        await db.commit()
    print(uid)

asyncio.run(main())
"
```

Then mint an access token with `JWTHandler.create_access_token` (or `pyjwt` HS256, claims `user_id`, `email`, `role`, `type=access`, `exp`, `iat`) using `JWT_SECRET_KEY`, and set `localStorage.access_token` on `http://localhost:1420`. You also need a `credit_balances` row or a BYOK user model — easiest is to complete one Google login once, or call `CreditService.ensure_balance_exists` from a similar snippet.

This bootstrap is a **laptop workaround**, not a product feature.

### 7. What “working” means on day one

| Capability | Without E2B | With E2B + cloud LLM | With Custom + llama-server |
|---|---|---|---|
| Login + session list | Yes (after OAuth/JWT) | Yes | Yes |
| Chat (REST/SSE) | Yes | Yes | Yes, if the model speaks Chat Completions |
| Agent Q&A with no tools | Yes | Yes | Fragile on small models |
| Agent shell / files / browser / “build a site” | **No** | Yes | LLM quality limited; sandbox still E2B |
| Use the 4090 | **No** | **No** | **Yes** (llama-server only) |
| Slides / storybook / media / Cloud Run / TestFlight | Extra keys + E2B + often GCS | Same | Do not start here |

### If you later allow WSL or Hyper-V Docker

Then Docker Desktop is useful **only** as a Postgres/Redis/MinIO appliance (`docker compose -f docker/docker-compose.dev.yaml up -d`). Still run Python/Node on the host so `base_url: http://127.0.0.1:8080/v1` reaches llama-server. Still do not expect `make stack` to be the golden path (C4).

---

## 7. `ii-agent-prod` vs this repo

- This environment **cannot read** `Intelligent-Internet/ii-agent-prod` (GitHub API 404). It is almost certainly private.
- Public docs are published from that name: [intelligent-internet.github.io/ii-agent-prod](https://intelligent-internet.github.io/ii-agent-prod/). The homepage describes the same `make setup` / `make dev-all` / domain map as this tree.
- Public issues (#189, #205) ask when “V1” / “Factory” will be open-sourced — social evidence that **prod is ahead of, or separate from, the public snapshot**.
- In-repo leftovers that smell like an export from a larger private tree: `ii_server` package, `ii_agent_tools` fallback, stack compose env for `sandbox-server` / celery / GCS, Dockerfile SSH mount comments, dead password UI.

**Practical rule:** treat **this public repo** as the thing you can run. Treat **ii-agent-prod** as the likely source of unpublished sandbox-server, fuller compose, and docs. Do not assume they are identical. Someone with org access should diff `SandboxService`, auth, and `docker-compose.stack.yaml` before betting a demo on public `main`.

---

## 8. Recommended next actions (not done in this review)

This review intentionally does **not** ship drive-by code. If you want follow-up PRs, in order:

1. **Local-dev auth:** a guarded `ENVIRONMENT=local` email login or `scripts/dev_token.py` that inserts a user + prints a JWT. Unblocks C1 without Google.
2. **Honest sandbox docs:** README + `.env.example` stating E2B is required for agent tools; `docker`/`local` are unimplemented.
3. **Windows section in README:** the recipe in §6 (Postgres native, no Docker, Custom `base_url`).
4. **Custom-provider knobs:** do not send `reasoning_effort` / 64k `max_completion_tokens` to llama-server.
5. **Fix or delete `make stack`** until celery/sandbox-server exist in compose.

---

## Appendix — file map for the G16 discussion

| Question | Read first |
|---|---|
| How do I add a local model? | `model_configs.example.yaml`, `settings/llm/seeding.py`, `agents/models/utils.py`, `chat/llm/custom.py` |
| Does a query hit the GPU? | `agents/factory/agent.py` → `get_model()` → cloud SDK or HTTP `base_url` |
| When is E2B created? | `agents/tools/sandbox/base.py`, `agents/sandboxes/service.py` |
| How does the UI talk to the agent? | `docs/CODEMAPS/frontend.md`, `realtime/manager.py`, `realtime/handlers/query.py` |
| What does Docker buy me? | `docker/docker-compose.dev.yaml` (infra only), `docker/docker-compose.stack.yaml` (Linux app images) |
| Can I skip MinIO/Redis? | `core/config/storage.py`, `core/storage/providers/local.py`, `core/config/redis.py` |
| How do users get created? | `users/service.py::find_or_create_oauth_user`, `auth/router.py` |
