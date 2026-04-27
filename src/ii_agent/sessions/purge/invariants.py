"""Lifecycle invariants — runtime-checkable predicates.

Each invariant is a numbered predicate that must hold at all times in
the production database. Every code path in `purge/` cites the invariants
it preserves; every test in §14.4 cites the invariants it verifies.

An invariant unenforced by any test or unclaimed by any code path is a gap.

These predicates are EXECUTABLE: each `check_I*` function returns a list of
violating row IDs. A nightly job (`tests/integration/test_invariants_in_prod.py`)
runs all checks against staging and pages on any non-empty result.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


# ─── State invariants ───────────────────────────────────────────────────────


async def check_I1_purge_after_implies_deleted(db: AsyncSession) -> list[uuid.UUID]:
    """I1: ``purge_after IS NOT NULL`` ⟹ ``is_deleted = true``.

    Violation means a session was scheduled for purge without being soft-deleted —
    the §4.1 sweep would never claim it (eligibility predicate excludes
    is_deleted=false), so the row sits forever with a stale purge_after.

    Enforced by: §4.1 phase-(a) WHERE clause; §4.7 step 6 in-tx INSERT;
    §16 step 2 UPDATE.
    """
    raise NotImplementedError


async def check_I2_dead_letter_consistency(db: AsyncSession) -> list[uuid.UUID]:
    """I2: every row in ``purge_dead_letter`` with ``resolved_at IS NULL``
    references a session that has ``is_deleted = true AND purge_started_at IS NOT NULL``,
    OR the session row no longer exists (dead-letter outlived its session).

    Violation means an unresolved dead-letter exists for an active session —
    operator action would re-leak data.
    """
    raise NotImplementedError


async def check_I3_is_purging_blocks_new_sessions(db: AsyncSession) -> list[uuid.UUID]:
    """I3: ``users.is_purging = true`` ⟹ no ``sessions`` row created with
    ``created_at > users.is_purging_set_at`` for that user.

    Enforced by: ``NotPurgingDep`` on every mutation endpoint (§16 v3.7).
    Test: ``test_is_purging_gate_enumeration.py``.
    """
    raise NotImplementedError


async def check_I4_art17_strip_unattributable(db: AsyncSession) -> list[uuid.UUID]:
    """I4: ``application_events`` rows with ``session_id IS NULL`` from an Art. 17
    purge MUST also have ``user_id IS NULL`` and ``content`` containing only
    keys in ``_BILLING_SAFE_KEYS``.

    Distinguishing Art. 17 rows from operational-grace rows: the audit row's
    own ``event_type`` is ``'session.purged_by_user'`` for Art. 17,
    ``'session.purged_by_grace'`` for operational. (The strip pass writes the
    event AFTER nulling user_id, so the new event row itself has user_id=NULL —
    see Adversarial Finding §4.7 step 9.)
    """
    raise NotImplementedError


async def check_I5_legal_hold_never_purged(db: AsyncSession) -> list[uuid.UUID]:
    """I5: a session that was EVER ``custody='legal_hold'`` (per audit log)
    MUST exist in the sessions table OR have an explicit
    ``application_events`` row of type ``'session.legal_hold_released'`` AND
    ``'session.purged_by_*'`` in that order.

    Hard violation: a session with current or historic legal_hold has been
    deleted without an audit trail — litigation exposure.
    """
    raise NotImplementedError


# ─── Concurrency invariants ─────────────────────────────────────────────────


async def check_I6_single_claim(db: AsyncSession) -> list[uuid.UUID]:
    """I6: ``purge_one_session`` is invoked exactly once per
    (session_id, claim_cycle) pair.

    Verifying this requires correlating ``purge_attempts`` increments against
    audit-log entries; in practice we assert via the
    ``test_user_purge_claim_arbitration.py`` integration test (§14.4 v3.7)
    that two concurrent invocations result in only one increment per cycle.

    No prod-time check is feasible without instrumentation; this invariant
    is enforced by code structure, not a query.
    """
    raise NotImplementedError


async def check_I7_phase_c_rechecks_deleted(db: AsyncSession) -> list[uuid.UUID]:
    """I7 (Adversarial Finding #2): phase (c)'s DELETE statement MUST include
    ``WHERE id = :id AND is_deleted = true``. If a concurrent ``restore`` call
    set ``is_deleted=false`` between phases (a) and (c), phase (c) MUST be a
    no-op and return ``PurgeOutcome.SKIPPED_RESTORED``.

    This is a STRUCTURAL invariant — verified by
    ``test_purge_phase_c_recheck_is_deleted.py`` (new in §14.4 v3.8).
    """
    raise NotImplementedError


async def check_I8_no_purge_now_during_user_purge(db: AsyncSession) -> list[uuid.UUID]:
    """I8 (Adversarial Finding #7): when ``users.is_purging=true``,
    per-session ``purge_now`` MUST reject with 423 Locked. The two paths
    must not concurrently drive ``purge_one_session`` for the same session.

    Enforced by: ``PurgeBlockedError`` raised by §4.7 step 1 if the owning
    user has ``is_purging=true``.
    """
    raise NotImplementedError


# ─── Provider-cleanup invariants ────────────────────────────────────────────


async def check_I9_provider_artefacts_traceable(db: AsyncSession) -> list[uuid.UUID]:
    """I9: every external provider artefact ID we have ever written
    (``chat_provider_files.provider_file_id``, etc.) is either:
        (a) referenced by an existing row in the corresponding table, OR
        (b) referenced by a ``provider_cleanup_dead_letter`` row (resolved or unresolved), OR
        (c) verified deleted by a successful provider-DELETE call audit-logged
            in ``application_events`` with ``event_type='provider.delete.success'``.

    A provider artefact ID with NONE of (a/b/c) is a leak — the doc's
    central failure mode.

    This invariant cannot be checked locally; requires reconciling with
    provider's own list endpoint via a separate audit job.
    """
    raise NotImplementedError


async def check_I10_dead_letter_user_id_set(db: AsyncSession) -> list[uuid.UUID]:
    """I10: every ``purge_dead_letter`` row has ``user_id IS NOT NULL``.

    Required by §16 step 4 — an unknown user_id makes the row invisible to
    the user-purge block check, allowing user account deletion to proceed
    while leaks remain.

    Enforced by: ``providers.run_provider_cleanup`` insert path
    (must populate user_id).
    """
    raise NotImplementedError


# ─── Audit-row invariants (post-strip) ──────────────────────────────────────


async def check_I11_no_pii_keys_in_stripped_rows(db: AsyncSession) -> list[uuid.UUID]:
    """I11: any ``application_events`` row with ``user_id IS NULL`` (Art. 17 stripped)
    MUST NOT contain any of the known PII keys in ``content``:
    {'prompt', 'message', 'file_name', 'error_detail', 'email', 'ip_address'}.

    Run as a nightly check. Any violation = compliance bug.
    """
    raise NotImplementedError


# ─── Legal-compliance invariants (added v3.9 from external counsel memo) ────


async def check_I12_sar_preempts_grace(db: AsyncSession) -> list[uuid.UUID]:
    """I12: when an `sar_intake` row exists with `verified_at IS NOT NULL`
    AND `closed_at IS NULL` for a user, NO `sessions` row for that user
    may have ``is_deleted=true AND purged_at IS NULL AND
    sar_priority IS NULL OR sar_priority=false``.

    Plain: a verified active SAR forces every is_deleted session of that user
    onto the fast-track queue. The grace path is forbidden once SAR fires.

    Source: lawyer memo §1, §7. CJEU Case C-460/20 (TU and RE v Google).

    Enforced by: SAR intake handler MUST set sessions.sar_priority=true and
    re-route to fast queue (target 24h). Restore endpoint MUST reject if active
    SAR exists. Grace sweep MUST NOT claim SAR-flagged sessions.

    Violation = GDPR Art. 17(1) violation. Up to 4% global turnover.
    """
    raise NotImplementedError


async def check_I13_sar_audit_fields_complete(db: AsyncSession) -> list[uuid.UUID]:
    """I13: every `erasure_audit_log` row with ``request_type='SAR'`` MUST have
    all of: sar_receipt_timestamp, sar_verification_method, erasure_completion_timestamp,
    affected_systems (JSON array, non-empty).

    Source: lawyer memo §5 — the four fields engineering's v3.7 design omitted.

    Returns audit row IDs missing any required field. Any non-empty result =
    audit trail incomplete = cannot defend Art. 5(2) accountability under
    regulator inspection.
    """
    raise NotImplementedError


async def check_I14_user_delete_after_session_purge(db: AsyncSession) -> list[uuid.UUID]:
    """I14: when ``users`` row is deleted, all of that user's sessions MUST
    have been processed through purge_user_account() (with audit rows) FIRST.

    Background: origin/main has Session.user_id ON DELETE CASCADE. Naively
    deleting the User row first will silently CASCADE-drop sessions with
    NO audit trail — Art. 5(2) accountability violation.

    Cannot be checked post-hoc (cascaded sessions are gone). Instead, this
    invariant is enforced by a DB trigger or application invariant: the User
    DELETE statement may only run when `users.is_purging=true AND
    NOT EXISTS (SELECT 1 FROM sessions WHERE user_id=users.id)`.

    Returns user_ids whose erasure_audit_log shows a USER_PURGE event but
    where the audit row count for sessions doesn't match the (now-cascaded)
    historical count from `application_events` session-create entries.
    """
    raise NotImplementedError


async def check_I15_retention_exception_disclosed(db: AsyncSession) -> list[uuid.UUID]:
    """I15: any session deferred under Art. 17(3) (retention_exception IS NOT NULL)
    MUST have a corresponding outbound user-notification logged in
    `application_events` with ``event_type='art17_3.disclosure'`` within 30 days
    of the SAR receipt.

    Source: lawyer memo §6 — 'DO NOT silently retain data; must notify under
    Art. 17(3)'. Backup retention is the most common case; user must be told.
    """
    raise NotImplementedError


# ─── Concurrency / deployment invariants (v3.10 — adversarial pass #2) ──────


async def check_I16_restore_blocked_during_active_sar(db: AsyncSession) -> list[uuid.UUID]:
    """I16 (NEW v3.10, Adversarial v3.9 #2): when a verified SAR is active for
    a user, NO ``sessions`` row for that user may transition
    ``is_deleted=true → is_deleted=false`` (restore is forbidden).

    Why: if the restore endpoint allowed reactivation while phase (b) was
    mid-flight, the provider DELETEs would already have fired but the
    session row would survive — a guaranteed data loss attack with the
    user blaming the operator.

    Enforced by:
      (1) Application: restore endpoint (§4.3) MUST query for
          ``sar_intake.verified_at IS NOT NULL AND closed_at IS NULL``
          before allowing the UPDATE; on hit, returns HTTP 423 Locked.
      (2) Database (defence in depth): trigger on ``sessions`` rejecting
          ``is_deleted: true → false`` when the user has an active SAR.

    Returns user_ids whose session restore audit shows reactivation
    timestamp inside an active SAR window. Any non-empty result =
    Art. 17(1) violation.
    """
    raise NotImplementedError


async def check_I17_grace_sweep_reads_primary(db: AsyncSession) -> list[uuid.UUID]:
    """I17 (NEW v3.10, Adversarial v3.9 #4): the grace-purge sweep query
    MUST execute against the primary database, not a read replica.

    Why: if the cleanup loop reads from a replica with non-zero replication
    lag, a session whose ``sar_priority=true`` was set on the primary
    moments before may still appear with ``sar_priority=false`` on the
    replica. The grace path then claims it, racing the SAR fast-track
    queue and violating I12.

    Enforced by:
      (1) Cleanup-loop DB session uses the writer engine, not a reader.
      (2) Connection-string assertion at startup (production gate).

    This invariant cannot be checked post-hoc from data alone; it is
    enforced by deployment configuration. The check function asserts
    that the runtime configuration has ``cleanup_db_url == primary_db_url``;
    if it doesn't, returns a sentinel UUID (operator must investigate).
    """
    raise NotImplementedError


async def check_I18_legal_hold_supersedes_sar(db: AsyncSession) -> list[uuid.UUID]:
    """I18 (NEW v3.10, Adversarial v3.9 §C / lawyer memo §4(a)):
    when a session has ``custody='legal_hold'`` AND a SAR arrives for the
    owning user, the legal hold WINS — the session is NOT moved to the
    fast-track queue and the SAR audit row records
    ``retention_exception=LEGAL_HOLD`` with the case number from the hold.

    Why: GDPR Art. 17(3)(b)/(e) explicitly preserves the controller's
    obligation to comply with legal claims. A SAR cannot override active
    litigation. Lawyer memo §4(a) explicit.

    But: per Art. 17(3) closing clause + §15 of this doc, the user MUST
    be notified that erasure was deferred and the reason. I15 covers the
    notification; I18 covers the routing decision.

    Enforced by:
      (1) ``intake_sar`` checks each candidate session's custody before
          setting ``sar_priority=true``. Sessions in legal_hold are
          recorded with retention_exception=LEGAL_HOLD instead.
      (2) ``commit_purge`` raises ``LegalHoldError`` if it ever encounters
          a legal-hold session, regardless of trigger.

    Returns session_ids where a SAR fast-track purge happened on a session
    that had custody='legal_hold' at the SAR receipt time (=I18 violation,
    indefensible legal exposure if the hold authority finds out).
    """
    raise NotImplementedError


async def check_I19_already_purged_idempotent(db: AsyncSession) -> list[uuid.UUID]:
    """I19 (NEW v3.11): ``purge_one_session`` invoked on a session that has
    already reached terminal state (``application_events`` contains a
    ``session.purge_committed`` row for this session_id) MUST return
    ``PurgeOutcome.ALREADY_PURGED`` without re-running phase (b)/(c).

    Why: admins legitimately retry failed purges; cleanup-loop sweeps race
    successful prior runs; SAR fast-track may re-target a session whose
    grace expired moments before. Re-running phase (b) re-issues provider
    DELETEs (idempotent, fine) but re-running phase (c) attempts to DELETE
    a row that no longer exists — surfaces as a spurious 0-row UPDATE that
    masks real bugs.

    Returns session_ids where two ``session.purge_committed`` audit rows
    exist for the same session_id (= I19 violation: double-purge
    accounting, dead-letter retention math broken).

    Enforced by: ``session_purge.purge_one_session`` phase-(a) precheck
    queries ``application_events WHERE session_id=:sid AND
    event_type='session.purge_committed' LIMIT 1`` and returns
    ALREADY_PURGED on hit.
    """
    raise NotImplementedError


# ─── Catalog ────────────────────────────────────────────────────────────────

ALL_INVARIANTS = (
    check_I1_purge_after_implies_deleted,
    check_I2_dead_letter_consistency,
    check_I3_is_purging_blocks_new_sessions,
    check_I4_art17_strip_unattributable,
    check_I5_legal_hold_never_purged,
    check_I6_single_claim,
    check_I7_phase_c_rechecks_deleted,
    check_I8_no_purge_now_during_user_purge,
    check_I9_provider_artefacts_traceable,
    check_I10_dead_letter_user_id_set,
    check_I11_no_pii_keys_in_stripped_rows,
    check_I12_sar_preempts_grace,
    check_I13_sar_audit_fields_complete,
    check_I14_user_delete_after_session_purge,
    check_I15_retention_exception_disclosed,
    check_I16_restore_blocked_during_active_sar,
    check_I17_grace_sweep_reads_primary,
    check_I18_legal_hold_supersedes_sar,
    check_I19_already_purged_idempotent,
)
"""Run every check sequentially in `tests/integration/test_invariants_in_prod.py`.

A passing run is the formal definition of 'design converged in production'."""
