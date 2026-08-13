"""Load custom agent config from DB and return overrides for CallAgentInput."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from sqlalchemy import select

from ii_agent.core.logger import logger
from ii_agent.core.db import get_db_session_local
from ii_agent.users.models import UserAgent


@dataclass
class CustomAgentOverrides:
    """Fields extracted from UserAgent DB row to inject into CallAgentInput."""

    agent_type_value: str = "custom"  # always "custom"
    model_id: Optional[str] = None
    custom_system_prompt: Optional[str] = None
    tool_args: Optional[Dict[str, Any]] = None
    skill_mode: Optional[str] = "default"
    connector_mode: Optional[str] = "default"


async def process_custom_agent(
    agent_id: str,
    user_id: str,
) -> Optional[CustomAgentOverrides]:
    """Load a UserAgent row by *agent_id* + *user_id* and return overrides.

    Returns None if no matching active agent is found.
    """
    try:
        async with get_db_session_local() as db:
            result = await db.execute(
                select(UserAgent).where(
                    UserAgent.id == agent_id,
                    UserAgent.user_id == user_id,
                    UserAgent.is_active == True,
                )
            )
            agent_row = result.scalars().first()

            if agent_row is None:
                logger.warning(
                    "No active UserAgent found: agent_id=%s user_id=%s",
                    agent_id,
                    user_id,
                )
                return None

            return CustomAgentOverrides(
                model_id=agent_row.model_id,
                custom_system_prompt=agent_row.system_prompt,
                tool_args=agent_row.tool_args,
                skill_mode=agent_row.skill_mode,
                connector_mode=agent_row.connector_mode,
            )

    except Exception as e:
        logger.error("Failed to load custom agent: %s", e, exc_info=True)
        return None
