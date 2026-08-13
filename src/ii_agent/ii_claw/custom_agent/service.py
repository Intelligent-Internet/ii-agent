"""User agents service layer.

Business logic for managing user-defined custom agents.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.users.models import UserAgent
from ii_agent.core.logger import logger

from ii_agent.ii_claw.custom_agent.models import UserAgentCreate, UserAgentUpdate, UserAgentInfo, UserAgentList


def _to_agent_info(agent: UserAgent) -> UserAgentInfo:
    """Convert database UserAgent model to response model."""
    return UserAgentInfo(
        id=str(agent.id),
        agent_name=agent.agent_name,
        tag=agent.tag,
        model_id=agent.model_id,
        system_prompt=agent.system_prompt,
        tool_args=agent.tool_args,
        skill_mode=agent.skill_mode,
        connector_mode=agent.connector_mode,
        skill_config=agent.skill_config,
        connector_config=agent.connector_config,
        metadata=agent.agent_metadata,
        is_active=agent.is_active,
        created_at=agent.created_at,
        updated_at=agent.updated_at,
    )


async def create_user_agent(
    *,
    db_session: AsyncSession,
    user_id: str,
    agent_in: UserAgentCreate,
) -> UserAgentInfo:
    """Create a new custom agent for a user.

    Raises:
        ValueError: If an agent with the same name already exists.
    """
    # Check for duplicate name
    existing = await db_session.execute(
        select(UserAgent).where(
            and_(
                UserAgent.user_id == user_id,
                UserAgent.agent_name == agent_in.agent_name,
            )
        )
    )
    if existing.scalar_one_or_none():
        raise ValueError(
            f"Agent '{agent_in.agent_name}' already exists. "
            f"Choose a different name or delete the existing one first."
        )

    agent = UserAgent(
        user_id=uuid.UUID(user_id) if isinstance(user_id, str) else user_id,
        agent_name=agent_in.agent_name,
        tag=agent_in.tag,
        model_id=agent_in.model_id,
        system_prompt=agent_in.system_prompt,
        tool_args=agent_in.tool_args or {},
        skill_mode=agent_in.skill_mode,
        connector_mode=agent_in.connector_mode,
        skill_config=agent_in.skill_config,
        connector_config=agent_in.connector_config,
        agent_metadata=agent_in.metadata,
        is_active=True,
    )

    db_session.add(agent)
    await db_session.commit()
    await db_session.refresh(agent)

    logger.info(f"Created custom agent '{agent.agent_name}' (id={agent.id}) for user {user_id}")

    return _to_agent_info(agent)


async def list_user_agents(
    *,
    db_session: AsyncSession,
    user_id: str,
    active_only: bool = False,
) -> UserAgentList:
    """List all custom agents for a user."""
    query = select(UserAgent).where(UserAgent.user_id == user_id)
    if active_only:
        query = query.where(UserAgent.is_active == True)
    query = query.order_by(UserAgent.created_at.desc())

    result = await db_session.execute(query)
    agents = list(result.scalars().all())

    return UserAgentList(
        agents=[_to_agent_info(a) for a in agents],
        total=len(agents),
    )


async def get_user_agent(
    *,
    db_session: AsyncSession,
    agent_id: str,
    user_id: str,
) -> Optional[UserAgentInfo]:
    """Get a single custom agent by ID (must belong to user)."""
    result = await db_session.execute(
        select(UserAgent).where(
            and_(
                UserAgent.id == agent_id,
                UserAgent.user_id == user_id,
            )
        )
    )
    agent = result.scalar_one_or_none()
    return _to_agent_info(agent) if agent else None


async def update_user_agent(
    *,
    db_session: AsyncSession,
    agent_id: str,
    user_id: str,
    agent_update: UserAgentUpdate,
) -> Optional[UserAgentInfo]:
    """Update a custom agent. Only provided (non-None) fields are changed.

    Raises:
        ValueError: If renaming to a name that already exists.
    """
    result = await db_session.execute(
        select(UserAgent).where(
            and_(
                UserAgent.id == agent_id,
                UserAgent.user_id == user_id,
            )
        )
    )
    agent = result.scalar_one_or_none()
    if not agent:
        return None

    # If renaming, check for duplicate
    if agent_update.agent_name is not None and agent_update.agent_name != agent.agent_name:
        dup = await db_session.execute(
            select(UserAgent).where(
                and_(
                    UserAgent.user_id == user_id,
                    UserAgent.agent_name == agent_update.agent_name,
                    UserAgent.id != agent_id,
                )
            )
        )
        if dup.scalar_one_or_none():
            raise ValueError(f"Agent '{agent_update.agent_name}' already exists.")

    # Apply only provided fields
    update_data = agent_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if field == "metadata":
            setattr(agent, "agent_metadata", value)
        else:
            setattr(agent, field, value)

    agent.updated_at = datetime.now(timezone.utc)

    await db_session.commit()
    await db_session.refresh(agent)

    logger.info(f"Updated custom agent '{agent.agent_name}' (id={agent.id})")

    return _to_agent_info(agent)


async def delete_user_agent(
    *,
    db_session: AsyncSession,
    agent_id: str,
    user_id: str,
) -> bool:
    """Delete a custom agent. Returns True if deleted, False if not found."""
    result = await db_session.execute(
        select(UserAgent).where(
            and_(
                UserAgent.id == agent_id,
                UserAgent.user_id == user_id,
            )
        )
    )
    agent = result.scalar_one_or_none()
    if not agent:
        return False

    agent_name = agent.agent_name
    await db_session.delete(agent)
    await db_session.commit()

    logger.info(f"Deleted custom agent '{agent_name}' (id={agent_id}) for user {user_id}")

    return True
