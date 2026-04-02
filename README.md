<div align="center">
<img width="1200" height="630" alt="ii-agent-banner" src="https://github.com/user-attachments/assets/7b61e0c0-0d98-495f-a126-6f1b92990631" />


# II Agent

[![GitHub stars](https://img.shields.io/github/stars/Intelligent-Internet/ii-agent?style=social)](https://github.com/Intelligent-Internet/ii-agent/stargazers)
[![Discord Follow](https://dcbadge.limes.pink/api/server/yDWPsshPHB?style=flat)](https://discord.gg/yDWPsshPHB)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Blog](https://img.shields.io/badge/Blog-II--Agent-blue)](https://ii.inc/web/blog/post/ii-agent)
[![GAIA Benchmark](https://img.shields.io/badge/GAIA-Benchmark-green)](https://ii-agent-gaia.ii.inc/)
[<img src="https://devin.ai/assets/deepwiki-badge.png" alt="Ask DeepWiki.com" height="20"/>](https://deepwiki.com/Intelligent-Internet/ii-agent)

</div>

II-Agent is an open-source AI agent built for real work — now out of beta. 100% open source under the Apache-2.0 license.

Whether you're a solo developer, a research team, or an enterprise building internal tooling — you can run it, fork it, and extend it. No black boxes. No vendor lock-in. Bring your own API keys (BYOK) for full control over cost and model providers.

[**Try the web app**](https://agent.ii.inc/) | [**Join our Discord**](https://discord.gg/yDWPsshPHB)

## Introduction

https://github.com/user-attachments/assets/430425c4-2352-4101-9fdb-46bdfc63d26a

## Key Features

### Build

* **Mobile App Development** — Go from a short prompt to a full mobile application
* **Website App Development** — Go from a short prompt to a full website application
* **Storybook Generation** — Create fully illustrated picture books from a single prompt
* **Video & Image Generation** — Multiple model support within one workflow
* **Live Editing** — Real-time editing for websites, slides, and storybooks
* **Plan Mode** — Visual project planning before building


### Research

* **Fast Research & Deep Research** — Quick answers or multi-step investigations
* **Interactive Website Generation** — Turn research briefs into complete websites with structure, visuals, citations, and embedded Q&A

### Automate & Integrate

* **Built-in & Custom Skills** — Reuse workflows and connect GitHub-based processes
* **App Integrations** — Gmail, Slack, GitHub, Notion, Google Calendar, Discord, Dropbox, Canva, and more
* **Faster Execution** — Significantly improved speed compared to earlier beta iterations

### Everything Else

| Domain | Capabilities |
| :--- | :--- |
| **Chat** | Multi-model conversations (switch providers mid-thread), file attachments, code interpreter, text file search |
| **Agent** | General tasks with multi-step task planning |
| **Documents** | PDF extraction & creation, Excel formulas & charts, Word editing, PowerPoint manipulation |
| **Slides** | Prompt-to-deck creation with live collaborative editing and templates |


## Installation

### Prerequisites

- **Docker** — [Install Docker](https://docs.docker.com/get-docker/)
- **uv** — `curl -LsSf https://astral.sh/uv/install.sh | sh`
- **Node.js & npm** — [Install Node.js](https://nodejs.org/) (or use nvm)

### Quick Start

```bash
# 1. Clone the repository
git clone https://github.com/Intelligent-Internet/ii-agent.git
cd ii-agent

# 2. Run first-time setup (creates .env files + installs deps)
make setup

# 3. Configure your LLM API keys
#    Edit .env and set at least one LLM provider:

#    Option A: Inline JSON in .env
#    MODEL_CONFIGS='[{"model_id":"claude-sonnet-4-6","provider":"Anthropic","api_key":"sk-ant-...","display_name":"Claude Sonnet 4","is_default":true}]'

#    Option B: YAML config file
#    Copy model_configs.example.yaml to model_configs.yaml, fill in your keys,
#    then set MODEL_CONFIGS_FILE=model_configs.yaml in .env

# 4. Start everything (infra + backend + frontend)
make dev-all
```

This starts:
- **Backend** at http://localhost:8000
- **Frontend** at http://localhost:1420
- **PostgreSQL** at localhost:5432
- **Redis** at localhost:6379
- **MinIO** (S3-compatible storage) at http://localhost:9001 (minioadmin/minioadmin)

### Configuration Files

| File | Created from | Purpose |
|------|-------------|---------|
| `.env` | `.env.example` | Backend config: database, Redis, storage, auth, LLM keys |
| `frontend/.env` | `frontend/.env.example` | Frontend config: API URL, Google OAuth, theme |
| `model_configs.yaml` | `model_configs.example.yaml` | LLM model definitions (alternative to inline JSON in `.env`) |

### LLM Providers

II-Agent supports multiple LLM providers. Configure them in `model_configs.yaml` or via `MODEL_CONFIGS` in `.env`:

| Provider | Example model_id | Notes |
|----------|-----------------|-------|
| OpenAI | `gpt-5.4` | Requires `api_key` |
| Anthropic | `claude-opus-4-6` | Direct API or Vertex AI |
| Google | `gemini-3.1-pro-preview` | Direct API or Vertex AI |

See [`model_configs.example.yaml`](model_configs.example.yaml) for full configuration options including Vertex AI, Azure, and self-hosted models.

### Useful Make Commands

```bash
make help             # Show all available commands
make dev-all          # Start everything (infra + backend + frontend)
make infra            # Start only Postgres, Redis, MinIO
make backend-dev      # Start backend only (port 8000)
make frontend-dev     # Start frontend only (port 5173)
make db-migrate       # Run database migrations
make lint             # Lint backend + frontend
make format           # Auto-format backend + frontend
make test             # Run all tests
make stack            # Start full stack via Docker Compose
```

### Docker Compose (Full Stack)

To run everything in Docker (no local Python/Node required):

```bash
# Copy and edit the stack env file
cp docker/.stack.env.example docker/.stack.env
# Edit docker/.stack.env with your credentials

make stack            # Start full stack
make stack-build      # Start with --build (rebuild images)
make stack-down       # Stop and clean up
make stack-logs       # Tail all logs
```

### Additional Resources

For more details, refer to our [official guide](https://intelligent-internet.github.io/ii-agent-prod/)

https://github.com/user-attachments/assets/d1fa7cde-06cc-4103-bed0-d4ad5e640de4
