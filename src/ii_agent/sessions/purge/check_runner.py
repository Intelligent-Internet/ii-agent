"""Runner for the §2.3 lifecycle-invariants nightly job.

Design contract: ``docs/design-docs/session-lifecycle-and-data-custody.md`` §2.3.

The 19 invariants in :mod:`ii_agent.sessions.purge.invariants` partition into:

  * **DB-checkable** (cheap data-shape predicates) — return a list of
    violating row UUIDs. Empty list = pass.
  * **Structural / cross-system** (I3, I5, I6, I7, I8, I9, I14, I17) —
    intentionally raise :class:`NotImplementedError` because the contract
    is enforced by code structure, deployment configuration, or external
    audit reconciliation rather than a SQL predicate. The runner skips
    these and records the skip reason in the report so an operator can
    confirm the corresponding test / deployment guard is in place.

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


__all__ = [
    "InvariantOutcome",
    "InvariantReport",
    "InvariantStatus",
    "run_all_invariants",
]
