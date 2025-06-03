# II-Agent – Usage Guide

This document explains how to **install**, **configure**, and **run** II-Agent in every supported mode:

1. Quick install (pip or Docker)
2. Environment-variable configuration
3. Running:
   * Command-line interface (CLI)
   * WebSocket back-end + React front-end
   * Batch / benchmark runner
4. Advanced options & tips

---

## 1. Installation

### 1.1 Via `pip` (recommended for local dev)

```bash
# Clone the repo (fork first if you plan to contribute)
git clone https://github.com/Intelligent-Internet/ii-agent.git
cd ii-agent

# Create & activate virtual environment
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# Install core + dev extras
pip install -e .[dev]
```

Playwright (browser tools) needs browsers:

```bash
playwright install chromium
```

### 1.2 Via **Docker Compose** (all-in-one stack)

> Requires Docker ≥ 24 and Docker Compose plugin.

```bash
# Copy sample env files
cp .env.example .env
cp frontend/.env.example frontend/.env

# Build & start
./start.sh                 # or: docker compose up --build
```

The script spins up:

| Service   | Port | URL                            |
|-----------|------|--------------------------------|
| Back-end  | 8000 | http://localhost:8000          |
| Front-end | 3000 | http://localhost:3000          |

`./stop.sh` tears everything down.

---

## 2. Configuration

All secrets & tunables live in **`.env`** (backend) and **`frontend/.env`**.

### 2.1 Minimal `.env` (backend)

```
# Required
ANTHROPIC_API_KEY=sk-...
TAVILY_API_KEY=tv-...
STATIC_FILE_BASE_URL=http://localhost:8000/

# Optional (unlock extra tools)
JINA_API_KEY=
FIRECRAWL_API_KEY=
SERPAPI_API_KEY=
OPENAI_API_KEY=
OPENAI_AZURE_ENDPOINT=
```

If you run on **Vertex AI Claude**:

```
GOOGLE_APPLICATION_CREDENTIALS=/abs/path/service-account.json
PROJECT_ID=my-gcp-project
REGION=us-east5
```

### 2.2 Front-end `.env`

```
NEXT_PUBLIC_API_URL=http://localhost:8000
```

---

## 3. Running II-Agent

### 3.1 Command-line Interface (CLI)

```bash
# Anthropic backend
python cli.py

# Vertex backend
GOOGLE_APPLICATION_CREDENTIALS=cred.json \
python cli.py --project-id $PROJECT_ID --region $REGION
```

Useful flags:

| Flag | Default | Description |
|------|---------|-------------|
| `--workspace` | ./workspace | Where session files are stored |
| `--needs-permission` | **true** | Ask before executing bash / browser tools |
| `--minimize-stdout-logs` | false | Hide verbose tokens & debug lines |

Stop the session with `Ctrl-C`.

### 3.2 WebSocket Back-end

```bash
python ws_server.py --port 8000
```

Options mirror `cli.py` (`--project-id`, `--region`, `--workspace`, …).

### 3.3 Front-end (React / Next.js)

In a separate terminal:

```bash
cd frontend
npm install          # first time only
npm run dev          # or: npm run build && npm start
```

Open <http://localhost:3000> – the UI connects to the WS server automatically.

### 3.4 Batch Runner (GAIA benchmark or custom dataset)

```bash
python run_gaia.py \
  --dataset-path data/gaia.jsonl \
  --output-dir output/gaia-run \
  --start-index 0 \
  --end-index 99 \
  --task-uuid 2025-05-30
```

Key arguments:

| Arg | Purpose |
|-----|---------|
| `--dataset-path` | JSONL file containing tasks |
| `--start-index / --end-index` | Slice dataset for partial runs |
| `--task-uuid` | Tag results for trace lookup |
| `--context-manager` | Override strategy (`summary`, `forgetting`, …) |
| `--memory-tool` | Enable long-term memory store |

Outputs:

* `trace_logs/` – per-task event dumps
* `metrics.json` – accuracy & token stats

---

## 4. Environment Variables Reference

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | ✔ if using Anthropic | Claude API key |
| `GOOGLE_APPLICATION_CREDENTIALS` | ✔ if using Vertex | Path to GCP service-account JSON |
| `PROJECT_ID`, `REGION` | same | GCP project & region for Vertex |
| `TAVILY_API_KEY` | ✔ | Web search |
| `STATIC_FILE_BASE_URL` | ✔ | Public URL prefix for workspace files |
| `OPENAI_API_KEY` | optional | Image generation & Gemini tools |
| `JINA_API_KEY`, `FIRECRAWL_API_KEY`, `SERPAPI_API_KEY` | optional | Alt search / crawl providers |
| `PLAYWRIGHT_BROWSERS_PATH` | optional | Override browser cache dir |

---

## 5. Advanced Options

### 5.1 Permissionless Mode

Add flag `--needs-permission false` (CLI/WS) **or** enable **Auto Triggers** (UI) to skip interactive approval.

### 5.2 Custom Context Management

Both `cli.py` and `ws_server.py` expose:

```bash
--context-manager summary            # LLMSummarizingContextManager
--context-manager forgetting         # AmortizedForgettingContextManager
--context-manager summary+forgetting # Pipeline (both)
```

### 5.3 Workspace Location & Persistence

* Default: `./workspace/<session_uuid>/`
* Override with `--workspace /tmp/custom-workspace`
* Docker volume `workspace_data` keeps files across container restarts.

### 5.4 Logging

* Text logs stream to stdout (respect `--minimize-stdout-logs`).  
* Detailed per-session traces live in `trace_logs/` when `TRACE_LOGS=1`.  
* Set `LOG_LEVEL=DEBUG` for verbose internal debugging.

---

## 6. Troubleshooting

| Symptom | Fix |
|---------|-----|
| “Playwright browsers not found” | Run `playwright install chromium`, or ensure Docker image built with `--build`. |
| WS front-end shows *“Cannot connect”* | Check backend running on `port 8000` & `NEXT_PUBLIC_API_URL`. |
| Context overflow errors | Try `--context-manager forgetting` or lower `MAX_CONTEXT_TOKENS` in `.env`. |
| CLI hangs on tool step | Some tools (e.g., browser) need X display on Linux; run with `xvfb-run -s "-screen 0 1024x768x24" python cli.py` or use Docker. |

---

Happy automating — and feel free to open an issue if you hit a snag!  
