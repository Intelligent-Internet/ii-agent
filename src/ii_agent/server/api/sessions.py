"""
Session management API endpoints.
"""

import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from ii_agent.db.manager import Sessions
from ii_agent.server.models.sessions import SessionInfo, SessionList, SessionFile
from ii_agent.server.models.messages import EventInfo, EventResponse
from ii_agent.server.api.deps import CurrentUser
from ii_agent.server.shared import file_service
from ii_agent.server.shared import session_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sessions", tags=["Sessions"])

# Internal router for sandbox-server communication (no auth required)
internal_router = APIRouter(prefix="/internal/sandboxes", tags=["Internal"])


@internal_router.get("/{sandbox_id}/has-active-session")
async def check_sandbox_has_active_session(sandbox_id: str) -> dict:
    """Check if a sandbox is attached to an active (non-deleted) session.

    This is an internal endpoint for sandbox-server to verify before cleanup.
    No authentication required as this is internal service-to-service communication.

    Args:
        sandbox_id: The sandbox ID to check

    Returns:
        {"has_active_session": bool} indicating if sandbox is still in use
    """
    try:
        has_active = await Sessions.has_active_session_for_sandbox(sandbox_id)
        return {"has_active_session": has_active, "sandbox_id": sandbox_id}
    except Exception as e:
        logger.error(f"Error checking sandbox session status: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error checking sandbox session status: {str(e)}"
        )


@router.get("/{session_id}", response_model=SessionInfo)
async def get_session(
    session_id: str,
    current_user: CurrentUser,
) -> SessionInfo:
    """Get detailed information for a specific session.

    Args:
        session_id: The session identifier to look up
        current_user: The authenticated user

    Returns:
        Session details if found and user has access

    Raises:
        HTTPException: If session not found or user lacks access
    """
    try:
        session_data = await Sessions.get_session_details(
            session_id, str(current_user.id)
        )

        if not session_data:
            raise HTTPException(
                status_code=404,
                detail=f"Session {session_id} not found or access denied",
            )

        return SessionInfo(**session_data)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving session {session_id}: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error retrieving session: {str(e)}"
        )


@router.get("", response_model=SessionList)
async def list_sessions(
    current_user: CurrentUser,
    query: Optional[str] = Query(
        None, description="Search term to filter sessions by name"
    ),
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page"),
    public_only: bool = Query(
        False, description="If true, return only public sessions"
    ),
) -> SessionList:
    """List sessions for the current user with optional search and pagination.

    Args:
        query: Optional search term to filter sessions by name
        page: Page number for pagination (1-indexed)
        per_page: Number of items per page (max 100)
        current_user: The authenticated user
        public_only: When true, only include sessions where is_public is true

    Returns:
        A paginated list of sessions with metadata
    """
    try:
        sessions_data, total = await Sessions.get_user_sessions(
            user_id=str(current_user.id),
            search_term=query,
            page=page,
            per_page=per_page,
            public_only=public_only,
        )

        sessions = [SessionInfo(**session) for session in sessions_data]

        return SessionList(sessions=sessions, total=total, page=page, per_page=per_page)

    except Exception as e:
        logger.error(f"Error listing sessions: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error listing sessions: {str(e)}")


@router.get("/{session_id}/events", response_model=EventResponse)
async def get_session_events(
    session_id: str,
    current_user: CurrentUser,
) -> EventResponse:
    """Get all events for a specific session.

    Args:
        session_id: The session identifier to look up events for
        current_user: The authenticated user

    Returns:
        A list of events with their details, sorted by timestamp ascending

    Raises:
        HTTPException: If session not found, user lacks access, or error occurs
    """
    # First verify the user has access to this session
    session_data = await Sessions.get_session_details(session_id, str(current_user.id))

    if not session_data:
        raise HTTPException(
            status_code=404,
            detail=f"Session {session_id} not found or access denied",
        )

    # Get events for the session
    events_raw = await session_service.get_session_events_with_details(session_id)
    events = [EventInfo(**event) for event in events_raw]

    return EventResponse(events=events)


@router.get("/{session_id}/files", response_model=list[SessionFile])
async def get_session_files(
    session_id: str,
    current_user: CurrentUser,
):
    try:
        # First verify the user has access to this session
        session_data = await Sessions.get_session_details(
            session_id, str(current_user.id)
        )

        if not session_data:
            raise HTTPException(
                status_code=404,
                detail=f"Session {session_id} not found or access denied",
            )

        files = await file_service.get_files_by_session_id(session_id)
        return [
            SessionFile(
                id=file.id,
                name=file.name,
                size=file.size,
                content_type=file.content_type,
                url=file.url,
            )
            for file in files
        ]

    except HTTPException:
        raise


@router.post("/{session_id}/publish")
async def publish_session(
    session_id: str,
    current_user: CurrentUser,
) -> dict:
    """Set a session as public.

    Args:
        session_id: The session identifier to publish
        current_user: The authenticated user

    Returns:
        Success message if published

    Raises:
        HTTPException: If session not found or user lacks access
    """
    try:
        success = await Sessions.set_session_public(
            session_id, str(current_user.id), True
        )

        if not success:
            raise HTTPException(
                status_code=404,
                detail=f"Session {session_id} not found or access denied",
            )

        return {"message": f"Session {session_id} published successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error publishing session {session_id}: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error publishing session: {str(e)}"
        )


@router.post("/{session_id}/unpublish")
async def unpublish_session(
    session_id: str,
    current_user: CurrentUser,
) -> dict:
    """Set a session as private.

    Args:
        session_id: The session identifier to unpublish
        current_user: The authenticated user

    Returns:
        Success message if unpublished

    Raises:
        HTTPException: If session not found or user lacks access
    """
    try:
        success = await Sessions.set_session_public(
            session_id, str(current_user.id), False
        )

        if not success:
            raise HTTPException(
                status_code=404,
                detail=f"Session {session_id} not found or access denied",
            )

        return {"message": f"Session {session_id} unpublished successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error unpublishing session {session_id}: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error unpublishing session: {str(e)}"
        )


@router.get("/{session_id}/public", response_model=SessionInfo)
async def get_public_session(
    session_id: str,
) -> SessionInfo:
    """Get detailed information for a public session without authentication.

    Args:
        session_id: The session identifier to look up

    Returns:
        Session details if found and session is public

    Raises:
        HTTPException: If session not found or not public
    """
    try:
        session_data = await Sessions.get_public_session_details(session_id)

        if not session_data:
            raise HTTPException(
                status_code=404,
                detail=f"Session {session_id} not found or not public",
            )

        return SessionInfo(**session_data)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving public session {session_id}: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error retrieving public session: {str(e)}"
        )


@router.get("/{session_id}/public/events", response_model=EventResponse)
async def get_public_session_events(
    session_id: str,
) -> EventResponse:
    """Get all events for a public session without authentication.

    Args:
        session_id: The session identifier to look up events for

    Returns:
        A list of events with their details, sorted by timestamp ascending

    Raises:
        HTTPException: If session not found, not public, or error occurs
    """
    # First verify the session is public
    session_data = await Sessions.get_public_session_details(session_id)

    if not session_data:
        raise HTTPException(
            status_code=404,
            detail=f"Session {session_id} not found or not public",
        )

    # Get events for the session
    events_raw = await session_service.get_session_events_with_details(session_id)
    events = [EventInfo(**event) for event in events_raw]

    return EventResponse(events=events)


@router.delete("/{session_id}")
async def delete_session(
    session_id: str,
    current_user: CurrentUser,
) -> dict:
    """Delete a session by setting its deleted_at timestamp.

    Args:
        session_id: The session identifier to delete
        current_user: The authenticated user

    Returns:
        Success message if deleted

    Raises:
        HTTPException: If session not found or user lacks access
    """
    try:
        # Verify the user has access to this session
        session_data = await Sessions.get_session_details(
            session_id, str(current_user.id)
        )

        if not session_data:
            raise HTTPException(
                status_code=404,
                detail=f"Session {session_id} not found or access denied",
            )

        # Soft delete the session
        await Sessions.soft_delete_session(session_id, str(current_user.id))

        return {"message": f"Session {session_id} deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting session {session_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error deleting session: {str(e)}")
