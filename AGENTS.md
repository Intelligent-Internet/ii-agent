# II-Agent Contributor Guide

This file is the entry point for agents working in this repository. It provides the architecture overview plus a map to deeper documentation.

**Read `CLAUDE.md` for the full development reference** (patterns, billing system, dependency injection, code examples).

## Quick Start

```bash
uv sync --frozen          # Install dependencies
./scripts/start.sh        # Start the server
curl localhost:8000/health # Verify
```

## Repository Map

| Resource | What it covers |
|----------|---------------|
| [`CLAUDE.md`](CLAUDE.md) | Full development guide: patterns, billing, dependency injection, code examples |
| [`docs/DESIGN.md`](docs/DESIGN.md) | Design patterns: service pattern, Dep aliases, domain module structure |
| [`docs/PLANS.md`](docs/PLANS.md) | How to write and maintain execution plans |
| [`docs/RELIABILITY.md`](docs/RELIABILITY.md) | Billing reliability, cron recovery, Redis fallbacks |
| [`docs/SECURITY.md`](docs/SECURITY.md) | Auth flow (OAuth, JWT, API keys), secrets management |
| [`docs/FRONTEND.md`](docs/FRONTEND.md) | Socket.IO events, REST API surface, real-time event flow |
| [`docs/PRODUCT_SENSE.md`](docs/PRODUCT_SENSE.md) | Product principles, user personas, key journeys |
| [`docs/QUALITY_SCORE.md`](docs/QUALITY_SCORE.md) | Per-domain quality grades and health metrics |
| [`docs/design-docs/`](docs/design-docs/index.md) | Indexed design decisions with verification status |
| [`docs/exec-plans/`](docs/exec-plans/) | Active and completed execution plans |
| [`docs/generated/db-schema.md`](docs/generated/db-schema.md) | Database schema reference (from SQLAlchemy models) |
| [`docs/product-specs/`](docs/product-specs/index.md) | Product specifications |
| [`docs/references/`](docs/references/) | LLM-optimized reference material for key dependencies |

## Mandatory Rules

1. **Use `uv run`** for all Python commands (`uv run pytest`, `uv run python ...`).
2. **Run Ruff only on the Python files you changed** before marking work complete (`uv run ruff check --fix-only <changed_python_files>`, `uv run ruff format <changed_python_files>`, `uv run ruff check <changed_python_files>`, `uv run ruff format --check <changed_python_files>`). If you changed no Python files, skip Ruff.
3. **Never call `CreditService.deduct()` directly** for LLM/tool billing — use the reservation system (see `CLAUDE.md` Billing section).
4. **Use Dep aliases everywhere** — never bare `= Depends(get_x)` in function signatures (see `CLAUDE.md` Dependency Injection Pattern).
5. **Use `LLMExecutionService`** for any new code that calls an LLM outside the agent runtime loop.

## Architecture

### Domain Map

II-Agent is organized into domain modules under `src/ii_agent/`. Each domain owns its models, repository, service, dependencies, router, and schemas.

```text
src/ii_agent/
├── app/                    # FastAPI bootstrap package, middleware, lifespan, router wiring
│
├── core/                   # Shared infrastructure (no business logic)
│   ├── config/             # Pydantic settings (database, redis, storage, oauth, stripe)
│   ├── db/                 # SQLAlchemy 2.0 base, async session management, migrations
│   ├── llm/                # LLM billing service, execution service, base client
│   ├── redis/              # Redis client, cache, pubsub, lock, cancel management
│   ├── secrets/            # GCP Secret Manager integration
│   ├── storage/            # File storage abstraction (GCS, MinIO)
│   ├── container.py        # ServiceContainer for complex dependency graphs
│   └── dependencies.py     # DBSession, SettingsDep (shared Dep aliases)
│
├── auth/                   # Authentication & authorization
│   ├── jwt_handler.py      # JWT creation/verification (HS256)
│   ├── oidc_verify.py      # OIDC token verification (RS/ES families)
│   ├── api_key_utils.py    # API key generation
│   └── users/              # User profiles, CRUD, waitlist
│
├── billing/                # Credit ledger & billing
│   ├── credits/            # Balance, ledger, pricing, service
│   ├── reservations/       # Reserve -> settle -> release state machine
│   ├── usage/              # Usage records, LLM/tool invocation telemetry
│   ├── customers/          # Stripe customer management
│   └── webhook_handler.py  # Stripe webhook processing
│
├── sessions/               # Chat session management
│   ├── models.py           # Session model, SessionStateEnum, AppKind, delete_after
│   ├── service.py          # Session CRUD, state transitions
│   ├── fork_service.py     # Session forking
│   ├── title_service.py    # Auto-title generation
│   ├── wishlist/           # Session bookmarks
│   └── pin/                # Pinned sessions
│
├── agent/                  # Agent execution framework
│   ├── application/        # Validation, execution orchestration
│   ├── runtime/            # Agent runtime models, streaming
│   ├── runs/               # Agent run task management
│   ├── events/             # Event handling & logging
│   ├── prompts/            # System prompts & templates
│   ├── sandboxes/          # E2B sandbox management
│   ├── socket/             # Socket.IO command handlers (query, cancel, plan)
│   └── subscribers/        # Event subscribers (metrics, database)
│
├── chat/                   # Chat API & LLM providers
│   ├── api/                # Chat REST endpoints
│   ├── llm/                # LLM provider implementations (Anthropic)
│   ├── media/              # Media processing (image gen, video gen, web search)
│   ├── runs/               # Chat run management
│   ├── tools/              # Chat tools (code interpreter, tool registry)
│   └── vectorstore/        # Vector store integration (OpenAI)
│
├── content/                # Content generation
│   ├── media/              # Media templates, tools, config
│   ├── skills/             # Custom skills management
│   ├── slides/             # Slide/presentation generation + templates + design
│   └── storybook/          # Storybook generation
│
├── files/                  # File upload/download service
│
├── integrations/           # External integrations
│   ├── a2a/                # Agent-to-Agent protocol
│   ├── connectors/         # External connectors (GitHub, Google Drive via Composio)
│   ├── enhance_prompt/     # Prompt enhancement
│   └── mobile/             # Mobile platform integrations (Apple, future Android)
│
├── projects/               # Project & deployment management
│   ├── cloud_run/          # Google Cloud Run deployment
│   ├── databases/          # Database provisioning
│   ├── deployments/        # Deployment orchestration
│   ├── design/             # Project design
│   ├── secrets/            # Project-level secrets
│   └── subdomains/         # Subdomain management
│
├── settings/               # User settings
│   ├── llm/                # User LLM model preferences
│   └── mcp/                # MCP server configuration
│
├── utils/                  # Shared utilities
├── workers/                # Background jobs (Celery cron)
├── scripts/                # Admin scripts
└── ws_server.py            # WebSocket server entry point
```

### Layer Architecture

Within each domain, code follows a fixed layer hierarchy. Dependencies flow downward only.

```text
    Router (FastAPI endpoints)
      |
    Dependencies (Dep aliases, factory functions)
      |
    Service (business logic, takes db: AsyncSession)
      |
    Repository (data access, SQLAlchemy queries)
      |
    Models (SQLAlchemy 2.0 declarative models)
      |
    Schemas (Pydantic DTOs for request/response)
```

### Layer Rules

- **Models** may only import from `core.db` and standard library.
- **Repository** imports models and core utilities. Never imports services.
- **Service** imports repository and models. May import other services' Dep aliases for cross-domain work.
- **Dependencies** defines factory functions and Dep aliases. Imports services and repositories.
- **Router** imports Dep aliases from dependencies. Never imports repositories directly.
- **Schemas** are pure Pydantic models. No database or service imports.

### Cross-Cutting Concerns

These `core/` modules are available to all domains:

| Module | Purpose | Key exports |
|--------|---------|-------------|
| `core/config/` | Application settings | `Settings`, `get_settings()` |
| `core/db/` | Database connection | `Base`, `TimestampColumn`, `get_db_session_local()` |
| `core/redis/` | Caching, pubsub, locks | `redis_client`, `EntityCache`, `AsyncIOPubSub` |
| `core/storage/` | File storage (GCS, MinIO) | `BaseStorage`, `storage`, `media_storage` |
| `core/llm/` | LLM billing & execution | `LLMBillingService`, `LLMExecutionService` |
| `core/secrets/` | Secret management | GCP Secret Manager integration |
| `core/dependencies.py` | Shared Dep aliases | `DBSession`, `SettingsDep` |
| `core/container.py` | Service container | `ServiceContainer` |

### Request Flow

```text
HTTP Request
  -> FastAPI middleware (CORS, trusted hosts)
    -> Auth dependency (get_current_user -> JWT/OIDC/API key verification)
      -> Router endpoint
        -> Service (business logic + billing reservation if needed)
          -> Repository (SQLAlchemy queries)
            -> PostgreSQL
          -> External APIs (LLM providers, GCS, Stripe, E2B)
        -> Response schema (Pydantic serialization)
  -> HTTP Response

WebSocket (Socket.IO)
  -> Socket.IO server (app/)
    -> Auth via handshake token
      -> Command handler (agent/socket/)
        -> Agent runtime (agent/runtime/)
          -> LLM provider (streaming)
          -> Tool execution (sandboxes, file system, web)
        -> Event subscribers (metrics, database persistence)
      -> Real-time events back to client
```

### API Surface

| Router | Prefix | Domain |
|--------|--------|--------|
| auth | `/auth` | Authentication |
| users | `/auth/me` | User profiles |
| sessions | `/sessions` | Chat sessions |
| credits | `/credits` | Credit balance |
| billing | `/billing` | Stripe billing |
| chat | `/chat` | Chat API |
| files | `/files` | File uploads |
| project | `/project` | Projects |
| subdomains | `/subdomains` | Subdomain management |
| llm_settings | `/user-settings/models` | LLM preferences |
| mcp_settings | `/user-settings/mcp` | MCP config |
| skills_settings | `/user-settings/skills` | Custom skills |
| slides | `/slides` | Slide generation |
| slide_templates | `/slide-templates` | Slide templates |
| storybook | `/storybooks` | Storybook generation |
| media | `/media` | Media generation |
| media_templates | `/media-templates` | Media templates |
| media_tools | `/media-tools` | Media tools |
| connectors | `/connectors` | External connectors |
| enhance_prompt | `/enhance-prompt` | Prompt enhancement |
| wishlist | `/wishlist` | Session bookmarks |
| pin | `/pin` | Pinned sessions |
| project_design | `/projects/design` | Project design |
| slide_design | `/slides/design` | Slide design |
| nano_banana | `/slides/nano-banana` | Nano banana slides |
| health | `/health` | Health check |
| storage_proxy | `/storage` | Storage proxy (local deploy) |
| slide_assets | `/files/slides/assets` | Slide assets |
| sandbox_files | `/sandbox-files` | Sandbox file preview |

### Key Design Decisions

- **SQLAlchemy 2.0 async**: All database access uses `AsyncSession` with `mapped_column` style.
- **Dep aliases everywhere**: FastAPI dependency injection uses `Annotated[T, Depends(factory)]` pattern exclusively.
- **Redis optional**: All Redis usage has in-memory fallbacks for single-worker deployments.
- **Billing via reservations**: All billable work uses reserve -> settle -> release, never direct deductions.
- **GCS/MinIO for storage**: File uploads, media, and slides use Google Cloud Storage (prod) or MinIO (local Docker) with signed or proxied URLs.
- **E2B/Docker for sandboxes**: Code execution happens in isolated E2B (cloud) or Docker (local) sandbox environments. Docker sandboxes use `read_only=True` + tmpfs. File ownership rules: `/workspace` is `user:user 755` (uid=1001); **never use `user="root"` for operations under `/workspace`**. All host-mediated uploads (`write_file`/`put_archive`) must target `/workspace`, not `/tmp`. See [`docs/design-docs/sandbox-filesystem-design.md`](docs/design-docs/sandbox-filesystem-design.md).
- **A2A optional extras**: `a2a-sdk` and `github-copilot-sdk` are optional deps (`pip install -e ".[a2a]"`). Backend runs without them; adapter server inside sandbox always has them.
- **Chat A2A is sandbox-independent**: When `AGENT_CHAT_INNER_LOOP_MODE=a2a`, set `AGENT_A2A_AGENT_URL` to a standalone adapter (the local Docker stack ships an `a2a-adapter` sidecar at `http://a2a-adapter:18100`). With `AGENT_A2A_CHAT_STRICT=true` (default) a missing URL **crashes the backend at startup** — silent native-LLM fallback has historically cost real money. See [docs/design-docs/chat-a2a-adapter-sidecar.md](docs/design-docs/chat-a2a-adapter-sidecar.md).
- **A2A fallback**: Genuine runtime A2A failures (circuit breaker open, rate-limit `session.error`, transport error) transparently fall back to native LLM when `AGENT_A2A_FALLBACK_TO_NATIVE=true` (default). No double-billing. Misconfig is gated separately by `AGENT_A2A_CHAT_STRICT`.

## Where to Look

| Task | Start here |
|------|-----------|
| Understand the full architecture | The [Architecture](#architecture) sections in this file |
| Add a new domain module | `CLAUDE.md` > "Adding a New Domain" |
| Add a new API endpoint | `CLAUDE.md` > "Router Pattern" + the [Architecture](#architecture) sections in this file |
| Work on billing / credits | `CLAUDE.md` > "Billing & Credit System" + [`docs/RELIABILITY.md`](docs/RELIABILITY.md) |
| Add a new LLM feature | `CLAUDE.md` > "Rules for New Code" |
| Add a billable tool | `CLAUDE.md` > "Adding a new billable tool" |
| Understand auth flow | [`docs/SECURITY.md`](docs/SECURITY.md) |
| Work on WebSocket events | [`docs/FRONTEND.md`](docs/FRONTEND.md) |
| Review design decisions | [`docs/design-docs/`](docs/design-docs/index.md) |
| Sandbox file ownership & write paths | [`docs/design-docs/sandbox-filesystem-design.md`](docs/design-docs/sandbox-filesystem-design.md) |
| Plan multi-step work | [`docs/PLANS.md`](docs/PLANS.md) |
| Check code quality | [`docs/QUALITY_SCORE.md`](docs/QUALITY_SCORE.md) |
| Understand the database | [`docs/generated/db-schema.md`](docs/generated/db-schema.md) |

## Development Workflow

1. Create a feature branch from `develop`.
2. Implement changes following patterns in `CLAUDE.md`.
3. Run Ruff on the Python files you changed.
4. Run tests: `uv run pytest`.
5. For complex work, create an ExecPlan (see [`docs/PLANS.md`](docs/PLANS.md)).

## Key Commands

```bash
make install          # Install deps + pre-commit hooks
uv run ruff check --fix-only <changed_python_files>
uv run ruff format <changed_python_files>
uv run ruff check <changed_python_files>
uv run ruff format --check <changed_python_files>
uv run pytest         # Run tests
uv run pytest -k "test_name"  # Run specific test
./scripts/start.sh    # Start server (Xvfb + uv run python -m ii_agent.ws_server)
uv run python -m ii_agent.ws_server  # Start server directly
```
