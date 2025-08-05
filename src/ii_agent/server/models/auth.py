"""Authentication Pydantic models."""

from datetime import datetime
from pydantic import BaseModel


class TokenResponse(BaseModel):
    """Model for token response."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class TokenPayload(BaseModel):
    """Model for token payload."""

    user_id: str
    email: str
    role: str = "user"
    type: str = "access"  # or "refresh"
    exp: datetime
    iat: datetime
