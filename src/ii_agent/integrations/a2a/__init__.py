"""A2A integration helpers used by the agent inner-loop strategy.

Imports are **lazy** so the package can be loaded inside the lightweight
sandbox environment where backend-only dependencies
(``ii_agent.agents``, ``ii_agent.realtime``, …) are not available.
"""

from __future__ import annotations

import importlib
from typing import Any

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
