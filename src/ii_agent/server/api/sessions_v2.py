"""Enhanced session management API endpoints."""

import uuid
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import Optional

from ii_agent.db.manager import get_db
from ii_agent.db.models import Session as SessionModel, User, Event
from ii_agent.server.models.sessions import (
    SessionCreate,
    SessionUpdate,
    SessionInfo,
    SessionList,
    SessionStats,
)
from ii_agent.server.auth.middleware import get_current_user
from ii_agent.utils.workspace_manager import WorkspaceManager


router = APIRouter(prefix="/sessions", tags=["Session Management"])


@router.post("/", response_model=SessionInfo, status_code=status.HTTP_201_CREATED)
async def create_session(
    session_data: SessionCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a new chat session."""

    session_uuid = uuid.uuid4()

    # Create workspace directory for this session
    workspace_manager = WorkspaceManager()
    workspace_dir = workspace_manager.create_workspace(str(session_uuid))

    # Create new session
    new_session = SessionModel(
        id=session_uuid,
        user_id=uuid.UUID(current_user.id),
        workspace_dir=workspace_dir,
        name=session_data.name
        or f"Session {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        status="active",
        settings=session_data.settings or {},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    db.add(new_session)
    db.commit()
    db.refresh(new_session)

    return SessionInfo(
        id=new_session.id,
        user_id=new_session.user_id,
        name=new_session.name,
        status=new_session.status,
        sandbox_id=new_session.sandbox_id,
        workspace_dir=new_session.workspace_dir,
        is_public=new_session.is_public or False,
        public_url=new_session.public_url,
        token_usage=new_session.token_usage,
        settings=new_session.settings,
        created_at=new_session.created_at.isoformat() if new_session.created_at else "",
        updated_at=new_session.updated_at.isoformat()
        if new_session.updated_at
        else None,
        last_message_at=new_session.last_message_at.isoformat()
        if new_session.last_message_at
        else None,
        device_id=new_session.device_id,
    )


@router.get("/", response_model=SessionList)
async def list_sessions(
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page"),
    status: Optional[str] = Query(None, description="Filter by status"),
    search: Optional[str] = Query(None, description="Search by name"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List user's sessions with pagination."""

    query = db.query(SessionModel).filter(
        SessionModel.user_id == current_user.id, SessionModel.deleted_at.is_(None)
    )

    # Apply filters
    if status:
        query = query.filter(SessionModel.status == status)

    if search:
        query = query.filter(SessionModel.name.ilike(f"%{search}%"))

    # Get total count
    total = query.count()

    # Order by last message or creation date
    query = query.order_by(
        desc(SessionModel.last_message_at), desc(SessionModel.created_at)
    )

    # Apply pagination
    offset = (page - 1) * per_page
    sessions = query.offset(offset).limit(per_page).all()

    session_list = [
        SessionInfo(
            id=session.id,
            user_id=session.user_id,
            name=session.name,
            status=session.status,
            sandbox_id=session.sandbox_id,
            workspace_dir=session.workspace_dir,
            is_public=session.is_public or False,
            public_url=session.public_url,
            token_usage=session.token_usage,
            settings=session.settings,
            created_at=session.created_at.isoformat() if session.created_at else "",
            updated_at=session.updated_at.isoformat() if session.updated_at else None,
            last_message_at=session.last_message_at.isoformat()
            if session.last_message_at
            else None,
            device_id=session.device_id,
        )
        for session in sessions
    ]

    return SessionList(sessions=session_list, total=total, page=page, per_page=per_page)


@router.get("/{session_id}", response_model=SessionInfo)
async def get_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get a specific session."""

    session = (
        db.query(SessionModel)
        .filter(
            SessionModel.id == session_id,
            SessionModel.user_id == current_user.id,
            SessionModel.deleted_at.is_(None),
        )
        .first()
    )

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Session not found"
        )

    return SessionInfo(
        id=session.id,
        user_id=session.user_id,
        name=session.name,
        status=session.status,
        sandbox_id=session.sandbox_id,
        workspace_dir=session.workspace_dir,
        is_public=session.is_public or False,
        public_url=session.public_url,
        token_usage=session.token_usage,
        settings=session.settings,
        created_at=session.created_at.isoformat() if session.created_at else "",
        updated_at=session.updated_at.isoformat() if session.updated_at else None,
        last_message_at=session.last_message_at.isoformat()
        if session.last_message_at
        else None,
        device_id=session.device_id,
    )


@router.patch("/{session_id}", response_model=SessionInfo)
async def update_session(
    session_id: str,
    session_data: SessionUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update a session."""

    session = (
        db.query(SessionModel)
        .filter(
            SessionModel.id == session_id,
            SessionModel.user_id == current_user.id,
            SessionModel.deleted_at.is_(None),
        )
        .first()
    )

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Session not found"
        )

    # Update fields
    if session_data.name is not None:
        session.name = session_data.name
    if session_data.status is not None:
        session.status = session_data.status
    if session_data.settings is not None:
        session.settings = session_data.settings
    if session_data.is_public is not None:
        session.is_public = session_data.is_public

    session.updated_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(session)

    return SessionInfo(
        id=session.id,
        user_id=session.user_id,
        name=session.name,
        status=session.status,
        sandbox_id=session.sandbox_id,
        workspace_dir=session.workspace_dir,
        is_public=session.is_public or False,
        public_url=session.public_url,
        token_usage=session.token_usage,
        settings=session.settings,
        created_at=session.created_at.isoformat() if session.created_at else "",
        updated_at=session.updated_at.isoformat() if session.updated_at else None,
        last_message_at=session.last_message_at.isoformat()
        if session.last_message_at
        else None,
        device_id=session.device_id,
    )


@router.delete("/{session_id}")
async def delete_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a session (soft delete)."""

    session = (
        db.query(SessionModel)
        .filter(
            SessionModel.id == session_id,
            SessionModel.user_id == current_user.id,
            SessionModel.deleted_at.is_(None),
        )
        .first()
    )

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Session not found"
        )

    # Soft delete
    session.deleted_at = datetime.now(timezone.utc)
    session.status = "deleted"

    db.commit()

    return {"message": "Session deleted successfully"}


@router.post("/{session_id}/pause")
async def pause_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Pause a session."""

    session = (
        db.query(SessionModel)
        .filter(
            SessionModel.id == session_id,
            SessionModel.user_id == current_user.id,
            SessionModel.deleted_at.is_(None),
        )
        .first()
    )

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Session not found"
        )

    if session.status != "active":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Can only pause active sessions",
        )

    session.status = "pause"
    session.updated_at = datetime.now(timezone.utc)

    db.commit()

    return {"message": "Session paused successfully"}


@router.post("/{session_id}/resume")
async def resume_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Resume a paused session."""

    session = (
        db.query(SessionModel)
        .filter(
            SessionModel.id == session_id,
            SessionModel.user_id == current_user.id,
            SessionModel.deleted_at.is_(None),
        )
        .first()
    )

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Session not found"
        )

    if session.status != "pause":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Can only resume paused sessions",
        )

    session.status = "active"
    session.updated_at = datetime.now(timezone.utc)

    db.commit()

    return {"message": "Session resumed successfully"}


@router.get("/stats/overview", response_model=SessionStats)
async def get_session_stats(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Get session statistics for the current user."""

    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=now.weekday())
    month_start = today_start.replace(day=1)

    # Base query for user's sessions
    base_query = db.query(SessionModel).filter(
        SessionModel.user_id == current_user.id, SessionModel.deleted_at.is_(None)
    )

    # Get counts
    total_sessions = base_query.count()
    active_sessions = base_query.filter(SessionModel.status == "active").count()
    paused_sessions = base_query.filter(SessionModel.status == "pause").count()

    sessions_today = base_query.filter(SessionModel.created_at >= today_start).count()
    sessions_this_week = base_query.filter(
        SessionModel.created_at >= week_start
    ).count()
    sessions_this_month = base_query.filter(
        SessionModel.created_at >= month_start
    ).count()

    # Get total messages
    total_messages = (
        db.query(Event)
        .join(SessionModel)
        .filter(
            SessionModel.user_id == current_user.id, SessionModel.deleted_at.is_(None)
        )
        .count()
    )

    return SessionStats(
        total_sessions=total_sessions,
        active_sessions=active_sessions,
        paused_sessions=paused_sessions,
        sessions_today=sessions_today,
        sessions_this_week=sessions_this_week,
        sessions_this_month=sessions_this_month,
        total_messages=total_messages,
    )
