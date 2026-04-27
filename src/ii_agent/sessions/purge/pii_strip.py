"""Art. 17 PII strip — allowlist filter applied SQL-side.

Operational grace (§4.1, trigger=GRACE_EXPIRED) does NOT call this module
— billing forensics preserved. Only Art. 17 erasure paths (§4.7, §16,
SAR_PRIORITY) strip.

Adversarial #14: allowlist is config-driven, not hardcoded, so ops can
override without a code deploy. Default in `core/config/sessions.py`.

Defence-in-depth (Adversarial v3.9 #6): every strip is followed by an
``assert_strip_complete`` re-read in the SAME transaction that aborts the
purge if any forbidden key survived. See `commit_purge`.
"""

from __future__ import annotations

import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


# Default allowlist; overridable via Settings.
# Adversarial #14: every key here is reviewed for PII risk on schema review.
DEFAULT_BILLING_SAFE_KEYS: frozenset[str] = frozenset(
    {
        "cost_usd",
        "credits",
        "token_count",
        "model",
        "tool_name",
        "duration_ms",
        "billing_backend",
        "event_type",
        "http_status",
    }
)


# ---- application_events.content strip (per-session OR per-user) ----
#
# We use ``jsonb_object_agg(k, v) FILTER (WHERE k = ANY(:allowlist))`` to
# rebuild content with only allowlisted keys. ``jsonb_each`` unrolls the
# object; the FILTER clause discards everything else.
_STRIP_EVENTS_BY_SESSION_SQL = text(
    """
    UPDATE application_events
       SET content = COALESCE(
               (
                   SELECT jsonb_object_agg(k, v)
                     FROM jsonb_each(application_events.content) AS kv(k, v)
                    WHERE k = ANY(CAST(:allowlist AS text[]))
               ),
               '{}'::jsonb
           ),
           user_id = NULL
     WHERE session_id = :session_id
    """
)

_STRIP_EVENTS_BY_USER_SQL = text(
    """
    UPDATE application_events
       SET content = COALESCE(
               (
                   SELECT jsonb_object_agg(k, v)
                     FROM jsonb_each(application_events.content) AS kv(k, v)
                    WHERE k = ANY(CAST(:allowlist AS text[]))
               ),
               '{}'::jsonb
           ),
           user_id = NULL
     WHERE user_id = :user_id
    """
)


# ---- credit_transactions.data strip ----
# Per-session: filter the ``data`` column on rows matching session_id.
# Per-user: also NULL the user_id (whole-account erasure).
_STRIP_CREDITS_BY_SESSION_SQL = text(
    """
    UPDATE credit_transactions
       SET data = COALESCE(
               (
                   SELECT jsonb_object_agg(k, v)
                     FROM jsonb_each(credit_transactions.data) AS kv(k, v)
                    WHERE k = ANY(CAST(:allowlist AS text[]))
               ),
               '{}'::jsonb
           )
     WHERE session_id = :session_id
    """
)

_STRIP_CREDITS_BY_USER_SQL = text(
    """
    UPDATE credit_transactions
       SET data = COALESCE(
               (
                   SELECT jsonb_object_agg(k, v)
                     FROM jsonb_each(credit_transactions.data) AS kv(k, v)
                    WHERE k = ANY(CAST(:allowlist AS text[]))
               ),
               '{}'::jsonb
           ),
           user_id = NULL
     WHERE user_id = :user_id
    """
)


async def strip_user_pii_art17(
    *,
    db: AsyncSession,
    user_id: uuid.UUID | None = None,
    session_id: uuid.UUID | None = None,
    allowlist: frozenset[str] = DEFAULT_BILLING_SAFE_KEYS,
) -> int:
    """Apply the Art. 17 strip pass.

    Exactly one of ``user_id`` or ``session_id`` MUST be provided:

      - ``session_id``: per-session strip (§4.7) — covers rows for this session.
      - ``user_id``: whole-user strip (§16) — covers rows whose session was
        purged in earlier attempts plus rows still attached to existing sessions.

    Behaviour:
      - ``application_events.content`` filtered to allowlist via SQL-side
        ``jsonb_object_agg(k, v) FILTER (WHERE k = ANY(:allowlist))``.
      - ``application_events.user_id`` set to NULL.
      - ``credit_transactions.data`` filtered identically.
      - ``credit_transactions.user_id`` set to NULL only when called with
        ``user_id`` (whole-user). Per-session strip leaves credit_transactions
        ``user_id`` alone — they're user-scoped, not session-scoped.

    Invariants preserved: I4, I11.

    Returns:
        Total rows mutated across both tables (for metrics).
    """
    if (user_id is None) == (session_id is None):
        raise ValueError("strip_user_pii_art17: exactly one of user_id or session_id required")

    allowlist_param = list(allowlist)
    total = 0
    if session_id is not None:
        r1 = await db.execute(
            _STRIP_EVENTS_BY_SESSION_SQL,
            {"session_id": str(session_id), "allowlist": allowlist_param},
        )
        total += int(getattr(r1, "rowcount", 0) or 0)
        r2 = await db.execute(
            _STRIP_CREDITS_BY_SESSION_SQL,
            {"session_id": str(session_id), "allowlist": allowlist_param},
        )
        total += int(getattr(r2, "rowcount", 0) or 0)
    else:
        assert user_id is not None  # narrow for mypy
        r1 = await db.execute(
            _STRIP_EVENTS_BY_USER_SQL,
            {"user_id": str(user_id), "allowlist": allowlist_param},
        )
        total += int(getattr(r1, "rowcount", 0) or 0)
        r2 = await db.execute(
            _STRIP_CREDITS_BY_USER_SQL,
            {"user_id": str(user_id), "allowlist": allowlist_param},
        )
        total += int(getattr(r2, "rowcount", 0) or 0)
    return total


# ---- Defence-in-depth: post-strip assertion ----
#
# These queries return any (id, key) pair where the surviving JSON content
# contains a key NOT in the allowlist, OR any row with non-NULL user_id.
# If either query returns rows, the surrounding tx MUST roll back.
_ASSERT_EVENTS_BY_SESSION_SQL = text(
    """
    SELECT e.id, kv.k
      FROM application_events e,
           LATERAL jsonb_object_keys(e.content) AS kv(k)
     WHERE e.session_id = :session_id
       AND kv.k <> ALL(CAST(:allowlist AS text[]))
     LIMIT 50
    """
)
_ASSERT_EVENTS_USERID_BY_SESSION_SQL = text(
    """
    SELECT id FROM application_events
     WHERE session_id = :session_id AND user_id IS NOT NULL
     LIMIT 50
    """
)
_ASSERT_EVENTS_BY_USER_SQL = text(
    """
    SELECT e.id, kv.k
      FROM application_events e,
           LATERAL jsonb_object_keys(e.content) AS kv(k)
     WHERE e.user_id = :user_id
       AND kv.k <> ALL(CAST(:allowlist AS text[]))
     LIMIT 50
    """
)
_ASSERT_CREDITS_BY_SESSION_SQL = text(
    """
    SELECT t.id, kv.k
      FROM credit_transactions t,
           LATERAL jsonb_object_keys(t.data) AS kv(k)
     WHERE t.session_id = :session_id
       AND kv.k <> ALL(CAST(:allowlist AS text[]))
     LIMIT 50
    """
)
_ASSERT_CREDITS_BY_USER_SQL = text(
    """
    SELECT t.id, kv.k
      FROM credit_transactions t,
           LATERAL jsonb_object_keys(t.data) AS kv(k)
     WHERE t.user_id = :user_id
       AND kv.k <> ALL(CAST(:allowlist AS text[]))
     LIMIT 50
    """
)
_ASSERT_CREDITS_USERID_BY_USER_SQL = text(
    """
    SELECT id FROM credit_transactions
     WHERE user_id = :user_id
     LIMIT 50
    """
)


async def assert_strip_complete(
    *,
    db: AsyncSession,
    session_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    allowlist: frozenset[str] = DEFAULT_BILLING_SAFE_KEYS,
) -> None:
    """Post-strip assertion (Adversarial v3.9 #6).

    Re-read every row touched by ``strip_user_pii_art17`` in the SAME tx and
    fail loudly if any surviving JSON key is NOT in ``allowlist`` or any
    ``user_id`` column is non-NULL.

    Defends against:
      - Allowlist drift between the Python constant and the runtime SQL filter
        (e.g. SQL uses ``= ANY(:allowlist)`` against a stale parameter).
      - Future schema additions that introduce new JSONB columns the strip
        function forgot to touch.
      - Concurrent INSERT after the strip but before audit row + DELETE
        (caught because it runs inside ``commit_purge``'s single tx).

    Exactly one of ``session_id`` or ``user_id`` MUST be provided (matches
    the corresponding ``strip_user_pii_art17`` call).

    Raises:
        AssertionError: a forbidden key survived, or a ``user_id`` was not
            nulled. Message includes the offending row ids and keys for
            forensic diagnosis. The surrounding transaction MUST roll back.

    Invariants preserved: I4, I11 (defence-in-depth).
    """
    if (user_id is None) == (session_id is None):
        raise ValueError("assert_strip_complete: exactly one of user_id or session_id required")

    allowlist_param = list(allowlist)
    failures: list[str] = []

    if session_id is not None:
        leaked_keys = (
            await db.execute(
                _ASSERT_EVENTS_BY_SESSION_SQL,
                {"session_id": str(session_id), "allowlist": allowlist_param},
            )
        ).all()
        if leaked_keys:
            failures.append(
                f"application_events leaked keys: {[(str(r[0]), r[1]) for r in leaked_keys]}"
            )

        leaked_uids = (
            await db.execute(
                _ASSERT_EVENTS_USERID_BY_SESSION_SQL,
                {"session_id": str(session_id)},
            )
        ).all()
        if leaked_uids:
            failures.append(
                f"application_events non-NULL user_id rows: {[str(r[0]) for r in leaked_uids]}"
            )

        leaked_credit_keys = (
            await db.execute(
                _ASSERT_CREDITS_BY_SESSION_SQL,
                {"session_id": str(session_id), "allowlist": allowlist_param},
            )
        ).all()
        if leaked_credit_keys:
            failures.append(
                f"credit_transactions leaked keys: {[(str(r[0]), r[1]) for r in leaked_credit_keys]}"
            )
    else:
        assert user_id is not None  # narrow for mypy
        leaked_keys = (
            await db.execute(
                _ASSERT_EVENTS_BY_USER_SQL,
                {"user_id": str(user_id), "allowlist": allowlist_param},
            )
        ).all()
        if leaked_keys:
            failures.append(
                f"application_events leaked keys: {[(str(r[0]), r[1]) for r in leaked_keys]}"
            )

        leaked_credit_keys = (
            await db.execute(
                _ASSERT_CREDITS_BY_USER_SQL,
                {"user_id": str(user_id), "allowlist": allowlist_param},
            )
        ).all()
        if leaked_credit_keys:
            failures.append(
                f"credit_transactions leaked keys: {[(str(r[0]), r[1]) for r in leaked_credit_keys]}"
            )

        leaked_uids = (
            await db.execute(
                _ASSERT_CREDITS_USERID_BY_USER_SQL,
                {"user_id": str(user_id)},
            )
        ).all()
        if leaked_uids:
            failures.append(
                f"credit_transactions non-NULL user_id rows: {[str(r[0]) for r in leaked_uids]}"
            )

    if failures:
        raise AssertionError(
            "assert_strip_complete failed (I4/I11). Tx will roll back. Details: "
            + " | ".join(failures)
        )
