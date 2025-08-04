"""Authentication API endpoints."""

import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from ii_agent.db.manager import get_db
from ii_agent.db.models import User
from ii_agent.server.models.auth import (
    UserRegistration,
    UserLogin,
    TokenResponse,
    RefreshTokenRequest,
    UserProfile,
    UserProfileUpdate,
    ChangePassword,
)
from ii_agent.server.auth.jwt_handler import jwt_handler
from ii_agent.server.auth.password_utils import hash_password, verify_password
from ii_agent.server.auth.middleware import get_current_user


router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED
)
async def register(user_data: UserRegistration, db: Session = Depends(get_db)):
    """Register a new user."""

    # Check if user already exists
    existing_user = (
        db.query(User)
        .filter((User.email == user_data.email) | (User.username == user_data.username))
        .first()
    )

    if existing_user:
        if existing_user.email == user_data.email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered",
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Username already taken"
            )

    # Hash the password
    hashed_password = hash_password(user_data.password)

    # Create new user
    new_user = User(
        id=str(uuid.uuid4()),
        email=user_data.email,
        username=user_data.username,
        password_hash=hashed_password,
        first_name=user_data.first_name,
        last_name=user_data.last_name,
        organization=user_data.organization,
        role="user",
        subscription_tier="free",
        is_active=True,
        email_verified=False,
        created_at=datetime.now(timezone.utc),
    )

    try:
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="User registration failed"
        )

    # Create tokens
    access_token = jwt_handler.create_access_token(
        user_id=new_user.id, email=new_user.email, role=new_user.role
    )
    refresh_token = jwt_handler.create_refresh_token(user_id=new_user.id)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=jwt_handler.access_token_expire_minutes * 60,
    )


@router.post("/login", response_model=TokenResponse)
async def login(credentials: UserLogin, db: Session = Depends(get_db)):
    """Login with email and password."""

    # Find user by email
    user = db.query(User).filter(User.email == credentials.email).first()

    if not user or not user.password_hash:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password"
        )

    # Verify password
    if not verify_password(credentials.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password"
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Account is disabled"
        )

    # Update last login
    user.last_login_at = datetime.now(timezone.utc)
    db.commit()

    # Create tokens
    access_token = jwt_handler.create_access_token(
        user_id=user.id, email=user.email, role=user.role
    )
    refresh_token = jwt_handler.create_refresh_token(user_id=user.id)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=jwt_handler.access_token_expire_minutes * 60,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(request: RefreshTokenRequest, db: Session = Depends(get_db)):
    """Refresh access token using refresh token."""

    # Verify refresh token
    payload = jwt_handler.verify_refresh_token(request.refresh_token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    # Get user
    user_id = payload.get("user_id")
    user = db.query(User).filter(User.id == user_id).first()

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    # Create new access token
    access_token = jwt_handler.create_access_token(
        user_id=user.id, email=user.email, role=user.role
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=request.refresh_token,  # Keep the same refresh token
        expires_in=jwt_handler.access_token_expire_minutes * 60,
    )


@router.get("/me", response_model=UserProfile)
async def get_current_user_profile(current_user: User = Depends(get_current_user)):
    """Get current user profile."""
    return UserProfile(
        id=current_user.id,
        email=current_user.email,
        username=current_user.username,
        first_name=current_user.first_name,
        last_name=current_user.last_name,
        role=current_user.role,
        subscription_tier=current_user.subscription_tier,
        is_active=current_user.is_active,
        email_verified=current_user.email_verified,
        created_at=current_user.created_at.isoformat()
        if current_user.created_at
        else "",
        last_login_at=current_user.last_login_at.isoformat()
        if current_user.last_login_at
        else None,
        organization=current_user.organization,
        login_provider=current_user.login_provider,
    )


@router.put("/me", response_model=UserProfile)
async def update_user_profile(
    profile_data: UserProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update current user profile."""

    # Update fields
    if profile_data.first_name is not None:
        current_user.first_name = profile_data.first_name
    if profile_data.last_name is not None:
        current_user.last_name = profile_data.last_name
    if profile_data.organization is not None:
        current_user.organization = profile_data.organization

    current_user.updated_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(current_user)

    return UserProfile(
        id=current_user.id,
        email=current_user.email,
        username=current_user.username,
        first_name=current_user.first_name,
        last_name=current_user.last_name,
        role=current_user.role,
        subscription_tier=current_user.subscription_tier,
        is_active=current_user.is_active,
        email_verified=current_user.email_verified,
        created_at=current_user.created_at.isoformat()
        if current_user.created_at
        else "",
        last_login_at=current_user.last_login_at.isoformat()
        if current_user.last_login_at
        else None,
        organization=current_user.organization,
        login_provider=current_user.login_provider,
    )


@router.post("/change-password")
async def change_password(
    password_data: ChangePassword,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Change user password."""

    # Verify current password
    if not current_user.password_hash or not verify_password(
        password_data.current_password, current_user.password_hash
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )

    # Hash new password
    new_password_hash = hash_password(password_data.new_password)
    current_user.password_hash = new_password_hash
    current_user.updated_at = datetime.now(timezone.utc)

    db.commit()

    return {"message": "Password changed successfully"}


@router.post("/logout")
async def logout():
    """Logout user (client should discard tokens)."""
    return {"message": "Logged out successfully"}
