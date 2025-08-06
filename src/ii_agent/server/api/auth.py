"""Authentication API endpoints."""

from typing import Any
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Request
from fastapi_sso.sso.google import GoogleSSO
from sqlalchemy import select

from ii_agent.db.models import User
from ii_agent.server.api.deps import SessionDep
from ii_agent.server.auth.middleware import CurrentUser
from ii_agent.server.models.auth import (
    TokenResponse,
)
from ii_agent.server.auth.jwt_handler import jwt_handler
from ii_agent.core.config.ii_agent_config import config
from ii_agent.server.models.users import UserPublic


def get_google_sso() -> GoogleSSO:
    return GoogleSSO(
        config.google_client_id or "",
        config.google_client_secret or "",
        redirect_uri=config.google_redirect_uri,
    )


router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.get("/oauth/google/login")
async def google_login(google_sso: GoogleSSO = Depends(get_google_sso)):
    """Redirect to Google SSO login."""
    return await google_sso.get_login_redirect(
        params={"prompt": "consent", "access_type": "offline"}
    )


@router.get("/oauth/google/callback")
async def google_callback(
    request: Request,
    db: SessionDep,
    google_sso: GoogleSSO = Depends(get_google_sso),
):
    """Handle Google SSO callback and login."""

    user_info = await google_sso.verify_and_process(request)
    if not user_info:
        raise ValueError("Failed to get user info from Google SSO")

    result = await db.execute(select(User).where(User.email == user_info.email))
    user_stored = result.scalar_one_or_none()
    if not user_stored:
        # Register new user if not exists
        new_user = User(
            id=str(uuid.uuid4()),
            email=user_info.email,
            first_name=user_info.first_name or "",
            last_name=user_info.last_name or "",
            role="user",
            subscription_tier="free",
            is_active=True,
            email_verified=True,
            created_at=datetime.now(timezone.utc),
        )
        db.add(new_user)
        await db.commit()
        await db.refresh(new_user)
        user_stored = new_user

    access_token = jwt_handler.create_access_token(
        user_id=str(user_stored.id),
        email=str(user_stored.email),
        role=str(user_stored.role),
    )

    refresh_token = jwt_handler.create_refresh_token(user_id=str(user_stored.id))

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=jwt_handler.access_token_expire_minutes * 60,
    )


@router.get("/me", response_model=UserPublic)
async def reader_user_me(current_user: CurrentUser) -> Any:
    return current_user
