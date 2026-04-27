"""Session purge subsystem — executable design contract.

This module is the SOURCE OF TRUTH for session lifecycle / data custody.
The design doc (`docs/design-docs/session-lifecycle-and-data-custody.md`)
EXPLAINS this module; this module DEFINES the contract.

All signatures here MUST mypy --strict clean. Bodies raise NotImplementedError
until PR-E lands. Each public function's docstring cites the invariants
(see `invariants.py`) it preserves and the doc section it implements.

Call graph (single arbitration point: ``purge_one_session``):

    cleanup_loop_step()  ─┐
                          ├─► claim.claim_one_session()        (phase a)
    purge_now_handler() ──┤    │
                          │    ▼
    user_account_purge() ─┘   providers.run_provider_cleanup() (phase b)
                              │   (heartbeats claim every ~120s)
                              ▼
                              commit.commit_purge()             (phase c)
                                  re-check + strip + assert + audit + DELETE
                                  — all in ONE tx

Every callsite goes through ``session_purge.purge_one_session`` — never
directly to phase (a)/(b)/(c). This eliminates the §16-step-3 race
documented in v3.7.

PR sequence (lands in this order):

  PR-A  Add ``purge_after`` / ``custody`` / ``purge_started_at`` /
        ``purge_attempts`` columns + indexes. Schema-only, no behaviour.
  PR-B  Add ``provider_cleanup_dead_letter`` table + ``users.is_purging``
        + ``sar_intake`` table. Schema-only.
  PR-C  Add the 9 missing FK constraints with ``NOT VALID``; data-hygiene
        script for orphans; ``VALIDATE CONSTRAINT`` follow-up migration.
  PR-D  Update ``database-design.md``; remove inert ``cascade=`` from
        ``Session.events``; ORM cascade consistency tests (§7).
  PR-E  Implement every body in this package; wire ``purge_one_session``
        into ``orphan_cleanup.py`` between ``_pause_stale_sandboxes`` and
        ``_cleanup_docker_zombies``; register ``register_purge_guards()``
        in ``app/lifespan.py``; ship the test contract from §14.4.
  PR-F  Implement ``purge_now`` HTTP endpoint + ``restore`` endpoint with
        SAR-blocked check (I16); admin unblock-purge endpoint.
  PR-G  Implement ``purge_user_account`` + ``intake_sar``; gate every
        mutation endpoint with ``NotPurgingDep`` per §16 enumeration.
"""

from __future__ import annotations

from .exceptions import (
    ExhaustedRetriesError,
    LegalHoldError,
    PurgeBlockedError,
    PurgeRetryableError,
    SandboxTeardownTimeoutError,
    TransientProviderError,
    UserPurgeBlockedError,
    UserPurgeFailedError,
    UserPurgeRetryableError,
)
from .orm_guards import register_purge_guards
from .pii_strip import assert_strip_complete
from .session_purge import purge_one_session
from .types import (
    PurgeOutcome,
    PurgeResult,
    PurgeTrigger,
    RetentionException,
    RetentionExceptionRecord,
    SARRequest,
    UserPurgeReason,
)

__all__ = [
    "ExhaustedRetriesError",
    "LegalHoldError",
    "PurgeBlockedError",
    "PurgeOutcome",
    "PurgeResult",
    "PurgeRetryableError",
    "PurgeTrigger",
    "RetentionException",
    "RetentionExceptionRecord",
    "SARRequest",
    "SandboxTeardownTimeoutError",
    "TransientProviderError",
    "UserPurgeBlockedError",
    "UserPurgeFailedError",
    "UserPurgeReason",
    "UserPurgeRetryableError",
    "assert_strip_complete",
    "purge_one_session",
    "register_purge_guards",
]
