"""Tool bridge for forwarding ii-agent native tools to the Copilot CLI.

This module provides schema serialization so ii-agent's ``Function`` tools
can be transported through the A2A protocol and registered as custom tools
in the Copilot CLI session via the SDK.

Architecture
------------

Backend side (``inner_loop.py``):
    Function tools → :func:`serialize_tool_schemas` → JSON schemas → A2A metadata

Sandbox side (``copilot_backend.py``):
    JSON schemas → Copilot SDK ``Tool`` objects → ``create_session(tools=[…])``

When the Copilot CLI's LLM invokes a bridged tool the SDK handler injects
a ``tool.execution_request`` event into the SSE stream.  The backend-side
inner loop intercepts this event, executes the tool locally (where it has
full infrastructure access), and POSTs the result back through the adapter.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tools that have equivalents in the Copilot CLI built-in tool set.
# These are NOT bridged — the CLI handles them natively.
# ---------------------------------------------------------------------------
_CLI_NATIVE_TOOL_NAMES: frozenset[str] = frozenset(
    {
        # Shell / bash — CLI has built-in shell tools
        "Bash",
        "BashView",
        "BashList",
        "WriteToProcess",
        # File I/O — CLI has built-in file tools
        "Read",
        "Write",
        "Edit",
        "ApplyPatch",
        "StrReplaceEditor",
    }
)


def serialize_tool_schemas(
    tools: list[Any],
    *,
    exclude_cli_native: bool = True,
) -> list[dict[str, Any]]:
    """Convert ii-agent Function tools to JSON-serializable schemas.

    Parameters
    ----------
    tools:
        List of ``Function`` or ``dict`` tool definitions from the agent.
    exclude_cli_native:
        If *True* (default), exclude tools whose names match Copilot CLI
        built-in tools.

    Returns
    -------
    list[dict]
        Tool schemas: ``[{"name": …, "description": …, "parameters": …}]``
    """
    schemas: list[dict[str, Any]] = []

    for tool in tools:
        if isinstance(tool, dict):
            name = str(tool.get("name") or "")
            if not name:
                continue
            if exclude_cli_native and name in _CLI_NATIVE_TOOL_NAMES:
                continue
            schemas.append(
                {
                    "name": name,
                    "description": str(tool.get("description") or ""),
                    "parameters": tool.get("parameters") or {"type": "object", "properties": {}},
                }
            )
        else:
            name = getattr(tool, "name", "")
            if not name:
                continue
            if exclude_cli_native and name in _CLI_NATIVE_TOOL_NAMES:
                continue
            schemas.append(
                {
                    "name": name,
                    "description": getattr(tool, "description", None) or "",
                    "parameters": getattr(tool, "parameters", None)
                    or {"type": "object", "properties": {}},
                }
            )

    logger.info(
        "Serialized %d tool schemas for A2A bridge (excluded %d CLI-native)",
        len(schemas),
        len(tools) - len(schemas),
    )
    return schemas
