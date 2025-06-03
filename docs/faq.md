# Frequently Asked Questions (FAQ)

_Last updated: 31 May 2025_

---

## 📦 Installation

### Q1  I ran `pip install -e .[dev]` and Playwright fails with “Executable doesn’t exist”.
Install Chromium once:

```bash
playwright install chromium
```

When using Docker, the backend image already runs this step in `docker/backend/Dockerfile`.  
On Apple M-series chips be sure Xcode CLI tools are installed.

### Q2  `npm run dev` throws “ELIFECYCLE ERR ENOENT”.
Make sure you are in the `frontend/` directory and have Node 18 + npm 9+. Run:

```bash
corepack enable && pnpm install   # alternative to npm/yarn
```

---

## ⚙️ Configuration

### Q3  Which environment variables are **required**?
Minimal backend `.env`:

```
ANTHROPIC_API_KEY=sk-...
TAVILY_API_KEY=tv-...
STATIC_FILE_BASE_URL=http://localhost:8000/
```

Add `GOOGLE_APPLICATION_CREDENTIALS`, `PROJECT_ID`, and `REGION` when using Vertex Anthropic.

### Q4  Why does the Web UI show “Cannot connect to WebSocket backend”?
* Backend not running: `python ws_server.py --port 8000`  
* `NEXT_PUBLIC_API_URL` in `frontend/.env` must match backend origin.  
* If using HTTPS reverse-proxy, enable `--cors-allow-origins "*"` on backend.

---

## 🚀 Performance & Tuning

### Q5  How do I reduce API cost?
* Use `--context-manager summary+forgetting` (default in CLI).  
* Lower `MAX_ITERATIONS` (e.g. `6`).  
* Increase summarisation ratio: `LLM_SUMMARY_RATIO=0.3`.  
* Disable “thinking mode” tokens for short tasks (`--thinking-tokens 0`).

### Q6  Browser tools feel slow.
* Run browser pods locally to avoid cold-start in Docker.  
* Disable PDF/PNG upload with `DISABLE_SCREENSHOTS=1`.  
* Use `BROWSER_POOL_SIZE=4` for parallelism.

---

## 🔐 Security

### Q7  Can II-Agent read files outside its workspace?
No. `WorkspaceManager` resolves paths under `workspace/<session_uuid>` only.  
Attempting `../` escapes raises `PermissionError`.

### Q8  How do I sandbox shell commands?
Leave `--needs-permission` **true** (default) to prompt before executing each `bash_tool` call, or revoke the tool entirely by removing it from `ToolManager.default()`.

### Q9  Best practices for secret management?
Store keys in a cloud secret manager and inject at runtime; never commit secrets.  
Docker users can mount a read-only `.env` file via `--env-file`.

---

## ⚖️ Comparison with Other Agents

| Feature                | II-Agent | OpenAI Deep Research | Manus | GenSpark |
|------------------------|----------|----------------------|-------|----------|
| Licence               | Apache-2 | Closed-source | AGPL | Closed |
| GAIA accuracy (2025-05) | **56 %** | 48 % | 52 % | 46 % |
| Cost / GAIA run        | **\$409** | \$618 | \$465 | \$540 |
| Browser automation     | Playwright + CV | Puppeteer | Playwright | Headless Chrome |
| Extensibility          | 40+ pluggable tools | limited | medium | limited |

---

## 📝 Licensing

### Q10  Can I use II-Agent in commercial software?
Yes. Apache 2.0 permits commercial and closed-source use provided you preserve the licence and notice files.

### Q11  Are generated artifacts (slides, code) also Apache 2.0?
Content produced by the agent is yours; no additional licence is imposed.

---

## 🤝 Contributing

### Q12  What is the contribution workflow?
1. Fork → clone → create feature branch (`feat/<topic>`).  
2. Run `pre-commit run --all-files`.  
3. Add tests (`pytest`) and docs (`docs/`).  
4. Open a PR against `Intelligent-Internet/ii-agent:main`.  
5. CI must pass; at least one maintainer review.

### Q13  How do I create a new tool?
See [`docs/tool_development.md`](tool_development.md) for a full tutorial.

---

## 🛠️ Troubleshooting Common Errors

| Error Message | Cause | Fix |
|---------------|-------|-----|
| `ValueError: prompt too long` | context > `MAX_CONTEXT_TOKENS` | switch to `summary` manager or raise limit |
| `playwright._impl._api_types.TimeoutError` | element not visible | increase `wait` param or scroll first |
| `403 from LLM API` | wrong key or quota exhausted | verify env vars; check provider dashboard |
| `sqlite3.OperationalError: database is locked` | concurrent writes on SQLite | use Postgres in production or set `PRAGMA journal_mode=WAL;` |

---

## ⚙️ Operational Questions

### Q14  How do I purge old session files?
Set `WORKSPACE_RETENTION_DAYS=14` and run `python utils/cleanup.py` as a daily cron, or mount workspace on a tmpfs in staging.

### Q15  Is horizontal scaling supported?
Yes. Backend is stateless; share a DB and object store. Use a queue (Redis, RabbitMQ) for browser-worker jobs.

### Q16  Where are trace logs stored?
If `TRACE_LOGS=1`, each session writes JSON to `trace_logs/<session>.jsonl`. Excellent for replay/debugging.

### Q17  How do I upgrade to a newer Claude model?
Export `CLAUDE_MODEL=claude-4-opus` (if available) or pass `--model` flag in `cli.py` / `ws_server.py`.

---

Still stuck?  
* **GitHub Discussions** – ask the community.  
* **Discord #help** – real-time troubleshooting.  
* **security@ii.inc** – responsible disclosure.  
