---
id: llm-auth
title: LLM and Authentication Variables
slug: /required-environment-variables/llm-auth
sidebar_position: 13
---

The backend relies on these secrets to talk to model providers, orchestrate researcher/report agents, and enable OAuth flows.

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

