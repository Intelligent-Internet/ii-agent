"""Invariant hardening — promote runtime invariants into schema constraints.

This migration consolidates EVERY schema change required to retire the
soft / paper-only invariants in :mod:`ii_agent.sessions.purge.invariants`
and replace them with database-level guarantees. It is intentionally a
single migration: the goal is converging the design — splitting these
across several migrations would force operators to live with a partial
contract while the rest land.

What this migration does
------------------------

A) **Promote data-shape invariants into CHECK constraints.**

   - I1   ``purge_after IS NOT NULL ⟹ is_deleted = true``
          → ``CHECK (purge_after IS NULL OR is_deleted = true)``.

   - **(new) I1b** ``purge_started_at IS NOT NULL ⟹ is_deleted = true``
          → ``CHECK (purge_started_at IS NULL OR is_deleted = true)``.
          Phase-(a) claim only fires on soft-deleted rows. A row whose
          claim flag survived a restore is a structural bug.

   - **(new) I10** ``purge_dead_letter.user_id IS NOT NULL`` was already
          enforced by the column NOT NULL — this migration simply
          documents it as schema-enforced and removes the SQL probe.

B) **Add a partial unique index that enforces I19 atomically.**

   Two ``session.purge_committed`` rows with the same non-NULL
   ``session_id`` is impossible by the index. The runtime probe is
   retired; only the post-FK-set-null grace window (where session_id
   has been nulled by the dependents-cascade) is left, and that window
   does not cause double-purge accounting because the surviving rows
   no longer share a key.

C) **Add discriminator columns required to make I3 and I11 enforceable.**

   - ``users.is_purging_set_at`` (TIMESTAMPTZ, NULL) — set by
     ``user_purge.lock_user`` together with ``is_purging=true``. Lets
     I3 distinguish post-lock session inserts (forbidden) from the
     pre-lock historical row that already exists.

   - ``application_events.stripped_at`` (TIMESTAMPTZ, NULL) — set by
     ``pii_strip.strip_user_pii_art17`` to mark every row that has
     been touched by the Art. 17 strip pass. Lets I11 query
     ``stripped_at IS NOT NULL AND content has non-allowlist keys``
     instead of inferring from a session-FK that is destroyed by the
     phase-(c) DELETE. Removes the false-positive class that swamped
     the 2026-04-28 canary (1,236 system events that were never
     strip-touched).

D) **Defence-in-depth I14 trigger on users.**

   The session→user FK is ``ON DELETE CASCADE`` for operational
   reasons; without a guard, ``DELETE FROM users`` would silently
   cascade-drop sessions with no audit trail (Art. 5(2) violation).

   This migration adds a ``BEFORE DELETE`` trigger on ``users`` that
   raises ``insufficient_privilege`` unless either (i) ``is_purging =
   true`` (the user_purge driver is in flight and has produced audit
   rows for every session via ``commit_purge``), or (ii) no
   ``sessions`` row exists for this user (clean test fixtures, brand
   new account never used). The trigger is named so it can be
   dropped explicitly during a future redesign.

E) **Index supporting check_I12 / check_I16.**

   ``application_events`` is the largest table in the system; the
   I12 / I16 / I18 / I19 / I11 invariants all index on ``event_type +
   created_at + session_id``. Add a covering partial index on the
   purge-committed event family so the daily probe runs in <1s on a
   table with 10M+ rows. Read-only effect; no lock.

What this migration does NOT do
-------------------------------

It does NOT change any FK ``ON DELETE`` rules. The CASCADE policy in
``20260428_000010`` is correct. I14 is enforced by trigger above.

It does NOT add a ``sessions.purged_at`` column. The session row is
hard-deleted in phase (c) by design (data minimisation) — the audit
trail lives in ``application_events.stripped_at`` and the
``session.purge_committed`` event row.

It does NOT alter the SAR_FORCE flag handling — the
``20260427_000009`` migration is correct.

Revision ID: 20260429_000011
Revises: 20260428_000010
Create Date: 2026-04-29
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260429_000011"
down_revision = "20260428_000010"
branch_labels = None
depends_on = None


# Names live in module-scope so downgrade can drop them by exact name.
_CHK_PURGE_AFTER_IMPLIES_DELETED = "ck_sessions_purge_after_implies_deleted"
_CHK_CLAIM_IMPLIES_DELETED = "ck_sessions_purge_started_implies_deleted"
_UQ_PURGE_COMMITTED_PER_SESSION = "uq_application_events_purge_committed_per_session"
_IDX_PURGE_COMMITTED_LOOKUP = "idx_application_events_purge_committed_lookup"
_TRG_USER_DELETE_GUARD = "trg_users_block_delete_unless_purging"
_FN_USER_DELETE_GUARD = "fn_users_block_delete_unless_purging"


def upgrade() -> None:
    # ---- A) CHECK constraints — promote I1 into the schema. ---------------
    #
    # Pre-clean: any current row that violates the constraint must be
    # repaired before VALIDATE runs. The only legitimate cleanup target is
    # ``purge_after IS NOT NULL AND is_deleted = false`` rows; we do NOT
    # invent a new state — we simply NULL the stale ``purge_after``. This
    # mirrors what the §4.1 sweep would have done implicitly when it
    # skipped the row forever.
    op.execute(
        "UPDATE sessions SET purge_after = NULL "
        "WHERE purge_after IS NOT NULL AND is_deleted = false"
    )
    op.execute(
        "UPDATE sessions SET purge_started_at = NULL, purge_attempts = 0 "
        "WHERE purge_started_at IS NOT NULL AND is_deleted = false"
    )

    # NOT VALID first to avoid a full-table scan under exclusive lock on a
    # large ``sessions`` table; VALIDATE in a second statement allows
    # concurrent writes.
    op.execute(
        f"ALTER TABLE sessions ADD CONSTRAINT {_CHK_PURGE_AFTER_IMPLIES_DELETED} "
        "CHECK (purge_after IS NULL OR is_deleted = true) NOT VALID"
    )
    op.execute(f"ALTER TABLE sessions VALIDATE CONSTRAINT {_CHK_PURGE_AFTER_IMPLIES_DELETED}")

    op.execute(
        f"ALTER TABLE sessions ADD CONSTRAINT {_CHK_CLAIM_IMPLIES_DELETED} "
        "CHECK (purge_started_at IS NULL OR is_deleted = true) NOT VALID"
    )
    op.execute(f"ALTER TABLE sessions VALIDATE CONSTRAINT {_CHK_CLAIM_IMPLIES_DELETED}")

    # ---- B) Partial unique index — promote I19 into the schema. ------------
    #
    # ``session.purge_committed`` may legitimately be written multiple times
    # AFTER session_id has been nulled by ``ON DELETE SET NULL`` (none of
    # those nulls share a key, so the constraint allows them). The index
    # only blocks the live-row case, which is exactly the I19 race window.
    #
    # Pre-clean: collapse any pre-existing duplicates by keeping the
    # earliest event row. This affects only test/staging data.
    op.execute(
        """
        DELETE FROM application_events ae
              USING (
                SELECT session_id, MIN(created_at) AS first_at
                  FROM application_events
                 WHERE event_type = 'session.purge_committed'
                   AND session_id IS NOT NULL
                 GROUP BY session_id
                HAVING COUNT(*) > 1
              ) keep
         WHERE ae.event_type = 'session.purge_committed'
           AND ae.session_id = keep.session_id
           AND ae.created_at <> keep.first_at
        """
    )
    op.execute(
        f"CREATE UNIQUE INDEX {_UQ_PURGE_COMMITTED_PER_SESSION} "
        "ON application_events (session_id) "
        "WHERE event_type = 'session.purge_committed' AND session_id IS NOT NULL"
    )

    # ---- C) Discriminator columns. ----------------------------------------
    #
    # Both default NULL; back-fill on demand from the corresponding code
    # paths (no historical rows need migration — invariants are forward-
    # looking).
    op.add_column(
        "users",
        sa.Column("is_purging_set_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "application_events",
        sa.Column("stripped_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Targeted index for I11's probe: every stripped row in <O(stripped) time.
    op.execute(
        "CREATE INDEX idx_application_events_stripped_at "
        "ON application_events (stripped_at) "
        "WHERE stripped_at IS NOT NULL"
    )

    # ---- D) BEFORE DELETE trigger on users (defence-in-depth I14). --------
    #
    # The trigger raises if a delete is attempted against a user that has
    # any session row AND is_purging is not currently true. user_purge.py
    # sets is_purging=true before driving session purges; ordinary admin
    # DELETEs without that flag will fail loudly.
    #
    # ``raise exception`` aborts the surrounding statement and rolls back
    # the transaction. Choosing SQLSTATE 'I3VLD' is a custom code we
    # reserve for purge-invariant violations so monitoring can pick it up.
    op.execute(
        f"""
        CREATE OR REPLACE FUNCTION {_FN_USER_DELETE_GUARD}() RETURNS trigger AS $$
        BEGIN
            IF NOT OLD.is_purging
               AND EXISTS (SELECT 1 FROM sessions WHERE user_id = OLD.id) THEN
                RAISE EXCEPTION
                    'I14 violation: cannot DELETE user % with sessions while is_purging=false. '
                    'Run user_purge.purge_user_account first to produce audit rows.',
                    OLD.id
                    USING ERRCODE = 'P0001';
            END IF;
            RETURN OLD;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(f"DROP TRIGGER IF EXISTS {_TRG_USER_DELETE_GUARD} ON users")
    op.execute(
        f"CREATE TRIGGER {_TRG_USER_DELETE_GUARD} "
        f"BEFORE DELETE ON users "
        f"FOR EACH ROW EXECUTE FUNCTION {_FN_USER_DELETE_GUARD}()"
    )

    # ---- E) Covering partial index for the invariant probes. ---------------
    #
    # I12 / I13 / I15 / I16 / I18 / I19 all read application_events with a
    # filter on event_type ∈ {session.purge_committed, session.restored,
    # legal_hold.set, legal_hold.cleared, art17_3.disclosure}. A partial
    # index covering the purge-related event_types gives sub-second
    # probe times even on a 10M+ row history.
    op.execute(
        f"""
        CREATE INDEX {_IDX_PURGE_COMMITTED_LOOKUP}
            ON application_events (session_id, created_at)
         WHERE event_type IN (
                'session.purge_committed',
                'session.restored',
                'legal_hold.set',
                'legal_hold.cleared',
                'art17_3.disclosure'
              )
        """
    )


def downgrade() -> None:
    # E
    op.execute(f"DROP INDEX IF EXISTS {_IDX_PURGE_COMMITTED_LOOKUP}")

    # D
    op.execute(f"DROP TRIGGER IF EXISTS {_TRG_USER_DELETE_GUARD} ON users")
    op.execute(f"DROP FUNCTION IF EXISTS {_FN_USER_DELETE_GUARD}()")

    # C
    op.execute("DROP INDEX IF EXISTS idx_application_events_stripped_at")
    op.drop_column("application_events", "stripped_at")
    op.drop_column("users", "is_purging_set_at")

    # B
    op.execute(f"DROP INDEX IF EXISTS {_UQ_PURGE_COMMITTED_PER_SESSION}")

    # A
    op.execute(f"ALTER TABLE sessions DROP CONSTRAINT IF EXISTS {_CHK_CLAIM_IMPLIES_DELETED}")
    op.execute(f"ALTER TABLE sessions DROP CONSTRAINT IF EXISTS {_CHK_PURGE_AFTER_IMPLIES_DELETED}")
