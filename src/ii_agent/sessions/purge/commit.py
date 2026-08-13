"""Phase (c) — commit. Strip-then-delete in a single transaction.

CRITICAL ordering inside the tx (resolves Adversarial #2, #4, #10, §4.7-step-9):

    1. Re-check ``is_deleted = true`` (Adversarial #2 — restore-vs-purge TOCTOU).
       If false, abort the tx and return PurgeOutcome.SKIPPED_RESTORED.
       EXCEPTION (I12): if trigger=SAR_PRIORITY and is_deleted became false,
       this is a violation — a restore happened concurrently with a verified
       SAR. Raise PurgeBlockedError.
    2. Run Art. 17 strip pass (USER_INVOKED_ART17, USER_ACCOUNT_DELETION,
       SAR_PRIORITY). Sets user_id=NULL, allowlist content.
    2a. Call ``pii_strip.assert_strip_complete`` — re-reads every stripped row
       and fails the tx if any forbidden key survived (Adversarial v3.9 #6).
    3. INSERT the audit event row. Art. 17 triggers: ``user_id=NULL`` from the
       start (Adversarial §4.7-step-9). SAR_PRIORITY: include lawyer-memo §5
       four fields. I13 enforced.
    4. DELETE the session row. CASCADE/SET NULL fires per §3.1.

All four steps in ONE transaction. Caller is responsible for begin/commit.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .exceptions import PurgeBlockedError
from .pii_strip import assert_strip_complete, strip_user_pii_art17
from .types import PURGE_COMMITTED_EVENT_TYPE, PurgeOutcome, PurgeTrigger, SARRequest


# Triggers that perform the Art. 17 strip pass.
_STRIPPING_TRIGGERS: frozenset[PurgeTrigger] = frozenset(
    {
        PurgeTrigger.USER_INVOKED_ART17,
        PurgeTrigger.USER_ACCOUNT_DELETION,
        PurgeTrigger.SAR_PRIORITY,
    }
)


_RECHECK_DELETED_SQL = text(
    "SELECT is_deleted, user_id FROM sessions WHERE id = :session_id FOR UPDATE"
)

_INSERT_AUDIT_SQL = text(
    """
    INSERT INTO application_events (id, session_id, user_id, event_type, event_group, content)
    VALUES (gen_random_uuid(), :session_id, :user_id, :event_type, 'session', CAST(:content AS jsonb))
    """
)

_DELETE_SESSION_SQL = text("DELETE FROM sessions WHERE id = :session_id")


# Canonical event_type for the audit row. The string lives in ``types``
# (``PURGE_COMMITTED_EVENT_TYPE``) so that the I19 idempotency precheck
# in ``session_purge.purge_one_session`` and the invariant checks in
# ``invariants.py`` can import a single source of truth. Sub-trigger
# lives in ``content.trigger``.
_AUDIT_EVENT_TYPE = PURGE_COMMITTED_EVENT_TYPE


async def commit_purge(
    *,
    session_id: uuid.UUID,
    user_id: uuid.UUID,
    trigger: PurgeTrigger,
    db: AsyncSession,
    sar_request: SARRequest | None = None,
    affected_systems: tuple[str, ...] = ("postgres_prod",),
) -> PurgeOutcome:
    """Phase (c). Atomic strip + audit + delete.

    Args:
        sar_request: REQUIRED if trigger=SAR_PRIORITY (precondition I13).
        affected_systems: Lawyer-memo §5 audit field — systems touched.

    Returns:
        PurgeOutcome.PURGED on success.
        PurgeOutcome.ALREADY_PURGED if the session row no longer exists
        (concurrent worker reached terminal state — I19).
        PurgeOutcome.SKIPPED_RESTORED if step 1 finds is_deleted=false
        (only for non-SAR triggers; SAR triggers raise PurgeBlockedError).

    Invariants preserved: I1, I4, I5, I7, I11, I12, I13.

    Raises:
        PurgeBlockedError: I12 violation (concurrent restore vs SAR).
        ValueError: precondition failure (e.g., I13 audit fields missing).
    """
    # I13 precondition.
    if trigger == PurgeTrigger.SAR_PRIORITY and sar_request is None:
        raise ValueError(
            "I13 violation: trigger=SAR_PRIORITY requires sar_request. "
            "Audit trail without SAR receipt timestamp + verification method "
            "is indefensible under GDPR Art. 5(2). See lawyer memo §5."
        )

    # Step 1 — re-check is_deleted (Adversarial #2).
    row = (await db.execute(_RECHECK_DELETED_SQL, {"session_id": str(session_id)})).one_or_none()

    if row is None:
        # Row gone — a concurrent worker already completed phase (c) for this
        # session_id (I19 idempotency). Distinct from SKIPPED_RESTORED, which
        # means the row exists but was un-soft-deleted by a restore.
        return PurgeOutcome.ALREADY_PURGED

    is_deleted, current_user_id = bool(row[0]), row[1]
    if not is_deleted:
        # Restore-vs-purge race. SAR cannot be restored away (I12).
        if trigger == PurgeTrigger.SAR_PRIORITY:
            raise PurgeBlockedError(
                f"I12 violation: session {session_id} restore raced with SAR_PRIORITY purge. "
                "Restore endpoint must reject SAR-flagged sessions; this code path "
                "being reached means the restore-side guard failed."
            )
        return PurgeOutcome.SKIPPED_RESTORED

    # Step 2 — Art. 17 strip + 2a — assertion.
    if trigger in _STRIPPING_TRIGGERS:
        await strip_user_pii_art17(db=db, session_id=session_id)
        await assert_strip_complete(db=db, session_id=session_id)

    # Step 3 — audit row.
    audit_user_id: str | None
    audit_content: dict[str, Any]
    if trigger in _STRIPPING_TRIGGERS:
        # Adversarial §4.7-step-9: audit row's user_id is NULL from construction.
        audit_user_id = None
        audit_content = {
            "trigger": trigger.value,
            "affected_systems": list(affected_systems),
        }
        if trigger == PurgeTrigger.SAR_PRIORITY:
            assert sar_request is not None  # narrow for mypy (checked above)
            # Lawyer memo §5 — 4 audit fields.
            audit_content.update(
                {
                    "sar_receipt_timestamp": sar_request.sar_receipt_timestamp,
                    "sar_verification_method": sar_request.verification_method,
                    "sar_requesting_authority": sar_request.requesting_authority,
                    "sar_scope": sar_request.scope,
                    "erasure_completion_timestamp": "now()",
                }
            )
    else:
        # GRACE_EXPIRED — preserve user_id for billing-dispute investigation.
        audit_user_id = str(current_user_id) if current_user_id is not None else None
        audit_content = {"trigger": trigger.value}

    await db.execute(
        _INSERT_AUDIT_SQL,
        {
            "session_id": str(session_id),
            "user_id": audit_user_id,
            "event_type": _AUDIT_EVENT_TYPE,
            "content": json.dumps(audit_content),
        },
    )

    # Step 4 — DELETE the session row. CASCADE/SET NULL handles dependents.
    await db.execute(_DELETE_SESSION_SQL, {"session_id": str(session_id)})

    # Caller commits the surrounding transaction.
    return PurgeOutcome.PURGED
