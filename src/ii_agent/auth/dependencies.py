"""FastAPI dependencies for auth domain.

This module provides authentication-related dependencies that are used
across all domains that need user authentication.
"""

from typing import Annotated, TypeAlias

from fastapi import Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from ii_agent.core.dependencies import DBSession
from ii_agent.core.dependencies import SettingsDep
from ii_agent.users.dependencies import UserRepositoryDep
from ii_agent.users.models import User
from ii_agent.auth.jwt_handler import jwt_handler
from ii_agent.auth.schemas import TokenPayload
from ii_agent.auth.exceptions import InvalidTokenException, UserNotFoundException
from ii_agent.users.exceptions import UserDisabledException

# Re-export security scheme for use in routers
security = HTTPBearer()


async def get_current_user(
    db: DBSession,
    user_repo: UserRepositoryDep,
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> User:
    """Get the current authenticated user from JWT token.

    This dependency validates the JWT token and retrieves the user
    from the database.

    Usage:
        @router.get("/me")
        async def get_me(current_user: CurrentUser):
            return current_user
    """
    token = credentials.credentials

    # Verify the access token
    payload = jwt_handler.verify_access_token(token)
    if not payload:
        raise InvalidTokenException("Invalid or expired token")

    token_data = TokenPayload(**payload)

    # Get user from database
    user = await user_repo.get_by_id(db, token_data.user_id)

    if not user:
        raise UserNotFoundException("User not found")

    if not user.is_active:
        raise UserDisabledException("User account is disabled")

    return user


# Type alias for current user dependency
CurrentUser: TypeAlias = Annotated[User, Depends(get_current_user)]


async def get_current_user_not_purging(current_user: CurrentUser) -> User:
    """Reject requests when the caller's account is mid-purge.

    Per design-doc §16 + I3/I8, once ``users.is_purging=true`` the user-account
    purge driver is iterating over every owned session. Allowing a new
    session-mutating request to land would either:

      - Re-create a session row that the purge driver has already scanned
        (I3 violation, GDPR Art. 17 re-emergence), or
      - Race ``purge_one_session`` for the same session id (I8 violation,
        ``purge_attempts`` accounting corruption).

    Apply this dependency to ANY endpoint that creates or mutates a Session
    or its child rows. Read-only endpoints (list/detail) are exempt — they
    do not block the purge driver.

    Returns the same User object as ``CurrentUser`` (so the dep can stand
    in directly). Raises HTTP 423 Locked on block.

    Defence-in-depth: the ORM ``before_insert`` listener
    (``register_purge_guards``) catches direct DB inserts that bypass this
    HTTP-level check.
    """
    if bool(getattr(current_user, "is_purging", False)):
        from fastapi import HTTPException, status

        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail=(
                "account is undergoing erasure; mutation endpoints are "
                "locked until the purge completes (GDPR Art. 17 / §16)."
            ),
        )
    return current_user


# Type alias for the not-purging variant.
NotPurgingDep: TypeAlias = Annotated[User, Depends(get_current_user_not_purging)]


__all__ = [
    "get_current_user",
    "get_current_user_not_purging",
    "CurrentUser",
    "NotPurgingDep",
    "DBSession",
    "SettingsDep",
    "security",
]
