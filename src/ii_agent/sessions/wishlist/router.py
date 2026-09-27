"""Wishlist management API endpoints."""

import logging
import uuid
from fastapi import APIRouter

from ii_agent.auth.dependencies import CurrentUser, DBSession, NotPurgingDep
from ii_agent.sessions.wishlist.dependencies import WishlistServiceDep
from ii_agent.sessions.wishlist.schemas import (
    SessionWishlistResponse,
    WishlistActionResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/wishlist", tags=["Wishlist"])


@router.get("", response_model=SessionWishlistResponse)
async def get_wishlist_sessions(
    current_user: CurrentUser,
    wishlist_service: WishlistServiceDep,
    db: DBSession,
) -> SessionWishlistResponse:
    """Get all wishlist sessions for the current user."""
    items = await wishlist_service.get_user_wishlist(db, current_user.id)
    return SessionWishlistResponse(sessions=items, total=len(items))


@router.post("/{session_id}", response_model=WishlistActionResponse)
async def add_to_wishlist(
    session_id: uuid.UUID,
    current_user: NotPurgingDep,
    wishlist_service: WishlistServiceDep,
    db: DBSession,
) -> WishlistActionResponse:
    """Add a session to the current user's wishlist.

    Gated by ``NotPurgingDep`` (I3/I8 §16): blocked while ``users.is_purging``.
    """
    success = await wishlist_service.add_to_wishlist(db, current_user.id, session_id)

    if not success:
        return WishlistActionResponse(
            success=False,
            message="Session already in wishlist",
            session_id=session_id,
        )

    return WishlistActionResponse(
        success=True, message="Session added to wishlist", session_id=session_id
    )


@router.delete("/{session_id}", response_model=WishlistActionResponse)
async def remove_from_wishlist(
    session_id: uuid.UUID,
    current_user: NotPurgingDep,
    wishlist_service: WishlistServiceDep,
    db: DBSession,
) -> WishlistActionResponse:
    """Remove a session from the current user's wishlist.

    Gated by ``NotPurgingDep`` (I3/I8 §16): blocked while ``users.is_purging``.
    """
    success = await wishlist_service.remove_from_wishlist(db, current_user.id, session_id)

    if not success:
        return WishlistActionResponse(
            success=False,
            message="Session not found in wishlist",
            session_id=session_id,
        )

    return WishlistActionResponse(
        success=True, message="Session removed from wishlist", session_id=session_id
    )
