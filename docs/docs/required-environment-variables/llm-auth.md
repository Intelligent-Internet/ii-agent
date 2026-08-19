---
id: llm-auth
title: LLM and Authentication Variables
slug: /required-environment-variables/llm-auth
sidebar_position: 13
---

The backend relies on these secrets to talk to model providers, orchestrate researcher/report agents, and enable OAuth flows.

## Optional inner loop mode controls

These settings are optional and are intended for teams evaluating delegated A2A execution. For normal onboarding, keep the default `native` mode.

```bash
AGENT_INNER_LOOP_MODE=native
AGENT_A2A_AGENT_URL=http://localhost:18100
AGENT_A2A_TIMEOUT_SECONDS=30
AGENT_A2A_FALLBACK_TO_NATIVE=true
AGENT_A2A_CONTEXT_REUSE=true
```

### Practical guidance

- Use `native` as your baseline for production onboarding.
- Use `a2a` when you want to test delegated Copilot-style inner-loop behavior.
- Keep fallback enabled to preserve reliability if the adapter is unavailable.
- If your deployment uses Copilot-backed delegated inference, it is often significantly cheaper than direct API-key-only native inference.
- If delegated mode is configured as BYOK passthrough, cost follows your provider billing plan.

### What still stays native in `a2a` mode

Even when delegated mode is enabled, II-Agent intentionally keeps some request categories on the native path:

- Slides workflows.
- Storybook generation.
- Media generation.
- Connector-backed operations.
- Planning/milestone workflows.
- Dev infrastructure operations.
- Safety/compliance/capability exceptions.

This preserves platform behavior while allowing delegated routing for eligible requests.

## `LLM_CONFIGS`

1. Decide which providers you want to use (OpenAI-compatible, Anthropic, Gemini, etc.).
2. For each provider, collect the API key and base URL if the provider requires a custom endpoint.
3. Build a JSON array describing each model, e.g.:
   ```json
   [
     {
       "provider": "openai",
       "model": "gpt-4o-mini",
       "apiKey": "sk-your-key",
       "baseUrl": "https://api.openai.com/v1",
       "maxRetries": 3
     }
   ]
   ```
4. Paste the serialized JSON blob into `LLM_CONFIGS` (wrap the value in single quotes inside `.stack.env` so special characters survive).

### Supported Anthropic models

The frontend model selector includes:

- `claude-sonnet-4-5` / `claude-sonnet-4-6`
- `claude-opus-4-5` / `claude-opus-4-6`

When extended thinking is enabled (`thinking_tokens >= 1024`), the Anthropic provider automatically sets `max_tokens = thinking_tokens + 8192` to leave room for both reasoning and the final response.

