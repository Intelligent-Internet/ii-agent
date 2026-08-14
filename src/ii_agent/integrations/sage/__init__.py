"""SAGE persistent-memory integration for ii-agent.

SAGE (Sovereign Agent Governed Experience) is a BFT-consensus memory layer
for AI agents. This integration wires an :class:`IIAgent` instance into a
SAGE node via the async SDK so each turn recalls prior memories before the
model runs and stores an observation after the turn completes.

The integration is strictly opt-in: when ``SAGE_ENABLED`` is unset or
``false``, :func:`register_sage_hooks` is a no-op and the agent behaves as
if the integration did not exist. If the optional ``sage-agent-sdk``
dependency is not installed the integration also falls back to a no-op
with a debug log — the framework continues to work end-to-end.

Install extras::

    pip install "ii-agent[sage]"

Typical usage::

    from ii_agent.agents.agent import IIAgent
    from ii_agent.integrations.sage import register_sage_hooks

    agent = IIAgent(...)
    register_sage_hooks(agent)
"""

from __future__ import annotations

from ii_agent.integrations.sage.registrar import register_sage_hooks

__all__ = ["register_sage_hooks"]
