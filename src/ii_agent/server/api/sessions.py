"""
Session management API endpoints.
"""

import logging
from fastapi import APIRouter, HTTPException

from ii_agent.db.manager import Events, Sessions
from ..models.messages import SessionResponse, EventResponse, SessionInfo, EventInfo

logger = logging.getLogger(__name__)

sessions_router = APIRouter(prefix="/api", tags=["sessions"])


@sessions_router.get("/sessions/{device_id}", response_model=SessionResponse)
def get_sessions_by_device_id(device_id: str):
    """Get all sessions for a specific device ID, sorted by creation time descending.
    
    Args:
        device_id: The device identifier to look up sessions for

    Returns:
        A list of sessions with their details, sorted by creation time descending
    """
    try:
        sessions_raw = Sessions.get_sessions_by_device_id(device_id)
        sessions = [SessionInfo(**session) for session in sessions_raw]
        return SessionResponse(sessions=sessions)

    except Exception as e:
        logger.error(f"Error retrieving sessions: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error retrieving sessions: {str(e)}"
        )


@sessions_router.get("/sessions/{session_id}/events", response_model=EventResponse)
def get_session_events(session_id: str):
    """Get all events for a specific session ID, sorted by timestamp ascending.

    Args:
        session_id: The session identifier to look up events for

    Returns:
        A list of events with their details, sorted by timestamp ascending
    """
    try:
        events_raw = Events.get_session_events_with_details(session_id)
        events = [EventInfo(**event) for event in events_raw]
        return EventResponse(events=events)
        

    except Exception as e:
        logger.error(f"Error retrieving events: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error retrieving events: {str(e)}"
        )
