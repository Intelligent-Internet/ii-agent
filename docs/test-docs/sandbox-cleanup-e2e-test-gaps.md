# Sandbox Cleanup — E2E Test Coverage

## Context

All 9 recommendations from `docs/design-docs/sandbox-lifecycle-assessment.md` have been implemented and covered by unit tests (42 tests in `test_orphan_cleanup.py`, 137 in `test_docker_sandbox.py`). Five feasible e2e tests have been added to the main test runner (`scripts/local/test_e2e.py`) under the `SBOX` category.

## Implemented E2E Tests

| ID | Rec | Test | Method | Timeout | Status |
|----|-----|------|--------|---------|--------|
| SBOX-01 | R3 | FK constraint rejects orphaned sandbox rows | Docker exec psql INSERT | 10s | Implemented |
| SBOX-02 | R7 | Port pool overflow protection active | REST health check | 10s | Implemented |
| SBOX-03 | R9 | Orphaned Docker volumes cleaned up | Docker volume create + poll | 90s | Implemented |
| SBOX-04 | R6 | timeout_at column persisted in DB | Docker exec psql schema check | 10s | Implemented |
| SBOX-05 | R5 | Cleanup loop active (6 stages) | Backend log inspection | 10s | Implemented |

### Running

```bash
# Run just the sandbox lifecycle tests
python3 scripts/local/test_e2e.py --category SBOX

# Run a single test
python3 scripts/local/test_e2e.py --test SBOX-01
```

## E2E Test Feasibility Matrix

| Rec | Fix | E2E Feasible | Reason |
|-----|-----|:---:|--------|
| R1 | Conditional DELETED marking | Yes | Can create a sandbox, kill the Docker daemon briefly, verify sandbox is NOT marked DELETED after one sweep |
| R2 | Per-sandbox DB session isolation | No | Requires injecting DB errors mid-transaction — not reproducible in real stack |
| R3 | FK constraint on session_id | Yes | Run migration, then try to INSERT a sandbox with a non-existent session_id — should get FK violation |
| R4 | 120s zombie sweep timeout | No | Would need to stall Docker API for >15s but <120s — fragile and slow |
| R5 | Sleep-at-end loop ordering | No | Ordering is a code-level concern; observed behavior (first cleanup happens immediately on startup) could be tested but is timing-sensitive |
| R6 | Persistent timeout_at enforcement | Yes | Create sandbox with short timeout, wait, verify it's paused after cleanup sweep |
| R7 | Port pool overflow protection | Yes | Exhaust port pool, attempt creation — should get `SandboxCreationError` |
| R8 | Concurrent sandbox cap | Yes | Set `max_concurrent_sandboxes=1`, create one sandbox, attempt second — should fail |
| R9 | Orphaned volume cleanup | Yes | Create a Docker volume with `ii-sandbox-workspace-` prefix and no matching sandbox/container, trigger cleanup, verify removed |

## Recommended E2E Tests

### 1. FK Constraint Enforcement (R3)

**Prerequisites:** Migration `20260416_000005` applied.

```python
async def test_fk_constraint_rejects_orphaned_sandbox():
    """INSERT into agent_sandboxes with non-existent session_id should raise IntegrityError."""
    async with get_db_session_local() as db:
        from sqlalchemy import text
        result = await db.execute(
            text("INSERT INTO agent_sandboxes (session_id, status) VALUES (:sid, 'running')"),
            {"sid": "00000000-0000-0000-0000-000000000000"}
        )
        # Should raise IntegrityError before reaching this line
```

**Automation:** Runs as part of migration smoke tests. No Docker dependency.

### 2. Persistent Timeout Enforcement (R6)

```python
async def test_timeout_at_persisted_and_enforced():
    """Create sandbox with short timeout, verify timeout_at is set in DB, trigger cleanup."""
    sandbox = await DockerSandbox.create(sandbox_id="test-timeout", session_id=session_id)
    await sandbox.set_timeout(seconds=5)

    # Verify timeout_at is persisted
    async with get_db_session_local() as db:
        record = await db.get(AgentSandbox, sandbox.sandbox_id)
        assert record.timeout_at is not None

    await asyncio.sleep(6)
    killed = await _kill_timed_out_sandboxes(cfg)
    assert killed >= 1
```

**Automation:** Needs a running Docker daemon and database. ~10s test.

### 3. Port Pool Overflow (R7)

```python
async def test_port_pool_overflow_rejects_creation():
    """When all ports are allocated, create() should raise SandboxCreationError."""
    # Artificially exhaust port pool
    pm = PortPoolManager.get_instance(cfg)
    while pm.stats()["free"] >= 7:
        pm.allocate(7)

    with pytest.raises(SandboxCreationError, match="Not enough free ports"):
        await DockerSandbox.create(sandbox_id="overflow", session_id=session_id)
```

**Automation:** No Docker containers needed — just the port manager. Fast.

### 4. Concurrent Sandbox Cap (R8)

```python
async def test_concurrent_cap_rejects_excess(monkeypatch):
    """With max_concurrent_sandboxes=1, second create should fail."""
    monkeypatch.setattr(cfg.sandbox, "max_concurrent_sandboxes", 1)
    # Insert one active sandbox record
    # ...
    with pytest.raises(SandboxCreationError, match="Concurrent sandbox limit"):
        await DockerSandbox.create(sandbox_id="excess", session_id=session_id)
```

**Automation:** Needs database with one active sandbox row. Fast.

### 5. Orphaned Volume Cleanup (R9)

```python
async def test_orphaned_volume_removed():
    """Docker volume with ii-sandbox-workspace- prefix and no matching record is removed."""
    client = docker.from_env()
    vol = client.volumes.create(name="ii-sandbox-workspace-orphan-test")

    removed = await _cleanup_orphaned_volumes(cfg)
    assert removed >= 1

    with pytest.raises(docker.errors.NotFound):
        client.volumes.get("ii-sandbox-workspace-orphan-test")
```

**Automation:** Needs Docker daemon. Creates/removes a single volume. ~2s.

## Tests Not Recommended for E2E

| Rec | Why Not |
|-----|---------|
| R1 | Requires killing Docker daemon mid-sweep — destructive to other containers |
| R2 | DB error injection during async session context — only feasible with mocks |
| R4 | Stalling Docker API for specific duration — fragile, flaky |
| R5 | Loop ordering is an internal implementation detail — timing-dependent observation |

## Implementation Notes

- E2E tests should go in `tests/e2e/sandbox/` (new directory)
- Tests R3, R7, R8 can run without Docker containers (DB-only or port-manager-only)
- Tests R6 and R9 need a running Docker daemon
- All tests should be marked `@pytest.mark.e2e` for selective execution
- R6 test has a 6-second sleep — consider parametrizing timeout for faster CI runs
