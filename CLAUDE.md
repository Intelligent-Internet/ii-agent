# II-Agent Project Guide

## Project Overview

II-Agent is an AI agent platform built with FastAPI and SQLAlchemy 2.0. The codebase follows a domain-driven architecture where business logic is organized into domain modules.

## Architecture

### Domain Structure

```
src/ii_agent/
├── app/                        # FastAPI factory, router registration, lifespan, middleware
│
├── core/                       # Shared infrastructure & configuration
│   ├── config/                 # 13+ Pydantic settings classes (DB, Redis, Storage, Stripe, OAuth, LLM...)
│   ├── db/                     # SQLAlchemy 2.0 Base (UUID PK, DateTime timestamps), engine, session deps
│   ├── llm/                    # LLM billing service, execution service, base utilities
│   ├── middleware/              # CORS, request tracing, exception handling
│   ├── redis/                  # Async Redis client, cache, cancel tokens
│   ├── storage/                # GCS/MinIO file storage abstraction + path resolver
│   └── container.py            # ApplicationContainer singleton (global + app.state)
│
├── auth/                       # OAuth 2.0, JWT (uuid.UUID user_id), session management
├── users/                      # User CRUD, API keys
│
├── billing/                    # Stripe webhooks, payment transactions
├── credits/                    # Credit balance, transactions
│
├── tasks/                      # Unified run lifecycle tracker (RunTask + TaskLog) -- CANONICAL DOMAIN
│
├── sessions/                   # Chat sessions (CRUD, state, fork, title, timed delete)
│   ├── pin/                    # Session pins
│   └── wishlist/               # Session wishlists/bookmarks
│
├── chat/                       # Chat API & LLM providers
│   ├── api/                    # Chat REST endpoints
│   ├── application/            # Chat orchestration (chat_service, tool_service, context, turn loop)
│   ├── llm/                    # LLM provider implementations (Anthropic, etc.)
│   ├── media/                  # Media processing (handlers, modes, services, utils)
│   ├── messages/               # Chat message storage & history
│   ├── prompts/                # Chat system prompts
│   ├── providers/              # Provider containers, files, vector stores
│   ├── runs/                   # Chat run management
│   ├── tools/                  # Chat tools (code interpreter, tool registry)
│   └── vectorstore/            # Vector store integration (OpenAI)
│
├── agents/                     # Agent execution framework
│   ├── models/                 # LLM provider models (Anthropic, OpenAI, Google, Cerebras, VertexAI)
│   ├── runs/                   # Agent run management (AgentRunTask)
│   ├── sandboxes/              # Sandbox environment management (E2B/Docker/local)
│   ├── skills/                 # Skills framework (built-in + custom)
│   ├── tools/                  # Tool implementations (13 categories, 100+ tools)
│   └── ...                     # connector, hooks, media, prompts, sessions, utils
│
├── content/                    # Content generation
│   ├── media/                  # Media templates & tools
│   ├── slides/                 # Slide/presentation generation
│   └── storybook/              # Storybook generation
│
├── files/                      # File upload/download, user & session assets
│
├── integrations/               # External integrations
│   ├── connectors/             # External connectors (GitHub, Google Drive, Composio)
│   ├── enhance_prompt/         # Prompt enhancement service
│   └── mobile/                 # Mobile integrations (Apple credentials)
│
├── projects/                   # Project & deployment management
│   ├── cloud_run/              # Google Cloud Run deployment
│   ├── databases/              # Database provisioning
│   ├── deployments/            # Deployment management
│   ├── design/                 # Project design preview
│   ├── secrets/                # Project secrets management
│   └── subdomains/             # Subdomain management
│
├── realtime/                   # Real-time communication
│   ├── events/                 # Event handling & persistence
│   ├── handlers/               # Socket.IO command handlers (21 total)
│   └── pubsub/                 # Async pub/sub (SioCallback + DatabaseCallback)
│
├── settings/                   # Admin/user settings (LLM, MCP, skills)
│
└── workers/                    # Background jobs
    ├── celery/                 # Celery task definitions & decorators
    └── cron/                   # Scheduled jobs (credit refresh, sandbox timeout)
```

### ORM Base & ID Conventions

All models inherit from `Base` (`core/db/base.py`) which provides:

```python
from ii_agent.core.db.base import Base, TimestampColumn

class Base(DeclarativeBase):
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True,
        server_default=text("gen_random_uuid()"), default=uuid.uuid4,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

TimestampColumn = DateTime(timezone=True)  # Reusable for extra timestamp columns
```

**ID rules:**
- All entity PKs: `uuid.UUID` (inherited from Base -- do NOT override with `str`)
- All FK columns: `Mapped[uuid.UUID]` with `UUID(as_uuid=True)`
- Exception: `TaskLog.id` and `AgentRunMessage.id` use `BigInteger` autoincrement
- External system IDs (`stripe_customer_id`, `composio_entity_id`, etc.) stay as `str`

**Timestamp rules:**
- All timestamps use `DateTime(timezone=True)` via `TimestampColumn`
- Do NOT use `TIMESTAMP(timezone=True)` directly -- always use `TimestampColumn`

### Bootstrap Sequence (`app/lifespan.py`)

```
Startup:
  1. DB engine + pool
  2. Redis client
  3. Alembic migrations (unless II_AGENT_SKIP_MIGRATIONS=true)
  4. ApplicationContainer.init() + set_app_container() (global singleton)
  5. PubSub (SioCallbackHandler + DatabaseCallbackHandler)
  6. SocketIOManager (register handlers)
  7. Seed: admin LLM settings + built-in skills
  8. APScheduler cron start

Shutdown: reverse order (cron -> sio -> pubsub -> db -> redis)
```

### Request Flow

```
HTTP:  Client -> CORS -> Session -> Tracing -> Exception -> GZip -> FastAPI Router -> Service -> Repository -> DB
WS:    Client -> Socket.IO connect (JWT auth) -> join_session -> chat_message -> CommandHandlerFactory -> Handler -> PubSub -> SioCallback -> Client
```

### Event System

```
Handler emits -> PubSub.publish(topic, event)
  +-- SioCallbackHandler -> Socket.IO room broadcast
  +-- DatabaseCallbackHandler -> application_events table
```

### Agent Execution

```
Socket "chat_message" -> CommandHandlerFactory
  -> QueryHandler / PlanHandler / ContinueHandler
    -> AgentRunService -> Agent (agents/agent.py)
      -> LLM Provider (Anthropic/OpenAI/Google/Cerebras/VertexAI)
      -> Tools (13 categories, 100+ tools)
      -> Skills (built-in + custom)
      -> Sandbox (E2B/Docker/local)
```

## API Routes

| Prefix | File | Tags |
|--------|------|------|
| `/` | `app/health.py` | Health |
| `/auth` | `auth/router.py` | Authentication (OAuth, JWT) |
| `/auth` | `users/router.py` | Users (CRUD, profile) |
| `/billing` | `billing/router.py` | Billing (Stripe) |
| `/credits` | `credits/router.py` | Credits (balance, transactions) |
| `/v1/chat` | `chat/api/router.py` | Chat API |
| `/sessions` | `sessions/router.py` | Sessions |
| `/pin` | `sessions/pin/router.py` | Session Pins |
| `/wishlist` | `sessions/wishlist/router.py` | Session Wishlists |
| `/user-settings/models` | `settings/llm/router.py` | LLM Settings |
| `/user-settings/mcp` | `settings/mcp/router.py` | MCP Settings |
| `/user-settings/skills` | `settings/skills/router.py` | Skills Settings |
| `/files` | `files/router.py` | File Upload/Download |
| `/slides` | `content/slides/router.py` | Slides |
| `/slide-templates` | `content/slides/templates/router.py` | Slide Templates |
| `/slides/design` | `content/slides/design/router.py` | Slide Design |
| `/slides/nano-banana` | `content/slides/nano_banana/router.py` | Nano Banana |
| `/storybooks` | `content/storybook/router.py` | Storybooks |
| `/media`, `/media-templates`, `/media-tools` | `content/media/router.py` | Media |
| `/project` | `projects/router.py` | Projects |
| `/projects/design` | `projects/design/router.py` | Project Design |
| `/subdomains` | `projects/subdomains/router.py` | Subdomains |
| `/connectors/composio` | `integrations/connectors/composio/router.py` | Composio |
| `/connectors` | `integrations/connectors/router.py` | Connectors (GitHub, Google) |
| `/enhance-prompt` | `integrations/enhance_prompt/router.py` | Prompt Enhancement |
| `/storage` | `files/storage_proxy_router.py` | Storage Proxy (local deploy) |
| `/files/slides/assets` | `files/slide_assets_router.py` | Slide Assets |
| `/sandbox-files` | `files/sandbox_files_router.py` | Sandbox File Preview |

Router registration: `app/routers.py::include_routers(app)`

## Middleware Chain (`app/middleware.py`)

```
1. CORSMiddleware (all origins)
2. SessionMiddleware (OAuth session secret)
3. request_tracing_middleware (request context)
4. exception_logging_middleware (error logging)
5. GZipMiddleware (compression)
+ Global: ii_agent_error_handler for IIAgentError
```

## Socket.IO Handlers (`realtime/handlers/`)

| Command | Handler | Purpose |
|---------|---------|---------|
| `query` | `UserQueryHandler` | Main agent execution |
| `plan` | `PlanHandler` | Planning mode |
| `continue_run` | `ContinueRunHandler` | Resume agent |
| `cancel` | `CancelHandler` | Cancel execution |
| `ping` | `PingHandler` | Keep-alive |
| `awake_sandbox` | `AwakeSandboxHandler` | Wake sandbox |
| `sandbox_status` | `SandboxStatusHandler` | Check sandbox |
| `workspace_info` | `WorkspaceInfoHandler` | Workspace details |
| `enhance_prompt` | `EnhancePromptHandler` | Prompt enhancement |
| `publish` | `PublishProjectHandler` | Publish project |
| `cloud_run_publish` | `CloudRunPublishHandler` | Deploy to Cloud Run |
| `save_env` | `SaveEnvHandler` | Save env vars |
| `start_fork` | `StartForkHandler` | Fork session |
| `submit_testflight` | `SubmitTestflightHandler` | iOS TestFlight |
| `apple_auth` | `AppleAuthLoginHandler` | Apple OAuth login |
| `apple_auth_2fa` | `AppleAuth2FAHandler` | Apple 2FA |
| `apple_auth_select_team` | `AppleAuthSelectTeamHandler` | Apple team selection |
| `apple_app_setup` | `AppleAppSetupHandler` | Apple app config |
| `apple_list_apps` | `AppleListAppsHandler` | List Apple apps |
| `apple_check_auth` | `AppleCheckAuthHandler` | Check Apple auth |
| `save_expo_token` | `SaveExpoTokenHandler` | Save push token |

Factory: `realtime/handlers/factory.py::CommandHandlerFactory`

## Service-Repository Mapping

| Domain | Service | Repository |
|--------|---------|------------|
| users | `UserService` | `UserRepository`, `APIKeyRepository` |
| sessions | `SessionService` | `SessionRepository` |
| sessions/pin | `SessionPinService` | `PinRepository` |
| sessions/wishlist | `SessionWishlistService` | `WishlistRepository` |
| tasks | `RunTaskService` | `RunTaskRepository`, `TaskLogRepository` |
| chat/messages | `MessageService` | `ChatMessageRepository` |
| agents/runs | `AgentRunService` | `AgentRunTaskRepository` |
| billing | `BillingService` | (via Stripe API) |
| credits | `CreditService` | (credit models) |
| files | `FileService` | `FileRepository` |
| projects | `ProjectService` | `ProjectRepository` |
| projects/deployments | `DeploymentsService` | `DeploymentsRepository` |
| projects/databases | `DatabaseService` | `ProjectDatabaseRepository` |
| projects/subdomains | `SubdomainService` | `SubdomainRepository` |
| projects/design | `ProjectDesignService` | `ProjectDesignRepository` |
| content/slides | `SlideService` | `SlideContentRepository` |
| content/media | `MediaTemplateService` | `MediaTemplateRepository` |
| content/storybook | `StorybookService` | `StorybookRepository` |
| integrations/connectors | `ConnectorService` | `ConnectorRepository` |
| integrations/composio | `ComposioService` | `ComposioProfileRepository` |
| integrations/apple | `AppleCredentialService` | `AppleCredentialRepository` |
| settings/llm | `LLMSettingService` | `LLMSettingRepository` |
| settings/mcp | `MCPSettingService` | `MCPSettingRepository` |
| settings/skills | `SkillService` | `SkillRepository` |
| realtime/events | -- | `EventRepository` |

## Data Model (38 tables)

### Key Tables by Domain

**User & Auth:** `users`, `api_keys`
**Sessions:** `sessions`, `session_pins`, `session_wishlists`
**Chat:** `chat_messages`, `chat_summaries`, `chat_provider_containers`, `chat_provider_files`, `chat_provider_vector_stores`
**Tasks (canonical):** `run_tasks` (UUID PK), `task_logs` (BigInteger PK)
**Agent:** `agent_run_tasks` (UUID PK), `agent_run_messages` (BigInteger PK)
**Settings:** `llm_settings`, `mcp_settings`, `skills`
**Billing & Credits:** `billing_transactions`, `credit_balances`, `credit_transactions`
**Files:** `user_assets`, `session_assets`
**Projects:** `projects`, `project_deployments`, `project_databases`, `project_custom_domains`
**Content:** `slide_contents`, `slide_versions`, `slide_templates`, `media_templates`, `storybooks`, `storybook_pages`, `storybook_page_links`
**Integrations:** `connectors`, `composio_profiles`, `apple_credentials`
**Events:** `application_events`

### Key Relationships

```
User 1──N Session 1──N ChatMessage
User 1──N APIKey
User 1──N CreditBalance (1 per user)
User 1──N CreditTransaction
User 1──N BillingTransaction
User 1──N FileAsset
Session 1──N SessionAsset
Session 1──N RunTask 1──N TaskLog
Session 1──N ChatRun 1──N AgentRunTask
Session 1──N SessionPin
Session 1──N SessionWishlist
Session 1──N ApplicationEventModel
Project 1──N ProjectDeployment
Project 1──N ProjectDatabase
Project 1──N ProjectCustomDomain
Storybook 1──N StorybookPage 1──N StorybookPageLink
SlideContent 1──N SlideVersion
```

## Billing & Credit System

### Credit Conversion

```
100 II-Agent credits == $1.50 USD
1 USD ≈ 66.67 credits
```

Defined in `billing/utils.py`. All USD→credit math uses `Decimal` arithmetic to avoid floating-point loss.

### Mandatory Rule

**Never call `CreditService.deduct()` directly** for LLM or tool billing. All billable work flows through the event-driven `CreditUsageHandler` which subscribes to `ModelUsageEvent` and `ToolUsageEvent` on the pub/sub bus.

### Native Billing Flow

```
LLM call completes → ModelUsageEvent published → CreditUsageHandler
  → token_count × PricingInfo → USD → credits → CreditService.deduct()
  → CreditsDeductedEvent (frontend balance update)
  → if balance < minimum: cancel agent run
```

Tool billing follows the same pattern via `ToolUsageEvent` with a direct `cost_usd` field.

### A2A Billing (Inner-Loop Subsidisation)

When `billing_backend` on a `ModelUsageEvent` starts with `"a2a:"`, the handler uses a configurable strategy instead of standard token pricing. This accounts for subsidised backends like Copilot Business (unlimited) or Copilot Pro+ (premium-request pricing).

| Strategy (`AGENT_A2A_BILLING_STRATEGY`) | Behaviour |
|---|---|
| `token_based` (default) | Standard token cost × `AGENT_A2A_BILLING_MULTIPLIER` (default 1.0) |
| `provider_reported` | Copilot: `premium_requests × model_multiplier × $0.04`; others: adapter-reported USD |
| `none` | Zero LLM charge (subscription covers inference) |

Key details:
- Tool costs (image gen, web search) are **always** billed at native rates regardless of strategy
- `is_user_key=True` skips LLM billing entirely (user pays their own API bill)
- Copilot premium-request multipliers are hot-configurable via `AGENT_A2A_COPILOT_MULTIPLIERS` (JSON env)

**Full design doc:** [`docs/design-docs/a2a-billing-model.md`](docs/design-docs/a2a-billing-model.md) — strategies, deployment decision tree, cost comparisons, config examples.

**Key files:** `credits/usage/handler.py` (billing logic), `core/config/agent.py` (A2A billing settings), `realtime/events/app_events.py` (ModelUsageEvent schema), `billing/utils.py` (USD↔credit conversion).

## External Services & Configuration

### External Services

| Service | Purpose | Config |
|---------|---------|--------|
| PostgreSQL | Primary database | `core/config/database.py::DatabaseSettings` |
| Redis | Cache, pubsub, cancel tokens | `core/config/redis.py::RedisSettings` |
| Google Cloud Storage | File storage (prod) | `core/config/storage.py::StorageSettings` |
| Stripe | Payments, subscriptions | `core/config/stripe.py::StripeSettings` |
| E2B | Sandbox execution (prod) | `core/config/sandbox.py::SandboxSettings` |
| Anthropic | Claude LLM provider | via `anthropic[vertex]` |
| OpenAI | GPT models + embeddings | via `openai` |
| Google GenAI | Gemini models | via `google-genai` |
| Composio | External tool integrations | `integrations/connectors/composio/` |
| FastAPI-SSO | OAuth 2.0 (Google, GitHub, MS) | `core/config/oauth.py::OAuth2Settings` |

### Configuration Hierarchy

Main: `core/config/settings.py::Settings` (Pydantic BaseSettings, `@lru_cache` singleton via `get_settings()`)

| Config Class | File |
|-------------|------|
| `DatabaseSettings` | `core/config/database.py` |
| `RedisSettings` | `core/config/redis.py` |
| `StorageSettings` | `core/config/storage.py` |
| `SandboxSettings` | `core/config/sandbox.py` |
| `StripeSettings` | `core/config/stripe.py` |
| `OAuth2Settings` | `core/config/oauth.py` |
| `LLMConfig` | `core/config/llm_config.py` |
| `CreditsSettings` | `core/config/credits.py` |
| `AgentSettings` | `core/config/agent.py` |
| `MCPSettings` | `core/config/mcp.py` |
| `MobileSettings` | `core/config/mobile.py` |
| `EnhancePromptConfig` | `core/config/enhance_prompt_config.py` |
| `NanoBananaConfig` | `core/config/nano_banana.py` |
| `SessionTitleConfig` | `core/config/session_title.py` |

### Key Python Packages

```
fastapi, uvicorn, socketio       # Web framework
sqlalchemy[asyncio], alembic     # Database ORM + migrations
pydantic, pydantic-settings      # Validation + config
redis[hiredis]                   # Cache + pubsub
anthropic[vertex]                # Claude API
openai                           # OpenAI API
google-genai                     # Gemini API
stripe                           # Payments
google-cloud-storage             # File storage
e2b-code-interpreter             # Sandbox
celery                           # Task queue
apscheduler                      # Cron scheduling
```

## Patterns

### Service Pattern

Services take `db: AsyncSession` as first parameter. All services are wired once in `ApplicationContainer.init()` (`core/container.py`).

```python
class SessionService:
    def __init__(self, session_repo, event_repo, ...) -> None:
        self._session_repo = session_repo

    async def get_session(self, db: AsyncSession, session_id: uuid.UUID) -> SessionInfo:
        session = await self._session_repo.get_by_id(db, session_id)
        return SessionInfo.model_validate(session)
```

### Container Pattern (`core/container.py`)

`ApplicationContainer` is the single source of truth for service wiring. Global singleton:

```python
# In FastAPI routes -- use ContainerDep
from ii_agent.core.dependencies import ContainerDep

# Outside request scope (Socket.IO, cron, workers) -- use global getter
from ii_agent.core.container import get_app_container
container = get_app_container()

# Lifespan manages the lifecycle
container = ApplicationContainer.init()   # startup
set_app_container(container)              # store globally
set_app_container(None)                   # shutdown cleanup
```

### Dependency Injection Pattern (`dependencies.py`)

Each domain has a `dependencies.py` that defines factory functions and `Dep` type aliases using `Annotated`. **Always use Dep aliases** -- both in routers and in other factory functions that compose dependencies.

#### Structure rules

1. **Define Dep aliases immediately after** the factory they wrap (before any factory that uses them).
2. **Use Dep aliases everywhere** -- never use bare `= Depends(get_x)` in function signatures (exception: `credentials: HTTPAuthorizationCredentials = Depends(security)` in auth).
3. **Import Dep aliases** from other domains instead of importing their factory functions.

```python
# In sessions/dependencies.py:
from typing import Annotated
from fastapi import Depends
from ii_agent.core.dependencies import ContainerDep

# Repository: fresh instance per request
def get_session_repository() -> SessionRepository:
    return SessionRepository()
SessionRepositoryDep = Annotated[SessionRepository, Depends(get_session_repository)]

# Service: pulled from container (created once at startup)
def _get_session_service(container: ContainerDep) -> SessionService:
    return container.session_service
SessionServiceDep = Annotated[SessionService, Depends(_get_session_service)]
```

#### Anti-patterns (DO NOT)

```python
# BAD: bare Depends(get_x) -- use the Dep alias instead
def get_session_service(
    session_repo: SessionRepository = Depends(get_session_repository),
) -> SessionService: ...

# BAD: importing factory functions from other domains for Depends()
from ii_agent.sessions.dependencies import get_session_service
# GOOD: import the Dep alias
from ii_agent.sessions.dependencies import SessionServiceDep

# BAD: defining Dep aliases at the bottom of the file, after factories that need them
def get_session_service(session_repo: SessionRepositoryDep): ...  # NameError!
SessionRepositoryDep = Annotated[...]  # Too late
```

### Router Pattern

Use Dep aliases for auth, database, and all service dependencies. **All entity ID path params use `uuid.UUID`.**

```python
from ii_agent.auth.dependencies import CurrentUser, DBSession
from ii_agent.sessions.dependencies import SessionServiceDep
import uuid

router = APIRouter(prefix="/sessions", tags=["Sessions"])

@router.get("/{session_id}")
async def get_session(
    session_id: uuid.UUID,
    current_user: CurrentUser,
    db: DBSession,
    session_service: SessionServiceDep,
):
    return await session_service.get_session(db, session_id)
```

### SQLAlchemy 2.0 Models

```python
import uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from ii_agent.core.db.base import Base, TimestampColumn

class Session(Base):
    __tablename__ = "sessions"

    # id, created_at, updated_at inherited from Base
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    state: Mapped[SessionStateEnum] = mapped_column(default=SessionStateEnum.IDLE)

    user: Mapped["User"] = relationship(back_populates="sessions")
```

### Pydantic Schemas

```python
from uuid import UUID
from pydantic import BaseModel, ConfigDict
from ii_agent.sessions.types import SessionState

class SessionInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    name: str | None = None
    status: SessionState  # Use enum types, NEVER raw str for enum fields
```

### Domain `__init__.py` Pattern

Export all public APIs from domain module:

```python
# In sessions/__init__.py:
from .models import Session, SessionStateEnum
from .service import SessionService
from .router import router
from .schemas import SessionCreate, SessionInfo

__all__ = [
    "Session", "SessionStateEnum",
    "SessionService",
    "router",
    "SessionCreate", "SessionInfo",
]
```

## Development Guidelines

### Adding a New Domain

1. Create domain folder: `src/ii_agent/{domain_name}/`
2. Create files:
   - `__init__.py` - Export all public APIs
   - `models.py` - SQLAlchemy models (inherit Base, use `Mapped[uuid.UUID]` for FKs)
   - `repository.py` - Data access layer (extends BaseRepository)
   - `service.py` - Business logic
   - `schemas.py` - Pydantic request/response DTOs (with `ConfigDict(from_attributes=True)`)
   - `types.py` - StrEnum types (if domain has enums)
   - `dependencies.py` - Factory functions & Dep aliases
   - `router.py` - FastAPI endpoints (UUID path params)
   - `exceptions.py` - Domain-specific exceptions
3. Register router in `app/routers.py`

**Canonical reference:** `tasks/` domain is the template. All new domains must match its structure.

### Adding a New Database Table

1. Define model in `{domain}/models.py`:
   - Inherit `Base` (gives `id: uuid.UUID`, `created_at`, `updated_at`)
   - Use `TimestampColumn` for extra datetime columns
   - Use `Mapped[uuid.UUID]` with `UUID(as_uuid=True)` for FK columns
2. Run `alembic revision --autogenerate -m "description"`
3. Review + apply: `alembic upgrade head`

### Adding a New Socket.IO Handler

1. Create `realtime/handlers/{command}.py` extending `BaseCommandHandler`
2. Add command to `CommandType` enum in `realtime/schemas.py`
3. Register in `CommandHandlerFactory` (`realtime/handlers/factory.py`)

### Adding a New Cron Job

1. Create `workers/cron/jobs/{job_name}.py` with async runner
2. Add `CronJobSpec` to `workers/cron/cron_jobs.py::CRON_JOBS`

### Sandbox Cleanup Pipeline

The sandbox cleanup loop (`agents/sandboxes/orphan_cleanup.py`) runs every 60 seconds (configurable) via `run_orphan_cleanup_loop()` with 6 stages executed in order:

1. **`_soft_delete_expired_sessions`** — Mark sessions with `delete_after <= now()` as `is_deleted=True`
2. **`_cleanup_orphans` (R1+R2)** — Kill Docker containers for deleted sessions; mark sandbox DELETED **only if** container confirmed removed (R1); use per-sandbox DB session to prevent rollback cascades (R2)
3. **`_pause_stale_sandboxes`** — Stop running containers idle >30 min (→ PAUSED status)
4. **`_cleanup_docker_zombies` (R4)** — Remove Docker containers with no matching active sandbox DB record; 120s timeout, 5 min grace period
5. **`_cleanup_orphaned_volumes` (R9)** — Remove Docker volumes with `ii-sandbox-workspace-` prefix and no matching active record or container
6. **`_kill_timed_out_sandboxes` (R6)** — Stop containers where `timeout_at <= now()` (pauses to preserve state)

**Key patterns:**
- **R1 — Conditional state marking:** Never mark a sandbox DELETED until the Docker container is confirmed removed. If removal times out or fails, skip the sandbox and retry next sweep.
- **R2 — Per-item DB isolation:** Phase 1 reads all candidates in a single DB session. Phase 2 processes each candidate in its own `get_db_session_local()` context with try/except. One failure doesn't roll back others.
- **R6 — Persistent timeout:** `AgentSandbox.timeout_at` column persists the deadline across backend restarts. In-memory `asyncio.Task` provides best-effort fast path; the cleanup loop enforces the deadline as fallback.

**Design docs:** [`sandbox-lifecycle-assessment.md`](docs/design-docs/sandbox-lifecycle-assessment.md), [`sandbox-accumulation-root-cause-analysis.md`](docs/design-docs/sandbox-accumulation-root-cause-analysis.md)

### Docker Sandbox Local Mode

When `SANDBOX_PROVIDER=docker` and `SANDBOX_LOCAL_MODE=true`, sandboxes run as local Docker containers instead of E2B cloud instances.

**Container hardening (applied in `agents/sandboxes/docker.py`):**
- `read_only=True` with tmpfs mounts (`/tmp`, `/var/tmp`, `/run`, `/home/user`)
- `cap_drop=ALL`, selective `cap_add` (CHOWN, SETUID, SETGID, DAC_OVERRIDE, FOWNER)
- `no-new-privileges`, `mem_limit=3GB`, `pids_limit=512`
- Docker socket auto-detection: `DOCKER_SOCK_PATH` env var, or auto-probes `/var/run/docker.sock`, Colima, OrbStack, Podman sockets

**Orphan cleanup distributed lock:** `run_orphan_cleanup_loop` acquires a Redis advisory lock (`sandbox:cleanup:lock`, 5-min TTL, `SET NX EX`) so only one backend instance runs cleanup at a time.

**Graceful shutdown:** On SIGTERM, the backend waits 10s for in-flight sandbox turns to complete before shutting down Redis/DB connections.

### A2A Inner Loop

The A2A inner loop replaces direct LLM calls with an adapter server that proxies the A2A protocol to a backend CLI (Copilot, Claude Code, Codex). **Two deployment topologies, do not confuse them:**

- **Agent A2A** — adapter runs **inside each sandbox container** (started by `docker/sandbox/start-services.sh`). Each agent run owns a sandbox and resolves its adapter URL via `sandbox.expose_port(18100)`. Per-session, per-sandbox.
- **Chat A2A** — chat sessions do NOT own sandboxes. The adapter runs as a **standalone sidecar** (`a2a-adapter` service in `docker/docker-compose.local.yaml`) and the backend resolves its URL **only** from `AGENT_A2A_AGENT_URL`. Sandbox-independent by design.

```
ChatService → A2AChatTurnLoop.run() → IIAgentA2AClient.astream()
                                    → ChatA2AEventTranslator.translate()
                                    → tool bridging via ChatToolService
                                    → billing via pubsub (billing_backend="a2a:<backend>")
```

**Configuration:** Set `AGENT_CHAT_INNER_LOOP_MODE=a2a` to enable. Backends: `copilot` (default), `claude-code`, `codex`, `simulate` (mock).

**Two failure classes (do not conflate):**

- **Misconfig** — `AGENT_A2A_AGENT_URL` unset while chat A2A enabled. With `AGENT_A2A_CHAT_STRICT=true` (default since 2026-04-18) the backend **crashes at startup** with an actionable error. This is intentional: silent fallback to native LLM has historically caused unexpected 10×+ provider charges. With strict=false the backend logs ERROR and falls back to native (legacy back-compat only).
- **Runtime A2A failure** — circuit breaker open, rate-limit `session.error`, transport error mid-stream. With `AGENT_A2A_FALLBACK_TO_NATIVE=true` (default) chat transparently falls back to direct LLM for that turn. No double-billing because A2A billing only fires after stream completion.

The two settings gate orthogonal concerns: `a2a_chat_strict` covers "did the operator configure me?"; `a2a_fallback_to_native` covers "should I tolerate runtime failures?".

**Optional dependencies:** `a2a-sdk` and `github-copilot-sdk` are in `[project.optional-dependencies.a2a]`. Install with `pip install -e ".[a2a]"`. The sandbox image and the `a2a-adapter` sidecar always have them (via `docker/sandbox/pyproject.toml`).

**Startup validation (lifespan step 8b):** When `inner_loop_mode=a2a` or `chat_inner_loop_mode=a2a`, the backend validates that `a2a-sdk` is importable, logs active backend + required credentials, and — for chat A2A under strict mode — raises `RuntimeError` if `AGENT_A2A_AGENT_URL` is unset.

**Key files:** `chat/application/a2a_turn_loop_service.py` (turn loop), `integrations/a2a/as_client.py` (HTTP streaming client), `integrations/a2a/circuit_breaker.py`, `integrations/a2a/adapter_server.py` (adapter binary, used by both sidecar and per-sandbox), `integrations/a2a/exceptions.py` (`A2AAdapterUnavailableError` → HTTP 503), `chat/api/dependencies.py` (DI wiring; **must not** probe Docker / discover sandboxes — enforced by `test_no_docker_socket_probing`).

**Deployment contract:** [docs/design-docs/chat-a2a-adapter-sidecar.md](docs/design-docs/chat-a2a-adapter-sidecar.md)

### Import Patterns

```python
# Auth (always needed in routers)
from ii_agent.auth.dependencies import CurrentUser, DBSession

# Domain service dep
from ii_agent.sessions.dependencies import SessionServiceDep

# Settings
from ii_agent.core.config.settings import get_settings

# Container (for non-DI contexts like Socket.IO, cron)
from ii_agent.core.container import get_app_container

# Base + TimestampColumn (for models)
from ii_agent.core.db.base import Base, TimestampColumn
```

### Verification

```bash
python -c "from ii_agent.sessions import Session; print('OK')"
./scripts/start.sh
curl http://localhost:8000/health
```

## Key Files

| File | Purpose |
|------|---------|
| `app/` | FastAPI bootstrap: app factory, router registration, lifespan, middleware |
| `app/routers.py` | Router registration (`include_routers`) |
| `app/lifespan.py` | Startup/shutdown lifecycle (DB, Redis, Container, PubSub, Cron) |
| `core/container.py` | ApplicationContainer -- global singleton, wires 21+ services |
| `core/dependencies.py` | ContainerDep, DBSession, SettingsDep -- shared FastAPI Depends |
| `core/config/settings.py` | Pydantic settings (`get_settings` singleton) |
| `core/db/base.py` | SQLAlchemy Base (UUID PK, DateTime timestamps), TimestampColumn, BaseRepository |
| `core/redis/` | Redis client, cache, pubsub, lock, cancel management |
| `core/storage/` | File storage abstraction (GCS, MinIO) + path resolver |
| `auth/dependencies.py` | CurrentUser, DBSession, get_current_user |
| `tasks/` | Canonical domain implementation (RunTask, TaskLog, types, schemas, exceptions) |
| `realtime/handlers/factory.py` | CommandHandlerFactory -- 21 Socket.IO command handlers |
| `realtime/pubsub/` | AsyncIOPubSub with SioCallback + DatabaseCallback subscribers |
| `workers/cron/cron_jobs.py` | Cron job definitions (CronJobSpec list) |
