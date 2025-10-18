# Scribe AI-Salon Runtime

Scribe AI-Salon is an orchestration environment designed for multi-agent research, live voice collaboration, and model experimentation. This branch finalises the pure Scribe namespace for the salon runtime, Agent-S personas, safe-mode registry, and related tooling.

## What's inside

- **scribe_core/** – provider routing scaffolding plus shared infrastructure for safe-mode, storage, and sandbox helpers
- **scribe_agents/** – Agent-S personas/orchestrator, salon coordination, tool library, and voice adapters
- **apps/scribe-web/** – WebSocket handlers and HTTP routes for salon and research entry points
- **frontend/** – Next.js experience for orchestrating salons and research sessions

## Getting started

```bash
pip install -e .
uvicorn scribe_core.server.app:create_app --factory --reload
```

Export the provider API keys required for your target models (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, etc.) before booting the server.

### Frontend

The existing Next.js frontend continues to live under `frontend/`. To exercise the new registry hook and model picker:

```bash
cd frontend
npm install
npm run dev
```

The UI fetches the registry from `/api/models` and augments the provider selectors dynamically.

## Voice, Safe Mode, and Salon

All Agent-S tooling is exposed under `scribe_agents.agent_s`. The salon WebSocket runtime (`apps/scribe-web/api/ws/handlers.py`) uses the new `ProviderRouter` to invoke models, while the voice services and safe-mode registry live under `scribe_agents/voice` and `scribe_core/safe_mode` respectively.

## Guardrails

- `.claude/hooks/validate_write_paths.py` denies write attempts outside the allowed Scribe namespaces.
- `.github/workflows/ci.yml` invokes `scripts/ci/no-legacy-namespace.sh` to ensure legacy namespaces do not creep back into the tree.

## Next steps

- Flesh out the research board flows (Novix-style L1/L2 intake) in the UI.
- Expand `ProviderRouter.send_message` with streaming responses and richer message assembly.
- Finalise the co-scientist pipeline by wiring the research stages to real toolchains.

The repo is now ready to continue Scribe development without dependencies on the earlier fork.
