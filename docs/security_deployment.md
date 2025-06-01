# Security & Deployment Guide

This guide details how to **safely deploy II-Agent in production**, protect user data, and operate the system at scale.

---

## 1  Deployment Patterns

| Pattern | When to Use | Stack |
|---------|-------------|-------|
| **All-in-One Docker Compose** | PoC / single-host staging | `backend + db + frontend` on one VM |
| **Kubernetes Micro-services** | Multi-tenant SaaS or on-prem enterprise | `backend`, `frontend`, `browser-workers`, `postgres`, optional `redis` |
| **Serverless API** | Burst workloads, cost-optimised batch | `backend` on Cloud Run / Lambda; object storage for workspaces; Cloud SQL R/W replica |

### Reference Helm Chart (K8s)

```
charts/
 ├─ ii-agent-backend          # FastAPI + Uvicorn
 ├─ ii-agent-frontend         # Next.js static site
 ├─ ii-agent-browser-workers  # Playwright jobs
 └─ postgres
```

*Images are built from `docker/backend/Dockerfile` and `docker/frontend/Dockerfile`.*

---

## 2  Security Model Overview

```
+---------------------------+
|  Public Internet          |
+---┬-----------------------+
    | HTTPS
    ▼
┌──────────────┐   WS/REST     ┌─────────────┐
│  API Gateway ├──────────────▶│  Backend    │
└──────────────┘               │  (FastAPI)  │
                               └────┬────────┘
         Secrets / TLS               │ gRPC
                                      ▼
                               ┌─────────────┐
                               │ BrowserPool │  ← isolated
                               └────┬────────┘
     DB (TLS)                       │
           ┌────────────────────────▼────────┐
           │ PostgreSQL / SQLite (sessions)  │
           └──────────────────────────────────┘
```

* Every external request is terminated at an **API Gateway** with WAF & rate-limits.  
* **Backend** is stateless; all user files stay in a per-session workspace.  
* **BrowserPool** pods run Playwright with seccomp/apparmor confinement.  

---

## 3  Sandboxing & Permission Model

| Layer | Mechanism | Default |
|-------|-----------|---------|
| File system | `WorkspaceManager` scopes all paths to `workspace/<session>` | strict |
| Shell exec | `bash_tool` runs in a non-root UID with `--needs-permission` gate | ask |
| Browser | Playwright `--no-sandbox` **disabled**; Chromium runs in user NS; CV clicks only visible elems | strict |
| Python runtime | `pydantic` validation of tool params; JSON only | strict |
| Network | Egress limited to TCP 80/443 unless `VISIT_WEB` tool whitelisted | strict |

### Hardening Tips

1. Run backend user as **non-root** inside container.  
2. Mount `workspace/` on a dedicated volume with `noexec,nodev`.  
3. Use **seccomp-bpf** profile that denies `ptrace`, `mount` syscalls.  
4. Add `CAP_DROP=ALL` and keep only `CAP_NET_RAW` if needed.  

---

## 4  Network Security

* **TLS 1.3** everywhere; rotate certs via ACME or cloud cert-manager.  
* Enable **WAF rules** for common attacks (SQLi, XSS) even though backend is JSON-only.  
* Limit egress IP ranges; force browser pods through upstream **HTTP proxy** for audit.  
* Optionally isolate LLM traffic via private VPC endpoints (Anthropic/Vertex).  

---

## 5  API Key Management

| Secret | Recommendation |
|--------|----------------|
| `ANTHROPIC_API_KEY` | Store in cloud secret manager; mount at runtime; rotate quarterly |
| `OPENAI_API_KEY` | Scope to image/video gen only; enable usage caps |
| `TAVILY_API_KEY` etc. | Use distinct keys per environment |
| `GOOGLE_APPLICATION_CREDENTIALS` | Prefer workload identity on GKE / IAM role on AWS |

Use **12-factor** environment variables.  
Never bake secrets into container images or git history (pre-commit hook rejects).

---

## 6  Monitoring & Logging

### 6.1 Structured Logs

| Field | Description |
|-------|-------------|
| `session_id` | UUID per user session |
| `event_type` | TOOL_CALL / TOOL_RESULT / AGENT_MSG / ERROR |
| `latency_ms` | Wall-clock per request |
| `tokens_in/out` | Prompt / completion counters |

Logs are emitted in JSON; ship to **ELK, Cloud Logging, or Loki**.

### 6.2 Metrics

* `llm_latency_seconds` - histogram  
* `tool_error_total{tool=...}`  
* `active_sessions` gauge  
* `api_requests_total{status}`

Expose `/metrics` for **Prometheus** scrape.

### 6.3 Tracing

Enable **OpenTelemetry** in `utils.py` to trace each reasoning loop → tool path.

---

## 7  Scaling Considerations

1. **Horizontal Pod Autoscaling** on p95 CPU **and** `LLM_PENDING_REQUESTS`.  
2. Offload heavy browser tasks to a **worker queue** (RabbitMQ/Redis Streams).  
3. Store workspace artifacts in **object storage** (S3/GCS) and serve via CDN.  
4. Split long-running batch (`run_gaia.py`) into CronJob + job queue cluster.  
5. Use **cloud NAT** pools to avoid IP-block exhaustion when crawling.  

---

## 8  Operational Best Practices

| Practice | Checklist |
|----------|-----------|
| **CI / CD** | `pre-commit`, `pytest`, `ruff`, `docker build --sbom`, Snyk scan |
| **Backups** | Daily DB dump; weekly object storage replication |
| **Incident Response** | Alert on 5xx > 1% or tool error spike |
| **Rate Limits** | 60 req/min IP-based; per-API key quota |
| **Data Retention** | Purge workspace files after 14 days (configurable) |
| **Pen-Testing** | Quarterly; focus on SSRF via browser tools |
| **Dependency Updates** | Dependabot + Renovate for Python/Node |

---

## 9  FAQ

**Q:** *Can I disable network access entirely?*  
**A:** Set env `DISABLE_VISIT_WEB=1`; web tools will short-circuit.

**Q:** *How do I audit tool outputs?*  
**A:** Enable trace logging (`TRACE_LOGS=1`); each event includes SHA-256 of any saved file and URL it’s served under.

**Q:** *What if an LLM leaks sensitive data in prompts?*  
**A:** Use prompt redaction middleware—regex or OpenAI content-filter—to scrub before logging.

---

## 10  Further Reading

* [Technical Overview](technical_overview.md)  
* [Architecture](architecture.md) – component diagram  
* [Usage Guide](usage.md) – runtime flags  
* [OpenTelemetry Spec](https://opentelemetry.io/)  
* [CIS Docker Benchmark](https://docs.docker.com/go/cis-docker-benchmark/)  

---

*Last updated: 31 May 2025*  
