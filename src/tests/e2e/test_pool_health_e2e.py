"""End-to-end tests for the pre-warmed sandbox pool surface.

These tests run against a live local stack and:

  * verify ``GET /health/sandbox-pool`` returns the documented shape;
  * inject a stuck ``INITIALIZING`` row directly into PostgreSQL and
    confirm the orphan-cleanup loop reaps it (Fix A end-to-end);
  * verify ``stack_control.sh status --json`` exposes ``modules.pool``
    with a sensible verdict.

Gated by ``II_AGENT_E2E=1`` — see :mod:`src.tests.e2e.conftest`.

Stack prerequisites:
  * Backend reachable on ``$BACKEND_URL`` (default http://localhost:8000)
  * Postgres container ``$POSTGRES_CONTAINER`` reachable via ``docker exec``
  * Pool enabled (``configured >= 1``); tests that need a warm pool will
    skip themselves rather than fail when ``ready == 0``.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import time
import uuid

import httpx
import pytest

from .conftest import BACKEND_URL, POSTGRES_CONTAINER, POSTGRES_DB, POSTGRES_USER

pytestmark = pytest.mark.asyncio


_REQUIRED_KEYS = {
    "available",
    "enabled",
    "configured",
    "ready",
    "initializing",
    "initializing_age_max_seconds",
    "stuck_initializing",
    "claimed",
    "retiring",
    "stuck_threshold_seconds",
}


async def _fetch_pool_health() -> dict:
    async with httpx.AsyncClient(base_url=BACKEND_URL, timeout=10.0) as client:
        resp = await client.get("/health/sandbox-pool")
        resp.raise_for_status()
        return resp.json()


def _psql(sql: str) -> tuple[int, str, str]:
    """Run a one-shot psql command inside the postgres container."""
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


async def test_pool_health_returns_documented_shape():
    """Every documented key is present and has the expected type."""
    body = await _fetch_pool_health()
    missing = _REQUIRED_KEYS - set(body.keys())
    assert not missing, f"missing keys: {sorted(missing)}"
    assert body["available"] is True, f"available must be True; body={body!r}"
    assert isinstance(body["enabled"], bool)
    assert isinstance(body["configured"], int)
    assert isinstance(body["ready"], int)
    assert isinstance(body["initializing"], int)
    assert isinstance(body["stuck_initializing"], int)
    assert isinstance(body["claimed"], int)
    assert isinstance(body["retiring"], int)
    assert body["stuck_threshold_seconds"] == 600


async def test_pool_status_json_module_reports_pool_section():
    """stack_control.sh status --json exposes modules.pool with reachable=True."""
    proc = subprocess.run(
        ["./scripts/stack_control.sh", "status", "--json"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, f"status --json failed: {proc.stderr[:200]}"
    payload = json.loads(proc.stdout)
    pool = (payload.get("modules") or {}).get("pool")
    assert pool is not None, "modules.pool missing"
    assert pool.get("reachable") is True, f"pool not reachable: {pool!r}"
    assert pool.get("verdict") in {"OK", "WATCH"}, f"unexpected verdict: {pool!r}"


async def test_pool_stuck_initializing_row_is_reaped():
    """End-to-end Fix A: an injected stuck row clears within two cleanup sweeps.

    Skipped when the pool is disabled (``configured == 0``).
    """
    before = await _fetch_pool_health()
    if not before["enabled"] or before["configured"] == 0:
        pytest.skip("pool disabled; reap path not applicable")

    baseline_stuck = int(before["stuck_initializing"])
    # Use a slot well past the configured size so we don't race the
    # bootstrap fill. The reaper is slot-agnostic — slot value only
    # matters for clarity in the assertion message.
    slot = int(before["configured"]) + 50

    inject_sql = (
        "INSERT INTO agent_sandboxes "
        "(id, session_id, provider, status, pool_state, pool_slot, created_at, updated_at) "
        "VALUES (gen_random_uuid(), NULL, 'docker', 'initializing', 'available', "
        f"{slot}, NOW() - INTERVAL '11 hours', NOW() - INTERVAL '11 hours') "
        "RETURNING id;"
    )
    rc, out, err = _psql(inject_sql)
    assert rc == 0, f"injection failed: {err}"
    # psql -t -A still appends the command tag ("INSERT 0 1") on a second
    # line; the row id is the first line.
    injected_id = out.splitlines()[0].strip() if out else ""
    assert injected_id, f"no row id returned; psql out={out!r}"
    # Sanity: result looks like a UUID.
    uuid.UUID(injected_id)

    # The pool snapshot uses the same threshold as the reaper (10 min)
    # so the injected row appears as stuck immediately.
    bumped = await _fetch_pool_health()
    assert int(bumped["stuck_initializing"]) > baseline_stuck, (
        f"injection did not bump stuck_initializing: baseline={baseline_stuck} "
        f"after_inject={bumped!r}"
    )

    # Wait up to 180s for two cleanup sweeps (default interval = 60s).
    deadline = time.monotonic() + 180
    last: dict | None = None
    while time.monotonic() < deadline:
        await asyncio.sleep(15)
        last = await _fetch_pool_health()
        if int(last["stuck_initializing"]) <= baseline_stuck:
            break

    assert last is not None
    assert int(last["stuck_initializing"]) <= baseline_stuck, (
        f"stuck_initializing did not return to {baseline_stuck} within 180s; "
        f"last snapshot={last!r}"
    )

    rc, status, err = _psql(
        f"SELECT status FROM agent_sandboxes WHERE id = '{injected_id}';"
    )
    assert rc == 0, f"verify query failed: {err}"
    assert status == "deleted", (
        f"injected row {injected_id} status={status!r} (expected 'deleted')"
    )
