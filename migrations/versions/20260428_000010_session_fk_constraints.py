"""PR-C — add missing FK constraints on session_id / task_id / audit user_id.

Pattern: each constraint is added with ``NOT VALID`` (skips the full-table
scan and only takes a brief ShareRowExclusiveLock) and then validated in
a separate statement (`VALIDATE CONSTRAINT`, no table rewrite, allows
concurrent reads/writes).

Design: docs/design-docs/session-lifecycle-and-data-custody.md §3.1
(v3.7 audit-FK clauses included). Closes pre-flip gate #3.

Revision ID: 20260428_000010
Revises: 20260427_000009
Create Date: 2026-04-28
"""

from alembic import op


revision = "20260428_000010"
down_revision = "20260427_000009"
branch_labels = None
depends_on = None


# ---- (table, column, ref_table, ref_col, on_delete, constraint_name) ----
# Unconstrained UUID `session_id` columns + task_logs.task_id +
# audit-row user_id columns (§3.1 v3.7).
#
# IMPORTANT: ``application_events.session_id`` and
# ``credit_transactions.session_id`` are intentionally NOT FK-constrained.
# These are FORENSIC audit references that MUST survive the deletion of the
# referenced session row — that is the entire point of the
# ``session.purge_committed`` audit event (logged immediately before the
# session row is DELETEd in commit.py phase-c). Adding even ``ON DELETE
# SET NULL`` would nullify the session_id column at exactly the moment
# the audit row becomes useful, breaking I19 idempotency (which queries
# ``application_events WHERE session_id=:sid``) and erasing the billing
# audit trail required by the lawyer memo §5. Leaving these as
# unconstrained UUID columns is the correct design.
_SESSION_FKS = [
    # CASCADE — session is the natural parent
    ("run_tasks", "session_id", "sessions", "id", "CASCADE", "fk_run_tasks_session_id"),
    (
        "agent_run_messages",
        "session_id",
        "sessions",
        "id",
        "CASCADE",
        "fk_agent_run_messages_session_id",
    ),
    (
        "agent_sandboxes",
        "session_id",
        "sessions",
        "id",
        "CASCADE",
        "fk_agent_sandboxes_session_id",
    ),
    (
        "chat_messages",
        "session_id",
        "sessions",
        "id",
        "CASCADE",
        "fk_chat_messages_session_id",
    ),
    (
        "chat_summaries",
        "session_id",
        "sessions",
        "id",
        "CASCADE",
        "fk_chat_summaries_session_id",
    ),
    (
        "chat_provider_containers",
        "session_id",
        "sessions",
        "id",
        "CASCADE",
        "fk_chat_provider_containers_session_id",
    ),
    (
        "chat_provider_files",
        "session_id",
        "sessions",
        "id",
        "CASCADE",
        "fk_chat_provider_files_session_id",
    ),
]

# task_logs.task_id → run_tasks.id (CASCADE) — the §1 doc-quoted "62 orphans"
_TASK_LOG_FK = (
    "task_logs",
    "task_id",
    "run_tasks",
    "id",
    "CASCADE",
    "fk_task_logs_task_id",
)

# Audit-table user_id columns (§3.1 v3.7).  These MUST be SET NULL so that
# the §16 user-purge PII strip nullifies the link without violating NOT NULL.
_AUDIT_USER_FKS = [
    (
        "credit_transactions",
        "user_id",
        "users",
        "id",
        "SET NULL",
        "fk_credit_transactions_user_id",
    ),
    (
        "application_events",
        "user_id",
        "users",
        "id",
        "SET NULL",
        "fk_application_events_user_id",
    ),
]


def _add_not_valid(
    table: str, col: str, ref_table: str, ref_col: str, on_delete: str, name: str
) -> None:
    op.execute(
        f"ALTER TABLE {table} "
        f"ADD CONSTRAINT {name} FOREIGN KEY ({col}) "
        f"REFERENCES {ref_table}({ref_col}) ON DELETE {on_delete} NOT VALID"
    )


def _validate(table: str, name: str) -> None:
    op.execute(f"ALTER TABLE {table} VALIDATE CONSTRAINT {name}")


def _drop_constraint_if_exists(table: str, name: str) -> None:
    op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {name}")


def upgrade() -> None:
    # 1. Pre-clean orphans for tables we're about to constrain with VALIDATE.
    #    For session_id columns, orphans are operationally improbable (CASCADE
    #    semantics already informally implemented by the cleanup pipeline),
    #    but we DELETE defensively so VALIDATE CONSTRAINT cannot fail.
    op.execute("DELETE FROM task_logs WHERE task_id NOT IN (SELECT id FROM run_tasks)")
    for table, col, ref_table, ref_col, _on_delete, _name in _SESSION_FKS + [_TASK_LOG_FK]:
        op.execute(
            f"DELETE FROM {table} "
            f"WHERE {col} IS NOT NULL AND {col} NOT IN (SELECT {ref_col} FROM {ref_table})"
        )

    # 2. Make audit user_id columns nullable so SET NULL is feasible.
    #    application_events.user_id is already nullable; credit_transactions.user_id is NOT NULL.
    op.execute("ALTER TABLE credit_transactions ALTER COLUMN user_id DROP NOT NULL")

    # 3. Pre-clean audit user_id orphans, then add SET NULL FKs.
    for table, col, ref_table, ref_col, _on_delete, _name in _AUDIT_USER_FKS:
        op.execute(
            f"UPDATE {table} SET {col} = NULL "
            f"WHERE {col} IS NOT NULL AND {col} NOT IN (SELECT {ref_col} FROM {ref_table})"
        )

    # 4. Idempotency: drop any pre-existing constraint with the same name
    #    before re-adding (informal manual-fix or partial prior run).
    for table, _col, _ref_table, _ref_col, _on_delete, name in _SESSION_FKS:
        _drop_constraint_if_exists(table, name)
    _drop_constraint_if_exists(_TASK_LOG_FK[0], _TASK_LOG_FK[5])
    for table, _col, _ref_table, _ref_col, _on_delete, name in _AUDIT_USER_FKS:
        _drop_constraint_if_exists(table, name)

    # 5. Add all FKs as NOT VALID (cheap), then VALIDATE in a second pass.
    for table, col, ref_table, ref_col, on_delete, name in _SESSION_FKS:
        _add_not_valid(table, col, ref_table, ref_col, on_delete, name)
    _add_not_valid(*_TASK_LOG_FK)
    for table, col, ref_table, ref_col, on_delete, name in _AUDIT_USER_FKS:
        _add_not_valid(table, col, ref_table, ref_col, on_delete, name)

    for table, _col, _ref_table, _ref_col, _on_delete, name in _SESSION_FKS:
        _validate(table, name)
    _validate(_TASK_LOG_FK[0], _TASK_LOG_FK[5])
    for table, _col, _ref_table, _ref_col, _on_delete, name in _AUDIT_USER_FKS:
        _validate(table, name)


def downgrade() -> None:
    for table, _col, _ref_table, _ref_col, _on_delete, name in _AUDIT_USER_FKS:
        _drop_constraint_if_exists(table, name)
    _drop_constraint_if_exists(_TASK_LOG_FK[0], _TASK_LOG_FK[5])
    for table, _col, _ref_table, _ref_col, _on_delete, name in _SESSION_FKS:
        _drop_constraint_if_exists(table, name)

    # Note: we do NOT restore credit_transactions.user_id NOT NULL on downgrade
    # because nulled rows may exist by the time downgrade is run.
