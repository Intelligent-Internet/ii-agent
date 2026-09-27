"""Runner for the §2.3 lifecycle-invariants nightly job.

Design contract: ``docs/design-docs/session-lifecycle-and-data-custody.md`` §2.3.

After the v3.10 hardening pass (migration 20260429_000011) the 19
invariants in :mod:`ii_agent.sessions.purge.invariants` partition into
**three** tiers:

  * **SCHEMA_ENFORCED** — physically rejected by CHECK / UNIQUE / TRIGGER
    in the database. NOT executed by this runner; the invariant cannot
    be violated on a row that was successfully written.
  * **DB_CHECKABLE** — cheap data-shape predicates against live tables.
    Return a list of violating row UUIDs. Empty list = pass. The runner
    iterates :data:`ALL_INVARIANTS` (an alias for
    :data:`invariants.DB_CHECKABLE`) and pages on any non-empty result
    or unexpected exception.
  * **STRUCTURAL_TEST_ENFORCED** — code-shape, deployment-config, or
    external-reconciliation contracts pinned by named tests. NOT
    executed by this runner; the corresponding test suite is the
    enforcement point. The previous "stub raises NotImplementedError"
    pattern was removed because it conflated "checkable in principle"
    with "checked in practice"; the SKIPPED_STRUCTURAL state is kept
    only as a defensive landing pad in case a future check still
    raises.

The runner returns a :class:`InvariantReport` with one
:class:`InvariantOutcome` per invariant.  Three terminal states:

  - ``PASS`` — DB-checkable, empty result.
  - ``FAIL`` — DB-checkable, **at least one** violating row. **PAGE.**
  - ``SKIPPED_STRUCTURAL`` — :class:`NotImplementedError` raised by the
    check; not a failure on its own, but the corresponding code-structure
    test / deployment guard is the actual contract.
  - ``ERROR`` — unexpected exception (e.g. SQL syntax error after a
    schema change). **PAGE.** Treated as a failure by exit-code mapping.

Nonconformance handling (per design §6.1 / §2.3):

  * Any ``FAIL`` or ``ERROR`` outcome causes :func:`run_all_invariants` to
    return a non-zero ``exit_code``. Both the Prometheus ``invariant_*``
    gauge family AND a paging alert wired off the same gauge are the
    operational backstop. The CLI / pytest entry-point exits with that
    code so cron / CI fail loudly.
  * The full report (including offending row UUIDs, capped at 50 per
    invariant for log hygiene) is logged at ``ERROR`` level on any
    non-pass outcome.
"""

from __future__ import annotations

import enum
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.sessions.purge.invariants import ALL_INVARIANTS

logger = logging.getLogger(__name__)


# Cap rows logged per invariant to keep alert payloads bounded.
_MAX_ROWS_LOGGED_PER_INVARIANT = 50


class InvariantStatus(enum.StrEnum):
    """Terminal state for a single invariant check."""

    PASS = "PASS"
    FAIL = "FAIL"
    SKIPPED_STRUCTURAL = "SKIPPED_STRUCTURAL"
    ERROR = "ERROR"


@dataclass(frozen=True)
class InvariantOutcome:
    """Result of running one ``check_I*`` predicate."""

    name: str
    status: InvariantStatus
    violating_rows: tuple[uuid.UUID, ...] = ()
    error_message: str | None = None
    elapsed_seconds: float = 0.0

    @property
    def is_paging(self) -> bool:
        """Does this outcome merit a page (FAIL or ERROR)?"""
        return self.status in (InvariantStatus.FAIL, InvariantStatus.ERROR)


@dataclass(frozen=True)
class InvariantReport:
    """Aggregate result across all invariants in :data:`ALL_INVARIANTS`."""

    outcomes: tuple[InvariantOutcome, ...]
    total_elapsed_seconds: float
    started_at_unix: float = field(default_factory=time.time)

    @property
    def failed(self) -> tuple[InvariantOutcome, ...]:
        return tuple(o for o in self.outcomes if o.status == InvariantStatus.FAIL)

    @property
    def errored(self) -> tuple[InvariantOutcome, ...]:
        return tuple(o for o in self.outcomes if o.status == InvariantStatus.ERROR)

    @property
    def skipped(self) -> tuple[InvariantOutcome, ...]:
        return tuple(o for o in self.outcomes if o.status == InvariantStatus.SKIPPED_STRUCTURAL)

    @property
    def passed(self) -> tuple[InvariantOutcome, ...]:
        return tuple(o for o in self.outcomes if o.status == InvariantStatus.PASS)

    @property
    def exit_code(self) -> int:
        """0 iff every DB-checkable invariant passed.

        Skipped (structural) invariants do NOT influence the exit code —
        those are policed by tests / deployment guards, not this runner.
        """
        return 1 if (self.failed or self.errored) else 0

    def summary(self) -> str:
        return (
            f"invariants: passed={len(self.passed)} "
            f"failed={len(self.failed)} errored={len(self.errored)} "
            f"skipped_structural={len(self.skipped)} "
            f"elapsed={self.total_elapsed_seconds:.2f}s"
        )


_CheckFn = Callable[[AsyncSession], Awaitable[list[uuid.UUID]]]


async def _run_one(check: _CheckFn, db: AsyncSession) -> InvariantOutcome:
    name = check.__name__
    start = time.monotonic()
    try:
        rows = await check(db)
    except NotImplementedError:
        # Roll back defensively in case the structural check left the
        # session in an aborted state before raising.
        try:
            await db.rollback()
        except Exception:  # noqa: BLE001
            pass
        return InvariantOutcome(
            name=name,
            status=InvariantStatus.SKIPPED_STRUCTURAL,
            elapsed_seconds=time.monotonic() - start,
        )
    except Exception as exc:  # noqa: BLE001 — runner must catalogue every failure
        logger.exception("invariant %s raised unexpectedly", name)
        # Critical: a failed query (e.g. UndefinedColumn) leaves the
        # AsyncSession in an aborted state where every subsequent
        # statement raises ``InFailedSQLTransaction``. Rolling back here
        # isolates the failure to this one invariant; without it, one
        # bad query cascades the whole report into ERROR.
        try:
            await db.rollback()
        except Exception:  # noqa: BLE001
            pass
        return InvariantOutcome(
            name=name,
            status=InvariantStatus.ERROR,
            error_message=f"{type(exc).__name__}: {exc}",
            elapsed_seconds=time.monotonic() - start,
        )

    if rows:
        capped = tuple(rows[:_MAX_ROWS_LOGGED_PER_INVARIANT])
        return InvariantOutcome(
            name=name,
            status=InvariantStatus.FAIL,
            violating_rows=capped,
            elapsed_seconds=time.monotonic() - start,
        )
    return InvariantOutcome(
        name=name,
        status=InvariantStatus.PASS,
        elapsed_seconds=time.monotonic() - start,
    )


async def run_all_invariants(db: AsyncSession) -> InvariantReport:
    """Execute every invariant in :data:`ALL_INVARIANTS` against ``db``.

    The runner does NOT open or commit a transaction — every check is a
    plain SELECT that AsyncSession can execute outside a tx. The caller
    is responsible for the session lifecycle (use
    ``get_db_session_local()`` for ad-hoc operator runs).
    """
    overall_start = time.monotonic()
    outcomes: list[InvariantOutcome] = []
    for check in ALL_INVARIANTS:
        outcome = await _run_one(check, db)
        outcomes.append(outcome)
        if outcome.status == InvariantStatus.FAIL:
            logger.error(
                "INVARIANT FAIL %s: %d violating row(s) (first %d shown): %s",
                outcome.name,
                len(outcome.violating_rows),
                len(outcome.violating_rows),
                [str(r) for r in outcome.violating_rows],
            )
        elif outcome.status == InvariantStatus.ERROR:
            logger.error(
                "INVARIANT ERROR %s: %s",
                outcome.name,
                outcome.error_message,
            )
    total = time.monotonic() - overall_start
    return InvariantReport(outcomes=tuple(outcomes), total_elapsed_seconds=total)


def assert_cleanup_uses_primary_db() -> None:
    """I17 enforcement (deployment-config check).

    Validates that the grace-purge / orphan-cleanup loops bind to the
    PRIMARY database engine, not a read replica. A replica-bound sweep
    would (a) miss recently-deleted sessions due to replication lag —
    leaving GDPR Art. 17 deadlines silently breached — and (b) attempt
    DELETEs against a read-only connection, raising at runtime.

    Current contract: this codebase has a SINGLE async engine
    (``ii_agent.core.db.base.get_engine``); no reader split exists. The
    assertion is therefore that no module-level replica engine has been
    introduced without updating this function. The sentinel is the
    absence of any ``_reader_engine`` / ``_replica_engine`` attribute on
    the db module.

    When a read replica IS introduced in future, this function MUST be
    upgraded to inspect ``Cleanup.bind`` (or equivalent) and verify the
    resolved URL matches the writer's. Ignoring that upgrade would
    silently downgrade I17 to paper-only.

    Raises:
        AssertionError: if a replica engine attribute appears on the
            shared db module but this function has not been updated.

    Returns:
        None on pass. Called from app startup; failure should crash the
        process (fail-loud is the correct posture for compliance gates).
    """
    from ii_agent.core.db import base as db_base

    suspect_attrs = [
        name
        for name in dir(db_base)
        if name.startswith("_")
        and ("reader" in name.lower() or "replica" in name.lower())
        and "engine" in name.lower()
    ]
    if suspect_attrs:
        raise AssertionError(
            "I17 violation candidate: read-replica engine attribute(s) "
            f"detected on ii_agent.core.db.base — {suspect_attrs!r}. "
            "assert_cleanup_uses_primary_db must be upgraded to "
            "explicitly verify the cleanup loop binds to the writer "
            "engine before this code path can be considered I17-safe."
        )


__all__ = [
    "InvariantOutcome",
    "InvariantReport",
    "InvariantStatus",
    "assert_cleanup_uses_primary_db",
    "run_all_invariants",
]
