"""Pydantic schemas (DTOs) for users domain."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_serializer


class UserPreferences(BaseModel):
    has_memory: bool = True


class UserPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    role: str
    first_name: str
    last_name: str
    avatar: str | None = None
    subscription_status: str | None = None
    subscription_plan: str | None = None
    subscription_billing_cycle: str | None = None
    subscription_current_period_end: datetime | None = None
    language: str = "en"
    preferences: UserPreferences = UserPreferences()

    @field_serializer("subscription_current_period_end", when_used="json", mode="plain")
    def serialize_period_end(self, value: datetime | None, _info) -> str | None:
        if isinstance(value, datetime):
            return value.isoformat()
        return value


class UserResponse(BaseModel):
    """Internal service-layer DTO for cached user lookups."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    first_name: str | None = None
    last_name: str | None = None
    avatar: str | None = None
    role: str = "user"
    is_active: bool = True
    email_verified: bool = False
    language: str = "en"
    login_provider: str | None = None
    organization: str | None = None
    stripe_customer_id: str | None = None
