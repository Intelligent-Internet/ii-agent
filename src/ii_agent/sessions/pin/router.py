"""Pin management API endpoints."""

import logging
import uuid
from fastapi import APIRouter

from ii_agent.auth.dependencies import CurrentUser, DBSession, NotPurgingDep
from ii_agent.sessions.pin.dependencies import PinServiceDep
from ii_agent.sessions.pin.schemas import (
    SessionPinResponse,
    PinActionResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/pins", tags=["Pin"])


@router.get("", response_model=SessionPinResponse)
async def get_pinned_sessions(
    current_user: CurrentUser,
    pin_service: PinServiceDep,
    db: DBSession,
) -> SessionPinResponse:
    """Get all pinned sessions for the current user."""
    pins = await pin_service.get_user_pins(db, current_user.id)
    return SessionPinResponse(sessions=pins, total=len(pins))


@router.post("/{session_id}", response_model=PinActionResponse)
async def pin_session(
    session_id: uuid.UUID,
    current_user: NotPurgingDep,
    pin_service: PinServiceDep,
    db: DBSession,
) -> PinActionResponse:
    """Pin a session for the current user.

    Gated by ``NotPurgingDep`` (I3/I8 §16): blocked while ``users.is_purging``.
    """
    success = await pin_service.pin_session(db, current_user.id, session_id)

    if not success:
        return PinActionResponse(
            success=False,
            message="Session already pinned",
            session_id=session_id,
        )

    return PinActionResponse(success=True, message="Session pinned", session_id=session_id)


@router.delete("/{session_id}", response_model=PinActionResponse)
async def unpin_session(
    session_id: uuid.UUID,
    current_user: NotPurgingDep,
    pin_service: PinServiceDep,
    db: DBSession,
) -> PinActionResponse:
    """Unpin a session for the current user.

    Gated by ``NotPurgingDep`` (I3/I8 §16): blocked while ``users.is_purging``.
    """
    success = await pin_service.unpin_session(db, current_user.id, session_id)

    if not success:
        return PinActionResponse(
            success=False,
            message="Session not pinned",
            session_id=session_id,
        )

    return PinActionResponse(success=True, message="Session unpinned", session_id=session_id)
