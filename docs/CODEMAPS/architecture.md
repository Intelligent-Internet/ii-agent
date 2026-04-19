<!-- Generated: 2026-04-19 | Domains: 21 | Files: 750+ | Token estimate: ~1050 -->
# Architecture

## System Overview

Domain-driven FastAPI + Socket.IO platform. Entry: `app/__init__.py::create_app()` → `socketio.ASGIApp`.

## Domain Map

```
src/ii_agent/
├── app/            # FastAPI factory, router registration, lifespan, middleware
├── core/           # Config, DB, Redis, Storage, LLM billing, Middleware, Container
│   ├── config/     # 13+ Settings classes (DB, Redis, Storage, Stripe, OAuth, LLM…)
│   ├── db/         # SQLAlchemy 2.0 Base (UUID PK, DateTime timestamps), engine, session deps
│   ├── llm/        # LLM billing service, execution service, base utilities (stubs)
│   ├── middleware/  # CORS, request tracing, exception handling
│   ├── redis/      # Async Redis client, cache, cancel tokens
│   ├── storage/    # GCS/local file storage abstraction + path resolver
│   └── container.py # ApplicationContainer singleton (global + app.state)
├── auth/           # OAuth 2.0, JWT (uuid.UUID user_id), session management
├── users/          # User CRUD, API keys
├── billing/        # Stripe webhooks, payment transactions
├── credits/        # Credit balance, ledger, transactions (ADR-004 two-table design)
├── tasks/          # Unified run lifecycle tracker (RunTask + TaskLog) — canonical domain impl
├── sessions/       # Chat sessions, pins, wishlists, fork, title service
├── subscribers/    # Event subscribers (decoupled side-effects)
├── chat/           # Chat API, application services, messages, runs, providers, media
├── agents/         # Agent execution, plans, tools (13 categories), skills, sandboxes, LLM models
├── realtime/       # Socket.IO manager, 21 command handlers, pubsub, events
├── content/        # Slides, storybooks, media templates
├── files/          # File upload/download, user & session assets
├── projects/       # Project mgmt, Cloud Run deployments, databases, design, subdomains
├── integrations/   # A2A inner loop, Composio connectors, enhance prompt, mobile (Apple)
├── settings/       # Admin/user settings (LLM/MCP/skills)
└── workers/        # Celery tasks + cron jobs (credit refresh)
```

## ORM Conventions

```
Base (core/db/base.py):
  id:         Mapped[uuid.UUID]  — UUID PK, server_default=gen_random_uuid()
  created_at: Mapped[datetime]   — DateTime(timezone=True)
  updated_at: Mapped[datetime]   — DateTime(timezone=True), onupdate=func.now()

TimestampColumn = DateTime(timezone=True)  — reusable type for extra timestamp columns
All entity IDs: uuid.UUID (except TaskLog.id = BigInteger autoincrement)
All FK columns: Mapped[uuid.UUID] with UUID(as_uuid=True)
```

## Bootstrap Sequence (app/lifespan.py)

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
  8b. A2A inner-loop validation (if enabled): require [a2a] extras,
      enforce AGENT_A2A_AGENT_URL when AGENT_A2A_CHAT_STRICT=true
  9. Docker sandbox port-pool scan (local mode)

Shutdown: drain in-flight sandbox turns (10s) → cron → sio → pubsub → db → redis
```

## Request Flow

```
HTTP:  Client → CORS → Session → Tracing → Exception → GZip → FastAPI Router → Service → Repository → DB
WS:    Client → Socket.IO connect (JWT auth) → join_session → chat_message → CommandHandlerFactory → Handler → PubSub → SioCallback → Client
```

## Event System

```
Handler emits → PubSub.publish(topic, event)
  ├── SioCallbackHandler → Socket.IO room broadcast
  └── DatabaseCallbackHandler → application_events table

Payload contract:
  BaseEvent.name (dotted, e.g. "agent.response")
  → to_socket_payload() = model_dump() (Pydantic)
  → FE dispatches on data.name (AgentEvent enum)
  No "type" field — "name" IS the dispatch key.

EventType: 44 dotted values across 11 EventGroups
  (agent, session, connection, sandbox, billing, plan, file, media, system, integration, metrics)
```

## Agent Execution

```
Socket "chat_message" → CommandHandlerFactory
  → QueryHandler / PlanHandler / ContinueHandler
    → AgentRunService → Agent (agents/agent.py)
      → LLM Provider (Anthropic/OpenAI/Google/Cerebras/VertexAI)
      → Tools (13 categories, 100+ tools)
      → Skills (built-in + custom)
      → Sandbox (E2B/Docker/local)
```

## A2A Inner Loop (optional, gated by AGENT_INNER_LOOP_MODE / AGENT_CHAT_INNER_LOOP_MODE)

Two topologies — **do not conflate**:

| Mode | Adapter location | URL resolution |
|------|------------------|----------------|
| Agent A2A | Per-sandbox (`docker/sandbox/start-services.sh` starts adapter on :18100) | `sandbox.expose_port(18100)` |
| Chat A2A | Standalone sidecar (`a2a-adapter` service in `docker-compose.local.yaml`) | `AGENT_A2A_AGENT_URL` (required) |

Chat A2A is sandbox-independent by design. `AGENT_A2A_CHAT_STRICT=true` (default) crashes startup if `AGENT_A2A_AGENT_URL` is unset — silent fallback to native LLM has historically caused 10×+ unexpected provider charges. `AGENT_A2A_FALLBACK_TO_NATIVE` gates only genuine runtime failures (circuit breaker, rate limits, transport errors). `a2a-sdk` is an optional extra (`pip install -e ".[a2a]"`).

Design: [chat-a2a-adapter-sidecar](../design-docs/chat-a2a-adapter-sidecar.md), [a2a-inner-loop-url-resolution](../design-docs/a2a-inner-loop-url-resolution.md), [a2a-billing-model](../design-docs/a2a-billing-model.md).

## DI Pattern

```python
# Repositories: fresh per-request instance
def get_session_repository() -> SessionRepository:
    return SessionRepository()
SessionRepositoryDep = Annotated[SessionRepository, Depends(get_session_repository)]

# Services: pulled from container (created once at startup)
def _get_session_service(container: ContainerDep) -> SessionService:
    return container.session_service
SessionServiceDep = Annotated[SessionService, Depends(_get_session_service)]
```

## Canonical Domain Reference

`tasks/` is the canonical implementation. All domains must follow:
`models.py` → `repository.py` → `service.py` → `schemas.py` → `types.py` → `exceptions.py` → `dependencies.py`
