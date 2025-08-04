"""Authentication Pydantic models."""

from pydantic import BaseModel, EmailStr, Field
from typing import Optional


class UserRegistration(BaseModel):
    """Model for user registration."""

    email: EmailStr
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=8)
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    organization: Optional[str] = None


class UserLogin(BaseModel):
    """Model for user login."""

    email: EmailStr
    password: str


class OAuthLogin(BaseModel):
    """Model for OAuth login."""

    provider: str = Field(..., description="OAuth provider (google, github, etc.)")
    access_token: str = Field(..., description="OAuth access token")


class TokenResponse(BaseModel):
    """Model for token response."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RefreshTokenRequest(BaseModel):
    """Model for refresh token request."""

    refresh_token: str


class UserProfile(BaseModel):
    """Model for user profile response."""

    id: str
    email: str
    username: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    role: str
    subscription_tier: str
    is_active: bool
    email_verified: bool
    created_at: str
    last_login_at: Optional[str] = None
    organization: Optional[str] = None
    login_provider: Optional[str] = None


class UserProfileUpdate(BaseModel):
    """Model for updating user profile."""

    first_name: Optional[str] = None
    last_name: Optional[str] = None
    organization: Optional[str] = None


class PasswordReset(BaseModel):
    """Model for password reset request."""

    email: EmailStr


class PasswordResetConfirm(BaseModel):
    """Model for password reset confirmation."""

    reset_token: str
    new_password: str = Field(..., min_length=8)


class ChangePassword(BaseModel):
    """Model for changing password."""

    current_password: str
    new_password: str = Field(..., min_length=8)
