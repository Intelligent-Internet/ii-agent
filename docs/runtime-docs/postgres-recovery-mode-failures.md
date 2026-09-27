# Postgres Recovery-Mode Failures

Runtime triage notes for the failure mode where backend requests surface
as opaque `HTTP 500 {"detail":"Internal Server Error"}` and backend logs
are flooded with:

```
asyncpg.exceptions.CannotConnectNowError: the database system is in recovery mode
```

## Symptoms

- `/sessions`, `/v1/user-settings/models`, `/chat/*`, `/agent/*` all
  return HTTP 500 for a multi-minute window.
- E2E suite categories CHAT, SESS, AGEN, XFEAT, CNCL, A2A fail in bulk
  while INF / CHAT still pass (the lighter-weight health endpoints tend
  to bypass the DB).
- `docker logs ii-agent-local-postgres-1` shows:
  ```
  LOG:  database system was not properly shut down; automatic recovery in progress
  LOG:  syncing data directory (fsync), elapsed time: 420.09 s ...
  LOG:  redo starts at 0/...
  LOG:  redo done ... elapsed: 5.43 s
  LOG:  database system is ready to accept connections
  ```
- Orphan-cleanup loop prints a full traceback every 60 s until PG
  recovers.

## Root Cause

PostgreSQL cannot accept connections while it is replaying WAL or
performing the post-crash `fsync` scan of the data directory.  SQLSTATE
**57P03 / `CannotConnectNowError`** is the canonical signal; asyncpg
raises it directly.

Two distinct upstream causes have been observed:

1. **WSL2 hard kill** of the distro (host reboot, `wsl --shutdown`
   before docker has flushed, OOM in the WSL VM, swap-VHD stall).
   Postgres' postmaster is killed mid-checkpoint and child backends
   die without flushing buffers.
2. **Backend container churn under default `stop_grace_period: 10s`**
   (see ‘Why this keeps happening’ below). Postgres' postmaster
   stays alive, but ~30 asyncpg child backends are killed mid-
   transaction within the same millisecond. The postmaster receives
   `SIGCHLD` for an unclean exit, sends `SIGQUIT` to all sibling
   backends, and re-enters startup with
   ``database system was not properly shut down; automatic recovery``.

In both cases the proof is in the postmaster's PID-1 timestamps:
``docker inspect ii-agent-local-postgres-1 --format '{{.State.StartedAt}} | restartCount={{.RestartCount}}'``.
If `restartCount=0` and `StartedAt` predates the recovery event, the
container **never restarted** — what happened was an internal
child-backend crash, not a postmaster crash.

The recovery window scales with `O(files_in_PGDATA × per-file fsync
latency)`, so disk pressure (we observed 871 GiB / 1007 GiB at 92%
on the data volume during the 2026-04-24 incident) and a slow VHDX
backend can stretch a normally-3-second recovery into 7–15 minutes.

## Why it surfaced as 500

Prior to the 2026-04-25 fix, the FastAPI exception middleware in
[`src/ii_agent/core/middleware/exception_handler.py`](../../src/ii_agent/core/middleware/exception_handler.py)
mapped every unhandled exception to:

```python
return JSONResponse(status_code=500, content={"detail": "Internal Server Error"})
```

Clients (the React frontend and the E2E harness) had no way to
distinguish a transient "PG is recovering, retry shortly" condition
from a genuine backend bug.  The orphan-cleanup loop also logged a full
traceback every 60 s, making the log stream unusable.

## Why this keeps happening — backend container shutdown

The smoking-gun signature in the PG logs for *backend-induced* recovery
is a millisecond-aligned EOF storm immediately before the recovery
event:

```
11:53:13.312 [1668] LOG: unexpected EOF on client connection with an open transaction
11:53:13.312 [1670] LOG: unexpected EOF on client connection with an open transaction
11:53:13.312 [1669] LOG: unexpected EOF ...    (30+ identical lines)
```

This happens because the backend's compose service has the Docker
default `stop_grace_period: 10s` while the lifespan shutdown
sequence currently spends all 10 s in the sandbox-drain step:

```python
yield                                 # SIGTERM arrives here
await asyncio.sleep(10)               # sandbox drain — eats the entire grace
# ... never reaches shutdown_engine() — Docker sends SIGKILL at t=10.0s
```

The asyncpg pool is not drained, so 10–30 child backends die
mid-transaction in the same millisecond → postmaster sees unclean
exits → postmaster forces recovery.

## Fix (2026-04-25)

1. **HTTP middleware** — `CannotConnectNowError` (and any exception
   whose `__cause__`/`__context__` chain contains it) now returns
   **HTTP 503** with `Retry-After: 5` and `error_code: "db_unavailable"`,
   and logs at WARNING instead of emitting a full traceback.

2. **Orphan-cleanup loop** — `run_orphan_cleanup_loop` now detects the
   same condition via `_is_pg_unavailable(exc)` and logs a one-line
   WARNING before the 60 s back-off, instead of
   `logger.exception(...)`.  The loop continues polling so it
   self-heals automatically once PG comes back.

3. **Unit tests** — added:
   - [`test_middleware_exception_handler.py::test_cannot_connect_now_returns_503_with_retry_after`](../../src/tests/unit/core/test_middleware_exception_handler.py)
   - ... `::test_wrapped_cannot_connect_now_returns_503`
   - ... `::test_unrelated_runtime_error_still_500`
   - [`test_orphan_cleanup.py::TestIsPgUnavailable`](../../src/tests/unit/agent/test_orphan_cleanup.py) (4 tests)
   - `::TestLoopHandlesPostgresRecovery` (2 tests)

## Operator Playbook

If you see `CannotConnectNowError` in backend logs:

1. **Do not restart the stack.**  PG will finish recovery on its own.
   Bouncing it restarts the WAL replay from scratch.
2. `docker logs --tail 80 ii-agent-local-postgres-1` — look for
   `database system is ready to accept connections`.  Until that line
   appears, every SQL query will 503.
3. `docker exec ii-agent-local-postgres-1 pg_isready` — returns 0 once
   accepting connections.
4. Re-run the affected E2E categories via
   `python3 scripts/local/test_e2e.py --failed`.

### Preventing it

- **Graceful WSL shutdown**: `wsl --shutdown` on the Windows host
  flushes the VHD.  Hard power loss, hibernation with the distro
  running, or Windows forced reboots are the usual culprits.
- **WSL .wslconfig swap** on a fast disk (NVMe).  Slow `G:` drive
  swap stalls are visible as 6–10 min fsync recovery windows.
- **Do not `kill -9` or `docker kill` postgres**.  Always use
  `./scripts/stack_control.sh stop`.
- **Keep the PG data volume below 80% used**.  Recovery `fsync` is
  `O(files × sync_latency)` — at 92 % on a slow VHDX it took 7 min.
- **Compact the VHDX during planned maintenance**:
  ```bash
  docker system prune -af --volumes
  sudo fstrim -av                    # mark freed blocks for the host
  # then on Windows (elevated PowerShell):
  wsl --shutdown
  Optimize-VHD -Path '<...>\ext4.vhdx' -Mode Full
  ```
  `Optimize-VHD` cannot run while the distro is up — the VHDX is
  held open by `vmwp.exe`. This is intentional; it would otherwise
  corrupt running containers.
- **Engineer clean backend shutdown** so PG never enters
  child-backend recovery in the first place. See *Backend shutdown
  contract* below.

## Backend shutdown contract

For the backend to *not* induce PG recovery on stop/rebuild, four
things must align:

| Layer | Setting | Why |
|---|---|---|
| `docker-compose.local.yaml` (backend service) | `stop_grace_period: 30s` + `stop_signal: SIGTERM` | Gives lifespan time to reach `shutdown_engine()`. Default 10 s is not enough. |
| `entrypoint.sh` (gunicorn) | `--graceful-timeout 25` | Gunicorn waits 25 s after SIGTERM for the worker's lifespan teardown to complete (5 s headroom under the 30 s compose grace). |
| `app/lifespan.py` shutdown order | DB pool drain happens *after* sio + pubsub close, *before* the bounded sandbox drain | Ensures asyncpg.dispose() actually runs even if sandbox drain hits its deadline. |
| `stack_control.sh stop` | `docker compose stop --timeout 30` (or rely on per-service grace) | Otherwise CLI overrides the compose value. |

Acceptance test: after `./scripts/stack_control.sh restart backend`,
`docker logs ii-agent-local-postgres-1 --since 1m | grep 'unexpected EOF'`
must be empty.

## Liveness vs readiness

The Docker `HEALTHCHECK` in `docker-compose.local.yaml` points at
`GET /health` which returns 200 as long as the FastAPI process is
alive — it does **not** probe the DB. This is intentional: a 503
healthcheck would make Docker restart the backend, which is the wrong
action when PG (not the backend) is the problem.

A `/health/ready` endpoint (planned) probes DB + Redis with tight
timeouts and returns 503 + `Retry-After: 5` while any critical dep is
down. It is consumed by:

- `stack_control.sh status` — feeds the rollup verdict
- The frontend bootstrap — shows a "warming up" screen instead of
  crashing on the first `/sessions` request
- The E2E harness — gates DB-touching test categories so a single
  PG-recovery window does not cascade into 14 spurious test failures
- Any future k8s `readinessProbe` (does not restart, just removes the
  pod from the Service endpoints)

The Docker `HEALTHCHECK` stays on `/health` (liveness only).

## Related

- Compose healthcheck already gates `depends_on: service_healthy` for
  backend startup, so the backend never starts during recovery.  It
  only ever hits this if PG enters recovery *after* the backend has
  already started (backend rebuild without sufficient grace; WSL hard
  kill; OOM).
- See also `docs/runtime-docs/docker-wsl2-recovery.md` for the broader
  WSL2 recovery flow.

## Test-suite anti-patterns this incident exposed

The 2026-04-24 E2E run had two **misclassified** failures that looked
like feature regressions but were really PG-recovery side-effects:

- **SBOX-03** (orphan volume cleanup) — the test waited 150 s for the
  orphan-cleanup loop to remove a planted volume. The loop crashed
  every iteration with `CannotConnectNowError`, so the volume never
  got reaped. The test reported "cleanup may not be running" without
  ever checking whether the loop was actually able to reach the DB.
- **SBOX-04** (`timeout_at` column persistence) — the test ran
  `docker exec postgres psql -t -c 'SELECT column_name ...'` and
  treated *any* empty stdout as "column missing". During PG recovery
  psql writes
  ``connection failed: the database system is in recovery mode``
  to **stderr** and exits non-zero. The test ignored the exit code.

Fix pattern for both: **probe `/health/ready` (or `pg_isready`) before
the test body**, and on failure return `SKIP` with a notes field that
includes the recovery state. Don't fail the test for an environmental
precondition.

## History

| Date       | Event |
|------------|-------|
| 2026-04-24 11:53 UTC | First EOF storm of the day (30+ asyncpg connections cut in same ms) — backend container rebuild under 10 s grace. PG recovered in ~3 s (clean checkpoint). |
| 2026-04-24 14:36 UTC | Second EOF storm (24+ connections). PG recovered in ~3 s. |
| 2026-04-24 ~23:21 UTC | Third recovery event triggered the 7-minute window — disk at 92% + slow VHDX backed up the per-file fsync sweep. PG ready at 23:34:49. |
| 2026-04-24 23:18-23:38 UTC | E2E suite ran into the recovery window: 12 FAIL / 2 ERROR, **all 14** traceable to PG 57P03 (timeline correlation in [docs/runtime-docs/postgres-recovery-mode-failures.md] forensics section). SBOX-03 and SBOX-04 were misclassified as feature failures. |
| 2026-04-25 | Middleware 503 mapping + orphan-loop WARNING downgrade + 10 regression tests landed. |
| 2026-04-25 (planned) | `stop_grace_period: 30s` + lifespan reorder + `/health/ready` + SBOX-03/04 precondition guard. |
