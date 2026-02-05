"""Authentication Pydantic models."""

from datetime import datetime
from pydantic import BaseModel, EmailStr


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


class LoginRequest(BaseModel):
    """Model for email/password login request."""

    email: EmailStr
    password: str
