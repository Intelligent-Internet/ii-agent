"""The single arbitration point for session purge.

`purge_one_session` is the ONLY function that orchestrates phase (a)→(b)→(c).
Every entry point — cleanup loop, purge_now, user-account purge — calls
this function. Direct invocation of `claim`, `providers`, or `commit` from
callers is a code-review violation.

This collapses what was three separate call paths in v3.7 into a single
entry, eliminating the §16 step 3 race and the purge_now/user-purge mutex
gap (Adversarial #6, #7).
"""

from __future__ import annotations

import time
import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.core.db.base import get_db_session_local
from ii_agent.core.logger import logger

from .claim import claim_one_session, release_claim
from .commit import commit_purge
from .exceptions import (
    ExhaustedRetriesError,
    PurgeBlockedError,
    TransientProviderError,
)
from .providers import run_provider_cleanup
from .types import PurgeOutcome, PurgeResult, PurgeTrigger, SARRequest


# Read post-claim state needed by phases (b) and (c).
_READ_CLAIMED_SQL = text("SELECT user_id, purge_attempts FROM sessions WHERE id = :session_id")

# I19 precheck: did a prior worker already write the canonical purge audit?
# Single canonical event_type kept in sync with ``commit._AUDIT_EVENT_TYPE``.
_ALREADY_PURGED_SQL = text(
    "SELECT 1 FROM application_events "
    "WHERE session_id = :session_id AND event_type = 'session.purge_committed' "
    "LIMIT 1"
)


async def purge_one_session(
    *,
    session_id: uuid.UUID | None,
    trigger: PurgeTrigger,
    db: AsyncSession,
    sar_request: SARRequest | None = None,
) -> PurgeResult:
    """Drive one session through phase (a)→(b)→(c).

    Args:
        session_id: If given, attempt to claim this specific session.
            If ``None``, claim picks any eligible session.
        trigger: Why the purge is happening. Drives the strip policy.
        sar_request: REQUIRED if trigger=SAR_PRIORITY (I13 precondition).
        db: Database session for phase (a) and phase (c). Phase (b) opens
            its OWN sessions and must not run while ``db`` is in a tx.

    Returns:
        ``PurgeResult`` describing the outcome. Callers MUST switch on
        ``result.outcome`` and not rely on exceptions for control flow.

    Invariants preserved: every invariant in `invariants.py`.

    Concurrency:
        Safe to call concurrently. Phase (a)'s ``FOR UPDATE SKIP LOCKED``
        ensures only one caller proceeds for a given session_id. The
        provided ``db`` MUST NOT be in an open transaction when this
        function is called.
    """
    started = time.monotonic()

    # ---- I19 precheck (specific-id only) ----
    # If caller targeted a specific session and a prior worker already wrote
    # the canonical purge audit row, return ALREADY_PURGED immediately and
    # skip phases (a)–(c). For session_id=None (drain mode), the claim CTE's
    # filter on the still-existing sessions table provides the equivalent
    # guarantee — a successfully-purged row no longer exists to be claimed.
    if session_id is not None:
        already = (await db.execute(_ALREADY_PURGED_SQL, {"session_id": str(session_id)})).first()
        await db.commit()
        if already is not None:
            return PurgeResult(
                session_id=session_id,
                outcome=PurgeOutcome.ALREADY_PURGED,
                trigger=trigger,
                attempts_used=0,
                elapsed_seconds=time.monotonic() - started,
                note="I19: prior session.purge_committed audit row found",
            )

    # ---- Phase (a) — atomic claim, short tx, then commit. ----
    claimed_id = await claim_one_session(db, session_id=session_id)
    await db.commit()

    if claimed_id is None:
        # Nothing to claim — empty queue, contended, or specific id ineligible.
        return PurgeResult(
            session_id=session_id or uuid.UUID(int=0),
            outcome=PurgeOutcome.SKIPPED_NOT_ELIGIBLE
            if session_id is None
            else PurgeOutcome.SKIPPED_RACED,
            trigger=trigger,
            attempts_used=0,
            elapsed_seconds=time.monotonic() - started,
            note="claim returned no row (queue empty, contended, or ineligible)",
        )

    # Read post-claim user_id + attempts (own short tx).
    row = (await db.execute(_READ_CLAIMED_SQL, {"session_id": str(claimed_id)})).one_or_none()
    await db.commit()
    if row is None:
        # Race: claimed but row gone. Treat as already-purged.
        return PurgeResult(
            session_id=claimed_id,
            outcome=PurgeOutcome.ALREADY_PURGED,
            trigger=trigger,
            attempts_used=0,
            elapsed_seconds=time.monotonic() - started,
            note="row vanished between claim and read — concurrent purge succeeded",
        )
    user_id = row[0] if isinstance(row[0], uuid.UUID) else uuid.UUID(str(row[0]))
    current_attempts = int(row[1])

    # ---- Phase (b) — provider cleanup. NO open tx held. ----
    dead_letter_count = 0
    try:
        dead_letter_count = await run_provider_cleanup(
            session_id=claimed_id,
            user_id=user_id,
            current_attempts=current_attempts,
        )
    except TransientProviderError as exc:
        # Release claim; let next sweep retry.
        try:
            await release_claim(db, claimed_id)
            await db.commit()
        except Exception:  # pragma: no cover — defensive
            logger.exception("release_claim failed after TransientProviderError")
        return PurgeResult(
            session_id=claimed_id,
            outcome=PurgeOutcome.DEFERRED_TRANSIENT,
            trigger=trigger,
            attempts_used=current_attempts,
            elapsed_seconds=time.monotonic() - started,
            note=f"phase (b) transient: {exc}",
        )
    except ExhaustedRetriesError as exc:
        # Dead-letter rows already persisted by run_provider_cleanup.
        # Leave claim set so the row is observable / triageable.
        # The session row is NOT deleted.
        return PurgeResult(
            session_id=claimed_id,
            outcome=PurgeOutcome.DEAD_LETTERED,
            trigger=trigger,
            attempts_used=current_attempts,
            elapsed_seconds=time.monotonic() - started,
            dead_letter_count=exc.dead_letter_count,
            note=f"phase (b) dead-lettered: {exc}",
        )

    # ---- Phase (c) — strip + audit + delete in ONE tx. ----
    # We use a fresh session per phase for clear tx boundaries.
    try:
        async with get_db_session_local() as commit_db:
            outcome = await commit_purge(
                session_id=claimed_id,
                user_id=user_id,
                trigger=trigger,
                db=commit_db,
                sar_request=sar_request,
            )
            await commit_db.commit()
    except PurgeBlockedError as exc:
        # I12 violation — SAR raced with restore. Do not retry.
        logger.error(
            "purge_one_session BLOCKED for {} (I12 violation): {}",
            claimed_id,
            exc,
        )
        return PurgeResult(
            session_id=claimed_id,
            outcome=PurgeOutcome.SKIPPED_RESTORED,
            trigger=trigger,
            attempts_used=current_attempts,
            elapsed_seconds=time.monotonic() - started,
            note=f"I12 violation: {exc}",
        )
    except AssertionError as exc:
        # assert_strip_complete fired. Tx already rolled back. Treat as
        # transient — operator must investigate, but the session is safe.
        logger.error(
            "purge_one_session phase (c) assertion failed for {}: {}",
            claimed_id,
            exc,
        )
        try:
            await release_claim(db, claimed_id)
            await db.commit()
        except Exception:  # pragma: no cover — defensive
            logger.exception("release_claim failed after assertion failure")
        return PurgeResult(
            session_id=claimed_id,
            outcome=PurgeOutcome.DEFERRED_TRANSIENT,
            trigger=trigger,
            attempts_used=current_attempts,
            elapsed_seconds=time.monotonic() - started,
            note=f"assert_strip_complete: {exc}",
        )

    return PurgeResult(
        session_id=claimed_id,
        outcome=outcome,
        trigger=trigger,
        attempts_used=current_attempts,
        elapsed_seconds=time.monotonic() - started,
        dead_letter_count=dead_letter_count,
        sar_request=sar_request if trigger == PurgeTrigger.SAR_PRIORITY else None,
    )
