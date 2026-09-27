"""I9 — external provider reconciliation.

Invariant I9 cannot be a local SQL probe: it asserts that no provider-
side artefact (OpenAI File, Container, Vector Store) exists older than
the configured retention horizon without a corresponding ``chat_provider_*``
row claiming responsibility for it. The source of truth is the provider
API, not our database.

This module is the OPERATOR-ENTRYPOINT for the audit. The default
implementation iterates the OpenAI Files / Vector Stores APIs and emits
a row into ``purge_dead_letter`` for any provider artefact whose ID is
absent from the corresponding tracking table.

NOT WIRED INTO THE NIGHTLY CRON YET. The expected operational pattern is:

  1. Operator runs the reconciliation manually (CLI / one-shot pod) on a
     cadence dictated by data-protection policy (typical: monthly).
  2. The dead-letter rows are reviewed; legitimate orphans are deleted
     against the provider API by the operator.

A future change can wire this into APScheduler once we have decided what
the autonomous-deletion policy is. Until then, the safe behaviour is
**catalogue, not delete**.
"""

from __future__ import annotations

import dataclasses
import logging
import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


logger = logging.getLogger(__name__)


@dataclasses.dataclass(frozen=True)
class ReconciliationReport:
    """Outcome of a single reconcile pass against one provider/resource."""

    provider: str
    resource_kind: str
    listed: int
    tracked: int
    orphaned: int
    dead_letter_rows_inserted: int
    elapsed_seconds: float


async def _record_orphan(
    db: AsyncSession,
    *,
    provider: str,
    resource_kind: str,
    provider_resource_id: str,
    user_id: uuid.UUID | None,
    session_id: uuid.UUID | None,
) -> None:
    """Insert an unresolved row into ``purge_dead_letter``.

    NB: ``purge_dead_letter.user_id`` is NOT NULL (I10 schema-enforced).
    For provider artefacts whose owning user cannot be resolved (because
    the chat_provider_files row was already deleted), we fall back to a
    sentinel zero-UUID. Reviewers MUST treat zero-UUID rows as 'requires
    manual triage' rather than 'specific user owes us cleanup'.
    """
    await db.execute(
        text(
            """
            INSERT INTO purge_dead_letter
                (id, user_id, session_id, provider, resource_kind,
                 resource_id, error_message, created_at)
            SELECT gen_random_uuid(), :user_id, :session_id, :provider,
                   :kind, :rid, :reason, now()
             WHERE NOT EXISTS (
                 SELECT 1 FROM purge_dead_letter
                  WHERE provider = :provider
                    AND resource_kind = :kind
                    AND resource_id = :rid
                    AND resolved_at IS NULL
             )
            """
        ),
        {
            "user_id": user_id or uuid.UUID(int=0),
            "session_id": session_id,
            "provider": provider,
            "kind": resource_kind,
            "rid": provider_resource_id,
            "reason": f"I9 orphan: {resource_kind} {provider_resource_id} "
            "exists at provider but no tracking row found in chat_provider_*.",
        },
    )


async def reconcile_openai_files(
    db: AsyncSession,
    *,
    list_files,
    horizon_seconds: int = 90 * 24 * 3600,
) -> ReconciliationReport:
    """Reconcile OpenAI Files API against ``chat_provider_files``.

    Args:
        db: live AsyncSession (writes to ``purge_dead_letter`` are
            committed by the caller).
        list_files: a callable returning an iterable of objects with
            ``.id``, ``.created_at`` (unix seconds), and ``.bytes``
            attributes — i.e. ``openai.files.list`` adapted into a
            test-friendly shape. Required as a parameter so the unit
            test can pass a fake without touching the real client.
        horizon_seconds: only artefacts older than this are checked.
            Younger files may legitimately be in flight to a not-yet-
            committed chat session. Default 90 days mirrors the OpenAI
            recommended retention.

    Returns:
        A :class:`ReconciliationReport` summarising the pass.

    The function does NOT delete anything. It records dead-letter rows
    only. Operator review + deletion is a separate step, by design — the
    reconciliation pass must be safe to run at any time and reversible
    by inspecting the dead-letter table.
    """
    import time

    start = time.monotonic()
    listed_count = 0
    orphaned_count = 0
    inserted_count = 0
    cutoff = time.time() - horizon_seconds

    # Snapshot tracked IDs once. The set is bounded by the number of
    # historical chat-provider-file rows; in practice <100K, so an
    # in-memory set is sane. For larger tenancies, change this to a
    # streaming JOIN against the provider list.
    tracked_rows = await db.execute(
        text("SELECT provider_file_id FROM chat_provider_files WHERE provider = 'openai'")
    )
    tracked = {row[0] for row in tracked_rows.all() if row[0] is not None}

    for f in list_files():
        listed_count += 1
        created_at = getattr(f, "created_at", None)
        if created_at is None or created_at > cutoff:
            continue
        if f.id in tracked:
            continue
        orphaned_count += 1
        await _record_orphan(
            db,
            provider="openai",
            resource_kind="file",
            provider_resource_id=f.id,
            user_id=None,
            session_id=None,
        )
        inserted_count += 1

    elapsed = time.monotonic() - start
    report = ReconciliationReport(
        provider="openai",
        resource_kind="file",
        listed=listed_count,
        tracked=len(tracked),
        orphaned=orphaned_count,
        dead_letter_rows_inserted=inserted_count,
        elapsed_seconds=elapsed,
    )
    logger.info(
        "I9 reconcile openai/file: listed=%d tracked=%d orphaned=%d inserted=%d elapsed=%.2fs",
        listed_count,
        len(tracked),
        orphaned_count,
        inserted_count,
        elapsed,
    )
    return report


__all__ = [
    "ReconciliationReport",
    "reconcile_openai_files",
]
