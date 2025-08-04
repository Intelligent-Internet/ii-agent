"""User management API endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import List, Optional

from ii_agent.db.manager import get_db
from ii_agent.db.models import User
from ii_agent.server.models.auth import UserProfile
from ii_agent.server.auth.middleware import require_admin


router = APIRouter(prefix="/users", tags=["User Management"])


@router.get("/", response_model=List[UserProfile])
async def list_users(
    skip: int = Query(0, ge=0, description="Number of users to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Number of users to return"),
    search: Optional[str] = Query(None, description="Search by email or username"),
    role: Optional[str] = Query(None, description="Filter by role"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """List all users (admin only)."""

    query = db.query(User)

    # Apply filters
    if search:
        query = query.filter(
            (User.email.ilike(f"%{search}%"))
            | (User.username.ilike(f"%{search}%"))
            | (User.first_name.ilike(f"%{search}%"))
            | (User.last_name.ilike(f"%{search}%"))
        )

    if role:
        query = query.filter(User.role == role)

    if is_active is not None:
        query = query.filter(User.is_active == is_active)

    # Order by creation date (newest first)
    query = query.order_by(desc(User.created_at))

    # Apply pagination
    users = query.offset(skip).limit(limit).all()

    return [
        UserProfile(
            id=user.id,
            email=user.email,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
            role=user.role,
            subscription_tier=user.subscription_tier,
            is_active=user.is_active,
            email_verified=user.email_verified,
            created_at=user.created_at.isoformat() if user.created_at else "",
            last_login_at=(
                user.last_login_at.isoformat() if user.last_login_at else None
            ),
            organization=user.organization,
            login_provider=user.login_provider,
        )
        for user in users
    ]


@router.get("/{user_id}", response_model=UserProfile)
async def get_user(
    user_id: str,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Get a specific user by ID (admin only)."""

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    return UserProfile(
        id=user.id,
        email=user.email,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        role=user.role,
        subscription_tier=user.subscription_tier,
        is_active=user.is_active,
        email_verified=user.email_verified,
        created_at=user.created_at.isoformat() if user.created_at else "",
        last_login_at=user.last_login_at.isoformat() if user.last_login_at else None,
        organization=user.organization,
        login_provider=user.login_provider,
    )


@router.patch("/{user_id}/role")
async def update_user_role(
    user_id: str,
    role: str = Query(
        ..., regex="^(user|admin|moderator)$", description="New role for the user"
    ),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Update a user's role (admin only)."""

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    # Prevent admin from demoting themselves
    if user.id == current_user.id and role != "admin":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot demote yourself"
        )

    user.role = role
    db.commit()

    return {"message": f"User role updated to {role}"}


@router.patch("/{user_id}/status")
async def update_user_status(
    user_id: str,
    is_active: bool = Query(..., description="Active status"),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Update a user's active status (admin only)."""

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    # Prevent admin from deactivating themselves
    if user.id == current_user.id and not is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot deactivate yourself",
        )

    user.is_active = is_active
    db.commit()

    status_text = "activated" if is_active else "deactivated"
    return {"message": f"User {status_text} successfully"}


@router.patch("/{user_id}/subscription")
async def update_user_subscription(
    user_id: str,
    subscription_tier: str = Query(
        ..., regex="^(free|pro|enterprise)$", description="Subscription tier"
    ),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Update a user's subscription tier (admin only)."""

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    user.subscription_tier = subscription_tier
    db.commit()

    return {"message": f"User subscription updated to {subscription_tier}"}


@router.delete("/{user_id}")
async def delete_user(
    user_id: str,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Delete a user (admin only)."""

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    # Prevent admin from deleting themselves
    if user.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot delete yourself"
        )

    db.delete(user)
    db.commit()

    return {"message": "User deleted successfully"}


@router.get("/stats/overview")
async def get_user_stats(
    current_user: User = Depends(require_admin), db: Session = Depends(get_db)
):
    """Get user statistics overview (admin only)."""

    total_users = db.query(User).count()
    active_users = db.query(User).filter(User.is_active).count()
    verified_users = db.query(User).filter(User.email_verified).count()

    # Count by subscription tier
    subscription_stats = {}
    for tier in ["free", "pro", "enterprise"]:
        count = db.query(User).filter(User.subscription_tier == tier).count()
        subscription_stats[tier] = count

    # Count by role
    role_stats = {}
    for role in ["user", "admin", "moderator"]:
        count = db.query(User).filter(User.role == role).count()
        role_stats[role] = count

    return {
        "total_users": total_users,
        "active_users": active_users,
        "verified_users": verified_users,
        "inactive_users": total_users - active_users,
        "unverified_users": total_users - verified_users,
        "subscription_stats": subscription_stats,
        "role_stats": role_stats,
    }
