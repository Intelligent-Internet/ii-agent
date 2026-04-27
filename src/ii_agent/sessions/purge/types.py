"""Type aliases and result objects for the purge subsystem.

These types make implicit branches explicit: every call to ``purge_one_session``
returns a `PurgeResult` whose `outcome` is one of the enum values below.
Callers MUST handle every outcome — relying on exceptions alone hides
the success-with-deferred-work case (`outcome=DEFERRED_TRANSIENT`).

Glossary:
  SAR = Subject Access Request (GDPR Art. 15) — used in this doc as the
  umbrella term for verified user requests covered by Art. 15 (access),
  Art. 16 (rectification), and Art. 17 (erasure). The lawyer memo treats
  them as one intake channel; engineering follows that contract.
"""

from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass


class PurgeTrigger(str, enum.Enum):
    """Why a purge ran. Drives the strip policy (see `pii_strip.py`) AND
    the urgency window (see legal memo §7, codified as I12)."""

    GRACE_EXPIRED = "grace_expired"
    """§4.1 — operator retention policy expired. Billing forensics PRESERVED.
    Urgency: best-effort (next sweep cycle). NOT a legal deadline."""

    USER_INVOKED_ART17 = "user_invoked_art17"
    """§4.7 — user invoked GDPR Art. 17 erasure. PII STRIPPED + user_id NULLED.
    Urgency: ROUTINE — user soft-deleted a session and asked for erasure of THAT
    session. Legal target: 5 business days (lawyer memo §7)."""

    USER_ACCOUNT_DELETION = "user_account_deletion"
    """§16 — entire user account being deleted. PII STRIPPED + user_id NULLED.
    Urgency: ROUTINE. Same 5-business-day target as Art. 17.
    NOTE: §3.1 — origin/main has Session.user_id ON DELETE CASCADE. The user-purge
    flow MUST run purge_user_account() (which audits + hard-deletes sessions) BEFORE
    deleting the User row. Deleting the User row first will silently CASCADE-drop
    sessions with NO audit trail — a GDPR Art. 5(2) accountability violation.
    Enforced by I14 (cascade-before-delete)."""

    SAR_PRIORITY = "sar_priority"
    """NEW v3.9 — verified Subject Access Request received via support channel.
    Pre-empts any in-flight grace window for the affected user (lawyer memo §1,
    §7; CJEU Case C-460/20). Bypasses purge_after timestamp; routes directly to
    fast-track queue. Legal target: 24 hours; absolute max: 5 business days.
    Enforced by I12 (SAR pre-empts grace).

    REQUIRES: sar_receipt_timestamp + sar_verification_method captured on the
    audit row (lawyer memo §5 — 4 fields engineering had previously omitted)."""


class UserPurgeReason(str, enum.Enum):
    SELF_SERVICE = "self_service"
    ADMIN_INITIATED = "admin_initiated"
    GDPR_ART17 = "gdpr_art17"


class RetentionException(str, enum.Enum):
    """GDPR Art. 17(3) exceptions — the only defensible reasons to delay erasure
    after a SAR. Each exception MUST be accompanied by a justification string
    and an exception_end_date (see `RetentionExceptionRecord`). Lawyer memo §4."""

    NONE = "none"
    LEGAL_HOLD = "legal_hold"
    """Active litigation/regulatory investigation. Requires case number, counsel."""

    TAX_RECORD = "tax_record"
    """Tax/accounting law (e.g. EU 7-10yr). Only minimum fields; PII de-linked."""

    FRAUD_INVESTIGATION = "fraud_investigation"
    """Active investigation; max 90 days post-incident; closure triggers erasure."""


@dataclass(frozen=True)
class RetentionExceptionRecord:
    """Captures the WHY when erasure is delayed past the SAR deadline.
    Lawyer memo §4: 'DO NOT silently retain data — must notify under Art. 17(3).'
    """

    kind: RetentionException
    justification: str
    """Human-readable reason. E.g. 'Active litigation case 2026-CV-1234'."""

    end_date: str
    """ISO-8601 UTC timestamp when exception expires. After this date, immediate erasure."""

    authority: str | None = None
    """Counsel / regulator / tax-jurisdiction issuing the hold."""


@dataclass(frozen=True)
class SARRequest:
    """Required intake fields for a verified Article 17 / CCPA SAR.
    Lawyer memo §5 — minimum audit fields. Missing any = audit trail incomplete.

    v3.10: __post_init__ validators close adversarial #1 + #3 — empty strings
    and non-ISO-8601 timestamps were previously accepted by the type system.
    Now rejected at construction; misuse fails fast with ValueError.
    """

    user_id: uuid.UUID
    sar_receipt_timestamp: str
    """ISO-8601 UTC — when the SAR arrived (NOT when erasure ran)."""

    verification_method: str
    """How identity was confirmed. E.g. 'EMAIL_VERIFICATION:user@x.com:2026-04-27',
    'SUPPORT_TICKET_#1234', 'OAUTH_LOGIN_REAUTH'. Free-form but MUST be specific."""

    requesting_authority: str = "USER_SELF_SERVICE"
    """USER_SELF_SERVICE | CNIL | ICO | <DPA name>. Lawyer memo §5."""

    scope: str = "ALL"
    """ALL | SESSIONS | BILLING | SELECTIVE:[csv]. Drives which domains erase."""

    def __post_init__(self) -> None:
        """Adversarial #1, #3 (v3.9): close empty-string + bad-timestamp gaps.

        Without these checks, a contributor could construct
        ``SARRequest(user_id=u, sar_receipt_timestamp='', verification_method='')``
        and the audit trail would be indefensible under regulator inspection
        (lawyer memo §5). I13 enforces this at the runtime check; this validator
        enforces it at construction.
        """
        from datetime import datetime

        for field_name in (
            "sar_receipt_timestamp",
            "verification_method",
            "requesting_authority",
            "scope",
        ):
            value = getattr(self, field_name)
            if not value or not value.strip():
                raise ValueError(
                    f"SARRequest.{field_name} must be non-empty (I13). "
                    f"Lawyer memo §5 — audit fields without content fail Art. 5(2)."
                )

        try:
            datetime.fromisoformat(self.sar_receipt_timestamp.replace("Z", "+00:00"))
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"SARRequest.sar_receipt_timestamp must be ISO-8601 UTC "
                f"(got {self.sar_receipt_timestamp!r}). Adversarial v3.9 #3."
            ) from exc


class PurgeOutcome(str, enum.Enum):
    """Terminal outcome of ``purge_one_session``. Callers branch on this."""

    PURGED = "purged"
    """Session row deleted; phase (c) committed. Final state."""

    SKIPPED_NOT_ELIGIBLE = "skipped_not_eligible"
    """Phase (a) returned no claim (not in grace, sandbox not deleted, legal hold).
    Caller should retry on next sweep cycle. NOT an error."""

    SKIPPED_RACED = "skipped_raced"
    """Phase (a) attempted but lost the SKIP LOCKED race to another worker.
    Another worker is purging this session. NOT an error."""

    SKIPPED_RESTORED = "skipped_restored"
    """Phase (c) found `is_deleted=false` (user restored mid-purge).
    Provider DELETEs from phase (b) ARE NOT undone — they're idempotent
    on next purge attempt. The user gets back a session whose provider
    artefacts may have been re-uploaded. Documented limitation.

    NOTE v3.9: SAR_PRIORITY trigger is NEVER restorable. If trigger=SAR_PRIORITY
    a concurrent restore attempt MUST be rejected (I12). Restore endpoint
    checks for active SAR before allowing."""

    DEFERRED_TRANSIENT = "deferred_transient"
    """Phase (b) hit a transient provider error AND attempt count < max.
    Claim was released; will be retried by next sweep."""

    DEAD_LETTERED = "dead_lettered"
    """Phase (b) exhausted retries; row written to `purge_dead_letter`.
    Session row is NOT deleted. Operator action required."""

    ALREADY_PURGED = "already_purged"
    """Phase (a) found the session row no longer exists, OR exists but is in a
    terminal post-purge state (purge_committed event already written).

    Returned for **idempotent re-invocation** — admin retry of `purge_now` on
    a session that has already completed phase (c), or a cleanup-loop sweep
    that races a successful prior run. NOT an error; callers should treat
    this as success.

    Distinct from PURGED: the current call did NOT perform the deletion.
    Distinct from SKIPPED_RACED: the prior worker reached terminal state,
    not just held the claim. Enforced by I19."""


@dataclass(frozen=True)
class PurgeResult:
    """Return value of ``purge_one_session``. Immutable, fully-described."""

    session_id: uuid.UUID
    outcome: PurgeOutcome
    trigger: PurgeTrigger
    attempts_used: int
    """Value of `purge_attempts` AFTER this call (post-increment)."""

    elapsed_seconds: float
    dead_letter_count: int = 0
    """Number of resources written to `provider_cleanup_dead_letter` this call."""

    sar_request: SARRequest | None = None
    """Set IFF trigger=SAR_PRIORITY. Captured on the audit row (lawyer memo §5).
    Invariant I13: trigger=SAR_PRIORITY ⇔ sar_request is not None."""

    retention_exception: RetentionExceptionRecord | None = None
    """Set IFF erasure was deferred under Art. 17(3). Persisted on the audit row.
    When set, outcome MUST be DEFERRED_TRANSIENT or DEAD_LETTERED, never PURGED."""

    note: str | None = None
    """Operator-readable diagnostic. Empty on success."""
