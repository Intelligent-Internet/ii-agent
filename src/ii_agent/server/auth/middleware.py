"""Authentication middleware for FastAPI."""

from typing import Annotated
from fastapi import HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import select

from ii_agent.db.models import User
from ii_agent.server.api.deps import SessionDep
from ii_agent.server.auth.jwt_handler import jwt_handler
from ii_agent.server.models.auth import TokenPayload


security = HTTPBearer()


async def get_current_user(
    db: SessionDep,
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> User:
    """Get the current authenticated user."""
    token = credentials.credentials

    # Verify the access token
    payload = jwt_handler.verify_access_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token_data = TokenPayload(**payload)
    # Get user from database
    # user = db.query(User).filter(User.id == token_data.user_id).first()
    result = await db.execute(select(User).where(User.id == token_data.user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is disabled",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
