"""User-account purge (§16). Drives every owned session through `purge_one_session`.

The single most important architectural change vs v3.7: this module DOES NOT
duplicate or shortcut the per-session pipeline. It:

  1. Sets ``users.is_purging=true`` (gates new sessions per ``NotPurgingDep``).
  2. Soft-deletes every owned session and sets ``purge_after=now()``.
  3. For each session, calls ``purge_one_session(session_id=..., trigger=USER_ACCOUNT_DELETION)``
     under bounded concurrency. Each call goes through phase (a) claim — so the
     orphan-loop sweep cannot race (Adversarial #6).
  4. Checks ``purge_dead_letter`` for unresolved rows by user_id (I10).
  5. Strips PII from audit rows that survived earlier purges (Art. 17 whole-user).
  6. ``DELETE FROM users``. CASCADE/SET NULL per §3.1.

CRITICAL v3.9 (Adversarial #1 + lawyer memo §7): origin/main has
Session.user_id ON DELETE CASCADE. Step 6 must run ONLY after step 3 has
produced an audit row for every session, AND step 4 has confirmed no
unresolved dead-letters. Naively deleting users first would silently
CASCADE-drop sessions with NO audit trail — a GDPR Art. 5(2) accountability
violation. Invariant I14 enforces this ordering at runtime.

Adversarial findings addressed:
  #1 (FK CASCADE silent loss) — see step-6 precondition + I14
  #6 (claim race) — by routing through phase (a)
  #7 (purge_now mutex)  — see ``check_user_not_purging`` precondition
  #16 step 5/6 ordering — strip and DELETE share a tx (commit.py contract)
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.core.config.settings import get_settings
from ii_agent.core.db.base import get_db_session_local
from ii_agent.core.logger import logger

from .exceptions import (
    PurgeBlockedError,
    UserPurgeBlockedError,
    UserPurgeFailedError,
    UserPurgeRetryableError,
)
from .pii_strip import assert_strip_complete, strip_user_pii_art17
from .session_purge import purge_one_session
from .types import (
    PurgeOutcome,
    PurgeResult,
    PurgeTrigger,
    SARRequest,
    UserPurgeReason,
)


# ---- SQL constants ---------------------------------------------------------

_LOCK_USER_SQL = text(
    "UPDATE users SET is_purging = true WHERE id = :uid AND is_purging = false RETURNING id"
)

_CHECK_IS_PURGING_SQL = text("SELECT is_purging FROM users WHERE id = :uid")

# Bulk soft-delete + purge_after=now() for every owned session that's
# eligible. Legal-hold sessions are NEVER auto-purged (I5/I18).
_BULK_SOFT_DELETE_SQL = text(
    """
    UPDATE sessions
       SET is_deleted = true,
           purge_after = COALESCE(purge_after, now())
     WHERE user_id = :uid
       AND custody != 'legal_hold'
    """
)

_LIST_OWNED_DELETED_SQL = text(
    """
    SELECT id FROM sessions
     WHERE user_id = :uid
       AND is_deleted = true
       AND custody != 'legal_hold'
    """
)

_UNRESOLVED_DEAD_LETTERS_SQL = text(
    """
    SELECT count(*) FROM purge_dead_letter
     WHERE user_id = :uid
       AND resolved_at IS NULL
    """
)

# Pre-condition for hard DELETE: every owned session must already be gone
# (either purged → deleted, or dead-lettered → deferred). I14 guard.
_REMAINING_SESSIONS_SQL = text("SELECT count(*) FROM sessions WHERE user_id = :uid")

_DELETE_USER_SQL = text("DELETE FROM users WHERE id = :uid")

# Insert sar_intake row + flip sar_priority on owned deleted sessions.
_INSERT_SAR_INTAKE_SQL = text(
    """
    INSERT INTO sar_intake (
        user_id, received_at, verified_at,
        verification_method, requesting_authority, scope,
        session_count_flagged
    )
    VALUES (
        :uid, CAST(:received_at AS timestamptz), now(),
        :verification_method, :requesting_authority, :scope,
        0
    )
    """
)

_FLAG_SAR_PRIORITY_SQL = text(
    """
    UPDATE sessions
       SET sar_priority = true
     WHERE user_id = :uid
       AND is_deleted = true
       AND custody != 'legal_hold'
    RETURNING id
    """
)

_UPDATE_SAR_INTAKE_COUNT_SQL = text(
    """
    UPDATE sar_intake
       SET session_count_flagged = :n
     WHERE user_id = :uid
       AND received_at = CAST(:received_at AS timestamptz)
    """
)

_ACTIVE_SAR_SQL = text(
    """
    SELECT 1 FROM sar_intake
     WHERE user_id = :uid
       AND verified_at IS NOT NULL
       AND closed_at IS NULL
     LIMIT 1
    """
)


# ---- Public API ------------------------------------------------------------


async def is_user_under_active_sar(db: AsyncSession, user_id: uuid.UUID) -> bool:
    """Return True iff the user has at least one verified, unclosed SAR.

    Centralised here so restore endpoint (I16) and grace-sweep (I12) share
    the exact same predicate.
    """
    row = (await db.execute(_ACTIVE_SAR_SQL, {"uid": str(user_id)})).first()
    return row is not None


async def check_user_not_purging(*, user_id: uuid.UUID) -> None:
    """Precondition for per-session purge_now (Adversarial #7).

    Raises ``PurgeBlockedError`` if the owning user has ``is_purging=true``.
    The user-account purge is already driving every owned session through
    the pipeline; concurrent per-session purge_now would double-claim.

    Invariants preserved: I3, I8.
    """
    async with get_db_session_local() as db:
        row = (await db.execute(_CHECK_IS_PURGING_SQL, {"uid": str(user_id)})).first()
        if row is None:
            raise PurgeBlockedError(f"user {user_id} not found")
        if bool(row[0]):
            raise PurgeBlockedError(
                f"user {user_id} has is_purging=true; per-session purge "
                f"would race the in-flight user-account purge (I8)."
            )


async def purge_user_account(
    *,
    user_id: uuid.UUID,
    reason: UserPurgeReason,
    sar_request: SARRequest | None = None,
) -> None:
    """Drive a user-account deletion through the per-session pipeline first.

    Args:
        sar_request: REQUIRED if reason=GDPR_ART17. Captures lawyer-memo §5
            audit fields. ValueError if reason=GDPR_ART17 and sar_request is None.

    Raises:
        UserPurgeFailedError: at least one session raised a non-transient error.
        UserPurgeRetryableError: at least one session hit ``TransientProviderError``;
            caller may retry after the next cleanup cycle.
        UserPurgeBlockedError: dead-letter rows remain; manual operator action required.

    Invariants preserved: I1, I3, I8, I10, I11, I13, I14.
    """
    if reason == UserPurgeReason.GDPR_ART17 and sar_request is None:
        raise ValueError(
            "I13 violation: reason=GDPR_ART17 requires sar_request for audit. "
            "See lawyer memo §5 (sar_receipt_timestamp, verification_method)."
        )

    cfg = get_settings().sessions
    overall_timeout = float(cfg.user_purge_overall_timeout_seconds)

    try:
        await asyncio.wait_for(
            _drive_user_purge(user_id=user_id, reason=reason, sar_request=sar_request),
            timeout=overall_timeout,
        )
    except asyncio.TimeoutError as exc:
        raise UserPurgeRetryableError(
            f"user purge for {user_id} exceeded {overall_timeout}s budget; retry after sweep"
        ) from exc


async def _drive_user_purge(
    *,
    user_id: uuid.UUID,
    reason: UserPurgeReason,
    sar_request: SARRequest | None,
) -> None:
    """Inner driver — separated so ``asyncio.wait_for`` can wrap with a budget."""

    cfg = get_settings().sessions

    # ---- Step 1: lock the user (atomic flip). ----
    async with get_db_session_local() as db:
        locked = (await db.execute(_LOCK_USER_SQL, {"uid": str(user_id)})).first()
        await db.commit()
        if locked is None:
            # Either the user doesn't exist OR is_purging is already true.
            # Distinguish: re-read.
            row = (await db.execute(_CHECK_IS_PURGING_SQL, {"uid": str(user_id)})).first()
            if row is None:
                raise UserPurgeFailedError(failures=[(user_id, "user not found")])
            if bool(row[0]):
                # Idempotent re-entry — proceed; another worker may have crashed.
                logger.warning(
                    "purge_user_account re-entered for user {} (is_purging "
                    "was already true). Continuing.",
                    user_id,
                )
            else:
                # Defensive: UPDATE ... RETURNING returned no row but
                # is_purging is false. Should not happen.
                raise UserPurgeFailedError(failures=[(user_id, "lock UPDATE returned no row")])

    # ---- Step 2: bulk soft-delete + purge_after=now() for owned sessions. ----
    async with get_db_session_local() as db:
        await db.execute(_BULK_SOFT_DELETE_SQL, {"uid": str(user_id)})
        await db.commit()

        rows = (await db.execute(_LIST_OWNED_DELETED_SQL, {"uid": str(user_id)})).all()
        session_ids: list[uuid.UUID] = [
            r[0] if isinstance(r[0], uuid.UUID) else uuid.UUID(str(r[0])) for r in rows
        ]

    logger.info(
        "purge_user_account: user={} sessions_to_purge={} reason={}",
        user_id,
        len(session_ids),
        reason.value,
    )

    # ---- Step 3: drive each session through purge_one_session. ----
    trigger = (
        PurgeTrigger.SAR_PRIORITY if sar_request is not None else PurgeTrigger.USER_ACCOUNT_DELETION
    )
    semaphore = asyncio.Semaphore(int(cfg.user_purge_parallelism))

    async def _drive_one(
        sid: uuid.UUID,
    ) -> tuple[uuid.UUID, PurgeResult | BaseException]:
        async with semaphore:
            try:
                async with get_db_session_local() as db:
                    res = await purge_one_session(
                        session_id=sid,
                        trigger=trigger,
                        db=db,
                        sar_request=sar_request,
                    )
                return sid, res
            except BaseException as exc:  # pragma: no cover — defensive
                return sid, exc

    results: list[tuple[uuid.UUID, PurgeResult | BaseException]] = await asyncio.gather(
        *(_drive_one(sid) for sid in session_ids), return_exceptions=False
    )

    # Classify results.
    failures: list[tuple[uuid.UUID, str]] = []
    transient: list[uuid.UUID] = []
    for sid, res in results:
        if isinstance(res, BaseException):
            failures.append((sid, f"{type(res).__name__}: {res}"))
            continue
        outcome = res.outcome
        if outcome in (PurgeOutcome.PURGED, PurgeOutcome.ALREADY_PURGED):
            continue
        if outcome == PurgeOutcome.DEFERRED_TRANSIENT:
            transient.append(sid)
            continue
        if outcome == PurgeOutcome.DEAD_LETTERED:
            failures.append((sid, f"dead-lettered ({res.dead_letter_count} resources)"))
            continue
        if outcome == PurgeOutcome.SKIPPED_RESTORED:
            failures.append((sid, "session restored mid-purge — I12 candidate"))
            continue
        # SKIPPED_NOT_ELIGIBLE / SKIPPED_RACED: another worker took it.
        # Treat as transient retry.
        transient.append(sid)

    if failures:
        raise UserPurgeFailedError(failures=failures)
    if transient:
        raise UserPurgeRetryableError(
            f"user {user_id}: {len(transient)} sessions deferred-transient; "
            f"retry after next cleanup sweep"
        )

    # ---- Step 4: dead-letter check (I10). ----
    async with get_db_session_local() as db:
        row = (await db.execute(_UNRESOLVED_DEAD_LETTERS_SQL, {"uid": str(user_id)})).first()
        unresolved = int(row[0]) if row is not None else 0
    if unresolved > 0:
        raise UserPurgeBlockedError(
            f"user {user_id}: {unresolved} unresolved purge_dead_letter rows; "
            f"operator must clean up upstream provider artefacts before "
            f"the user row can be deleted (I10)."
        )

    # ---- Step 5 & 6: strip whole-user PII + I14 guard + DELETE user. ----
    is_art17 = reason == UserPurgeReason.GDPR_ART17 or sar_request is not None
    async with get_db_session_local() as db:
        if is_art17:
            await strip_user_pii_art17(db=db, user_id=user_id)
            await assert_strip_complete(db=db, user_id=user_id)

        # I14 precondition: no sessions remain (cascade-or-orphan check).
        row2 = (await db.execute(_REMAINING_SESSIONS_SQL, {"uid": str(user_id)})).first()
        remaining = int(row2[0]) if row2 is not None else 0
        if remaining > 0:
            raise UserPurgeFailedError(
                failures=[
                    (
                        user_id,
                        f"I14 violation: {remaining} sessions still exist for user "
                        f"after step 3; refusing to DELETE FROM users (would CASCADE "
                        f"with no audit trail).",
                    )
                ]
            )
        await db.execute(_DELETE_USER_SQL, {"uid": str(user_id)})
        await db.commit()

    logger.info(
        "purge_user_account COMPLETE: user={} sessions_purged={} dead_lettered=0",
        user_id,
        len(session_ids),
    )


async def intake_sar(
    *,
    user_id: uuid.UUID,
    sar_request: SARRequest,
) -> int:
    """Lawyer memo §1/§7: SAR pre-empts grace.

    Receives a verified Subject Access Request and routes ALL of the user's
    is_deleted sessions onto the fast-track queue, bypassing purge_after.

    Implementation contract:
      1. Insert sar_intake row (user_id, sar_request fields, verified_at=now())
         AND COMMIT IT SYNCHRONOUSLY before this function returns
         (Adversarial v3.9 #7). The HTTP 202 to the data subject MUST NOT
         precede a durable audit record — GDPR Art. 5(2) accountability
         requires evidence that the SAR was received even if the backend
         crashes mid-fanout. The fast-track enqueue (step 3) may be async;
         the intake row may NOT.
      2. UPDATE sessions SET sar_priority=true WHERE user_id=:uid AND is_deleted=true.
      3. Caller (HTTP handler / admin tool) is expected to subsequently invoke
         ``purge_user_account(reason=GDPR_ART17, sar_request=...)`` to drive
         the actual fast-track erasure. Decoupling intake from drive keeps
         the 202 response fast.

    Target: 24 hours from this call to all sessions purged. Absolute max:
    5 business days. Anything beyond = GDPR Art. 17(1) violation.

    Returns the count of sessions flagged for fast-track erasure.

    Invariants preserved: I12, I13.

    Raises:
        ValueError if sar_request.user_id != user_id.
    """
    if sar_request.user_id != user_id:
        raise ValueError(
            f"SAR identity mismatch: sar_request.user_id={sar_request.user_id} "
            f"!= user_id={user_id}. Verification gap — lawyer memo §5."
        )

    # Step 1: durable intake row, committed synchronously.
    intake_params: dict[str, Any] = {
        "uid": str(user_id),
        "received_at": sar_request.sar_receipt_timestamp,
        "verification_method": sar_request.verification_method,
        "requesting_authority": sar_request.requesting_authority,
        "scope": sar_request.scope,
    }
    async with get_db_session_local() as db:
        await db.execute(_INSERT_SAR_INTAKE_SQL, intake_params)
        await db.commit()

    # Step 2: flag sessions sar_priority=true. Separate tx — if step 2 fails,
    # the intake row remains and operator can retry; the SAR is still on
    # record (Adversarial v3.9 #7 — never lose the receipt).
    async with get_db_session_local() as db:
        rows = (await db.execute(_FLAG_SAR_PRIORITY_SQL, {"uid": str(user_id)})).all()
        flagged = len(rows)
        await db.execute(
            _UPDATE_SAR_INTAKE_COUNT_SQL,
            {
                "uid": str(user_id),
                "received_at": sar_request.sar_receipt_timestamp,
                "n": flagged,
            },
        )
        await db.commit()

    logger.info(
        "intake_sar: user={} flagged_sessions={} verification={}",
        user_id,
        flagged,
        sar_request.verification_method,
    )
    return flagged
