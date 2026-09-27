"""Utilities for converting agent run events into serialisable info dicts."""

from __future__ import annotations

from typing import Any, Dict


def _get_sub_agent_info(event: Any) -> Dict[str, Any]:
    """Extract sub-agent identification fields from a run event or output.

    Handles both :class:`~ii_agent.agents.runs.agent.RunStartedEvent` and
    :class:`~ii_agent.agents.runs.agent.RunOutput` instances (or any object
    with compatible attributes).  Unknown attributes are silently ignored so
    new event types do not break existing callers.

    Returns a (possibly empty) dict containing only the fields that are set /
    truthy on the event.
    """
    info: Dict[str, Any] = {}

    delegated_from = getattr(event, "delegated_from", None)
    if delegated_from:
        info["delegated_from"] = delegated_from

    if getattr(event, "is_sub_agent_event", False):
        info["is_sub_agent_event"] = True

    agent_name = getattr(event, "agent_name", None)
    if agent_name:
        info["agent_name"] = agent_name

    parent_run_id = getattr(event, "parent_run_id", None)
    if parent_run_id:
        info["parent_run_id"] = str(parent_run_id)

    # RunOutput instances are considered sub-agent responses when they have a
    # delegated_from field set (indicating they were produced by a sub-agent).
    if delegated_from and hasattr(event, "run_id"):
        info["is_sub_agent_response"] = True

    return info
