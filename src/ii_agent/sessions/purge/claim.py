"""Phase (a) — atomic claim. The single arbitration point.

ALL purge entry points (cleanup loop, purge_now, user-account purge)
MUST go through `claim_one_session` to acquire a session for processing.
This eliminates the §16-step-3 race documented in v3.7 / Adversarial #6.

Adversarial Finding #5: PostgreSQL does NOT permit FOR UPDATE in a scalar
subquery used as a WHERE expression. The CTE form below is required.

Design: docs/design-docs/session-lifecycle-and-data-custody.md §4.1.
Migration dependency: 20260427_000008_session_purge_v34.py (PR-A).
"""

from __future__ import annotations

import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.core.config.settings import get_settings


# CTE form — Adversarial #5. ``SELECT ... FOR UPDATE SKIP LOCKED`` MUST be
# inside a CTE; PostgreSQL rejects FOR UPDATE inside a scalar subquery.
_CLAIM_SQL = text(
    """
    WITH candidate AS (
        SELECT s.id
          FROM sessions s
         WHERE s.is_deleted = true
           AND s.purge_after IS NOT NULL
           AND s.purge_after <= now()
           AND s.custody != 'legal_hold'
           AND s.purge_attempts < :max_attempts
           AND (
               s.purge_started_at IS NULL
               OR s.purge_started_at < now() - make_interval(secs => :claim_timeout)
           )
           AND NOT EXISTS (
               SELECT 1 FROM agent_sandboxes ab
                WHERE ab.session_id = s.id
                  AND ab.status != 'DELETED'
           )
           AND (CAST(:specific_id AS uuid) IS NULL OR s.id = CAST(:specific_id AS uuid))
           -- Drain mode (specific_id IS NULL) MUST NOT claim sar_priority
           -- sessions: those are driven directly via purge_user_account
           -- (trigger=SAR_PRIORITY) so the audit row carries the SARRequest
           -- (I13). A grace-mode claim would record trigger=GRACE_EXPIRED
           -- and break I13. Specific-id claims (e.g. user-purge driver
           -- targeting these sessions) bypass the filter.
           -- NB: ``<param>::<type>`` PG cast syntax confuses asyncpg's
           -- bind-param rewriter (it sees ``::`` as part of the param
           -- name); always use ``CAST(<param> AS <type>)`` in this module.
           -- (Also: SQLA's ``text()`` scans comments for ``<colon>name``
           -- bind tokens, so this comment uses angle-bracket placeholders.)
           AND (CAST(:specific_id AS uuid) IS NOT NULL OR s.sar_priority IS NOT TRUE)
         ORDER BY s.purge_after
         LIMIT 1
         FOR UPDATE SKIP LOCKED
    )
    UPDATE sessions
       SET purge_started_at = now(),
           purge_attempts   = sessions.purge_attempts + 1
      FROM candidate
     WHERE sessions.id = candidate.id
 RETURNING sessions.id
    """
)


async def claim_one_session(
    db: AsyncSession,
    *,
    session_id: uuid.UUID | None = None,
) -> uuid.UUID | None:
    """Atomically claim one eligible session for purge.

    Args:
        session_id: If provided, only claim if this specific session is
            eligible (used by ``purge_now`` and user-account purge). If
            ``None``, picks the oldest eligible session by ``purge_after``.

    Returns:
        The session's UUID on successful claim. Caller MUST proceed to
        phase (b) or release the claim (``release_claim``) on early abort.
        ``None`` if no session is eligible (queue empty or all in-flight).

    Invariants preserved: I1, I6, I7 (claim-then-recheck downstream).

    Concurrency:
        Uses ``FOR UPDATE SKIP LOCKED`` inside a CTE — the only safe
        PostgreSQL pattern (Adversarial #5).

    Note: executes a single statement and does NOT commit. Caller
    (``session_purge.purge_one_session``) commits the surrounding tx.
    """
    cfg = get_settings().sessions
    result = await db.execute(
        _CLAIM_SQL,
        {
            "max_attempts": cfg.purge_max_attempts,
            "claim_timeout": cfg.purge_claim_timeout_seconds,
            "specific_id": str(session_id) if session_id is not None else None,
        },
    )
    row = result.one_or_none()
    if row is None:
        return None
    claimed_id = row[0]
    if isinstance(claimed_id, uuid.UUID):
        return claimed_id
    return uuid.UUID(str(claimed_id))


_RELEASE_SQL = text(
    """
    UPDATE sessions
       SET purge_started_at = NULL,
           purge_attempts   = GREATEST(0, sessions.purge_attempts - 1)
     WHERE id = :session_id
       AND purge_started_at IS NOT NULL
    """
)


async def release_claim(db: AsyncSession, session_id: uuid.UUID) -> None:
    """Release a held claim WITHOUT deleting the session.

    Sets ``purge_started_at = NULL`` and decrements ``purge_attempts``
    (the attempt didn't progress). Decrement clamped at 0 to defend
    against double-release.

    Invariants preserved: I1, I6.
    """
    await db.execute(_RELEASE_SQL, {"session_id": str(session_id)})


_HEARTBEAT_SQL = text(
    """
    UPDATE sessions
       SET purge_started_at = now()
     WHERE id = :session_id
       AND purge_started_at IS NOT NULL
    """
)


async def heartbeat_claim(db: AsyncSession, session_id: uuid.UUID) -> None:
    """Refresh ``purge_started_at = now()`` mid-phase-(b).

    Required for any provider-DELETE batch that may exceed
    ``purge_claim_timeout_seconds`` (default 600s). Called every
    ``heartbeat_interval_seconds`` (default 120s).

    No-op if the claim was already released (defensive).
    """
    await db.execute(_HEARTBEAT_SQL, {"session_id": str(session_id)})
