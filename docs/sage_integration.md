# SAGE persistent memory integration

[SAGE](https://github.com/l33tdawg/sage) (Sovereign Agent Governed
Experience) is a BFT-consensus memory layer for AI agents. This
integration wires ii-agent into a SAGE node via the official async Python
SDK so each agent turn recalls prior committed memories before the model
runs and stores an observation after the turn completes.

## Installation

The SAGE SDK is an optional extra — the framework runs fine without it:

```bash
pip install "ii-agent[sage]"
```

## Environment variables

All configuration is driven by environment variables. No secrets live in
the source tree.

| Variable                 | Default              | Description                                                                                               |
| ------------------------ | -------------------- | --------------------------------------------------------------------------------------------------------- |
| `SAGE_ENABLED`           | `false`              | Master switch. When false, `register_sage_hooks` is a no-op and the integration never contacts any node. |
| `SAGE_NODE_URL`          | `http://localhost:8090` | Base URL of the SAGE REST API.                                                                       |
| `SAGE_AGENT_ID`          | unset                | Optional display name for the agent on the SAGE network.                                                 |
| `SAGE_AGENT_KEY`         | unset                | Filesystem path to a 32-byte Ed25519 seed. Falls back to `AgentIdentity.default()`.                      |
| `SAGE_DEFAULT_DOMAIN`    | `ii-agent`           | Domain tag used for recall and propose when no per-call override is supplied.                            |
| `SAGE_RECALL_TOP_K`      | `5`                  | Number of memories fetched per pre-hook recall.                                                          |
| `SAGE_PRE_HOOK_TIMEOUT_S`| `2.0`                | Strict timeout (seconds) for the pre-hook recall. On timeout the agent turn proceeds with no context.    |

## Registering the integration

```python
from ii_agent.agents.agent import IIAgent
from ii_agent.integrations.sage import register_sage_hooks

agent = IIAgent(
    user_id="user-123",
    session_id="session-abc",
    model=...,
)

# Appends a pre-hook and a post-hook to the agent. No-op when SAGE_ENABLED is false.
register_sage_hooks(agent)
```

`register_sage_hooks` extends (not replaces) the agent's existing
`pre_hooks` / `post_hooks` lists, so it is safe to combine SAGE with
other observability or policy hooks.

## Turn lifecycle

1. **Pre-hook (blocking, bounded)** — before the model runs, the pre-hook
   embeds the user's input and calls `AsyncSageClient.query()` for
   semantically similar committed memories under `SAGE_DEFAULT_DOMAIN`.
   Results are formatted into a context block and prepended to the
   user's input so the model sees both.
2. **Post-hook (background)** — after the model responds, the post-hook
   is scheduled as a FastAPI background task via
   `@hook(run_in_background=True)`. It submits a concise observation of
   the turn via `AsyncSageClient.propose()`. The agent response is
   returned to the caller without waiting for BFT consensus.

## Fallback behaviour

The integration is defensive by design. **None** of the following
conditions block or fail an agent turn:

- `SAGE_ENABLED` unset or `false` — `register_sage_hooks` is a no-op.
- `sage-agent-sdk` extra not installed — the integration logs a debug
  message and falls back to a no-op.
- SAGE node unreachable — `is_available()` returns `False`; recall
  returns an empty list; propose is skipped.
- Pre-hook recall times out (default 2 s) — the turn proceeds with no
  injected context.
- Any SDK exception on recall or propose — caught, logged at debug level,
  swallowed.

If you need end-to-end correctness guarantees (e.g. an audit trail that
cannot skip turns), run the SAGE node in-process or behind a reverse
proxy with its own retry semantics — this integration deliberately
prioritises agent-turn latency over delivery guarantees.

## Testing

Unit tests live under `src/tests/unit/integrations/` and cover:

- Hook registration is a no-op when `SAGE_ENABLED` is false.
- Hook registration appends two callables to the agent when enabled.
- Turn flow — pre-hook fetches recall, post-hook submits observation —
  with the SDK mocked out end to end.
