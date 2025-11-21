# Installation Guide

## Installation Modes

### Cloud Server (Default)

```bash
pip install -e .
```

**Full cloud/server build:**
- Core LLM providers: Anthropic, OpenAI, LiteLLM, NVIDIA
- **Server mode:** FastAPI, WebSocket, Redis, Postgres, SQLite
- **GCP:** Vertex AI, Cloud Storage, Google APIs, Gemini
- **Auth:** OAuth, JWT, Stripe
- **Sandboxing:** E2B, Playwright
- **Extras:** APScheduler, transformers, pytest, ii-researcher
- File processing, MCP support, Search/Web tools

**Size:** ~2GB | **Install time:** 3-5 minutes (GCP dependency resolution)

### Local REPL (Additive, no cloud)

```bash
pip install -r requirements-repl.txt
pip install -e . --no-deps
```

**Local development REPL:**
- Core LLM providers: Anthropic, OpenAI, LiteLLM, NVIDIA
- **REPL interface:** prompt-toolkit, rich
- **DuckDB** for local analytics and context management
- File processing, MCP support, Search/Web tools
- **No GCP, no server, no external databases, no Gemini**

**Size:** ~200MB | **Install time:** 30 seconds

Use this for local development without cloud dependencies.

## Quick Start

### Local REPL Mode
```bash
# Install REPL-only
pip install -r requirements-repl.txt
pip install -e . --no-deps

# Set API key (Anthropic, OpenAI, or NVIDIA - no Gemini in REPL mode)
export NVIDIA_API_KEY=nvapi-...

# Run REPL
ii-agent --repl
```

### Cloud Server Mode
```bash
# Install full cloud build
pip install -e .

# Set up database and configure .env
# Run server
ii-agent
# OR
ii-agent --port 8080

# Server also supports REPL with all providers including Gemini
export GOOGLE_API_KEY=...
ii-agent --repl
```

## Python 3.14 Compatibility

If using Python 3.14, set this environment variable before installing:

```bash
export PYO3_USE_ABI3_FORWARD_COMPATIBILITY=1
pip install -e .
```

## Dependencies

### REPL Install (requirements-repl.txt)
```
Core: anthropic, litellm, openai, pydantic
MCP/Tools: fastmcp, libtmux
REPL: prompt-toolkit, rich
File: pandas, pymupdf, python-pptx, weasyprint, mammoth
Search: ddgs, duckduckgo-search, tavily-python
Utils: python-dotenv, tenacity, ast-grep-cli
```
**Total:** ~45 packages, ~200MB

**Excludes:** GCP, Gemini, server, databases, auth, sandboxing

### Cloud Server Install (pip install -e .) - Includes everything:
```
Core: Same as REPL

Server: alembic, aiosqlite, asyncpg, psycopg2-binary, redis
        fastapi, fastapi-sso, python-socketio, starlette, uvicorn

GCP: anthropic[vertex], gcloud-aio-storage
     google-api-python-client, google-auth-oauthlib
     google-cloud-aiplatform, google-genai (Gemini support)

Sandboxing: e2b-code-interpreter, playwright

Auth: bcrypt, cryptography, email-validator, PyJWT, stripe

Extras: apscheduler, ii-researcher, pydub, pytest
        python-crontab, speechrecognition, transformers
```
**Total:** ~95 packages, ~2GB

## Known Issues

**GCP packages may cause slow dependency resolution:**
- `google-api-python-client` + `google-cloud-aiplatform` + `anthropic[vertex]` have complex dependency trees
- Pip resolver may take 3-5 minutes
- Total install size: ~2GB with all dependencies

## Troubleshooting

### Dependency resolver hangs
```bash
# Be patient - GCP packages take 3-5 minutes to resolve
# Or use --no-deps if you know dependencies are satisfied
pip install -e .
```

### Python 3.14 build errors
```bash
export PYO3_USE_ABI3_FORWARD_COMPATIBILITY=1
pip install -e .
```

## Development

```bash
# Full install (default)
pip install -e .

# GAIA benchmark tasks (adds datasets, huggingface-hub)
pip install -e .[gaia]
```
