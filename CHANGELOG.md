# Changelog
All notable changes to this project will be documented in this file.  
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)  
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]
### Added
- **Multi-agent Swarm**: groundwork for MCP protocol (RFC drafted, not yet enabled).
- **Memory v2**: vector-store long-term memory (feature flag hidden).
- **Helm chart** for Kubernetes and Terraform module for AWS EKS.
- **Vision & Whisper integration** (Claude Vision + Whisper 3) behind `--experimental-mm` flag.

### Changed
- Default browser worker replicas auto-scale based on `LLM_PENDING_REQUESTS`.
- Token counter switched to tokenizer-aware estimation library.
- GAIA batch runner accepts `--cost-cap` parameter to abort expensive tasks.

### Removed
- Legacy `simple_memory.py` slated for deprecation once Memory v2 lands.

---

## [0.2.0] - 2025-05-31
### Added
- **Comprehensive documentation suite** under `docs/`:
  - `technical_overview.md`, `architecture.md`, `usage.md`, `examples.md`,
    `api_reference.md`, `tool_development.md`, `performance_benchmarks.md`,
    `security_deployment.md`, `roadmap.md`, `faq.md`, plus index page.
- **Revised `CONTRIBUTING.md`** emphasising open-source spirit and fork-workflow.
- **Performance & Benchmarks** guide with GAIA leaderboard numbers.
- **Security & Deployment** hardening guide.
- **Roadmap** outlining short-, medium-, and long-term goals.
- **FAQ** for installation, config, troubleshooting.
- **CHANGELOG.md** (this file).

### Changed
- `README.md` now links to documentation index.
- Context-manager pipeline default: `summary+forgetting`.
- CLI/WS: reduced default thinking tokens to `0` for cost efficiency.
- Tool registry exposes JSON schema via `/tools` endpoint (internal use).

### Removed
- `CODE_OF_CONDUCT.md` and `SUPPORT.md` (moved relevant content into docs).

### Fixed
- SQLite write contention by enabling WAL mode on startup.
- Browser CV detector fallback when no visible interactive elements.

---

## [0.1.0] - 2025-05-20
### Added
- **Initial public release** of II-Agent:
  - Core `BaseAgent` orchestration loop with Anthropic Claude function-calling.
  - Token-aware context managers (`llm_summarizing`, `amortized_forgetting`).
  - 40+ built-in tools (browser, bash, pdf/audio, research, visualization).
  - Command-line interface (`cli.py`).
  - WebSocket backend (`ws_server.py`) and React/Next.js frontend.
  - Docker Compose stack for backend + frontend.
  - GAIA benchmark runner (`run_gaia.py`) with trace logging.
  - Unit / integration tests, pre-commit hooks, CI workflow.

[Unreleased]: https://github.com/Intelligent-Internet/ii-agent/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/Intelligent-Internet/ii-agent/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/Intelligent-Internet/ii-agent/releases/tag/v0.1.0
