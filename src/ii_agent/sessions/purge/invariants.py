"""Lifecycle invariants — runtime-checkable predicates AND their enforcement tier.

Every invariant in this module belongs to **exactly one** of three
enforcement tiers. The tier determines whether a runtime probe exists,
whether the runner schedules it, and what artefact pins the contract:

  * :data:`SCHEMA_ENFORCED` — the database physically rejects violating
    writes via CHECK constraint, UNIQUE index, or trigger. No runtime
    probe is needed because a violation cannot be persisted. The
    invariant number is listed for documentation and review-vocabulary
    continuity; ``check_I*`` functions for these are absent on purpose.

  * :data:`DB_CHECKABLE` — the invariant is a data-shape predicate that
    cannot be promoted to a constraint (typically because it spans
    tables, requires a join with a configurable threshold, or involves
    a temporal window). The runner executes the ``check_I*`` predicate
    nightly and pages on any non-empty result.

  * :data:`STRUCTURAL_TEST_ENFORCED` — the invariant is a property of
    code, not data: control-flow ordering, FOR UPDATE locking, primary-
    DB read routing, single-claim arbitration. These are pinned by
    unit/integration tests named in the invariant docstring; the
    runner does NOT execute them. (Past versions of this module raised
    ``NotImplementedError`` from a stub check function — that pattern
    was removed in the v3.10 hardening pass because it conflated
    "checkable in principle" with "checked in practice".)

If you are reading this file to add a new invariant: pick a tier, pin
the artefact (constraint name / test name / probe function), and add a
row to the catalogue at the bottom. An invariant that does not name an
enforcing artefact is a gap.
"""

from __future__ import annotations

import uuid
from typing import Awaitable, Callable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


_CheckFn = Callable[[AsyncSession], Awaitable[list[uuid.UUID]]]


# ─── Tier 1 — Schema-enforced (no runtime probe) ────────────────────────────


SCHEMA_ENFORCED: tuple[tuple[str, str], ...] = (
    (
        "I1",
        "Two CHECK constraints on sessions, both added by migration "
        "20260429_000011: "
        "(a) ck_sessions_purge_after_implies_deleted: "
        "CHECK (purge_after IS NULL OR is_deleted = true) — promotes the "
        "original I1 SQL probe into the schema; "
        "(b) ck_sessions_purge_started_implies_deleted: "
        "CHECK (purge_started_at IS NULL OR is_deleted = true) — defence-"
        "in-depth, ensures phase-(a) claim flag cannot survive a restore.",
    ),
    (
        "I10",
        "purge_dead_letter.user_id NOT NULL column constraint. "
        "Originally migration 20260427_000008. Documented here to retire "
        "the redundant runtime probe.",
    ),
    (
        "I14",
        "trg_users_block_delete_unless_purging: BEFORE DELETE ON users "
        "raises P0001 when (is_purging=false AND any sessions exist). "
        "Migration 20260429_000011. The trigger is the canonical I14 "
        "enforcement; the previous code-path-only contract (drive every "
        "session through commit_purge before the user DELETE) is now "
        "checked atomically by the database.",
    ),
    (
        "I19",
        "uq_application_events_purge_committed_per_session: UNIQUE INDEX "
        "ON application_events (session_id) WHERE event_type = "
        "'session.purge_committed' AND session_id IS NOT NULL. "
        "Two live-row purge_committed audits are physically impossible. "
        "Post-FK-set-null rows are unconstrained because their session_id "
        "is NULL. Migration 20260429_000011.",
    ),
)
"""Invariants whose violation is rejected by the database itself.

Format: ``(invariant_id, enforcing_artefact_description)``.

Adding a new entry here REQUIRES a corresponding migration that adds the
named CHECK / UNIQUE / TRIGGER. The runner never executes these — the
database does."""


# ─── Tier 2 — DB-checkable predicates (runner executes nightly) ─────────────


async def check_I2_dead_letter_consistency(db: AsyncSession) -> list[uuid.UUID]:
    """I2: every unresolved row in ``purge_dead_letter`` whose ``session_id``
    still references a live row must reference a session that has been
    soft-deleted AND claimed for purge (``is_deleted = true AND
    purge_started_at IS NOT NULL``).

    Dead-letter rows whose ``session_id`` no longer exists in ``sessions``
    are ALLOWED — phase-(c) of the purge driver hard-deletes the session
    row, and the dead-letter survives as forensic evidence (the FK is
    intentionally absent on this column for that reason). Hence the
    INNER JOIN below: a missing session is fine, a present-but-active
    session is the bug.

    Violation means an unresolved dead-letter exists for a still-active
    session — operator action would re-leak data. Cannot be promoted to
    a constraint because it joins across a deleted-row condition.
    """
    rows = (
        await db.execute(
            text(
                """
                SELECT dl.id FROM purge_dead_letter dl
                  JOIN sessions s ON s.id = dl.session_id
                 WHERE dl.resolved_at IS NULL
                   AND (s.is_deleted = false OR s.purge_started_at IS NULL)
                """
            )
        )
    ).all()
    return [r[0] if isinstance(r[0], uuid.UUID) else uuid.UUID(str(r[0])) for r in rows]


async def check_I3_is_purging_blocks_new_sessions(db: AsyncSession) -> list[uuid.UUID]:
    """I3: ``users.is_purging = true`` ⟹ no ``sessions`` row created with
    ``created_at > users.is_purging_set_at`` for that user.

    Promoted from STRUCTURAL_TEST_ENFORCED to DB_CHECKABLE in the v3.10
    hardening pass: migration 20260429_000011 added ``users.is_purging_set_at``,
    so the post-lock window now has a discriminator and an SQL probe is
    feasible. The ORM ``before_insert`` listener (orm_guards.py) remains
    the synchronous enforcement point; this probe is a nightly catch-net
    for paths that bypass the ORM (raw INSERT, future Celery tasks,
    admin scripts).

    Returns session IDs that exist despite the user being locked.
    """
    rows = (
        await db.execute(
            text(
                """
                SELECT s.id
                  FROM sessions s
                  JOIN users u ON u.id = s.user_id
                 WHERE u.is_purging = true
                   AND u.is_purging_set_at IS NOT NULL
                   AND s.created_at > u.is_purging_set_at
                """
            )
        )
    ).all()
    return [r[0] if isinstance(r[0], uuid.UUID) else uuid.UUID(str(r[0])) for r in rows]


async def check_I4_art17_strip_unattributable(db: AsyncSession) -> list[uuid.UUID]:
    """I4: every ``application_events`` row from an Art. 17 strip pass
    MUST have ``user_id IS NULL`` and contain only allowlisted keys in
    ``content``.

    Hardened discriminator (v3.10): ``stripped_at IS NOT NULL`` — set
    atomically with the strip in :func:`pii_strip.strip_user_pii_art17`.
    The previous heuristic (event_type + session_id IS NULL) was fragile
    because it assumed FK-cascade timing.

    Allowlist source-of-truth: :data:`pii_strip.DEFAULT_BILLING_SAFE_KEYS`.
    """
    from ii_agent.sessions.purge.pii_strip import DEFAULT_BILLING_SAFE_KEYS

    rows = (
        await db.execute(
            text(
                """
                SELECT id
                  FROM application_events
                 WHERE stripped_at IS NOT NULL
                   AND (
                          user_id IS NOT NULL
                       OR EXISTS (
                              SELECT 1 FROM jsonb_object_keys(content) k
                               WHERE k <> ALL(CAST(:allowlist AS text[]))
                          )
                   )
                """
            ),
            {"allowlist": list(DEFAULT_BILLING_SAFE_KEYS)},
        )
    ).all()
    return [r[0] if isinstance(r[0], uuid.UUID) else uuid.UUID(str(r[0])) for r in rows]


async def check_I11_no_pii_keys_in_stripped_rows(db: AsyncSession) -> list[uuid.UUID]:
    """I11: every strip-touched ``application_events`` row contains only
    keys from :data:`pii_strip.DEFAULT_BILLING_SAFE_KEYS`.

    Hardened discriminator (v3.10): ``stripped_at IS NOT NULL``. This
    replaces the previous heuristic that joined on ``sessions.purged_at``
    — a column that did not exist (silent UndefinedColumn at runtime,
    discovered during the architectural review of 2026-04-29) — and
    before that, the original denylist form that produced 1,236 false
    positives in the canary on 2026-04-28.

    With the explicit timestamp marker, this probe hits zero rows
    pre-flip and accurately catches strip leaks post-flip.

    NB: I4 covers the same row set with a stricter predicate (allowlist
    AND user_id NULL). I11 is intentionally narrower so a violation can
    be triaged from the failing invariant alone (I11 = strip incomplete;
    I4 = strip-AND-user-id incomplete).
    """
    from ii_agent.sessions.purge.pii_strip import DEFAULT_BILLING_SAFE_KEYS

    rows = (
        await db.execute(
            text(
                """
                SELECT id
                  FROM application_events
                 WHERE stripped_at IS NOT NULL
                   AND EXISTS (
                       SELECT 1 FROM jsonb_object_keys(content) k
                        WHERE k <> ALL(CAST(:allowlist AS text[]))
                   )
                """
            ),
            {"allowlist": list(DEFAULT_BILLING_SAFE_KEYS)},
        )
    ).all()
    return [r[0] if isinstance(r[0], uuid.UUID) else uuid.UUID(str(r[0])) for r in rows]


async def check_I12_sar_preempts_grace(db: AsyncSession) -> list[uuid.UUID]:
    """I12: when an ``sar_intake`` row exists with ``verified_at IS NOT NULL``
    AND ``closed_at IS NULL`` for a user, NO ``sessions`` row for that user
    may have ``is_deleted=true AND sar_priority=false`` (unless legal_hold).

    Plain: a verified active SAR forces every is_deleted session of that
    user onto the fast-track queue. The grace path is forbidden once SAR
    fires.

    Source: lawyer memo §1, §7. CJEU Case C-460/20 (TU and RE v Google).
    Violation = GDPR Art. 17(1) violation. Up to 4% global turnover.
    """
    rows = (
        await db.execute(
            text(
                """
                SELECT s.id
                  FROM sessions s
                  JOIN sar_intake si ON si.user_id = s.user_id
                 WHERE si.verified_at IS NOT NULL
                   AND si.closed_at IS NULL
                   AND s.is_deleted = true
                   AND COALESCE(s.sar_priority, false) = false
                   AND s.custody != 'legal_hold'
                """
            )
        )
    ).all()
    return [r[0] if isinstance(r[0], uuid.UUID) else uuid.UUID(str(r[0])) for r in rows]


async def check_I13_sar_audit_fields_complete(db: AsyncSession) -> list[uuid.UUID]:
    """I13: every Art. 17 SAR erasure audit row carries the four lawyer-memo
    §5 fields (``sar_receipt_timestamp``, ``sar_verification_method``,
    ``erasure_completion_timestamp``, non-empty ``affected_systems``
    array).

    Source: lawyer memo §5. Violation = audit trail incomplete = cannot
    defend Art. 5(2) accountability under regulator inspection.
    """
    rows = (
        await db.execute(
            text(
                """
                SELECT id
                  FROM application_events
                 WHERE event_type = 'session.purge_committed'
                   AND content ->> 'trigger' = 'sar_priority'
                   AND (
                          COALESCE(content ->> 'sar_receipt_timestamp', '') = ''
                       OR COALESCE(content ->> 'sar_verification_method', '') = ''
                       OR COALESCE(content ->> 'erasure_completion_timestamp', '') = ''
                       OR jsonb_typeof(content -> 'affected_systems') <> 'array'
                       OR jsonb_array_length(
                              COALESCE(content -> 'affected_systems', '[]'::jsonb)
                          ) = 0
                   )
                """
            )
        )
    ).all()
    return [r[0] if isinstance(r[0], uuid.UUID) else uuid.UUID(str(r[0])) for r in rows]


async def check_I15_retention_exception_disclosed(db: AsyncSession) -> list[uuid.UUID]:
    """I15: any user with a verified SAR older than 30 days MUST have at
    least one ``art17_3.disclosure`` event for that user dated within
    30 days of SAR receipt — UNLESS the SAR has since been closed.

    Source: lawyer memo §6 — 'DO NOT silently retain data; must notify
    under Art. 17(3)'. Returns ``user_id`` values whose verified,
    still-open SAR is past 30 days with no disclosure row on file.
    """
    rows = (
        await db.execute(
            text(
                """
                SELECT si.user_id
                  FROM sar_intake si
                 WHERE si.verified_at IS NOT NULL
                   AND si.closed_at IS NULL
                   AND si.verified_at <= now() - INTERVAL '30 days'
                   AND NOT EXISTS (
                          SELECT 1 FROM application_events ae
                           WHERE ae.user_id = si.user_id
                             AND ae.event_type = 'art17_3.disclosure'
                             AND ae.created_at >= si.verified_at
                             AND ae.created_at <= si.verified_at + INTERVAL '30 days'
                       )
                """
            )
        )
    ).all()
    return [r[0] if isinstance(r[0], uuid.UUID) else uuid.UUID(str(r[0])) for r in rows]


async def check_I16_restore_blocked_during_active_sar(db: AsyncSession) -> list[uuid.UUID]:
    """I16: when a verified SAR is active for a user, NO ``sessions`` row
    for that user may transition ``is_deleted=true → is_deleted=false``.

    Returns user_ids whose session restore audit shows reactivation
    timestamp inside an active SAR window. Any non-empty result =
    Art. 17(1) violation.
    """
    rows = (
        await db.execute(
            text(
                """
                SELECT DISTINCT ae.user_id
                  FROM application_events ae
                  JOIN sar_intake si ON si.user_id = ae.user_id
                 WHERE ae.event_type = 'session.restored'
                   AND si.verified_at IS NOT NULL
                   AND ae.created_at >= si.verified_at
                   AND (si.closed_at IS NULL OR ae.created_at <= si.closed_at)
                   AND ae.user_id IS NOT NULL
                """
            )
        )
    ).all()
    return [r[0] if isinstance(r[0], uuid.UUID) else uuid.UUID(str(r[0])) for r in rows]


async def check_I18_legal_hold_supersedes_sar(db: AsyncSession) -> list[uuid.UUID]:
    """I18: when a session has ``custody='legal_hold'`` AND a SAR fast-track
    purge audit row exists for that session, the legal hold lost — a
    GDPR Art. 17(3)(b)/(e) breach (a SAR cannot override active
    litigation). Lawyer memo §4(a). Adversarial v3.9 §C.
    """
    rows = (
        await db.execute(
            text(
                """
                WITH sar_purges AS (
                    SELECT ae.session_id, ae.created_at AS purged_at
                      FROM application_events ae
                     WHERE ae.event_type = 'session.purge_committed'
                       AND ae.content ->> 'trigger' = 'sar_priority'
                       AND ae.session_id IS NOT NULL
                ),
                holds_set AS (
                    SELECT ae.session_id, MAX(ae.created_at) AS held_at
                      FROM application_events ae
                     WHERE ae.event_type = 'legal_hold.set'
                       AND ae.session_id IS NOT NULL
                     GROUP BY ae.session_id
                ),
                holds_cleared AS (
                    SELECT ae.session_id, MAX(ae.created_at) AS cleared_at
                      FROM application_events ae
                     WHERE ae.event_type = 'legal_hold.cleared'
                       AND ae.session_id IS NOT NULL
                     GROUP BY ae.session_id
                )
                SELECT sp.session_id
                  FROM sar_purges sp
                  JOIN holds_set hs ON hs.session_id = sp.session_id
             LEFT JOIN holds_cleared hc ON hc.session_id = sp.session_id
                 WHERE hs.held_at < sp.purged_at
                   AND (hc.cleared_at IS NULL OR hc.cleared_at >= sp.purged_at)
                """
            )
        )
    ).all()
    return [r[0] if isinstance(r[0], uuid.UUID) else uuid.UUID(str(r[0])) for r in rows]


# ─── Tier 3 — Structural / cross-system (pinned by tests, NOT this runner) ──


STRUCTURAL_TEST_ENFORCED: tuple[tuple[str, str], ...] = (
    (
        "I5",
        "Test: src/tests/unit/sessions/purge/test_purge_contracts.py:"
        "test_legal_hold_audit (currently @pytest.mark.skip pending "
        "PR-E impl). The contract is: a session that was ever "
        "custody='legal_hold' MUST have either (a) a 'legal_hold.cleared' "
        "audit row preceding any purge, OR (b) no purge audit row. "
        "Cannot be a SQL probe because the claim is about historical log "
        "shape, not current state.",
    ),
    (
        "I6",
        "Test: src/tests/unit/sessions/purge/test_purge_contracts.py:"
        "test_user_purge_claim_arbitration (currently @pytest.mark.skip "
        "pending PR-E impl). Two concurrent invocations of "
        "purge_one_session for the same session_id produce exactly one "
        "purge_attempts increment per claim cycle (Adversarial v3.9 #19).",
    ),
    (
        "I7",
        "Test: src/tests/unit/sessions/purge/test_purge_structural_invariants.py:"
        "test_commit_phase_c_rechecks_is_deleted. Asserts the SQL string "
        "in commit.commit_purge contains 'is_deleted' and 'FOR UPDATE'.",
    ),
    (
        "I8",
        "Test: src/tests/unit/sessions/purge/test_purge_structural_invariants.py:"
        "test_orm_guard_blocks_inserts_during_user_purge. Asserts the "
        "before_insert listener registered by orm_guards.py raises "
        "PurgeBlockedError when users.is_purging=true.",
    ),
    (
        "I9",
        "Audit job: ii_agent.sessions.purge.reconcile_providers."
        "reconcile_openai_files. Lists provider artefacts older than the "
        "configured horizon and diffs against chat_provider_files. "
        "Cannot be a local probe because the source of truth is the "
        "external provider's API. Pinned by "
        "src/tests/unit/sessions/purge/test_reconcile_providers.py.",
    ),
    (
        "I17",
        "Deployment-config check: ii_agent.sessions.purge.check_runner."
        "assert_cleanup_uses_primary_db. Invoked from app/lifespan.py at "
        "startup. Validates that no replica engine attribute has been "
        "introduced on ii_agent.core.db.base without upgrading the "
        "function. Cannot be a SQL probe because it is about "
        "connection-string topology, not row contents.",
    ),
)
"""Invariants enforced by code structure, type system, deployment config,
or external reconciliation.

Format: ``(invariant_id, pinning_test_or_artefact_description)``. Adding
an entry here REQUIRES a corresponding test that fails when the contract
is violated. An invariant in this tier with no test is a gap."""


# ─── Catalogue (the only public surface of this module) ─────────────────────


DB_CHECKABLE: tuple[_CheckFn, ...] = (
    check_I2_dead_letter_consistency,
    check_I3_is_purging_blocks_new_sessions,
    check_I4_art17_strip_unattributable,
    check_I11_no_pii_keys_in_stripped_rows,
    check_I12_sar_preempts_grace,
    check_I13_sar_audit_fields_complete,
    check_I15_retention_exception_disclosed,
    check_I16_restore_blocked_during_active_sar,
    check_I18_legal_hold_supersedes_sar,
)
"""SQL probes the nightly runner executes. Each function returns a list of
violating row UUIDs; an empty list is a pass. The runner pages on any
non-empty result OR any unexpected exception."""


# Back-compat alias. The runner historically imported ``ALL_INVARIANTS``;
# now points at the same DB_CHECKABLE tuple.
ALL_INVARIANTS = DB_CHECKABLE


__all__ = [
    "ALL_INVARIANTS",
    "DB_CHECKABLE",
    "SCHEMA_ENFORCED",
    "STRUCTURAL_TEST_ENFORCED",
    "check_I2_dead_letter_consistency",
    "check_I3_is_purging_blocks_new_sessions",
    "check_I4_art17_strip_unattributable",
    "check_I11_no_pii_keys_in_stripped_rows",
    "check_I12_sar_preempts_grace",
    "check_I13_sar_audit_fields_complete",
    "check_I15_retention_exception_disclosed",
    "check_I16_restore_blocked_during_active_sar",
    "check_I18_legal_hold_supersedes_sar",
]
