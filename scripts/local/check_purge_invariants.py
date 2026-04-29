#!/usr/bin/env python3
"""Operator CLI: run the §2.3 lifecycle invariants against the live DB.

Companion to ``src/tests/integration/test_invariants_in_prod.py`` —
same runner, but invocable from a shell for ad-hoc audits or scheduled
cron without pytest.

Exit code 0 = every DB-checkable invariant passed; exit code 1 = at
least one failed or errored (PAGE per design §6.1). Skipped-structural
invariants do NOT influence the exit code.

Usage
-----
    # Against the local Docker stack (loads docker/.stack.env.local):
    scripts/local/check_purge_invariants.py

    # Against any other DB:
    DATABASE_URL=postgresql+asyncpg://... scripts/local/check_purge_invariants.py

    # Quiet (only print failures + summary; useful from cron):
    scripts/local/check_purge_invariants.py --quiet

    # JSON output for ingestion into log pipeline:
    scripts/local/check_purge_invariants.py --json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

# Make the in-tree package importable when run from source checkout.
_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "src"))

_STACK_ENV_FILE = _REPO_ROOT / "docker" / ".stack.env.local"


def _load_stack_env() -> None:
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


async def _run(quiet: bool, as_json: bool) -> int:
    from ii_agent.core.db.base import get_db_session_local
    from ii_agent.sessions.purge.check_runner import (
        InvariantStatus,
        run_all_invariants,
    )

    async with get_db_session_local() as db:
        report = await run_all_invariants(db)

    if as_json:
        payload = {
            "summary": report.summary(),
            "exit_code": report.exit_code,
            "elapsed_seconds": report.total_elapsed_seconds,
            "outcomes": [
                {
                    "name": o.name,
                    "status": o.status.value,
                    "violating_rows": [str(r) for r in o.violating_rows],
                    "error_message": o.error_message,
                    "elapsed_seconds": o.elapsed_seconds,
                }
                for o in report.outcomes
            ],
        }
        print(json.dumps(payload, indent=2))
        return report.exit_code

    if not quiet:
        for o in report.outcomes:
            tag = {
                InvariantStatus.PASS: "PASS",
                InvariantStatus.FAIL: "FAIL",
                InvariantStatus.SKIPPED_STRUCTURAL: "SKIP",
                InvariantStatus.ERROR: "ERR ",
            }[o.status]
            print(f"  {tag} {o.name} ({o.elapsed_seconds * 1000:.0f} ms)")

    for o in report.failed:
        print(
            f"FAIL {o.name}: {len(o.violating_rows)} violating row(s):",
            file=sys.stderr,
        )
        for row in o.violating_rows:
            print(f"  - {row}", file=sys.stderr)
    for o in report.errored:
        print(f"ERROR {o.name}: {o.error_message}", file=sys.stderr)

    print(report.summary())
    return report.exit_code


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quiet", action="store_true", help="Only print failures + summary.")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    args = parser.parse_args()
    _load_stack_env()
    return asyncio.run(_run(quiet=args.quiet, as_json=args.json))


if __name__ == "__main__":
    sys.exit(main())
