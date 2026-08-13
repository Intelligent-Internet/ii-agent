"""Periodic invariants check — design contract `test_invariants_in_prod.py`.

Spec: ``docs/design-docs/session-lifecycle-and-data-custody.md`` §2.3
("PR-E lands the nightly job that runs the implemented checks against
staging and pages on any non-empty result").

Run modes
---------
* **CI (per PR)** — runs against the local stack DB if the host can reach
  it (otherwise auto-skips). Cheap predicates only; full sweep < 5 s.
* **Nightly (staging)** — same test, run from a scheduled GitHub Actions /
  cron job pointed at staging via ``DATABASE_URL`` override. Non-zero exit
  pages the on-call rota via the standard Prometheus alert wired off the
  same gauge series (§6.1).

Failure semantics
-----------------
Any DB-checkable invariant returning ≥1 violating row, or any unexpected
exception during a check, fails the test. Skipped-structural invariants
do NOT fail the test — they are policed by structural tests / deployment
guards, not this runner.

The full report is included in the assertion message so log-scrapers can
emit the offending row UUIDs to the alert payload.
"""

from __future__ import annotations

import os
import socket
from pathlib import Path
from urllib.parse import urlparse

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


_STACK_ENV_FILE = Path(__file__).resolve().parents[3] / "docker" / ".stack.env.local"


def _load_stack_env_if_present() -> None:
    """Best-effort: source ``docker/.stack.env.local`` so a developer can
    run this test against the local stack from the host without exporting
    every var manually."""
    if not _STACK_ENV_FILE.exists():
        return
    for raw in _STACK_ENV_FILE.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())
    db_url = os.environ.get("DATABASE_URL", "")
    if "@postgres:" in db_url:
        host_port = os.environ.get("POSTGRES_PORT", "5433")
        os.environ["DATABASE_URL"] = db_url.replace("@postgres:5432", f"@localhost:{host_port}")


def _db_reachable() -> bool:
    raw = os.environ.get("DATABASE_URL")
    if not raw:
        return False
    parsed = urlparse(raw.replace("postgresql+asyncpg://", "postgresql://"))
    if not parsed.hostname:
        return False
    port = parsed.port or 5432
    try:
        with socket.create_connection((parsed.hostname, port), timeout=2):
            return True
    except OSError:
        return False


_load_stack_env_if_present()


async def test_all_invariants_in_prod() -> None:
    """Run every invariant in ``ALL_INVARIANTS`` and fail on any non-pass.

    The assertion message lists every failed / errored invariant with the
    first 50 offending row UUIDs — sufficient to triage from the alert
    without re-running the query.
    """
    if not _db_reachable():
        pytest.skip(
            "DATABASE_URL not set or host unreachable. "
            "This test runs in CI / nightly cron with DB access; locally, "
            "bring the stack up (`scripts/stack_control.sh start`) first."
        )

    # Imported lazily so the auto-skip path above doesn't require the full
    # Settings stack to import successfully.
    from ii_agent.core.db.base import get_db_session_local
    from ii_agent.sessions.purge.check_runner import (
        InvariantStatus,
        run_all_invariants,
    )

    async with get_db_session_local() as db:
        report = await run_all_invariants(db)

    paging = [o for o in report.outcomes if o.is_paging]
    if paging:
        lines = [report.summary(), ""]
        for outcome in paging:
            if outcome.status == InvariantStatus.FAIL:
                lines.append(
                    f"  FAIL {outcome.name}: {len(outcome.violating_rows)} "
                    f"violating row(s) (first {len(outcome.violating_rows)} shown)"
                )
                lines.extend(f"    - {row}" for row in outcome.violating_rows)
            else:
                lines.append(f"  ERROR {outcome.name}: {outcome.error_message}")
        pytest.fail("\n".join(lines))

    assert report.exit_code == 0, report.summary()
