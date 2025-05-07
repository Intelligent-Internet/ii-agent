# II Agent

An intelligent agent platform using Anthropic Claude models to assist with tasks through both a command-line interface and a web interface.

## Overview

II Agent is built around providing an agentic interface to Anthropic Claude models. It offers:

- A CLI interface for direct command-line interaction
- A WebSocket server that powers a modern React-based frontend
- Integration with Google Cloud's Vertex AI for API access to Anthropic models

## Requirements

- Python 3.10+
- Node.js 18+ (for frontend)
- Google Cloud project with Vertex AI API enabled or Anthropic API key

## Installation

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

## Usage

### Command Line Interface

Start the CLI with:

```bash
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

```bash
export STATIC_FILE_BASE_URL=http://localhost:8000
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


