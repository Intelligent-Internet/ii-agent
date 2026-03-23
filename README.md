<div align="center">
  <img src="assets/ii.png" width="200"/>

# II Agent

[![GitHub stars](https://img.shields.io/github/stars/Intelligent-Internet/ii-agent?style=social)](https://github.com/Intelligent-Internet/ii-agent/stargazers)
[![Discord Follow](https://dcbadge.limes.pink/api/server/yDWPsshPHB?style=flat)](https://discord.gg/yDWPsshPHB)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Blog](https://img.shields.io/badge/Blog-II--Agent-blue)](https://ii.inc/web/blog/post/ii-agent)
[![GAIA Benchmark](https://img.shields.io/badge/GAIA-Benchmark-green)](https://ii-agent-gaia.ii.inc/)
[<img src="https://devin.ai/assets/deepwiki-badge.png" alt="Ask DeepWiki.com" height="20"/>](https://deepwiki.com/Intelligent-Internet/ii-agent)

</div>

II-Agent is an open-source intelligent assistant designed to streamline and enhance workflows across multiple domains. It represents a significant advancement in how we interact with technology—shifting from passive tools to intelligent systems capable of independently executing complex tasks.

II-Agent Chat also feature within II-Agent that lets you work across multiple models and tools in one place. The web-hosted version comes with Gemini 3, Sonnet 4.5, and GPT-5 ready to use out of the box. You can connect your own API keys, switch models within a single thread, and use them alongside Claude Skills, GPT-5 Code Interpreter, and text file search.


### Discord Join US

📢 Join Our [Discord Channel](https://discord.gg/yDWPsshPHB)! Looking forward to seeing you there! 🎉

### Try now on our web application version at [II-Agent](https://agent.ii.inc/)



## Introduction
<https://github.com/user-attachments/assets/02ef0612-1696-4311-9002-14f36842ff3e>


## Key Features

* **Full-Stack Development**: Complete web app scaffolding and iterative development. From initial setup to deployment, II-Agent handles the entire development lifecycle with intelligent code generation and optimization.
* **Slide Creation**: Transform short briefs into polished presentations. Create professional slides and decks with intelligent content structuring, design suggestions, and automated formatting.
* **Deep Research**: Comprehensive research capabilities through tight integration with II-Researcher. Conduct thorough investigations, analyze data, and generate detailed reports with our specialized research agent.
* **Local Docker Sandbox**: Run sandboxes entirely on your own machine with Docker — no cloud dependencies, no data leaving your network. Ideal for air-gapped, NDA-protected, or self-hosted environments.
* **Agent-Human Handoff**: When the agent encounters CAPTCHAs, login forms, or 2FA, it opens a browser-based noVNC session so you can interact directly, then resumes automation once you're done.
* **Media Generation**: Built-in DALL-E 3 image generation and Sora video generation with cost tracking and multiple aspect ratio support.
* **Extended Thinking**: Claude 4 extended thinking with configurable token budgets, interleaved thinking during tool use, and optional 1M context window.
* **Tool Execution Safety**: Tiered timeout system (120s tool-level, 300s MCP backstop) with 2-second interrupt polling — prevents indefinitely hung sessions and supports mid-execution cancellation.

## SWE-Bench Pro

<img width="1778" height="1060" alt="swepro" src="https://github.com/user-attachments/assets/e955538d-986a-4c74-96b9-dbeb56e803e1" />


## Deployment Models

II-Agent supports two sandbox deployment modes through a pluggable provider architecture:

| | Cloud (E2B) | Local (Docker) |
|---|---|---|
| **Isolation** | Firecracker micro-VMs | Docker containers |
| **Network** | Public (ngrok tunnel) | Localhost only |
| **Startup** | ~150ms (pre-warmed) | 2–5s (cold start) |
| **Data location** | E2B infrastructure | Your machine |
| **Cost** | Per-use billing | Free (your hardware) |
| **Best for** | Production, quick start | Privacy, air-gapped, self-hosted |

Set `SANDBOX_PROVIDER=docker` or `SANDBOX_PROVIDER=e2b` in your environment to choose.


## Installation

For the latest installation and deployment instructions, please refer to our [official guide](https://intelligent-internet.github.io/ii-agent-prod/)

[![Installation Guide](https://img.youtube.com/vi/wPpeJMbdGi4/maxresdefault.jpg)](https://www.youtube.com/watch?v=wPpeJMbdGi4)

### Local Docker Quick Start

Run II-Agent entirely on your own machine with no cloud dependencies:

```bash
# 1. Build the sandbox image (Python, Node.js, Playwright, noVNC, code-server)
docker build -t ii-agent-sandbox:latest -f e2b.Dockerfile .

# 2. Configure environment
cp docker/.stack.env.local.example docker/.stack.env.local
# Edit docker/.stack.env.local — set JWT_SECRET_KEY and at least one LLM API key

# 3. Start the stack
scripts/stack_control.sh start --local

# 4. Access
#   Frontend:       http://localhost:1420
#   Backend API:    http://localhost:8000
#   Sandbox Server: http://localhost:8100
```

For detailed setup, see [docs/docs/local-docker-sandbox.md](docs/docs/local-docker-sandbox.md).

### Architecture (Local Mode)

```
┌─────────────┐
│   Frontend   │
│   (:1420)    │
└──────┬───────┘
       │ WebSocket
       ▼
┌─────────────┐     ┌───────────┐     ┌───────────┐
│   Backend    │◄───►│   Redis   │     │ Postgres  │
│   (:8000)    │     │  (:6379)  │     │  (:5433)  │
└──────┬───────┘     └───────────┘     └───────────┘
       │
  ┌────┴─────┐
  ▼          ▼
┌──────────┐ ┌─────────────┐
│ Sandbox  │ │ Tool Server │
│  Server  │ │   (:1236)   │
│ (:8100)  │ └─────────────┘
└────┬─────┘
     │ Docker API
     ▼
┌──────────────────────────────────┐
│    Sandbox Containers            │
│  ┌──────────┐  ┌──────────┐     │
│  │ Sandbox1 │  │ Sandbox2 │ ... │
│  │ Playwright│  │ noVNC   │     │
│  │ noVNC    │  │ code-svr │     │
│  └──────────┘  └──────────┘     │
└──────────────────────────────────┘
```

Each sandbox container gets 6 host ports allocated from a configurable pool (default 30000–30999), exposing noVNC (6080), code-server (9000), MCP (6060), and dev-server ports.


## Stack Management

The unified `scripts/stack_control.sh` script manages the full Docker stack:

```bash
scripts/stack_control.sh start [--local]              # Start services
scripts/stack_control.sh stop [--local]               # Stop services
scripts/stack_control.sh restart [--local] [service]  # Restart (picks up env changes)
scripts/stack_control.sh rebuild [--local] [service]  # Rebuild image + restart
scripts/stack_control.sh status [--local]             # Show service status and URLs
scripts/stack_control.sh logs [--local] [service] [-f]# View/follow logs
scripts/stack_control.sh build [--local]              # Build sandbox image
scripts/stack_control.sh setup [--local]              # Create .stack.env from template
scripts/stack_control.sh wake [--local] [uuid]        # Wake stopped sandbox containers
```

The `--local` flag switches between cloud (E2B) and local (Docker) compose configurations.


## Agent-Human-Agent Handoff

When the agent's browser encounters a CAPTCHA, login form, or 2FA challenge:

1. The agent calls `expose_port(6080)` to obtain a noVNC URL
2. The agent shares the URL and pauses
3. You open the noVNC link in your browser and interact with the sandbox's Chromium directly
4. You confirm completion via the chat UI
5. The agent resumes automation from a fresh screenshot

This works because both Playwright (agent) and noVNC (you) share the same X11 display (`:99`) inside the sandbox via `x11vnc --shared`.


## Configuration

### Key Environment Variables

| Variable | Default | Description |
|---|---|---|
| `SANDBOX_PROVIDER` | `e2b` | Sandbox backend: `e2b` or `docker` |
| `SANDBOX_DOCKER_IMAGE` | `ii-agent-sandbox:latest` | Docker image for local sandboxes |
| `SANDBOX_PORT_RANGE_START` | `30000` | Start of host port pool |
| `SANDBOX_PORT_RANGE_END` | `30999` | End of host port pool |
| `LOCAL_MODE` | `false` | Enable local-only features |
| `STORAGE_PROVIDER` | `gcs` | Storage backend: `gcs` or `local` |
| `ORPHAN_CLEANUP_ENABLED` | `true` | Auto-remove sandboxes with no active sessions |
| `ORPHAN_CLEANUP_INTERVAL_SECONDS` | `300` | Cleanup check interval |

See `docker/.stack.env.local.example` for the full list of configurable variables.


## Utility Scripts

| Script | Description |
|---|---|
| `scripts/stack_control.sh` | Unified Docker stack lifecycle management |
| `scripts/admin_credits.sh` | Query and manage user credits in PostgreSQL |
| `scripts/html_to_pdf.py` | Convert HTML slides/pages to multi-page PDF via Playwright |
