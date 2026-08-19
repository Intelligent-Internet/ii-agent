"""Session management API endpoints."""

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Query

from ii_agent.auth.dependencies import CurrentUser, DBSession
from ii_agent.core.exceptions import InternalError
from ii_agent.sessions.dependencies import RunTaskServiceDep
from ii_agent.chat.api.dependencies import ChatMessageRepositoryDep
from ii_agent.files.dependencies import FileServiceDep
from ii_agent.sessions.dependencies import SessionForkServiceDep, SessionServiceDep
from ii_agent.sessions.exceptions import SessionNotFoundError
from ii_agent.sessions.schemas import (
    BulkDeleteRequest,
    BulkDeleteResponse,
    ForkSessionRequest,
    ForkSessionResponse,
    ScheduleDeleteRequest,
    SessionInfo,
    SessionResponse,
    SessionFile,
    SessionPlanUpdate,
    SessionUpdate,
)
from ii_agent.sessions.schemas import EventInfo, EventResponse, SessionEventDetail
from ii_agent.sessions.models import AppKind
from ii_agent.sessions.pin.router import router as pin_router
from ii_agent.sessions.wishlist.router import router as wishlist_router


def _build_event_info(e: "SessionEventDetail", session_id: uuid.UUID) -> EventInfo:
    """Convert a service-layer event detail into the API response model."""
    return EventInfo(
        id=e.id,
        name=e.type,
        event_type=e.type,
        content=e.content,
        created_at=e.created_at,
        run_id=str(e.run_id) if e.run_id is not None else None,
        session_id=session_id,
    )


def _collect_file_ids(events: list[EventInfo]) -> set[uuid.UUID]:
    """Extract all file asset IDs referenced in event content."""
    file_ids: set[uuid.UUID] = set()
    for event in events:
        if not event.content:
            continue
        # content.files is a list of file ID strings
        raw_ids = event.content.get("files")
        if isinstance(raw_ids, list):
            for raw_id in raw_ids:
                try:
                    file_ids.add(uuid.UUID(str(raw_id)))
                except (ValueError, AttributeError):
                    continue
    return file_ids


def _inject_signed_urls(
    events: list[EventInfo],
    url_map: dict[uuid.UUID, str],
) -> None:
    """Inject signed_url into each files_metadata entry that has a matching ID."""
    if not url_map:
        return
    for event in events:
        if not event.content:
            continue
        metadata_list = event.content.get("files_metadata")
        if not isinstance(metadata_list, list):
            continue
        for entry in metadata_list:
            if not isinstance(entry, dict):
                continue
            raw_id = entry.get("id")
            if raw_id is None:
                continue
            try:
                fid = uuid.UUID(str(raw_id))
            except (ValueError, AttributeError):
                continue
            if fid in url_map:
                entry["signed_url"] = url_map[fid]


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sessions", tags=["Sessions"])
router.include_router(pin_router)
router.include_router(wishlist_router)


@router.post("/bulk-delete", response_model=BulkDeleteResponse)
async def bulk_delete_sessions(
    payload: BulkDeleteRequest,
    db: DBSession,
    current_user: CurrentUser,
    session_service: SessionServiceDep,
) -> BulkDeleteResponse:
    """Bulk soft delete sessions by list of IDs."""
    deleted_ids, failed_ids = await session_service.bulk_soft_delete_sessions(
        db, payload.session_ids, current_user.id
    )
    return BulkDeleteResponse(deleted_ids=deleted_ids, failed_ids=failed_ids)


@router.get("/{session_id}", response_model=SessionInfo)
async def get_session(
    session_id: uuid.UUID,
    db: DBSession,
    current_user: CurrentUser,
    session_service: SessionServiceDep,
) -> SessionInfo:
    """Get detailed information for a specific session."""
    session_data = await session_service.get_session_details(db, session_id, current_user.id)

    if not session_data:
        raise SessionNotFoundError(f"Session {session_id} not found or access denied")

    return session_data


@router.get("", response_model=SessionResponse)
async def list_sessions(
    db: DBSession,
    current_user: CurrentUser,
    session_service: SessionServiceDep,
    query: Optional[str] = Query(None, description="Search term to filter sessions by name"),
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page"),
    public_only: bool = Query(False, description="If true, return only public sessions"),
    session_type: Optional[Literal["agent", "chat"]] = Query(
        None,
        description="Filter by session type: 'chat' for chat sessions only, 'agent' for non-chat sessions",
    ),
) -> SessionResponse:
    """List sessions for the current user with optional search and pagination."""
    sessions_data, total = await session_service.get_user_sessions(
        db,
        user_id=current_user.id,
        search_term=query,
        page=page,
        per_page=per_page,
        public_only=public_only,
        session_type=session_type,
    )

    return SessionResponse(sessions=sessions_data, total=total, page=page, per_page=per_page)


@router.get("/{session_id}/events", response_model=EventResponse)
async def get_session_events(
    session_id: uuid.UUID,
    db: DBSession,
    current_user: CurrentUser,
    session_service: SessionServiceDep,
    run_task_service: RunTaskServiceDep,
    chat_message_repo: ChatMessageRepositoryDep,
    file_service: FileServiceDep,
) -> EventResponse:
    """Get all events for a specific session."""
    session_data = await session_service.get_session_details(db, session_id, current_user.id)

    if not session_data:
        raise SessionNotFoundError(f"Session {session_id} not found or access denied")

    events_raw = await session_service.get_session_events_with_details(db, session_id)
    events = [_build_event_info(e, session_id) for e in events_raw]

    # Resolve fresh signed URLs for file references in event content
    file_ids = _collect_file_ids(events)
    if file_ids:
        url_map = await file_service.resolve_signed_urls(db, list(file_ids))
        _inject_signed_urls(events, url_map)

    run_status = None
    try:
        if session_data.app_kind == AppKind.CHAT:
            last_msg = await chat_message_repo.get_last_assistant_by_session(db, session_id)
            if last_msg:
                run_status = "completed" if last_msg.is_finished else "running"
        else:
            last_run = await run_task_service.get_last_by_session_id(db, session_id)
            if last_run:
                run_status = last_run.status
    except Exception as e:
        logger.warning(f"Failed to get run status for session {session_id}: {e}")

    return EventResponse(events=events, run_status=run_status)


@router.get("/{session_id}/files", response_model=list[SessionFile])
async def get_session_files(
    session_id: uuid.UUID,
    db: DBSession,
    current_user: CurrentUser,
    session_service: SessionServiceDep,
    file_service: FileServiceDep,
):
    """Get all files for a specific session."""
    session_data = await session_service.get_session_details(db, session_id, current_user.id)

    if not session_data:
        raise SessionNotFoundError(f"Session {session_id} not found or access denied")

    files = await file_service.get_files_by_session_id(db, session_id)
    return [
        SessionFile(
            id=file.id,
            name=file.name,
            size=file.size,
            content_type=file.content_type,
            url=file.url,
        )
        for file in files
    ]


@router.post("/{session_id}/publish")
async def publish_session(
    session_id: uuid.UUID,
    db: DBSession,
    current_user: CurrentUser,
    session_service: SessionServiceDep,
) -> dict:
    """Set a session as public."""
    success = await session_service.set_session_public(db, session_id, current_user.id, True)

    if not success:
        raise SessionNotFoundError(f"Session {session_id} not found or access denied")

    return {"message": f"Session {session_id} published successfully"}


@router.post("/{session_id}/unpublish")
async def unpublish_session(
    session_id: uuid.UUID,
    db: DBSession,
    current_user: CurrentUser,
    session_service: SessionServiceDep,
) -> dict:
    """Set a session as private."""
    success = await session_service.set_session_public(db, session_id, current_user.id, False)

    if not success:
        raise SessionNotFoundError(f"Session {session_id} not found or access denied")

    return {"message": f"Session {session_id} unpublished successfully"}


@router.delete("/{session_id}")
async def delete_session(
    session_id: uuid.UUID,
    db: DBSession,
    current_user: CurrentUser,
    session_service: SessionServiceDep,
) -> dict:
    """Soft delete a session by setting is_deleted flag."""
    await session_service.soft_delete_session(db, session_id, current_user.id)
    return {"message": f"Session {session_id} deleted successfully"}


@router.post("/{session_id}/schedule-delete")
async def schedule_delete_session(
    session_id: uuid.UUID,
    payload: ScheduleDeleteRequest,
    db: DBSession,
    current_user: CurrentUser,
    session_service: SessionServiceDep,
) -> dict:
    """Schedule a session for automatic deletion at a future time.

    The session and its sandbox will remain available for inspection until
    the scheduled time passes, at which point the background cleanup loop
    will soft-delete the session and reap its sandbox container.
    """
    if payload.delete_after_seconds is not None:
        delete_at = datetime.now(timezone.utc) + timedelta(seconds=payload.delete_after_seconds)
    elif payload.delete_at is not None:
        delete_at = datetime.fromisoformat(payload.delete_at)
        if delete_at.tzinfo is None:
            delete_at = delete_at.replace(tzinfo=timezone.utc)
    else:
        raise HTTPException(
            status_code=422,
            detail="Provide either delete_after_seconds or delete_at",
        )

    await session_service.schedule_deletion(db, session_id, current_user.id, delete_at)
    return {
        "message": f"Session {session_id} scheduled for deletion",
        "delete_at": delete_at.isoformat(),
    }


@router.post("/{session_id}/fork", response_model=ForkSessionResponse)
async def fork_session(
    session_id: uuid.UUID,
    payload: ForkSessionRequest,
    db: DBSession,
    current_user: CurrentUser,
    fork_service: SessionForkServiceDep,
) -> ForkSessionResponse:
    """Fork a session to create a new child session with inherited context."""
    return await fork_service.fork_session(db, session_id, current_user.id, payload)


@router.patch("/{session_id}", response_model=SessionInfo)
async def update_session(
    session_id: uuid.UUID,
    payload: SessionUpdate,
    db: DBSession,
    current_user: CurrentUser,
    session_service: SessionServiceDep,
) -> SessionInfo:
    """Update session metadata (name, status, etc.)."""
    session_data = await session_service.get_session_details(db, session_id, current_user.id)

    if not session_data:
        raise SessionNotFoundError(f"Session {session_id} not found or access denied")

    if payload.name is not None:
        await session_service.update_session_name(db, session_id, payload.name)

    updated_session = await session_service.get_session_details(db, session_id, current_user.id)

    if not updated_session:
        raise InternalError("Failed to fetch updated session")

    return updated_session


@router.patch("/{session_id}/plan")
async def update_session_plan(
    session_id: uuid.UUID,
    payload: SessionPlanUpdate,
    db: DBSession,
    current_user: CurrentUser,
    session_service: SessionServiceDep,
) -> dict:
    """Update the session's stored plan (summary + milestones)."""
    await session_service.update_session_plan(
        db,
        session_id=session_id,
        user_id=current_user.id,
        summary=payload.summary,
        milestones=[m.model_dump() for m in payload.milestones],
    )
    return {"message": "Plan updated successfully"}


# ---------------------------------------------------------------------------
# Public endpoints (served under /v1/public/sessions)
# ---------------------------------------------------------------------------

public_router = APIRouter(prefix="/sessions", tags=["Sessions Public"])


@public_router.get("/{session_id}", response_model=SessionInfo)
async def get_public_session(
    session_id: uuid.UUID,
    db: DBSession,
    session_service: SessionServiceDep,
) -> SessionInfo:
    """Get detailed information for a public session without authentication."""
    session_data = await session_service.get_public_session_details(db, session_id)

    if not session_data:
        raise SessionNotFoundError(f"Session {session_id} not found or not public")

    return session_data


@public_router.get("/{session_id}/events", response_model=EventResponse)
async def get_public_session_events(
    session_id: uuid.UUID,
    db: DBSession,
    session_service: SessionServiceDep,
    run_task_service: RunTaskServiceDep,
    chat_message_repo: ChatMessageRepositoryDep,
    file_service: FileServiceDep,
) -> EventResponse:
    """Get all events for a public session without authentication."""
    session_data = await session_service.get_public_session_details(db, session_id)

    if not session_data:
        raise SessionNotFoundError(f"Session {session_id} not found or not public")

    events_raw = await session_service.get_session_events_with_details(db, session_id)
    events = [_build_event_info(e, session_id) for e in events_raw]

    # Resolve fresh signed URLs for file references in event content
    file_ids = _collect_file_ids(events)
    if file_ids:
        url_map = await file_service.resolve_signed_urls(db, list(file_ids))
        _inject_signed_urls(events, url_map)

    run_status = None
    try:
        if session_data.app_kind == AppKind.CHAT:
            last_msg = await chat_message_repo.get_last_assistant_by_session(db, session_id)
            if last_msg:
                run_status = "completed" if last_msg.is_finished else "running"
        else:
            last_run = await run_task_service.get_last_by_session_id(db, session_id)
            if last_run:
                run_status = last_run.status
    except Exception as e:
        logger.warning(f"Failed to get run status for session {session_id}: {e}")

    return EventResponse(events=events, run_status=run_status)
