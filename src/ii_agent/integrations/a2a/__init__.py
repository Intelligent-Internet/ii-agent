"""A2A integration helpers used by the agent inner-loop strategy.

Imports are **lazy** so the package can be loaded inside the lightweight
sandbox environment where backend-only dependencies
(``ii_agent.agents``, ``ii_agent.realtime``, …) are not available.

The ``a2a-sdk`` and ``github-copilot-sdk`` packages are **optional**.
Install them via::

    pip install ii-agent[a2a]    # or:  uv sync --extra a2a

The main backend imports only lightweight wrappers (``as_client``,
``circuit_breaker``, ``backend_compat``) that have no ``a2a-sdk``
dependency.  The adapter server (which *does* need the SDK) runs
inside the sandbox container where the SDK is always installed.
"""

from __future__ import annotations

import importlib
from typing import Any


def require_a2a_extras() -> None:
    """Raise a clear error if the ``[a2a]`` optional extras are not installed.

    Call this at startup when ``AGENT_INNER_LOOP_MODE=a2a`` so users get
    an actionable message instead of a cryptic ImportError later.
    """
    missing: list[str] = []
    for pkg, pip_name in [("a2a", "a2a-sdk"), ("copilot", "github-copilot-sdk")]:
        if importlib.util.find_spec(pkg) is None:  # type: ignore[union-attr]
            missing.append(pip_name)
    if missing:
        raise RuntimeError(
            f"A2A inner-loop mode requires optional packages: {', '.join(missing)}. "
            "Install them with:  pip install ii-agent[a2a]  (or: uv sync --extra a2a)"
        )


__all__ = [
    "A2AStreamEvent",
    "IIAgentA2AClient",
    "create_app",
    "ClaudeCodeBackend",
    "ClaudeCodeConfig",
    "CodexBackend",
    "CodexConfig",
    "CopilotBackend",
    "CopilotConfig",
    "AgentCard",
    "AgentRegistry",
    "AgentSkill",
    "AgentRouter",
    "TaskStore",
]

_LAZY_IMPORTS: dict[str, tuple[str, str]] = {
    "A2AStreamEvent": (".as_client", "A2AStreamEvent"),
    "IIAgentA2AClient": (".as_client", "IIAgentA2AClient"),
    "create_app": (".adapter_server", "create_app"),
    "ClaudeCodeBackend": (".claude_code_backend", "ClaudeCodeBackend"),
    "ClaudeCodeConfig": (".claude_code_backend", "ClaudeCodeConfig"),
    "CodexBackend": (".codex_backend", "CodexBackend"),
    "CodexConfig": (".codex_backend", "CodexConfig"),
    "CopilotBackend": (".copilot_backend", "CopilotBackend"),
    "CopilotConfig": (".copilot_backend", "CopilotConfig"),
    "AgentCard": (".registry", "AgentCard"),
    "AgentRegistry": (".registry", "AgentRegistry"),
    "AgentSkill": (".registry", "AgentSkill"),
    "AgentRouter": (".router", "AgentRouter"),
    "TaskStore": (".task_store", "TaskStore"),
}


def __getattr__(name: str) -> Any:
    if name in _LAZY_IMPORTS:
        module_path, attr = _LAZY_IMPORTS[name]
        mod = importlib.import_module(module_path, __package__)
        return getattr(mod, attr)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
