# Installation Guide

## Installation Modes

### Full Installation (Default)

```bash
pip install -e .
```

**Includes everything:**
- Core LLM providers: Anthropic, OpenAI, LiteLLM, NVIDIA
- REPL mode + Server mode
- File processing tools
- MCP support
- Search/Web tools
- **GCP:** Vertex AI, Cloud Storage, Google APIs
- **Server mode:** FastAPI, WebSocket, Redis, Postgres, SQLite
- **Sandboxing:** E2B, Playwright
- **Auth:** OAuth, JWT, Stripe
- **Extras:** APScheduler, transformers, pytest

**Size:** ~2GB | **Install time:** 3-5 minutes (GCP dependency resolution)

### Lite Installation (REPL only, no GCP)

```bash
pip install -r requirements-lite.txt
pip install -e . --no-deps
```

**Includes:**
- Core LLM providers: Anthropic, OpenAI, LiteLLM
- REPL mode only
- File processing tools
- MCP support
- Search/Web tools
- **No GCP, no server, no databases**

**Size:** ~200MB | **Install time:** 30 seconds

## Quick Start

### REPL Mode (Lite)
```bash
# Install lite
pip install -r requirements-lite.txt
pip install -e . --no-deps

# Set API key
export NVIDIA_API_KEY=nvapi-...

# Run REPL
ii-agent --repl
```

### REPL Mode (Full)
```bash
# Install full
pip install -e .

# Set API key
export NVIDIA_API_KEY=nvapi-...

# Run REPL
ii-agent --repl
```

### Server Mode
```bash
# Install full
pip install -e .

# Set up database
# Configure .env

# Run server
ii-agent
# OR
ii-agent --port 8080
```

## Python 3.14 Compatibility

If using Python 3.14, set this environment variable before installing:

```bash
export PYO3_USE_ABI3_FORWARD_COMPATIBILITY=1
pip install -e .
```

## Dependencies

### Lite Install (requirements-lite.txt)
```
Core: anthropic, litellm, openai, pydantic
MCP/Tools: fastmcp, libtmux
REPL: prompt-toolkit, rich
File: pandas, pymupdf, python-pptx, weasyprint, mammoth
Search: ddgs, duckduckgo-search, tavily-python
Utils: python-dotenv, tenacity, ast-grep-cli
```
**Total:** ~45 packages, ~200MB

### Full Install (pip install -e .) - Adds:
```
Server: alembic, aiosqlite, asyncpg, psycopg2-binary, redis
        fastapi, fastapi-sso, python-socketio, starlette, uvicorn

GCP: anthropic[vertex], gcloud-aio-storage
     google-api-python-client, google-auth-oauthlib
     google-cloud-aiplatform, google-genai

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
