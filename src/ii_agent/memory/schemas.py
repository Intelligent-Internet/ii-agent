"""Pydantic schemas (DTOs) for memory domain."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Domain DTO (used internally by service/manager)
# ---------------------------------------------------------------------------


class MemoryData(BaseModel):
    """Domain model for a single user memory record."""

    model_config = ConfigDict(from_attributes=True)

    memory_id: str
    memory: str
    topics: list[str] | None = None
    user_id: UUID | None = None
    input: str | None = None
    agent_id: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


# ---------------------------------------------------------------------------
# API request/response DTOs
# ---------------------------------------------------------------------------


class MemoryResponse(BaseModel):
    memory_id: str
    memory: str
    topics: list[str] | None = None
    input: str | None = None
    agent_id: str | None = None
    created_at: int | None = None
    updated_at: int | None = None


class MemoryListResponse(BaseModel):
    memories: list[MemoryResponse]
    total: int
    page: int
    per_page: int


class MemoryCreateRequest(BaseModel):
    memory: str = Field(..., min_length=1, max_length=5000)
    topics: list[str] | None = None


class MemoryUpdateRequest(BaseModel):
    memory: str | None = Field(None, min_length=1, max_length=5000)
    topics: list[str] | None = None


class MemoryBulkDeleteRequest(BaseModel):
    memory_ids: list[str]


# ---------------------------------------------------------------------------
# User preferences
# ---------------------------------------------------------------------------


class UserPreferences(BaseModel):
    has_memory: bool = True


class UpdatePreferencesRequest(BaseModel):
    has_memory: Optional[bool] = None


# ---------------------------------------------------------------------------
# Agentic search response
# ---------------------------------------------------------------------------


class MemorySearchResponse(BaseModel):
    """Model for agentic memory search results."""

    memory_ids: list[str] = Field(
        ...,
        description="The IDs of the memories that are most semantically similar to the query.",
    )
