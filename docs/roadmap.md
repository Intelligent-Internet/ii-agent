# II-Agent Roadmap

_Last updated: **31 May 2025**_

---

## 1  Current Status  🚦

| Area | State | Notes |
|------|-------|-------|
| Core Agent | **Stable v0.2** | Anthropic-Claude function-calling loop, token-aware context managers, 40+ built-in tools |
| Interfaces | CLI ✔ · WebSocket ✔ · React UI ✔ | Docker Compose & manual installs supported |
| Benchmarks | **GAIA #1** (56 % accuracy)<br>`2025-05` run | Validation set; traces published |
| Community | 2 k ⭐ · 300 forks · 40+ PRs merged | Discord launched 2025-05 |
| Licence | Apache 2.0 | Fully open-source, commercial use allowed |

---

## 2  Short-Term Goals ( 0 – 3 months )  🎯

| Theme | Milestone | ETA | Owner / Help Wanted |
|-------|-----------|-----|---------------------|
| 📦 **Release v0.3** | Cut tagged release with SBOM & signed images | Jun 2025 | maintainers |
| 🛠 **Tool SDK polish** | Publish PyPI package `ii-agent-toolkit`; improve type stubs | Jun 2025 | **community** |
| 🧪 **Benchmark parity** | Re-run GAIA with Vertex Anthropic & publish cost diff | Jul 2025 | research guild |
| 🔐 **Security hardening** | Add seccomp profile & OTel trace redaction | Jul 2025 | security volunteers |
| 📖 **Docs site** | Deploy MkDocs site on GitHub Pages (using current `/docs`) | Jul 2025 | **docs squad** |

---

## 3  Medium-Term Goals ( 6 – 12 months )  🚀

| Theme | Objective | Target Q |
|-------|-----------|----------|
| 🧠 **Multi-agent Swarm** | First MVP of II-Swarm protocol (MCP) for agent-to-agent comms | Q4 2025 |
| 💹 **Benchmark Expansion** | Add SWE-Bench, BIG-Bench Hard, GPQA; automate nightly CI runs | Q4 2025 |
| 🖼 **Full Multimodality** | Integrate Vision Claude + Whisper 3; browser screenshot OCR replace CV detector | Q1 2026 |
| 🔄 **Memory v2** | Vector-DB long-term memory (Chroma) w/ retrieval-augmented planning | Q1 2026 |
| ☁️ **Cloud Helm Chart** | Certified Helm chart for K8s & Terraform module for AWS EKS | Q1 2026 |

---

## 4  Long-Term Vision 🌐

> _“Autonomous, auditable agents for every regulated industry.”_

1. **Proactive Intelligence** – agents that plan across days/weeks, coordinate via open swarm protocols.  
2. **Regulatory-grade Transparency** – cryptographic audit logs, deterministic re-play, verifiable provenance.  
3. **Pluggable Foundation Models** – model-agnostic interfaces, on-prem fine-tuned Llama 4, Claude 4.x, Gemini Ultra.  
4. **Domain Packs** – healthcare, finance, education: curated toolkits + guardrails.  
5. **Community Governance** – steering council + RFC process to guide changes.

---

## 5  Upcoming Features 🆕 (next release cycles)

| Feature | Status | PR / Issue |
|---------|--------|------------|
| YAML-based workflow macros (`.ii.yaml`) | design spec drafted | #312 |
| Live-share sessions via URL | PoC | #287 |
| Browser video recording tool | in-progress | #301 |
| Plugin marketplace (tool registry) | backlog | #290 |
| Managed API SaaS tier | internal alpha | n/a |

---

## 6  Community Initiatives 🤝

| Initiative | Description | How to Join |
|------------|-------------|-------------|
| **Docs-Squad** | Sprint to convert `/docs` into MkDocs | #docs channel on Discord |
| **Benchmark Task Force** | Automate nightly GAIA/SWE-Bench runs | GitHub Discussions #benchmarks |
| **Tool-Jam** | Monthly hackathon—build a new tool in 24 h | Event calendar |
| **Localization** | Translate UI + docs (🇪🇸 🇨🇳 🇩🇪) | open `i18n` issues |
| **Security SIG** | Threat-model, pen-test, harden deployments | email security@ii.inc |

---

## 7  Integrations & Ecosystem 📚

| Integration | Status | Notes |
|-------------|--------|-------|
| **VS Code Extension** | prototype | run agent in editor sidebar |
| **Jupyter Magic** | planned | `%ii` cell magic to call agent |
| **Home Assistant** | PoC | agent as automation brain |
| **Slack Bot** | stable | webhook + WS bridge |
| **LangChain** | draft PR | II-Agent executor wrapper |

Contributions in the form of connectors or wrappers are **highly encouraged**.

---

## 8  Benchmarks 📈

| Benchmark | 2025-05 Score | Target |
|-----------|---------------|--------|
| **GAIA** (val) | **56.4 %** | 60 %+ by Q3 |
| SWE-Bench | n/a | ≥ 30 % pass rate |
| GPQA | n/a | Top-3 accuracy |
| BIG-Bench Hard | n/a | track |
| HumanEval+ | n/a | track |

*All benchmark harnesses will be published under `benchmarks/`.*

---

## 9  How _You_ Can Contribute 🔧

| Roadmap Item | Contribution Ideas |
|--------------|--------------------|
| **Docs Site** | Improve navigation, add GIFs, translate pages |
| **Tool SDK** | Build example tools (database, email, IoT), write tutorials |
| **Swarm Protocol** | Prototype message-passing over gRPC / MQTT |
| **Benchmark Harness** | Add new dataset loaders, write evaluation scripts |
| **Security Hardening** | Craft seccomp profile, run dependency scans, file CVEs |
| **Domain Packs** | Draft healthcare tool schemas, de-identify datasets |
| **Integrations** | Write LangChain runnable, create VS Code extension |

Start by opening an **Issue** or **GitHub Discussion** to co-ordinate, or claim an item labelled `good first issue` / `help wanted`.

---

### Funding & Sponsorship

If your organisation relies on II-Agent, please consider sponsoring development or reserving maintainer time for roadmap features.  Contact: _partners@ii.inc_.

---

Together, we will build the reference open-source agent platform.  
**Join us—PRs welcome!**
