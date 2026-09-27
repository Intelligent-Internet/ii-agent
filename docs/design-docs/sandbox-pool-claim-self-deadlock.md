# Sandbox Pool-Claim Self-Deadlock (2026-04-24 incident)

**Created:** 2026-04-24
**Status:** Mitigated 2026-04-24 (fix verified live). Structural fix #1, backstop #2, and regression test #3 LANDED 2026-04-24 (see [Recommended follow-ups](#recommended-follow-ups)). Only #4 (asyncpg pool-checkout alert) remains.
**Severity at time of incident:** P1 — entire user session silent for 12+ minutes; backend connection pool progressively wedged.
**Forward-referenced from:** [src/ii_agent/agents/sandboxes/service.py](../../src/ii_agent/agents/sandboxes/service.py) `init_sandbox` step 7 ("CRITICAL: commit `db` first…").

---

## TL;DR

`SandboxService.init_sandbox` claims a pre-warmed pool sandbox, calls `_sandbox_repo.update_provider_info` on the caller's `db` (taking a row-lock on `agent_sandboxes.id`), then (before the deployed fix) called `sandbox_mgr.set_timeout(...)`. `DockerSandbox.set_timeout` opens its **own** DB session via `get_db_session_local()` and `UPDATE`s the same row. The second session blocks on the still-held row-lock. Each blocked pair leaks two asyncpg connections (`idle in transaction` + `active blocked on ShareLock`). After ~17 such pairs the pool is exhausted and every code path that touches `agent_sandboxes` wedges. The user session that triggered the lock chain produces zero further output.

**Mitigation in place** (working tree):
1. `init_sandbox` step 7 now `await db.commit()` **before** calling `set_timeout`, releasing the row-lock so the second session's UPDATE can proceed.
2. `DockerSandbox.set_timeout._persist_deadline` is wrapped in `asyncio.wait_for(timeout=10.0)` so a future contention can never wedge the user-visible session-startup path indefinitely.

**Recommended follow-up** (not yet implemented):
3. Eliminate the second DB session entirely by passing the caller's `db` into `set_timeout`. This removes the contention by construction, not by ordering discipline.

---

## Incident timeline (2026-04-24)

| Local time | Event |
|---|---|
| 14:12:15.857 | User submits TDD/BDD interview prep query → `deep_research` agent created for session `f3b46421-a659-48eb-b701-a0e11655984f` |
| 14:12:15.950 | Pool claim succeeds: sandbox `d8ae515d-…` (slot=0) → CLAIMED |
| 14:12:16.x   | `update_provider_info` UPDATE on `agent_sandboxes.id = d8ae515d-…` (caller `db` open, row-locked) |
| 14:12:16.x   | `_persist_deadline()` opens fresh session, `SELECT … FROM agent_sandboxes WHERE id = …` succeeds (yields `idle in transaction`), then `UPDATE … SET timeout_at = …` blocks on the caller's row-lock |
| 14:12:17.899 | MCP configuration completes (this runs as fire-and-forget so it logs anyway) |
| 14:12:17 → 14:24 | **silence**. The session's caller is awaiting `set_timeout` which is awaiting the lock; nobody ever frees it. Each subsequent orphan-cleanup tick (60s) replays the same pattern via `mark_due_for_retirement` / `_kill_timed_out_sandboxes` paths, producing more `idle in transaction` connections that block on each others' row-locks. |
| 14:23 (diag)  | `pg_stat_activity`: 17 stuck PID pairs, each a `(idle in transaction SELECT, active UPDATE blocked on ShareLock)` pair. 8 ungranted ShareLocks on `transactionid`. RunTask `3824d1c7-…` still `status=running`, zero `chat_messages`, A2A adapter healthy but never received any backend request. |
| 14:24 | `./scripts/stack_control.sh restart backend` — restart clears all stuck connections; pool warms back to 2/2; only the diagnostic query remains active in the DB. |

---

## Root cause

### The two-session anti-pattern

`SandboxService.init_sandbox` and `DockerSandbox.set_timeout` use **two different `AsyncSession` instances** to mutate the same `agent_sandboxes` row in immediate succession:

```text
Caller (init_sandbox):
  async with caller_db:  # session A
    UPDATE agent_sandboxes SET status, provider_sandbox_id, … WHERE id = X
    # ↑ row-lock on id=X held until commit/rollback

    await sandbox_mgr.set_timeout(...)
        DockerSandbox.set_timeout:
          async with get_db_session_local() as db:  # session B
            SELECT … FROM agent_sandboxes WHERE id = X
            # ← held: session B is "idle in transaction"
            record.timeout_at = ...
            await db.commit()
              # ← UPDATE fires, blocks waiting for session A's row-lock
              # ← session A is awaiting set_timeout → cannot commit
              # ← DEADLOCK
```

Strictly, this is not a Postgres-detectable deadlock (Postgres only detects mutual `ShareLock` cycles between *different* transactions; here session A holds the lock and session B waits, but session A is also waiting on session B's coroutine). Postgres sees one waiter and one holder and waits indefinitely. asyncpg sees nothing wrong and does not release.

### Why the leak compounds

Other code paths that touch the same row table — `pool.mark_due_for_retirement`, `orphan_cleanup._kill_timed_out_sandboxes`, the next session's `init_sandbox`, even another `set_timeout` from a parallel pool-claim — all need a row-lock on `agent_sandboxes`. Each blocked attempt **leaves its own `idle in transaction` connection** because cancellation while awaiting an asyncpg query mid-flight does not reliably end the transaction (the rollback path gets short-circuited if the underlying connection is in `EXECUTE_STATEMENT` state). After ~17 stuck pairs the asyncpg `QueuePool` is exhausted and even unrelated requests start blocking on session checkout.

### Why the user session was silent

The wedged session is the **first** to deadlock. Its `agent.arun(...)` is awaiting `_ensure_sandbox_for_inner_loop()`, which is awaiting `init_sandbox`, which is awaiting `set_timeout`, which is awaiting the lock. No tokens are emitted because the agent loop has not yet reached the LLM call. The frontend sees no events. The A2A adapter sidecar is healthy and idle because it was never invited to the conversation.

### Why this surfaced now

Two preconditions, both new:

1. **Pool-claim path (Phase 6.e, 2026-04-24):** `init_sandbox` step 7 was added to refresh `timeout_at` on a freshly-claimed pool sandbox (whose deadline could be hours stale). Before pre-warmed pool sandboxes, `set_timeout` was only called on the post-create path where the caller's transaction had already committed before reaching `set_timeout`.
2. **Orphan-cleanup loop has many UPDATE sites:** R6 (`_kill_timed_out_sandboxes`), the new R9 (orphaned-volume cleanup), `mark_due_for_retirement`, `validate_available_slots`, the docker-zombie sweep — all touch `agent_sandboxes` rows on a 60-second cadence. Any one of them stalled on a row-lock is enough to start the cascade.

The `set_timeout(timeout_seconds)` call is harmless in isolation. The bug is that `set_timeout` and its caller race for the *same* row-lock when both run on a single agent's session-start path.

---

## Fix in place (working tree)

### Change 1 — commit before set_timeout (`service.py`)

`init_sandbox` step 7, only on the pool-claim branch (where `set_timeout` is called inline):

```python
# CRITICAL: commit ``db`` first so the row-lock taken by
# ``update_provider_info`` above is released. ``set_timeout`` opens
# its own DB session to UPDATE the same agent_sandboxes row; without
# this commit, that session blocks waiting for our own transaction,
# producing a self-deadlock that permanently leaks two connections
# per pool claim and eventually exhausts the QueuePool. See the
# 2026-04-24 incident in docs/design-docs/.
if is_pool_claim and self._config.sandbox.timeout_seconds:
    try:
        await db.commit()
    except Exception:
        logger.exception(...)
    try:
        await sandbox_mgr.set_timeout(self._config.sandbox.timeout_seconds)
    except Exception:
        logger.exception(...)
```

This unblocks the deadlock for the pool-claim path. The non-pool path was already safe because its `set_timeout` calls happen after the caller's transaction has committed.

### Change 2 — bounded `set_timeout` DB write (`docker.py`)

`DockerSandbox.set_timeout` now wraps the DB write in `asyncio.wait_for`:

```python
async def _persist_deadline() -> None:
    ...
    async with get_db_session_local() as db:
        result = await db.execute(select(AgentSandbox).where(AgentSandbox.id == ...))
        record = result.scalar_one_or_none()
        if record:
            record.timeout_at = deadline
            await db.commit()

try:
    await asyncio.wait_for(_persist_deadline(), timeout=10.0)
except asyncio.TimeoutError:
    logger.warning(
        f"Timed out (>10s) persisting timeout_at for sandbox {self.sandbox_id}; "
        f"in-memory timeout still active but deadline will not survive restart"
    )
except Exception as e:
    logger.warning(f"Failed to persist timeout_at for sandbox {self.sandbox_id}: {e}")
```

This is a *backstop*. It bounds the worst-case wedge time at 10 seconds per call, not zero. The caller's session-startup path can now never hang for more than 10 s on this code path even if Change 1 regresses or is bypassed by a future refactor. Cross-restart durability is sacrificed on timeout (the in-memory `_timeout_handler` task still fires), which is preferable to silent user-facing wedges.

### What the two changes leave in place

* The two-session pattern itself remains. `set_timeout` still opens its own session.
* If a future caller invokes `set_timeout` with the caller's transaction still uncommitted, the wait_for backstop will fire (10 s warning) but no permanent leak.
* If asyncpg's cancellation-during-execute leak reproduces under the wait_for path (the wait_for raises `CancelledError` into the inner coroutine, same root cause as before), the connection still leaks. The damage is bounded to one connection per set_timeout invocation; not 2 per pair as before.

---

## Recommended follow-ups

In priority order. None of these are blocking — the deployed fix is sufficient for the observed failure mode — but each closes a class of related risk.

**Status update 2026-04-24:** Items #1, #2, and #3 have all LANDED in the same working-tree push that wrote this doc. The two-session anti-pattern is gone on the pool-claim path; the separate-session path used by cron and `_create_or_resume` is now bounded by both `lock_timeout='5s'` and `asyncio.wait_for(10s)`; and the regression test in `test_docker_sandbox.py::TestSetTimeout::test_uses_caller_session_when_db_passed` locks in the invariant. Only #4 remains.

### 1. Pass `db` into `set_timeout` (eliminate the second session) — **LANDED 2026-04-24**

Refactor the `Sandbox` interface:

```python
async def set_timeout(self, timeout_seconds: int, *, db: AsyncSession | None = None) -> None: ...
```

When `db` is provided, mutate the row in the caller's transaction. When `db` is None (legacy callers, cron jobs), open a fresh session as today. Update `service.py::init_sandbox` step 7 to pass its own `db` and drop the explicit `await db.commit()` workaround.

Effect: removes contention by construction. No ordering discipline required. No way for a future caller to recreate the bug.

Cost: API change across `DockerSandbox.set_timeout` and `E2BSandbox.set_timeout`; touches a public-ish interface. Cleanup-loop callers (`_kill_timed_out_sandboxes`) keep the `db=None` path unchanged.

### 2. `SET LOCAL lock_timeout` inside `_persist_deadline` — **LANDED 2026-04-24**

Even if the second-session pattern stays, give the inner UPDATE a deterministic upper bound:

```python
async with get_db_session_local() as db:
    await db.execute(text("SET LOCAL lock_timeout = '5s'"))
    ... SELECT / UPDATE / commit ...
```

Effect: the inner transaction either acquires the lock within 5 s or fails fast with a `LockNotAvailable` error, releasing the connection cleanly. No `idle in transaction` accumulation possible.

Cost: small. Pairs naturally with #1; if #1 lands first, this becomes belt-and-braces for any remaining `db=None` callers.

### 3. Regression test — **LANDED 2026-04-24**

Unit-test in `src/tests/unit/agent/test_sandbox_service.py`:

```python
async def test_init_sandbox_pool_claim_commits_before_set_timeout():
    """Pool-claim path MUST commit caller's transaction before calling
    set_timeout, otherwise set_timeout's separate DB session deadlocks
    on the row-lock from update_provider_info. See
    docs/design-docs/sandbox-pool-claim-self-deadlock.md.
    """
    # Fixtures: real SandboxService with mocked repo + pool manager,
    # an AsyncSession spy that records the order of commit() calls and
    # set_timeout() calls.
    ...
    assert call_order == ["update_provider_info", "commit", "set_timeout"]
```

Effect: locks in the ordering. Any future refactor that reorders or removes the commit fails CI loudly.

### 4. Connection-pool wedge alert

Add a CRIT-state trigger to the integrated host monitor (Phase 2) when asyncpg's `QueuePool` checkout latency exceeds a threshold (e.g. p99 > 5 s). The monitor already gates pool warming and `_create_provider` on host state; surfacing DB-pool exhaustion as a state input lets the same gate apply.

Effect: future connection leaks (from any cause) become operator-visible in `stack_control.sh status` rather than producing silent user sessions.

Cost: requires a hook into the SQLAlchemy engine's pool events; non-trivial but isolated to `core/db/`.

---

## Why the pre-existing safeguards did not catch this

| Safeguard | Why it didn't trigger |
|---|---|
| Phase 2 host monitor (`HostHealthState`) | Only watches /proc fragmentation + docker_call latency. DB-pool exhaustion is invisible to it. Recommendation #4 closes this. |
| `_create_provider` semaphore (Phase 1) | Caps concurrent **container** creates, not concurrent DB UPDATEs. Pool claims don't go through `_create_provider`. |
| Per-sandbox circuit breaker | Triggered by reconnect/restart failures, not row-lock wedges. The pool sandbox was perfectly healthy. |
| Orphan cleanup R1 (only mark DELETED if container removed) | Different scope (container teardown, not session-start). |
| `asyncio.wait_for` on Docker calls | Docker was never called on the wedged path; we never got past `set_timeout`. |
| Session timeout (`agent_sandboxes.timeout_at`) | The whole point of `set_timeout` was to set `timeout_at` for this very session. The wedge happened during the set, before any deadline existed. |

The closest existing safeguard was the `agent.arun` path's own backpressure (the agent eventually times out user-side), but it had no upper bound on session-start. **Recommendation #4 + the existing `wait_for(10s)` together close this gap to ≤10 s per call.**

---

## Why the existing fix is not "complete" but is "correct enough to ship"

* **Correct:** the deployed Change 1 + Change 2 demonstrably prevent the observed cascade. Restart cleared the wedge; the subsequent backend has logged zero `idle in transaction` accumulation in `pg_stat_activity` over the post-restart window.
* **Not complete:** the structural anti-pattern (two sessions writing the same row consecutively) remains. Discipline-based fixes ("remember to commit first") are weaker than structural fixes ("there is no second session"). Recommendation #1 is the structural fix.
* **Concise:** Change 1 is 9 lines (commit + try/except). Change 2 is 6 lines (wait_for + TimeoutError handler). Neither changes any public interface. Both are local to the affected functions.
* **Future-regression risk:** medium without #3 (regression test). Anyone refactoring `init_sandbox` step 7 could re-order the commit and reintroduce the wedge. Recommendation #3 reduces this to ≈0.

The deployed mitigation is **shippable** for v1. The recommended follow-ups should land before the pool size is increased above the current `prewarm_pool_size=2` (more pool claims per minute → higher contention probability if discipline ever slips).

---

## Verification

Live verification, 2026-04-24 post-restart:

```text
$ docker exec ii-agent-local-postgres-1 psql -U iiagent -d iiagentdev \
    -c "SELECT count(*) FROM pg_stat_activity WHERE state='idle in transaction';"
 count
-------
     0

$ ./scripts/stack_control.sh status | grep -A1 "Sandbox Pool"
=== Sandbox Pool ===
  url:            http://localhost:8000/health/sandbox-pool
  configured:     2  ready: 2
  status:         OK (2/2 ready)
```

The wedge is cleared, the pool is warm, no transactional connections leaked. The backend has been processing new sessions normally since restart.

---

## References

* [src/ii_agent/agents/sandboxes/service.py](../../src/ii_agent/agents/sandboxes/service.py) — `init_sandbox` step 7 (commit-before-set_timeout)
* [src/ii_agent/agents/sandboxes/docker.py](../../src/ii_agent/agents/sandboxes/docker.py) — `DockerSandbox.set_timeout` (`asyncio.wait_for(10s)` backstop)
* [docs/runtime-docs/post-reboot-followups.md](../runtime-docs/post-reboot-followups.md) — incident ledger
* [docs/impl-docs/sandbox-robustness-impl-tracker.md](../impl-docs/sandbox-robustness-impl-tracker.md) — Phase 6.f tracking entry
* Phase 6.e (pool self-heal) is the immediate predecessor that introduced the pool-claim path's `set_timeout` call.
