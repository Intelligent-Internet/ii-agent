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

### Discord Join US

📢 Join Our [Discord Channel](https://discord.gg/yDWPsshPHB)! Looking forward to seeing you there! 🎉

## Introduction

<https://github.com/user-attachments/assets/2707b106-f37d-41a8-beff-8802b1c9b186>

## Overview

II Agent is built around providing an agentic interface to leading language models. It offers:

- A CLI interface for direct command-line interaction
- A WebSocket server that powers a modern React-based frontend
- Integration with multiple LLM providers:
  - Anthropic Claude models (direct API or via Google Cloud Vertex AI)
  - Google Gemini models (direct API or via Google Cloud Vertex AI)

## GAIA Benchmark Evaluation

II-Agent has been evaluated on the GAIA benchmark, which assesses LLM-based agents operating within realistic scenarios across multiple dimensions including multimodal processing, tool utilization, and web searching.

We identified several issues with the GAIA benchmark during our evaluation:

- **Annotation Errors**: Several incorrect annotations in the dataset (e.g., misinterpreting date ranges, calculation errors)
- **Outdated Information**: Some questions reference websites or content no longer accessible
- **Language Ambiguity**: Unclear phrasing leading to different interpretations of questions

Despite these challenges, II-Agent demonstrated strong performance on the benchmark, particularly in areas requiring complex reasoning, tool use, and multi-step planning.

![GAIA Benchmark](assets/gaia.jpg)
You can view the full traces of some samples here: [GAIA Benchmark Traces](https://ii-agent-gaia.ii.inc/)

## Requirements

- Docker Compose
- Python 3.10+
- Node.js 18+ (for frontend)
- At least one of the following:
  - Anthropic API key, or
  - Google Gemini API key, or
  - Google Cloud project with Vertex AI API enabled

> \[!TIP]
>
> - For best performance, we recommend using Claude 4.0 Sonnet or Claude Opus 4.0 models.
> - For fast and cheap, we recommend using GPT4.1 from OpenAI.
> - Gemini 2.5 Pro is a good balance between performance and cost.

## Environment

You need to set up `.env` files to run frontend.

**Shortcut:** Check file `.env.example` for example of `.env` file.

For the frontend, create a `.env` file in the frontend directory, point to the port of your backend:

```bash
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_BASE_URL=http://localhost:3000
GOOGLE_API_KEY=<your_google_api_key> # Optional, for Google Drive integration
GOOGLE_CLIENT_ID=<your_google_client_id> # Optional, for Google Drive integration
GOOGLE_CLIENT_SECRET=<your_google_client_secret> # Optional, for Google Drive integration
```

## Installation

### Docker Installation (Recommended)

1. Clone the repository
2. Set up the environment as mentioned in the above step
3. If you are using Anthropic Client run

```
docker compose up
```
Our II-Agent supports popular models such as Claude, Gemini, and OpenAI. If you'd like to use a model from OpenRouter, simply configure your OpenAI endpoint with your OpenRouter API key.
If you are using Vertex, run with these variables

```
GOOGLE_APPLICATION_CREDENTIALS=absolute-path-to-credential docker compose up
```

### Running II-Agent with MCP Docker Support

II-Agent supports running with MCP (Model Context Protocol) servers in Docker containers, providing additional tool capabilities in security mode.

#### Prerequisites

1. Build the backend Docker image:
```bash
sudo docker build -f docker/backend/DockerfileBackEndOnly.dockerfile -t ii-agent-backend:0.2 .
```

2. Create a Python virtual environment and install dependencies:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
pip install datasets docker
```

3. Configure your settings in `scripts/settings.json` (see example provided) or create your own settings file.

#### Running with MCP Docker

Execute ii-agent with MCP Docker support using the inference script:

```bash
python3 scripts/inference_with_docker.py \
  --query "your task description here" \
  --setting-path scripts/settings.json \
  --workspace-path your_workspace_directory \
  --session-id your_session_id
```

**Example:**
```bash
python3 scripts/inference_with_docker.py \
  --query "create the simple calculator web project" \
  --setting-path scripts/settings.json \
  --workspace-path scripts/calculator_workspace \
  --session-id trace_00
```

#### MCP Configuration

The MCP configuration is defined in `setting_mcp.json` and includes:
- **Playwright MCP Server**: Provides web automation capabilities including browser interaction, page navigation, and element manipulation

#### Parameters

- `--query`: Task description for the agent to execute
- `--setting-path`: Path to your settings JSON file containing LLM configuration
- `--workspace-path`: Directory where the agent will work and store files
- `--session-id`: Unique identifier for the session (useful for tracking and continuation)
- `--keep-running-docker`: Keep Docker container running after completion (useful for inspecting running services)
- `--image-name`: Docker image name to use (default: ii-agent-backend:0.2)

### Collecting Traces and Output

After running ii-agent with MCP Docker, you can collect traces and outputs from several locations:

#### 1. Workspace Directory
The main working directory specified by `--workspace-path` contains:
- All files created/modified by the agent
- Project artifacts and code
- Configuration files in `.ii_agent/` subdirectory

#### 2. Agent Output Directory
The `ii_agent_output/` directory contains:
- Extracted agent data and logs
- Session state information
- Tool execution traces

#### 3. Container Logs and Data
If using `--keep-running-docker`, you can access the running container to inspect:
- Live application state (e.g., running web servers)

#### 4. Session State Files
Located in `{workspace-path}/.ii_agent/`:
- `settings.json`: Agent configuration
- `other_config.json`: System prompt and tool definitions
- Session state data for continuation

#### Example: Extracting Complete Traces

```bash
# Run with session tracking
python3 scripts/inference_with_docker.py \
  --query "create and deploy a web application" \
  --setting-path scripts/settings.json \
  --workspace-path ./traces/web_app_session \
  --session-id web_app_001 \
  --keep-running-docker

# After completion, find your traces in:
# - ./traces/web_app_session/ (workspace files)
# - ./ii_agent_output/ (agent execution data)
# - Container logs via Docker commands
```

This approach provides comprehensive tracing of the agent's execution, including all intermediate steps, tool usage, and final outputs.

### Manual Installation

1. Clone the repository
2. Set up Python environment:

   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   pip install -e .
   ```

3. Set up frontend (optional):
   ```bash
   cd frontend
   npm install
   ```

### Web Interface

1. Start the WebSocket server:

When using Anthropic client:

```bash
STATIC_FILE_BASE_URL=http://localhost:8000 python ws_server.py --port 8000
```

When using Vertex:

```bash
GOOGLE_APPLICATION_CREDENTIALS=path-to-your-credential STATIC_FILE_BASE_URL=http://localhost:8000 python ws_server.py --port 8000
```

2. Start the frontend (in a separate terminal):

```bash
cd frontend
npm run dev
```

3. Open your browser to http://localhost:3000

## Project Structure

- `ws_server.py`: WebSocket server for the frontend
- `src/ii_agent/`: Core agent implementation
  - `agents/`: Agent implementations
  - `llm/`: LLM client interfaces
  - `tools/`: Tool implementations
  - `utils/`: Utility functions

## Core Capabilities

II-Agent is a versatile open-source assistant built to elevate your productivity across domains:

| Domain                        | What II‑Agent Can Do                                                                                       |
| ----------------------------- | ---------------------------------------------------------------------------------------------------------- |
| Research & Fact‑Checking      | Multistep web search, source triangulation, structured note‑taking, rapid summarization                    |
| Content Generation            | Blog & article drafts, lesson plans, creative prose, technical manuals, Website creations                  |
| Data Analysis & Visualization | Cleaning, statistics, trend detection, charting, and automated report generation                           |
| Software Development          | Code synthesis, refactoring, debugging, test‑writing, and step‑by‑step tutorials across multiple languages |
| Workflow Automation           | Script generation, browser automation, file management, process optimization                               |
| Problem Solving               | Decomposition, alternative‑path exploration, stepwise guidance, troubleshooting                            |

## Methods

The II-Agent system represents a sophisticated approach to building versatile AI agents. Our methodology centers on:

1. **Core Agent Architecture and LLM Interaction**

   - System prompting with dynamically tailored context
   - Comprehensive interaction history management
   - Intelligent context management to handle token limitations
   - Systematic LLM invocation and capability selection
   - Iterative refinement through execution cycles

2. **Planning and Reflection**

   - Structured reasoning for complex problem-solving
   - Problem decomposition and sequential thinking
   - Transparent decision-making process
   - Hypothesis formation and testing

3. **Execution Capabilities**

   - File system operations with intelligent code editing
   - Command line execution in a secure environment
   - Advanced web interaction and browser automation
   - Task finalization and reporting
   - Specialized capabilities for various modalities (Experimental) (PDF, audio, image, video, slides)
   - Deep research integration

4. **Context Management**

   - Token usage estimation and optimization
   - Strategic truncation for lengthy interactions
   - File-based archival for large outputs

5. **Real-time Communication**
   - WebSocket-based interface for interactive use
   - Isolated agent instances per client
   - Streaming operational events for responsive UX

## Conclusion

The II-Agent framework, architected around the reasoning capabilities of large language models like Claude 4.0 Sonnet or Gemini 2.5 Pro, presents a comprehensive and robust methodology for building versatile AI agents. Through its synergistic combination of a powerful LLM, a rich set of execution capabilities, an explicit mechanism for planning and reflection, and intelligent context management strategies, II-Agent is well-equipped to address a wide spectrum of complex, multi-step tasks. Its open-source nature and extensible design provide a strong foundation for continued research and development in the rapidly evolving field of agentic AI.

## Acknowledgement

We would like to express our sincere gratitude to the following projects and individuals for their invaluable contributions that have helped shape this project:

- **AugmentCode**: We have incorporated and adapted several key components from the [AugmentCode project](https://github.com/augmentcode/augment-swebench-agent). AugmentCode focuses on SWE-bench, a benchmark that tests AI systems on real-world software engineering tasks from GitHub issues in popular open-source projects. Their system provides tools for bash command execution, file operations, and sequential problem-solving capabilities designed specifically for software engineering tasks.

- **Manus**: Our system prompt architecture draws inspiration from Manus's work, which has helped us create more effective and contextually aware AI interactions.

- **Index Browser Use**: We have built upon and extended the functionality of the [Index Browser Use project](https://github.com/lmnr-ai/index/tree/main), particularly in our web interaction and browsing capabilities. Their foundational work has enabled us to create more sophisticated web-based agent behaviors.

We are committed to open source collaboration and believe in acknowledging the work that has helped us build this project. If you feel your work has been used in this project but hasn't been properly acknowledged, please reach out to us.
