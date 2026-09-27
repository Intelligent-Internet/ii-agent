"""HTTP endpoints for the session purge subsystem (PR-F).

Exposes:
  - POST /sessions/{id}/restore         — un-soft-delete a session (caller-scoped).
  - POST /sessions/{id}/purge-now       — caller-driven Art. 17 erasure of one session.
  - POST /admin/users/{id}/purge        — admin user-account purge (any reason).
  - POST /admin/users/{id}/unblock-purge — operator escape-hatch: flip is_purging=false.
  - POST /admin/sar                     — register a verified SAR + flag sessions.

Design: docs/design-docs/session-lifecycle-and-data-custody.md §4.3 (restore),
§4.4 (purge_now), §16 (user-account), §17 (SAR intake).

Authorisation:
  - Restore + purge_now: caller must own the session.
  - Admin endpoints: caller.role == 'admin'.

Concurrency / safety guards:
  - Restore checks for active SAR (I16) — rejects HTTP 423 Locked.
  - purge_now calls ``check_user_not_purging`` (Adversarial #7).
  - User-purge endpoint runs the long pipeline inline; the operator-facing
    timeout is ``sessions.user_purge_overall_timeout_seconds`` (default 30 min)
    enforced inside ``purge_user_account``.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Body, HTTPException, Path, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import text

from ii_agent.auth.dependencies import CurrentUser, DBSession
from ii_agent.core.db.base import get_db_session_local
from ii_agent.core.logger import logger
from ii_agent.sessions.purge.exceptions import (
    PurgeBlockedError,
    UserPurgeBlockedError,
    UserPurgeFailedError,
    UserPurgeRetryableError,
)
from ii_agent.sessions.purge.session_purge import purge_one_session
from ii_agent.sessions.purge.types import (
    PurgeOutcome,
    PurgeTrigger,
    SARRequest,
    UserPurgeReason,
)
from ii_agent.sessions.purge.user_purge import (
    check_user_not_purging,
    intake_sar,
    is_user_under_active_sar,
    purge_user_account,
)


router = APIRouter(prefix="/sessions", tags=["Sessions / Purge"])
admin_router = APIRouter(prefix="/admin", tags=["Admin / Purge"])


# ---- Schemas ---------------------------------------------------------------


class RestoreResponse(BaseModel):
    session_id: uuid.UUID
    restored: bool
    message: str


class PurgeNowResponse(BaseModel):
    session_id: uuid.UUID
    outcome: str
    attempts_used: int
    elapsed_seconds: float
    dead_letter_count: int = 0
    note: str | None = None


class AdminUserPurgeBody(BaseModel):
    reason: UserPurgeReason = Field(
        default=UserPurgeReason.ADMIN_INITIATED,
        description="Why this user is being deleted. GDPR_ART17 requires a SARRequest.",
    )
    sar_request: SARRequest | None = Field(
        default=None,
        description="Required when reason=GDPR_ART17 (lawyer memo §5).",
    )


class UnblockPurgeResponse(BaseModel):
    user_id: uuid.UUID
    was_purging: bool
    message: str


class SARIntakeBody(BaseModel):
    sar_request: SARRequest


class SARIntakeResponse(BaseModel):
    user_id: uuid.UUID
    flagged_session_count: int
    message: str


# ---- Helpers ---------------------------------------------------------------


def _require_admin(user: object) -> None:
    role = getattr(user, "role", "user")
    if role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="admin role required",
        )


# ---- Endpoints -------------------------------------------------------------


@router.post(
    "/{session_id}/restore",
    response_model=RestoreResponse,
    status_code=status.HTTP_200_OK,
    summary="Restore (un-soft-delete) a session before its grace period expires.",
)
async def restore_session(
    session_id: Annotated[uuid.UUID, Path()],
    db: DBSession,
    current_user: CurrentUser,
) -> RestoreResponse:
    """Un-soft-delete a session.

    Rejects with HTTP 423 if the caller has an active SAR (I16) — the
    erasure is in flight; restoration would race phase (b) provider
    deletes already issued.

    Honours phase-(c)'s ``WHERE is_deleted=true`` recheck (I7): if a
    purge worker has already started phase (c), this UPDATE will lose
    the race and return 0 rows.
    """
    # I16: block restore while user is under verified SAR.
    if await is_user_under_active_sar(db, current_user.id):
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail=(
                "active SAR for this account; restore is blocked while "
                "erasure is in flight (I16, Art. 17(1))."
            ),
        )

    # Atomic conditional restore: only flip if (still) deleted, owned, and
    # purge not yet committed (claim/strip not yet started).
    result = await db.execute(
        text(
            """
            UPDATE sessions
               SET is_deleted = false,
                   purge_after = NULL,
                   purge_started_at = NULL,
                   sar_priority = false
             WHERE id = :sid
               AND user_id = :uid
               AND is_deleted = true
               AND purge_started_at IS NULL
            RETURNING id
            """
        ),
        {"sid": str(session_id), "uid": str(current_user.id)},
    )
    row = result.first()
    await db.commit()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "session not found, not owned by caller, not soft-deleted, "
                "or purge already started — cannot restore."
            ),
        )
    return RestoreResponse(
        session_id=session_id,
        restored=True,
        message="session restored; purge_after cleared",
    )


@router.post(
    "/{session_id}/purge-now",
    response_model=PurgeNowResponse,
    status_code=status.HTTP_200_OK,
    summary="Caller-invoked Art. 17 erasure of a single session.",
)
async def purge_now(
    session_id: Annotated[uuid.UUID, Path()],
    db: DBSession,
    current_user: CurrentUser,
    confirm: Annotated[bool, Query(description="Required ack — must be true.")] = False,
) -> PurgeNowResponse:
    """Drive a single session through the purge pipeline immediately.

    Pre-conditions:
      - ``confirm=true`` query param (irreversible action).
      - Caller owns the session.
      - Caller's account is NOT undergoing user-account purge (I8 — see
        ``check_user_not_purging``).
      - Session is soft-deleted.

    Trigger: ``USER_INVOKED_ART17`` — PII strip applies, billing forensics
    are de-attributed.
    """
    if not confirm:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="confirm=true is required for irreversible purge",
        )

    # Ownership check.
    row = (
        await db.execute(
            text("SELECT user_id, is_deleted FROM sessions WHERE id = :sid"),
            {"sid": str(session_id)},
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="session not found")
    owner_id = row[0] if isinstance(row[0], uuid.UUID) else uuid.UUID(str(row[0]))
    if owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="caller does not own this session",
        )
    if not bool(row[1]):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="session must be soft-deleted before purge_now",
        )

    # I8: refuse if user is mid-purge.
    try:
        await check_user_not_purging(user_id=current_user.id)
    except PurgeBlockedError as exc:
        raise HTTPException(status_code=status.HTTP_423_LOCKED, detail=str(exc)) from exc

    # Drive the pipeline.
    async with get_db_session_local() as drive_db:
        result = await purge_one_session(
            session_id=session_id,
            trigger=PurgeTrigger.USER_INVOKED_ART17,
            db=drive_db,
        )

    # Map dead-lettered → 502 Bad Gateway so the caller can retry.
    if result.outcome == PurgeOutcome.DEAD_LETTERED:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                f"provider cleanup exhausted retries; "
                f"{result.dead_letter_count} resources dead-lettered. "
                f"Operator action required."
            ),
        )
    if result.outcome == PurgeOutcome.DEFERRED_TRANSIENT:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="transient provider error; retry after next sweep",
        )

    return PurgeNowResponse(
        session_id=result.session_id,
        outcome=result.outcome.value,
        attempts_used=result.attempts_used,
        elapsed_seconds=result.elapsed_seconds,
        dead_letter_count=result.dead_letter_count,
        note=result.note,
    )


# ---- Admin endpoints -------------------------------------------------------


@admin_router.post(
    "/users/{user_id}/purge",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Admin: drive a full user-account purge.",
)
async def admin_purge_user(
    user_id: Annotated[uuid.UUID, Path()],
    body: Annotated[AdminUserPurgeBody, Body()],
    current_user: CurrentUser,
) -> dict[str, str]:
    """Admin-only. Drives every owned session through the purge pipeline,
    then deletes the user row.

    For ``reason=GDPR_ART17`` the request body MUST include a SARRequest
    (lawyer memo §5).

    NOTE: the call blocks until the pipeline finishes or the
    ``user_purge_overall_timeout_seconds`` budget elapses. Operator UIs
    should display a progress spinner.
    """
    _require_admin(current_user)
    if body.sar_request is not None and body.sar_request.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="sar_request.user_id mismatch with path parameter",
        )

    try:
        await purge_user_account(
            user_id=user_id,
            reason=body.reason,
            sar_request=body.sar_request,
        )
    except UserPurgeBlockedError as exc:
        raise HTTPException(status_code=status.HTTP_423_LOCKED, detail=str(exc)) from exc
    except UserPurgeRetryableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    except UserPurgeFailedError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"failures": [{"session_id": str(s), "error": e} for s, e in exc.failures]},
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return {"status": "purged", "user_id": str(user_id)}


@admin_router.post(
    "/users/{user_id}/unblock-purge",
    response_model=UnblockPurgeResponse,
    summary="Admin: clear a stuck users.is_purging flag (operator escape hatch).",
)
async def admin_unblock_purge(
    user_id: Annotated[uuid.UUID, Path()],
    current_user: CurrentUser,
) -> UnblockPurgeResponse:
    """Reset ``users.is_purging=false`` after a backend crash mid-purge.

    Use only after verifying:
      - No purge worker is still running for this user.
      - Either the purge has completed or the operator has decided to
        abandon the attempt.

    Does NOT undo any work already performed by phase (b) / phase (c).
    """
    _require_admin(current_user)
    async with get_db_session_local() as db:
        row = (
            await db.execute(
                text(
                    "UPDATE users SET is_purging = false "
                    "WHERE id = :uid AND is_purging = true "
                    "RETURNING id"
                ),
                {"uid": str(user_id)},
            )
        ).first()
        await db.commit()
    if row is None:
        return UnblockPurgeResponse(
            user_id=user_id,
            was_purging=False,
            message="user not found or already not purging — no-op",
        )
    logger.warning(
        "admin_unblock_purge: user={} cleared by admin={}",
        user_id,
        current_user.id,
    )
    return UnblockPurgeResponse(
        user_id=user_id,
        was_purging=True,
        message="is_purging flag cleared",
    )


@admin_router.post(
    "/sar",
    response_model=SARIntakeResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Admin: register a verified Subject Access Request (SAR).",
)
async def admin_intake_sar(
    body: Annotated[SARIntakeBody, Body()],
    current_user: CurrentUser,
) -> SARIntakeResponse:
    """Persist a verified SAR record and flag every soft-deleted session
    of the data subject for fast-track purge.

    The flagged sessions are still claimed by the regular cleanup loop;
    operator must subsequently invoke ``/admin/users/{id}/purge`` with
    ``reason=GDPR_ART17`` to drive the actual erasure (decoupled to keep
    intake responsive — Adversarial v3.9 #7).
    """
    _require_admin(current_user)
    try:
        flagged = await intake_sar(user_id=body.sar_request.user_id, sar_request=body.sar_request)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return SARIntakeResponse(
        user_id=body.sar_request.user_id,
        flagged_session_count=flagged,
        message=(
            "SAR recorded; sessions flagged sar_priority=true. "
            "Invoke /admin/users/{id}/purge to drive erasure."
        ),
    )


__all__ = ["router", "admin_router"]
