"""
Factory functions for resolving skill_creator, connector_tool, and system_prompt
based on CallAgentInput configuration.

Modes (controlled via CallAgentInput fields):
  - None       → skip (pass None to agent_factory.create_agent)
  - "default"  → use production defaults (DbSkillCreator / ConnectorTool)
  - "custom_skill" / "custom_connector" → custom loading (currently same as default, placeholder for future)
"""

from __future__ import annotations

import platform as _platform
from datetime import datetime as _dt
from typing import TYPE_CHECKING, Literal, Optional

from ii_agent.core.logger import logger
from ii_agent.agents.prompts.agent_prompts import get_custom_agent_base_prompt

if TYPE_CHECKING:
    from ii_agent.ii_claw.call_agent import CallAgentInput
    from ii_agent.agents.connector.base import BaseConnectorTool
    from ii_agent.agents.skills.base import SkillCreator

# ---------------------------------------------------------------------------
# Type aliases for mode literals
# ---------------------------------------------------------------------------
SkillMode = Optional[Literal["default", "custom_skill", "default_and_custom_skill"]]
ConnectorMode = Optional[Literal["default", "custom_connector", "default_and_custom_connector"]]


# ---------------------------------------------------------------------------
# skill_creator
# ---------------------------------------------------------------------------

def resolve_skill_creator(
    inp: "CallAgentInput",
    mode: SkillMode = "default",
) -> Optional["SkillCreator"]:
    """Return a SkillCreator instance based on *mode*.

    Args:
        inp: The call-agent input (provides user_id, etc.).
        mode:
            - None                      → no skill creator (return None)
            - "default"                 → DbSkillCreator with production storage
            - "custom_skill"            → placeholder, currently same as "default"
            - "default_and_custom_skill" → both default + custom combined

    Returns:
        A SkillCreator or None.
    """
    if mode is None:
        return None

    from ii_agent.core.container import get_app_container
    from ii_agent.agents.skills.db_creator import DbSkillCreator

    container = get_app_container()
    storage = container.storage_service

    if mode == "default":
        return DbSkillCreator(user_id=inp.user_id, storage=storage)

    if mode == "custom_skill":
        # TODO: implement custom skill loading logic
        logger.info(f"custom_skill mode requested for user={inp.user_id}, falling back to default")
        return DbSkillCreator(user_id=inp.user_id, storage=storage)

    if mode == "default_and_custom_skill":
        # TODO: merge default DbSkillCreator + custom skill loading
        # Currently falls back to default until custom logic is implemented
        logger.info(f"default_and_custom_skill mode requested for user={inp.user_id}, falling back to default")
        return DbSkillCreator(user_id=inp.user_id, storage=storage)

    logger.warning(f"Unknown skill_mode={mode!r}, returning None")
    return None


# ---------------------------------------------------------------------------
# connector_tool
# ---------------------------------------------------------------------------

def resolve_connector_tool(
    inp: "CallAgentInput",
    mode: ConnectorMode = "default",
) -> Optional["BaseConnectorTool"]:
    """Return a BaseConnectorTool instance based on *mode*.

    Args:
        inp: The call-agent input (provides user_id, github_repository, etc.).
        mode:
            - None                          → no connector (return None)
            - "default"                     → ConnectorTool with production defaults
            - "custom_connector"            → placeholder, currently same as "default"
            - "default_and_custom_connector" → both default + custom combined

    Returns:
        A BaseConnectorTool or None.
    """
    if mode is None:
        return None

    from ii_agent.agents.connector.connector_tool import ConnectorTool

    if mode == "default":
        return ConnectorTool(
            user_id=inp.user_id,
            default_repository=inp.github_repository,
        )

    if mode == "custom_connector":
        # TODO: implement custom connector loading logic
        logger.info(f"custom_connector mode requested for user={inp.user_id}, falling back to default")
        return ConnectorTool(
            user_id=inp.user_id,
            default_repository=inp.github_repository,
        )

    if mode == "default_and_custom_connector":
        # TODO: merge default ConnectorTool + custom connector loading
        # Currently falls back to default until custom logic is implemented
        logger.info(f"default_and_custom_connector mode requested for user={inp.user_id}, falling back to default")
        return ConnectorTool(
            user_id=inp.user_id,
            default_repository=inp.github_repository,
        )

    logger.warning(f"Unknown connector_mode={mode!r}, returning None")
    return None


# ---------------------------------------------------------------------------
# system_prompt
# ---------------------------------------------------------------------------

def resolve_system_prompt(
    inp: "CallAgentInput",
) -> Optional[str]:
    """Build a custom system prompt if agent_type is CUSTOM, else return None.

    When agent_type is CUSTOM, returns the simplified base prompt with the
    user's custom_system_prompt injected as specialized instructions.
    For all other agent types returns None so agent_factory falls back to
    its default prompt generation via get_system_prompt_for_agent_type().
    """
    from ii_agent.agents.types import AgentType

    if inp.agent_type != AgentType.CUSTOM:
        return None

    base = get_custom_agent_base_prompt()
    specialized = ""
    if inp.custom_system_prompt:
        specialized = (
            "\n# CUSTOM INSTRUCTIONS\n"
            "<custom_instructions>\n"
            f"{inp.custom_system_prompt}\n"
            "</custom_instructions>\n"
        )

    return base.format(
        platform=_platform.system(),
        today=_dt.now().strftime("%Y-%m-%d"),
        specialized_instructions=specialized,
    )
