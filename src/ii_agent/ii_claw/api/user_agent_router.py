"""User agents management API endpoints."""

from fastapi import APIRouter, HTTPException, Query

from ii_agent.auth.dependencies import CurrentUser
from ii_agent.core.dependencies import DBSession
from ii_agent.core.logger import logger

from ii_agent.ii_claw.custom_agent.models import (
    UserAgentCreate,
    UserAgentUpdate,
    UserAgentInfo,
    UserAgentList,
    UserAgentDeleteResponse,
)
from ii_agent.ii_claw.custom_agent.service import (
    create_user_agent,
    list_user_agents,
    get_user_agent,
    update_user_agent,
    delete_user_agent,
)

router = APIRouter(prefix="/ii-claw/agents", tags=["II-Claw User Agents Management"])


@router.post("", response_model=UserAgentInfo, status_code=201)
async def create_agent(
    request: UserAgentCreate,
    current_user: CurrentUser,
    db: DBSession,
):
    """Create a new custom agent.

    The agent_name must be unique per user.
    """
    try:
        return await create_user_agent(
            db_session=db,
            user_id=str(current_user.id),
            agent_in=request,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception(f"Unexpected error creating agent: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create agent: {str(e)}")


@router.get("", response_model=UserAgentList)
async def list_agents(
    current_user: CurrentUser,
    db: DBSession,
    active_only: bool = Query(
        default=False,
        description="Whether to return only active agents",
    ),
):
    """List all custom agents for the current user."""
    return await list_user_agents(
        db_session=db,
        user_id=str(current_user.id),
        active_only=active_only,
    )


@router.get("/{agent_id}", response_model=UserAgentInfo)
async def get_agent(
    agent_id: str,
    current_user: CurrentUser,
    db: DBSession,
):
    """Get details of a specific custom agent by ID."""
    agent_info = await get_user_agent(
        db_session=db,
        agent_id=agent_id,
        user_id=str(current_user.id),
    )
    if not agent_info:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent_info


@router.put("/{agent_id}", response_model=UserAgentInfo)
async def update_agent(
    agent_id: str,
    request: UserAgentUpdate,
    current_user: CurrentUser,
    db: DBSession,
):
    """Update a custom agent. Only provided fields are changed."""
    try:
        agent_info = await update_user_agent(
            db_session=db,
            agent_id=agent_id,
            user_id=str(current_user.id),
            agent_update=request,
        )
        if not agent_info:
            raise HTTPException(status_code=404, detail="Agent not found")
        return agent_info
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{agent_id}", response_model=UserAgentDeleteResponse)
async def delete_agent(
    agent_id: str,
    current_user: CurrentUser,
    db: DBSession,
):
    """Delete a custom agent."""
    success = await delete_user_agent(
        db_session=db,
        agent_id=agent_id,
        user_id=str(current_user.id),
    )
    if not success:
        raise HTTPException(status_code=404, detail="Agent not found")
    return UserAgentDeleteResponse(
        success=True,
        message="Agent deleted successfully",
    )
