"""Exceptions raised by the purge subsystem.

Naming convention:
- `*Error` — terminal failure; caller should not retry without operator action
- `*RetryableError` — caller may retry after a delay
- `*BlockedError` — caller cannot proceed because of policy/state, not failure
"""

from __future__ import annotations


class PurgeError(Exception):
    """Base class for every purge-subsystem exception."""


class LegalHoldError(PurgeError):
    """Session has `custody='legal_hold'` — purge is forbidden by policy.

    Raised by §4.7 (purge_now) and §16 (user-account purge). Returns 423.
    """


class TransientProviderError(PurgeError):
    """Provider DELETE failed with a 5xx, timeout, or rate-limit error.

    Phase (b) catches this, increments `purge_attempts`, releases the claim.
    The session is left for the next sweep to retry. NOT terminal.
    """


class ExhaustedRetriesError(PurgeError):
    """Phase (b) exhausted the retry budget OR encountered permanent (4xx)
    failures. Dead-letter rows are persisted to ``purge_dead_letter`` BEFORE
    this exception is raised. Phase (c) is NOT executed; the session row
    remains in place and is now operator-visible via the dead-letter ledger.

    Terminal for this purge attempt. Caller maps to ``PurgeOutcome.DEAD_LETTERED``.

    ``dead_letter_count`` carries the number of leaked-resource rows
    persisted by this attempt so that ``purge_one_session`` can populate
    ``PurgeResult.dead_letter_count`` for monitoring (B3 fix).
    """

    def __init__(self, message: str, *, dead_letter_count: int = 0) -> None:
        super().__init__(message)
        self.dead_letter_count = dead_letter_count


class SandboxTeardownTimeoutError(PurgeError):
    """§4.7 step 5 — synchronous sandbox shutdown did not confirm DELETED
    within `purge_now_sandbox_timeout_seconds`. Returns 503.

    The user retries; the call is idempotent against `SandboxStatus
    IN (DELETING, DELETED)`.
    """


class PurgeBlockedError(PurgeError):
    """A precondition prevents purge from running.

    Used by §4.7 when `is_purging=true` overlaps with per-session purge_now
    attempts (Adversarial Finding #7).
    """


class PurgeRetryableError(PurgeError):
    """The purge couldn't proceed but the state is recoverable.

    Used internally by ``purge_one_session`` when phase (a) lost the
    SKIP-LOCKED race. Translated to ``PurgeOutcome.SKIPPED_RACED``.
    """


class UserPurgeFailedError(PurgeError):
    """§16 step 3 — at least one session raised a non-transient error.

    `failures` carries the per-session exceptions. User row is NOT deleted;
    `is_purging=true` remains set; operator runbook applies.
    """

    def __init__(self, failures: list[BaseException]) -> None:
        super().__init__(
            f"User purge failed for {len(failures)} session(s); operator action required."
        )
        self.failures = failures


class UserPurgeRetryableError(PurgeError):
    """§16 step 3 — at least one session hit `TransientProviderError`.

    Caller (admin endpoint, scheduled retry) should retry the entire
    `_purge_user_account` call after the next cleanup-loop cycle.
    """


class UserPurgeBlockedError(PurgeError):
    """§16 step 4 — unresolved `provider_cleanup_dead_letter` rows for this user.

    User row MUST NOT be deleted; losing the `user_id` makes the dead-letter
    row un-actionable. Operator must resolve the dead-letter row first.
    """
