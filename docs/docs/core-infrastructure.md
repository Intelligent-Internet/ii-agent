---
id: core-infrastructure
title: Core Infrastructure
sidebar_label: Core Infrastructure
sidebar_position: 5
description: Configure Postgres, Redis, and host ports so II-Agent services can talk to each other.
---

# Core Infrastructure

These variables keep the underlying databases, caches, and network ports consistent across every II-Agent container. Start with the safe defaults from `docker/.stack.env.example`, then adjust only when you have conflicts.

## Postgres credentials

Variables: `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `POSTGRES_PORT`

1. Choose credentials you are comfortable using for local development:
   ```bash
   POSTGRES_USER=app
   POSTGRES_PASSWORD=changeme
   POSTGRES_DB=ii
   POSTGRES_PORT=5432
   ```
2. Update the same values anywhere else they appear (Prisma, backend `.env` files, local clients).
3. If port `5432` conflicts with a local Postgres install, change `POSTGRES_PORT` (e.g., `55432`) and update your connection strings.

## Backend connection string

Variable: `DATABASE_URL`

- Use the async driver: `postgresql+asyncpg://USER:PASS@postgres:5432/ii`.
- Keep the host as `postgres` so services inside Docker can resolve it.

## Sandbox database

Variables: `SANDBOX_DB_NAME`, `SANDBOX_DATABASE_URL`

- Only required when the sandbox service uses a separate database.
- You can reuse the main Postgres host with a new database name to keep management simple.

## Redis

Variable: `REDIS_PORT`

- Defaults to `6379`. Change only if another local process already binds that port.
- Containers reference Redis by service name (`redis`), so host-only changes do not affect internal networking.

## HTTP-facing ports

Variables: `BACKEND_PORT`, `FRONTEND_PORT`, `SANDBOX_SERVER_PORT`, `TOOL_SERVER_PORT`, `NGROK_METRICS_PORT`, `MCP_PORT`

- Map each to an open host port. The defaults (8000/3000/9000/etc.) usually work.
- When a collision happens, bump the conflicting port and update any URLs or CLIs that pointed to the old value (e.g., `VITE_API_URL`).

## Docker sandbox port pool

When running in local Docker mode (`SANDBOX_PROVIDER=docker`), the sandbox server dynamically maps container ports to the host from the range **30000-30999**. Each sandbox reserves 6 host ports (MCP, code-server, noVNC, and spares), allowing approximately 166 concurrent sandboxes.

The frontend automatically rewrites `localhost` URLs to the browser's hostname so sandbox services remain accessible when the UI is accessed from a different machine on the LAN.

## Validation checklist

1. Run `./scripts/run_stack.sh --build` and ensure Docker does **not** report binding conflicts.
2. Use `docker compose ps` to inspect which host ports map to each container.
3. From your host, connect to the services directly:
   ```bash
   psql postgresql://app:changeme@localhost:${POSTGRES_PORT}/ii
   redis-cli -p ${REDIS_PORT} ping
   curl http://localhost:${BACKEND_PORT}/health
   ```
4. Document any custom port numbers in your team docs so other contributors can reuse them.
