"""Unit tests for ``_agent_kind_from_name``.

The helper derives the ``AgentType`` value encoded in an agent's ``name``
(e.g. ``"deep_research_agent"`` -> ``"deep_research"``) and is used by
``_ensure_sandbox_for_inner_loop`` to propagate ``agent_kind`` through
sandbox metadata.  Only values that round-trip through ``AgentType(...)``
are returned; subagent / tool-owned names (``task_agent``, connector tool
names, etc.) must map to ``None`` so they don't accidentally trigger the
long-horizon adapter timeout override.
"""

from __future__ import annotations

import pytest

from ii_agent.agents.agent import _agent_kind_from_name
from ii_agent.agents.types import AgentType


@pytest.mark.parametrize(
    "name,expected",
    [
        # Happy path: every AgentType value the factory can emit.
        ("general_agent", "general"),
        ("deep_research_agent", "deep_research"),
        ("fast_research_agent", "fast_research"),
        ("researcher_agent", "researcher"),
        ("slide_agent", "slide"),
        ("slide_nano_banana_agent", "slide_nano_banana"),
        ("media_agent", "media"),
        ("browser_agent", "browser"),
        ("website_build_agent", "website_build"),
        ("task_agent_agent", "task_agent"),
        ("design_document_agent", "design_document"),
        ("codex_agent", "codex"),
        ("claude_code_agent", "claude_code"),
        ("research_to_website_agent", "research_to_website"),
        ("mobile_app_agent", "mobile_app"),
    ],
)
def test_returns_enum_value_for_recognised_names(name: str, expected: str) -> None:
    assert _agent_kind_from_name(name) == expected
    # Sanity: the returned string must round-trip through AgentType.
    assert AgentType(expected).value == expected


@pytest.mark.parametrize(
    "name",
    [
        # Subagent / tool-owned names — suffix matches but candidate is not
        # in ``AgentType``.  MUST return None so the long-horizon override
        # is not applied to arbitrary tools that happen to end in _agent.
        "task_agent",
        "my_custom_tool_agent",
        "connector_github_agent",
        # Not suffixed with _agent at all.
        "plain_name",
        "",
        # Edge cases.
        "agent",  # would strip to "" — must not pass
        "_agent",  # same
    ],
)
def test_returns_none_for_unrecognised_or_short_names(name: str) -> None:
    assert _agent_kind_from_name(name) is None


def test_returns_none_for_none_input() -> None:
    assert _agent_kind_from_name(None) is None


def test_all_agent_type_values_round_trip() -> None:
    """Every ``AgentType`` enum member must be recoverable from its factory name.

    Guards against a future agent type being added without updating the
    factory naming contract (``f"{agent_type.value}_agent"``).
    """
    for member in AgentType:
        name = f"{member.value}_agent"
        assert _agent_kind_from_name(name) == member.value
