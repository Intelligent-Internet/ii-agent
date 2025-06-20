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
> - For best performance, we recommend using Claude 4.0 Sonnet or Claude Opus 4.0 models.
> - For fast and cheap, we recommend using GPT4.1 from OpenAI.
> - Gemini 2.5 Pro is a good balance between performance and cost.

## Environment

You need to set up 2 `.env` files to run both frontend and backend
**Shortcut:** Check file `.env.example` for example of `.env` file.

### Frontend Environment Variables

For the frontend, create a `.env` file in the frontend directory, point to the port of your backend:

```bash
NEXT_PUBLIC_API_URL=http://localhost:8000
```

### Backend Environment Variables

For the backend, create a `.env` file in the root directory with the following variables. Here are the required variables needed to run this project:


```bash
# Required API Keys - Choose one based on your LLM provider:
# Option 1: For Claude models via Anthropic
ANTHROPIC_API_KEY=your_anthropic_key

# Option 2: For Gemini models via Google
GEMINI_API_KEY=your_gemini_key

# Option 3: For OpenAI models
OPENAI_API_KEY=your_openai_key

# Search Provider API Key
TAVILY_API_KEY=your_tavily_key

STATIC_FILE_BASE_URL=http://localhost:8000/
```

We also support other search and crawl provider such as FireCrawl and SerpAPI (Optional but yield better performance):
```bash
JINA_API_KEY=your_jina_key
FIRECRAWL_API_KEY=your_firecrawl_key
SERPAPI_API_KEY=your_serpapi_key 
```

We are supporting image generation and video generation tool by Vertex AI (Optional, good for more creative output), to use this, you need to set up the following variables:
```bash
MEDIA_GCS_OUTPUT_BUCKET=gs://your_bucket_here
MEDIA_GCP_PROJECT_ID=your_vertex_project_id
MEDIA_GCP_LOCATION=your_vertex_location
```

Image Search Tool  (Optional, good for more beautiful output)
```
SERPAPI_API_KEY=your_serpapi_key 
```


## Installation

### Docker Installation (Recommended)

1. Clone the repository
2. Set up the 2 environment files as mentioned in the above step
3. If you are using Anthropic Client run
```
chmod +x start.sh stop.sh
./start.sh 
```
If you are using Vertex, run with these variables
```
GOOGLE_APPLICATION_CREDENTIALS=absolute-path-to-credential \
PROJECT_ID=project-id \
REGION=region \
./start.sh
```
*Note: Due to a bug in the latest docker, if you receive and error, try running with `--force-recreate`. For example `./start.sh --force-recreate `*

After running start.sh, you can check your application at: localhost:3000

Run `./stop.sh` to tear down the service.

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

### Command Line Interface

If you want to use anthropic client, set `ANTHROPIC_API_KEY` in `.env` file and run:
```bash
python cli.py 
```

If you want to use vertex, set `GOOGLE_APPLICATION_CREDENTIALS` and run:
```bash
GOOGLE_APPLICATION_CREDENTIALS=path-to-your-credential
python cli.py --project-id YOUR_PROJECT_ID --region YOUR_REGION
```

Options:
- `--project-id`: Google Cloud project ID
- `--region`: Google Cloud region (e.g., us-east5)
- `--workspace`: Path to the workspace directory (default: ./workspace)
- `--needs-permission`: Require permission before executing commands
- `--minimize-stdout-logs`: Reduce the amount of logs printed to stdout

### Web Interface

1. Start the WebSocket server:

When using Anthropic client:
```bash
python ws_server.py --port 8000
```

When using Vertex:
```bash
GOOGLE_APPLICATION_CREDENTIALS=path-to-your-credential \
python ws_server.py --port 8000 --project-id YOUR_PROJECT_ID --region YOUR_REGION
```

2. Start the frontend (in a separate terminal):

```bash
cd frontend
npm run dev
```

3. Open your browser to http://localhost:3000

## Project Structure

- `cli.py`: Command-line interface
- `ws_server.py`: WebSocket server for the frontend
- `src/ii_agent/`: Core agent implementation
  - `agents/`: Agent implementations
  - `llm/`: LLM client interfaces
  - `tools/`: Tool implementations
  - `utils/`: Utility functions


## Core Capabilities

II-Agent is a versatile open-source assistant built to elevate your productivity across domains:

| Domain | What II‑Agent Can Do |
|--------|----------------------|
| Research & Fact‑Checking | Multistep web search, source triangulation, structured note‑taking, rapid summarization |
| Content Generation | Blog & article drafts, lesson plans, creative prose, technical manuals, Website creations |
| Data Analysis & Visualization | Cleaning, statistics, trend detection, charting, and automated report generation |
| Software Development | Code synthesis, refactoring, debugging, test‑writing, and step‑by‑step tutorials across multiple languages |
| Workflow Automation | Script generation, browser automation, file management, process optimization |
| Problem Solving | Decomposition, alternative‑path exploration, stepwise guidance, troubleshooting |

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

