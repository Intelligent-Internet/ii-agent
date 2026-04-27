"""User-account purge (§16). Drives every owned session through `purge_one_session`.

The single most important architectural change vs v3.7: this module DOES NOT
duplicate or shortcut the per-session pipeline. It:

  1. Sets ``users.is_purging=true`` (gates new sessions per ``NotPurgingDep``).
  2. Soft-deletes every owned session and sets ``purge_after=now()``.
  3. For each session, calls ``purge_one_session(session_id=..., trigger=USER_ACCOUNT_DELETION)``
     under bounded concurrency. Each call goes through phase (a) claim \u2014 so the
     orphan-loop sweep cannot race (Adversarial #6).
  4. Checks ``provider_cleanup_dead_letter`` for unresolved rows by user_id (I10).
  5. Strips PII from audit rows that survived earlier purges (Art. 17 whole-user).
  6. ``DELETE FROM users``. CASCADE/SET NULL per \u00a73.1.

CRITICAL v3.9 (Adversarial #1 + lawyer memo \u00a77): origin/main has
Session.user_id ON DELETE CASCADE. Step 6 must run ONLY after step 3 has
produced an audit row for every session, AND step 4 has confirmed no
unresolved dead-letters. Naively deleting users first would silently
CASCADE-drop sessions with NO audit trail \u2014 a GDPR Art. 5(2) accountability
violation. Invariant I14 enforces this ordering at runtime.

Adversarial findings addressed:
  #1 (FK CASCADE silent loss) \u2014 see step-6 precondition + I14
  #6 (claim race) \u2014 by routing through phase (a)
  #7 (purge_now mutex)  \u2014 see ``check_user_not_purging`` precondition
  #16 step 5/6 ordering \u2014 strip and DELETE share a tx (commit.py contract)
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from .types import SARRequest, UserPurgeReason

if TYPE_CHECKING:
    pass


async def purge_user_account(
    *,
    user_id: uuid.UUID,
    reason: UserPurgeReason,
    sar_request: SARRequest | None = None,
) -> None:
    """Drive a user-account deletion through the per-session pipeline first.

    Args:
        sar_request: REQUIRED if reason=GDPR_ART17. Captures lawyer-memo \u00a75
            audit fields. ValueError if reason=GDPR_ART17 and sar_request is None.

    Raises:
        UserPurgeFailedError: at least one session raised a non-transient error.
        UserPurgeRetryableError: at least one session hit ``TransientProviderError``;
            caller may retry after the next cleanup cycle.
        UserPurgeBlockedError: dead-letter rows remain; manual operator action required.

    Invariants preserved: I1, I3, I4, I8, I10, I11, I13, I14.
    """
    if reason == UserPurgeReason.GDPR_ART17 and sar_request is None:
        raise ValueError(
            "I13 violation: reason=GDPR_ART17 requires sar_request for audit. "
            "See lawyer memo \u00a75 (sar_receipt_timestamp, verification_method)."
        )
    raise NotImplementedError


async def check_user_not_purging(*, user_id: uuid.UUID) -> None:
    """Precondition for per-session purge_now (Adversarial #7).

    Raises ``PurgeBlockedError`` if the owning user has ``is_purging=true``.
    The user-account purge is already driving every owned session through
    the pipeline; concurrent per-session purge_now would double-claim.

    Invariants preserved: I3, I8.
    """
    raise NotImplementedError


async def intake_sar(
    *,
    user_id: uuid.UUID,
    sar_request: SARRequest,
) -> int:
    """Lawyer memo \u00a71/\u00a77: SAR pre-empts grace.

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
      3. Enqueue purge_one_session(trigger=SAR_PRIORITY) for each affected session.

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
            f"!= user_id={user_id}. Verification gap \u2014 lawyer memo \u00a75."
        )
    raise NotImplementedError
