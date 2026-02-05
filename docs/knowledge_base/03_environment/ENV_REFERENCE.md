# Environment Variable Reference

Complete reference for all environment variables used by ii-agent.

## Required (Core)

| Variable | Description | Example |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql+asyncpg://user:pass@localhost:5432/ii_agent` |
| `REDIS_URL` | Redis connection string | `redis://localhost:6379/0` |

## Required (LLM - at least one)

| Variable | Description | Example |
|----------|-------------|---------|
| `ANTHROPIC_API_KEY` | Anthropic API key for Claude models | `sk-ant-api03-...` |
| `OPENAI_API_KEY` | OpenAI API key | `sk-...` |
| `GOOGLE_API_KEY` | Google GenAI API key | `AIza...` |

## Optional (Skills)

| Variable | Description | Used By | Default |
|----------|-------------|---------|---------|
| `NEWSAPI_KEY` | NewsAPI.org API key | market_newsletter | None (skill disabled) |
| `WHOOP_CLIENT_ID` | WHOOP OAuth client ID | health_dashboard | None (skill disabled) |
| `WHOOP_CLIENT_SECRET` | WHOOP OAuth client secret | health_dashboard | None |
| `WHOOP_ACCESS_TOKEN` | WHOOP access token | health_dashboard | None |
| `BRAVE_API_KEY` | Brave Search API key | daily_investment_newsletter | None |

## Optional (Email)

| Variable | Description | Default |
|----------|-------------|---------|
| `SMTP_SERVER` | SMTP server address | `smtp.gmail.com` |
| `SMTP_PORT` | SMTP server port | `587` |
| `SMTP_EMAIL` | Sender email address | None |
| `SMTP_PASSWORD` | Email app password | None |

## Optional (Storage)

| Variable | Description | Default |
|----------|-------------|---------|
| `GCS_BUCKET_NAME` | Google Cloud Storage bucket | None |
| `GOOGLE_APPLICATION_CREDENTIALS` | Path to GCP service account JSON | None |

## Optional (Services)

| Variable | Description | Default |
|----------|-------------|---------|
| `E2B_API_KEY` | E2B sandbox API key | None |
| `FILE_STORE_PATH` | Local file storage path | `/tmp/ii_agent_files` |
| `MCP_PORT` | MCP tool server port | `1236` |
| `CODEX_PORT` | Codex server port | `3284` |

## Optional (Infrastructure)

| Variable | Description | Default |
|----------|-------------|---------|
| `LOG_LEVEL` | Logging level | `INFO` |
| `ENVIRONMENT` | Deployment environment | `development` |
| `DISPLAY` | X display for Playwright | `:99` |

## Skills-Specific Configuration

Skills also read from their own `config.py` files in addition to environment
variables. The bridge layer will pass environment-based config to skills
automatically.

### IB Toolkit
No required API keys. Yahoo Finance (yfinance) works without authentication.
Optional: Financial Modeling Prep (FMP) key for enhanced data.

### IR Toolkit
No required API keys. Uses data provided by the user.

### Net Worth Newsletter
Requires: `SMTP_EMAIL`, `SMTP_PASSWORD` for email delivery.
Portfolio data is stored in the database.

### Market Newsletter
Requires: `NEWSAPI_KEY` for news aggregation.
Requires: `SMTP_EMAIL`, `SMTP_PASSWORD` for email delivery.

### Health Dashboard
Requires: `WHOOP_CLIENT_ID`, `WHOOP_CLIENT_SECRET`, `WHOOP_ACCESS_TOKEN`.
Requires: `SMTP_EMAIL`, `SMTP_PASSWORD` for email delivery.
