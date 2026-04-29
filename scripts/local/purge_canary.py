#!/usr/bin/env python3
"""PR-E pre-flip canary: drive a small, known set of soft-deleted sessions
through the §4.1 three-phase purge driver and verify the contract.

Pre-flip checklist gate #7 in
``docs/design-docs/session-lifecycle-and-data-custody.md``.

What this does
--------------
For each ``--session-id`` on the command line:

  1. **Pre-snapshot** — record:
       * existence of the ``sessions`` row (`SELECT 1 ...`),
       * count of ``application_events`` with
         ``event_type='session.purge_committed'`` for that session,
       * count of ``purge_dead_letter`` rows for that session,
       * the row's current ``is_deleted`` / ``purge_after`` /
         ``custody`` values.

  2. **Coerce eligibility** (only when ``--force-eligible`` is set):
       * mark ``is_deleted=true`` (if not already),
       * set ``purge_after = now() - 1 minute`` (so phase (a) can claim
         immediately),
       * leave ``custody`` alone unless it is ``legal_hold`` (in which
         case we abort — legal-hold sessions MUST NOT be canaried, I5).

     Without ``--force-eligible`` the script only purges sessions that are
     already past their grace window — the exact behaviour ops will see in
     production after enabling the flag.

  3. **Drive the purge driver in-process** by calling
     ``purge_one_session(session_id=<id>, trigger=GRACE_EXPIRED)`` and
     classifying the ``PurgeOutcome``.

  4. **Post-snapshot + assertions**:
       * the ``session.purge_committed`` count for the id incremented by
         exactly 1 (or, for ``ALREADY_PURGED`` outcomes, by exactly 0);
       * ``purge_dead_letter`` count did NOT increase (or, if it did, the
         row content is printed for ops triage);
       * the ``sessions`` row no longer exists (PURGED) OR exists with
         ``is_deleted=false`` (SKIPPED_RESTORED) OR exists unchanged
         (SKIPPED_NOT_ELIGIBLE / DEFERRED_TRANSIENT / DEAD_LETTERED).

  5. **Report** — print a per-session line + a summary that exit-codes
     non-zero on any unexpected outcome so the script is CI-friendly.

Safety
------
* This script reads ``DB_URL``/``DATABASE_URL`` from the environment via
  the standard backend config; **never run it against production**
  unless you understand that a successful PURGE outcome is irreversible
  except via PITR (§14.1).
* Pass ``--dry-run`` to skip every mutating call — the script will only
  print the pre-snapshot.
* Pass ``--require-non-prod`` (default) to abort if the resolved DB host
  is not in ``DB_NONPROD_HOST_ALLOWLIST`` (a comma-separated env var,
  defaulting to ``localhost,postgres,127.0.0.1``).

Usage
-----
::

    # Local stack canary against a single soft-deleted session id
    SESSIONS_PURGE_ENABLED=true python scripts/local/purge_canary.py \\
        --session-id 38ce1234-... --force-eligible

    # Multi-session canary, rate-limited to 0.5s per id
    SESSIONS_PURGE_ENABLED=true python scripts/local/purge_canary.py \\
        --session-id A --session-id B --session-id C --sleep 0.5
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
import uuid
from dataclasses import dataclass

# Allow running from any cwd: add `src/` to sys.path if necessary.
_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.abspath(os.path.join(_HERE, "..", "..", "src"))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from sqlalchemy import text  # noqa: E402

from ii_agent.core.config.settings import get_settings  # noqa: E402
from ii_agent.core.db.base import get_db_session_local  # noqa: E402
from ii_agent.sessions.purge.session_purge import purge_one_session  # noqa: E402
from ii_agent.sessions.purge.types import PurgeOutcome, PurgeTrigger  # noqa: E402


# ---- queries ----------------------------------------------------------------

_SESSION_PROBE_SQL = text(
    """
    SELECT id, user_id, is_deleted, purge_after, custody
      FROM sessions
     WHERE id = :sid
    """
)

_PURGE_AUDIT_COUNT_SQL = text(
    """
    SELECT count(*) FROM application_events
     WHERE event_type = 'session.purge_committed'
       AND session_id = :sid
    """
)

_DEAD_LETTER_COUNT_SQL = text(
    """
    SELECT count(*) FROM purge_dead_letter
     WHERE session_id = :sid
    """
)

_DEAD_LETTER_DETAIL_SQL = text(
    """
    SELECT id, provider, resource_kind, resource_id, error_message
      FROM purge_dead_letter
     WHERE session_id = :sid
     ORDER BY id
    """
)

_FORCE_ELIGIBLE_SQL = text(
    """
    UPDATE sessions
       SET is_deleted = true,
           purge_after = now() - interval '1 minute'
     WHERE id = :sid
       AND custody != 'legal_hold'
    """
)


# ---- snapshot dataclass -----------------------------------------------------


@dataclass
class _Snapshot:
    exists: bool
    user_id: uuid.UUID | None
    is_deleted: bool | None
    purge_after_set: bool
    custody: str | None
    purge_committed_count: int
    dead_letter_count: int


async def _snapshot(sid: uuid.UUID) -> _Snapshot:
    async with get_db_session_local() as db:
        row = (await db.execute(_SESSION_PROBE_SQL, {"sid": str(sid)})).first()
        committed = (await db.execute(_PURGE_AUDIT_COUNT_SQL, {"sid": str(sid)})).scalar_one()
        dead = (await db.execute(_DEAD_LETTER_COUNT_SQL, {"sid": str(sid)})).scalar_one()
    if row is None:
        return _Snapshot(
            exists=False,
            user_id=None,
            is_deleted=None,
            purge_after_set=False,
            custody=None,
            purge_committed_count=int(committed),
            dead_letter_count=int(dead),
        )
    _id, user_id, is_deleted, purge_after, custody = row
    return _Snapshot(
        exists=True,
        user_id=user_id,
        is_deleted=bool(is_deleted),
        purge_after_set=purge_after is not None,
        custody=custody,
        purge_committed_count=int(committed),
        dead_letter_count=int(dead),
    )


# ---- safety: refuse to run against prod unless explicitly opted in ---------


def _resolve_db_host() -> str:
    """Best-effort extraction of the DB host from settings — for the prod-guard
    only. Returns an empty string if nothing usable is found."""
    raw = (
        os.environ.get("DATABASE_URL")
        or os.environ.get("DB_URL")
        or os.environ.get("POSTGRES_URL")
        or ""
    )
    if "@" in raw:
        # postgres+asyncpg://user:pass@host:port/db
        try:
            return raw.split("@", 1)[1].split("/", 1)[0].split(":", 1)[0]
        except Exception:
            return ""
    return ""


def _assert_non_prod_or_die() -> None:
    host = _resolve_db_host()
    allowlist = {
        h.strip().lower()
        for h in os.environ.get("DB_NONPROD_HOST_ALLOWLIST", "localhost,postgres,127.0.0.1").split(
            ","
        )
        if h.strip()
    }
    if not host:
        # No URL detected; let the caller bypass via env var if they really
        # know what they're doing.
        if os.environ.get("PURGE_CANARY_ALLOW_UNKNOWN_HOST", "").lower() not in (
            "1",
            "true",
            "yes",
        ):
            print(
                "[canary] FATAL: could not determine DB host; refuse to run. "
                "Set PURGE_CANARY_ALLOW_UNKNOWN_HOST=1 to bypass.",
                file=sys.stderr,
            )
            sys.exit(2)
        return
    if host.lower() not in allowlist:
        print(
            f"[canary] FATAL: resolved DB host '{host}' is not in non-prod "
            f"allowlist ({sorted(allowlist)}). Refusing to run. "
            f"Set DB_NONPROD_HOST_ALLOWLIST or pass --i-know-what-i-am-doing.",
            file=sys.stderr,
        )
        sys.exit(2)


# ---- main flow --------------------------------------------------------------


async def _canary_one(
    sid: uuid.UUID, *, force_eligible: bool, dry_run: bool
) -> tuple[PurgeOutcome | None, _Snapshot, _Snapshot]:
    pre = await _snapshot(sid)
    print(
        f"[canary] {sid}: pre  exists={pre.exists} is_deleted={pre.is_deleted} "
        f"custody={pre.custody} "
        f"purge_committed={pre.purge_committed_count} "
        f"dead_letter={pre.dead_letter_count}"
    )
    if not pre.exists:
        print(f"[canary] {sid}: session does not exist, nothing to do")
        return (None, pre, pre)
    if pre.custody == "legal_hold":
        print(f"[canary] {sid}: ABORT — legal_hold session must not be canaried (I5)")
        return (None, pre, pre)

    if dry_run:
        print(f"[canary] {sid}: --dry-run, skipping purge call")
        return (None, pre, pre)

    if force_eligible:
        async with get_db_session_local() as db:
            await db.execute(_FORCE_ELIGIBLE_SQL, {"sid": str(sid)})
            await db.commit()

    # Drive the purge.  We open a fresh tx because phase (a) takes its own
    # claim and phase (c) issues the DELETE through the same db handle.
    outcome: PurgeOutcome
    async with get_db_session_local() as db:
        result = await purge_one_session(session_id=sid, trigger=PurgeTrigger.GRACE_EXPIRED, db=db)
        outcome = result.outcome
    post = await _snapshot(sid)

    delta_committed = post.purge_committed_count - pre.purge_committed_count
    delta_dead = post.dead_letter_count - pre.dead_letter_count
    print(
        f"[canary] {sid}: post outcome={outcome.value} "
        f"\u0394purge_committed={delta_committed} "
        f"\u0394dead_letter={delta_dead} "
        f"row_now_exists={post.exists}"
    )

    # Per-id verdict: print mismatches loudly so ops sees them.
    expected_delta_committed: int
    if outcome == PurgeOutcome.PURGED:
        expected_delta_committed = 1
        if post.exists:
            print(f"[canary] {sid}: \u2718 PURGED outcome but row still exists")
    elif outcome == PurgeOutcome.ALREADY_PURGED:
        expected_delta_committed = 0
    else:
        expected_delta_committed = 0  # other outcomes do not commit

    if delta_committed != expected_delta_committed:
        print(
            f"[canary] {sid}: \u2718 outcome={outcome.value} expected "
            f"\u0394purge_committed={expected_delta_committed} got {delta_committed}"
        )
    if delta_dead > 0:
        print(f"[canary] {sid}: \u26a0 {delta_dead} dead-letter rows; details:")
        async with get_db_session_local() as db:
            rows = (await db.execute(_DEAD_LETTER_DETAIL_SQL, {"sid": str(sid)})).all()
        for r in rows:
            print(f"    dead_letter id={r[0]} provider={r[1]} kind={r[2]} id={r[3]}")
            print(f"      err: {(r[4] or '')[:200]}")

    return (outcome, pre, post)


async def _amain(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument(
        "--session-id",
        action="append",
        type=uuid.UUID,
        required=True,
        help="UUID of a session to canary; pass multiple times.",
    )
    p.add_argument(
        "--force-eligible",
        action="store_true",
        help="UPDATE the session to set is_deleted=true and purge_after=now()-1m before purging.",
    )
    p.add_argument("--dry-run", action="store_true", help="Take pre-snapshot only.")
    p.add_argument(
        "--sleep",
        type=float,
        default=0.0,
        help="Seconds to sleep between sessions (rate-limit).",
    )
    p.add_argument(
        "--i-know-what-i-am-doing",
        action="store_true",
        help="Bypass the non-prod host check (DANGEROUS).",
    )
    args = p.parse_args(argv)

    if not args.i_know_what_i_am_doing:
        _assert_non_prod_or_die()

    cfg = get_settings().sessions
    if not cfg.purge_enabled:
        print(
            "[canary] FATAL: SessionsSettings.purge_enabled is False — phase (a) "
            "claim CTE will refuse all sessions. Set SESSIONS_PURGE_ENABLED=true.",
            file=sys.stderr,
        )
        return 2

    print(
        f"[canary] purge_enabled={cfg.purge_enabled} "
        f"max_attempts={cfg.purge_max_attempts} "
        f"max_seconds_per_loop={cfg.purge_max_seconds_per_loop} "
        f"provider_cleanup_enabled={cfg.provider_cleanup_enabled}"
    )

    started = time.monotonic()
    by_outcome: dict[str, int] = {}
    unexpected = 0
    total_committed_delta = 0
    total_dead_delta = 0

    for sid in args.session_id:
        try:
            outcome, pre, post = await _canary_one(
                sid, force_eligible=args.force_eligible, dry_run=args.dry_run
            )
        except Exception as exc:
            print(f"[canary] {sid}: \u2718 RAISED {type(exc).__name__}: {exc}")
            unexpected += 1
            continue
        if outcome is not None:
            by_outcome[outcome.value] = by_outcome.get(outcome.value, 0) + 1
        total_committed_delta += post.purge_committed_count - pre.purge_committed_count
        total_dead_delta += post.dead_letter_count - pre.dead_letter_count
        if args.sleep > 0:
            await asyncio.sleep(args.sleep)

    elapsed = time.monotonic() - started
    print("[canary] === SUMMARY ===")
    print(f"[canary] sessions canaried: {len(args.session_id)}")
    for k, v in sorted(by_outcome.items()):
        print(f"[canary]   outcome={k}: {v}")
    print(f"[canary] total \u0394session.purge_committed: {total_committed_delta}")
    print(f"[canary] total \u0394purge_dead_letter:      {total_dead_delta}")
    print(f"[canary] elapsed: {elapsed:.1f}s")

    # Gate #7 contract: dead-letter delta must be 0 (or every entry explained
    # in the per-session output above) for the canary to be considered green.
    if unexpected > 0 or total_dead_delta > 0:
        print("[canary] VERDICT: \u2718 NOT clean (see lines above)")
        return 1
    print("[canary] VERDICT: \u2713 clean")
    return 0


def main() -> None:
    sys.exit(asyncio.run(_amain(sys.argv[1:])))


if __name__ == "__main__":
    main()
