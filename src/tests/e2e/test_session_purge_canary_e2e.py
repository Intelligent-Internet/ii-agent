"""End-to-end canary for the §4.1 three-phase session purge driver.

Covers **pre-flip checklist gate #7** in
``docs/design-docs/session-lifecycle-and-data-custody.md``: drive a small
known set of soft-deleted sessions through ``purge_one_session`` against
the live local stack and verify the audit + dead-letter contract.

Strategy
--------
Mirrors ``test_pool_health_e2e.py``'s injection pattern (direct ``docker
exec psql`` → backend internals exercised in-process, results probed
back via psql):

  1. Pick an existing user_id (the test does NOT mutate the user row).
  2. Inject N synthetic ``sessions`` rows (id = test UUIDs we control)
     with ``is_deleted=true``, ``purge_after = now() - 1h``,
     ``custody='standard'``.
  3. Snapshot pre-counts of
     ``application_events WHERE event_type='session.purge_committed'``
     and ``purge_dead_letter`` for each id.
  4. Drive ``purge_one_session(session_id=<id>, trigger=GRACE_EXPIRED)``
     in-process via ``get_db_session_local()``; the test process loads
     ``docker/.stack.env.local`` to point at the host-mapped DB
     (``localhost:5433``).
  5. Assert each call returned ``PurgeOutcome.PURGED``.
  6. Snapshot post-counts; assert
     ``Δsession.purge_committed = N`` and ``Δpurge_dead_letter = 0``.
  7. Confirm the synthetic rows are gone from ``sessions``.
  8. Cleanup any stray rows on assertion failure (best-effort) so the
     suite is rerunnable.

This is the in-process equivalent of running
``scripts/local/purge_canary.py`` against staging — same internal call,
same contract.
"""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

from .conftest import POSTGRES_CONTAINER, POSTGRES_DB, POSTGRES_USER

pytestmark = pytest.mark.asyncio


# ---- env bootstrap ---------------------------------------------------------

# The backend in-process API needs the same DATABASE_URL the running
# stack uses, but pointed at the host-mapped port (5433) since the test
# runs on the host. We load `docker/.stack.env.local` and rewrite the
# host so settings.get_settings() resolves correctly when imported.
_ENV_FILE = Path(__file__).resolve().parents[3] / "docker" / ".stack.env.local"


def _load_stack_env() -> None:
    if not _ENV_FILE.exists():
        pytest.skip(f"{_ENV_FILE} missing; cannot reach stack DB")
    for raw in _ENV_FILE.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        # Don't clobber values the operator set explicitly.
        os.environ.setdefault(key.strip(), value.strip())
    # Rewrite container hostnames → localhost host-port for in-process use.
    db_url = os.environ.get("DATABASE_URL", "")
    if "@postgres:" in db_url:
        host_port = os.environ.get("POSTGRES_PORT", "5433")
        os.environ["DATABASE_URL"] = db_url.replace("@postgres:5432", f"@localhost:{host_port}")
    # Purge driver flag must be on for phase (a) to claim.
    os.environ.setdefault("SESSIONS_PURGE_ENABLED", "true")
    # Don't try to call OpenAI from a test.
    os.environ.setdefault("SESSIONS_PROVIDER_CLEANUP_ENABLED", "false")


_load_stack_env()


# ---- psql helper ----------------------------------------------------------


def _psql(sql: str) -> tuple[int, str, str]:
    proc = subprocess.run(
        [
            "docker",
            "exec",
            POSTGRES_CONTAINER,
            "psql",
            "-U",
            POSTGRES_USER,
            "-d",
            POSTGRES_DB,
            "-t",
            "-A",
            "-c",
            sql,
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def _psql_must(sql: str) -> str:
    rc, out, err = _psql(sql)
    assert rc == 0, f"psql failed: sql={sql!r} err={err!r}"
    return out


def _count_audit(sid: uuid.UUID) -> int:
    out = _psql_must(
        "SELECT count(*) FROM application_events "
        f"WHERE event_type='session.purge_committed' AND session_id='{sid}';"
    )
    return int(out.splitlines()[0] or "0")


def _count_dead_letter(sid: uuid.UUID) -> int:
    out = _psql_must(f"SELECT count(*) FROM purge_dead_letter WHERE session_id='{sid}';")
    return int(out.splitlines()[0] or "0")


def _session_exists(sid: uuid.UUID) -> bool:
    out = _psql_must(f"SELECT count(*) FROM sessions WHERE id='{sid}';")
    return int(out.splitlines()[0] or "0") > 0


def _cleanup_residue(ids: list[uuid.UUID]) -> None:
    """Best-effort teardown so the test suite is rerunnable."""
    id_list = ",".join(f"'{i}'" for i in ids)
    _psql(
        f"DELETE FROM application_events WHERE session_id IN ({id_list}) "
        "AND event_type='session.purge_committed';"
    )
    _psql(f"DELETE FROM purge_dead_letter WHERE session_id IN ({id_list});")
    _psql(f"DELETE FROM sessions WHERE id IN ({id_list});")


# ---- the test --------------------------------------------------------------


async def test_purge_canary_drives_three_phase_purge_to_completion():
    """Inject N synthetic soft-deleted rows; drain via the purge driver;
    assert audit count incremented by N and dead-letter stayed at zero."""
    # Late import: settings + DB session must see the env we set above.
    from ii_agent.core.config.settings import get_settings  # noqa: PLC0415
    from ii_agent.core.db.base import get_db_session_local  # noqa: PLC0415
    from ii_agent.sessions.purge.session_purge import purge_one_session  # noqa: PLC0415
    from ii_agent.sessions.purge.types import PurgeOutcome, PurgeTrigger  # noqa: PLC0415

    cfg = get_settings().sessions
    if not cfg.purge_enabled:
        pytest.skip("SessionsSettings.purge_enabled=False; gate #7 skipped")

    # Pick any user we can attach test sessions to.
    user_id = _psql_must("SELECT id FROM users LIMIT 1;").splitlines()[0]
    assert user_id, "no users in the local stack DB"

    n = 3
    sids = [uuid.uuid4() for _ in range(n)]

    try:
        # ---- inject ------------------------------------------------------
        for sid in sids:
            rc, _, err = _psql(
                "INSERT INTO sessions "
                "(id, user_id, name, status, agent_type, app_kind, "
                " is_deleted, custody, purge_after, "
                " created_at, updated_at) "
                f"VALUES ('{sid}', '{user_id}', 'canary-{sid}', 'active', "
                "'native', 'agent', true, 'standard', "
                "now() - interval '1 hour', "
                "now() - interval '2 hours', now() - interval '2 hours');"
            )
            assert rc == 0, f"injection failed for {sid}: {err}"

        # ---- pre-snapshot ------------------------------------------------
        pre_audit = {sid: _count_audit(sid) for sid in sids}
        pre_dead = {sid: _count_dead_letter(sid) for sid in sids}
        for sid in sids:
            assert pre_audit[sid] == 0, f"unexpected pre-existing audit row for synthetic sid {sid}"
            assert pre_dead[sid] == 0, (
                f"unexpected pre-existing dead-letter row for synthetic sid {sid}"
            )
            assert _session_exists(sid), f"injection did not land for {sid}"

        # ---- drive --------------------------------------------------------
        outcomes: dict[uuid.UUID, str] = {}
        for sid in sids:
            async with get_db_session_local() as db:
                result = await purge_one_session(
                    session_id=sid,
                    trigger=PurgeTrigger.GRACE_EXPIRED,
                    db=db,
                )
            outcomes[sid] = result.outcome.value

        for sid, outcome in outcomes.items():
            assert outcome == PurgeOutcome.PURGED.value, (
                f"sid={sid} got outcome={outcome} (expected PURGED). All outcomes={outcomes}"
            )

        # ---- post-snapshot ------------------------------------------------
        for sid in sids:
            assert not _session_exists(sid), (
                f"sid={sid} row still present after PURGED outcome (I8 violation)"
            )
            post_audit = _count_audit(sid)
            assert post_audit == pre_audit[sid] + 1, (
                f"sid={sid} \u0394audit={post_audit - pre_audit[sid]} (expected 1)"
            )
            post_dead = _count_dead_letter(sid)
            assert post_dead == pre_dead[sid], (
                f"sid={sid} \u0394dead_letter={post_dead - pre_dead[sid]} "
                "(expected 0); inspect purge_dead_letter for triage"
            )

    finally:
        _cleanup_residue(sids)


async def test_purge_canary_script_help_runnable():
    """Sanity: the operator-facing canary script parses arguments and prints
    its help text. This catches regressions in the script's imports without
    requiring the full DB plumbing the in-process test exercises."""
    repo_root = Path(__file__).resolve().parents[3]
    script = repo_root / "scripts" / "local" / "purge_canary.py"
    assert script.exists(), f"canary script missing at {script}"
    proc = subprocess.run(
        [sys.executable, str(script), "--help"],
        capture_output=True,
        text=True,
        timeout=30,
        cwd=str(repo_root),
    )
    assert proc.returncode == 0, (
        f"canary --help failed: rc={proc.returncode} stderr={proc.stderr[:500]}"
    )
    assert "--session-id" in proc.stdout
    assert "--force-eligible" in proc.stdout
    assert "--dry-run" in proc.stdout
