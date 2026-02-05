# Setup Guide

## Prerequisites

- Python 3.10+
- Node.js 18+ (for frontend)
- Docker & Docker Compose (for full stack)
- `uv` package manager (install: `curl -LsSf https://astral.sh/uv/install.sh | sh`)

## Quick Start (Development)

### 1. Clone and Install

```bash
git clone https://github.com/robertodbabaran/ii-agent.git
cd ii-agent

# Install Python dependencies
uv sync

# Install frontend dependencies
cd frontend && pnpm install && cd ..
```

### 2. Configure Environment

```bash
# Copy the environment template
cp .env.example .env

# Edit .env and fill in your credentials
# At minimum you need:
#   - ANTHROPIC_API_KEY (or OPENAI_API_KEY)
#   - DATABASE_URL (or use Docker PostgreSQL)
#   - REDIS_URL (or use Docker Redis)
```

### 3. Start Infrastructure (Docker)

```bash
# Start PostgreSQL and Redis only
docker compose -f docker/docker-compose.stack.yaml up postgres redis -d

# Run database migrations
uv run alembic upgrade head
```

### 4. Start the Backend

```bash
# Start WebSocket server
uv run python ws_server.py

# In another terminal, start the MCP tool server
uv run ii-tool
```

### 5. Start the Frontend

```bash
cd frontend
pnpm dev
```

### 6. Verify Skills Are Loaded

Check the backend logs for:
```
INFO - Loaded skill module: ib_toolkit
INFO - Registered skill: ib_toolkit v1.5.0
INFO - Registered skill tool: skill_ib_toolkit (28 actions)
```

## Full Stack (Docker Compose)

```bash
cd docker
docker compose -f docker-compose.stack.yaml up -d
```

This starts: PostgreSQL, Redis, frontend, tool-server, sandbox-server, ws-server.

## Environment Variable Reference

See `.env.example` for the complete list with descriptions.
See `docs/knowledge_base/03_environment/ENV_REFERENCE.md` for detailed documentation.

## Troubleshooting

### Skills not loading
```bash
# Test skill discovery manually
uv run python -c "from ii_skills.bridge import list_available_skills; print(list_available_skills())"
```

### Database connection issues
```bash
# Check PostgreSQL is running
docker compose -f docker/docker-compose.stack.yaml ps postgres

# Test connection
uv run python -c "import asyncpg; print('asyncpg ok')"
```

### Missing Python dependencies
```bash
# Some skills have optional dependencies
uv sync --all-extras
# Or install specific extras
pip install yfinance python-pptx openpyxl
```
