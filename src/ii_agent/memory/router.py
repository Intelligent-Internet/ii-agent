"""Memory dashboard API endpoints."""

from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query, status

from ii_agent.auth.dependencies import CurrentUser, DBSession
from ii_agent.memory.dependencies import MemoryServiceDep
from ii_agent.memory.schemas import (
    MemoryBulkDeleteRequest,
    MemoryCreateRequest,
    MemoryListResponse,
    MemoryResponse,
    MemoryUpdateRequest,
)

router = APIRouter(prefix="/memories", tags=["Memories"])


@router.get("", response_model=MemoryListResponse)
async def list_memories(
    current_user: CurrentUser,
    db: DBSession,
    memory_service: MemoryServiceDep,
    page: int = Query(1, ge=1),
    per_page: int = Query(10, ge=1, le=100),
    search: Optional[str] = Query(None, max_length=200),
    topics: Optional[str] = Query(None, description="Comma-separated topic filters"),
    sort_by: str = Query("updated_at"),
    sort_order: str = Query("desc"),
) -> Any:
    """List user memories with pagination, search, filter, and sort."""
    if sort_by not in ("updated_at", "memory", "topics_count"):
        sort_by = "updated_at"
    if sort_order not in ("asc", "desc"):
        sort_order = "desc"

    topic_list = [t.strip() for t in topics.split(",") if t.strip()] if topics else None

    memories, total = await memory_service.get_memories_paginated(
        db,
        current_user.id,
        page=page,
        per_page=per_page,
        search=search,
        topics=topic_list,
        sort_by=sort_by,
        sort_order=sort_order,
    )

    return MemoryListResponse(
        memories=memories,
        total=total,
        page=page,
        per_page=per_page,
    )


@router.get("/topics", response_model=list[str])
async def list_topics(
    current_user: CurrentUser,
    db: DBSession,
    memory_service: MemoryServiceDep,
) -> Any:
    """Get all distinct topics for the current user."""
    return await memory_service.get_distinct_topics(db, current_user.id)


@router.get("/{memory_id}", response_model=MemoryResponse)
async def get_memory(
    memory_id: str,
    current_user: CurrentUser,
    db: DBSession,
    memory_service: MemoryServiceDep,
) -> Any:
    """Get a single memory by ID."""
    memory = await memory_service.get_memory(db, memory_id, current_user.id)
    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")
    return memory


@router.post("", response_model=MemoryResponse, status_code=status.HTTP_201_CREATED)
async def create_memory(
    body: MemoryCreateRequest,
    current_user: CurrentUser,
    db: DBSession,
    memory_service: MemoryServiceDep,
) -> Any:
    """Create a new memory."""
    import uuid

    return await memory_service.upsert_memory(
        db,
        memory_id=str(uuid.uuid4()),
        user_id=current_user.id,
        memory_text=body.memory,
        topics=body.topics or [],
    )


@router.put("/{memory_id}", response_model=MemoryResponse)
async def update_memory(
    memory_id: str,
    body: MemoryUpdateRequest,
    current_user: CurrentUser,
    db: DBSession,
    memory_service: MemoryServiceDep,
) -> Any:
    """Update an existing memory."""
    existing = await memory_service.get_memory(db, memory_id, current_user.id)
    if not existing:
        raise HTTPException(status_code=404, detail="Memory not found")

    return await memory_service.upsert_memory(
        db,
        memory_id=memory_id,
        user_id=current_user.id,
        memory_text=body.memory if body.memory is not None else existing.memory,
        topics=body.topics if body.topics is not None else existing.topics,
    )


@router.delete("/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_memory(
    memory_id: str,
    current_user: CurrentUser,
    db: DBSession,
    memory_service: MemoryServiceDep,
) -> None:
    """Delete a single memory."""
    await memory_service.delete_memory(db, memory_id, current_user.id)


@router.post("/bulk-delete", status_code=status.HTTP_204_NO_CONTENT)
async def bulk_delete_memories(
    body: MemoryBulkDeleteRequest,
    current_user: CurrentUser,
    db: DBSession,
    memory_service: MemoryServiceDep,
) -> None:
    """Delete multiple memories at once."""
    await memory_service.delete_memories(db, body.memory_ids, current_user.id)
