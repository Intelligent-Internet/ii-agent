---
mode: agent
description: "Run full E2E test sweep, diagnose failures, fix+rebuild+retest until all tests pass"
---

# E2E Test / Fix / Retest Cycle

You are an autonomous test engineer. Your job is to run the full end-to-end test suite, identify
every failure, fix each one, and re-verify until **all runnable tests pass**. Do not stop until the
outer loop completes with zero failures.

## Prerequisites

Before starting, verify the stack is healthy:

```bash
# Check all services are running
./scripts/stack_control.sh status

# Quick health check
curl -sf http://localhost:8000/health || echo "BACKEND DOWN"
```

If services are down, bring them up with `./scripts/stack_control.sh start` and wait for health.
If the stack fails to start after two attempts, **stop and report the infrastructure issue** — do not
enter the test loop with a broken stack.

## State Management Overview

The E2E test suite maintains state in `.e2e_last_results.json` in `scripts/local/`:

- **First run:** Use `--clear` to delete old state and run all tests
- **Subsequent runs:** Use `--failed` to run only tests that failed or errored in the previous run
- Results file is automatically saved after each test run
- This enables efficient fix/rebuild/retest cycles without re-running passing tests

## Outer Loop: Full Test Sweep

### Entry Point (First Outer Loop — Clear State)

Clear previous state and run the **complete** E2E test suite:

```bash
cd /home/mdear/workspaces/git/ii-agent
source ~/workspaces/venvs/ii-agent/bin/activate
python3 scripts/local/test_e2e.py --clear 2>&1
```

This will:
1. Delete `.e2e_last_results.json` (if it exists)
2. Run all 32+ tests across 11 categories
3. Save results to `.e2e_last_results.json`

Parse the output summary to collect:
- Total tests run, passed, failed, skipped, errored
- For each non-passing test: the **test ID** (e.g. `CHAT-01`), **category**, **status**, and **failure notes**

### Decision Point

| Condition | Action |
|-----------|--------|
| All tests PASS (or SKIP with known reason) | **DONE** — report final results and exit |
| Any tests FAIL or ERROR | Enter the **Inner Loop** for each failure |

## Inner Loop: Fix Each Failure

Maintain a running tally of fix attempts per test ID (e.g. `CHAT-01: attempt 2/3`). This is
critical for enforcing the 3-attempt limit since the conversation may be long.

For **each** failed/errored test (process one at a time, in test-ID alphabetical order):

### Step 1 — Diagnose

1. Re-run the single failing test in isolation to confirm it still fails:
   ```bash
   python3 scripts/local/test_e2e.py --test <TEST_ID> 2>&1
   ```
2. Read the failure output carefully. Check backend and sandbox logs filtered to the relevant
   time window (use the test's session ID or a recent timestamp to narrow results):
   ```bash
   # Backend logs — filter by session ID from test output if available
   ./scripts/stack_control.sh logs backend 2>&1 | grep -i "error\|exception\|traceback" | tail -50

   # Sandbox container logs (find running sandbox first)
   SANDBOX_ID=$(docker ps --filter 'name=ii-sandbox' -q | head -1)
   [[ -n "$SANDBOX_ID" ]] && docker logs "$SANDBOX_ID" 2>&1 | grep -i "error\|exception\|traceback" | tail -50
   ```
   If grep filters too aggressively, fall back to `| tail -100` without grep.
3. Identify the **root cause** — is it:
   - A backend code bug? → fix the source file
   - A sandbox code bug? → fix under `src/ii_sandbox_server/` or `docker/sandbox/`
   - A test script bug? → fix `scripts/local/test_e2e.py`
   - A configuration/environment issue? → fix config or env
   - A timeout that needs tuning? → adjust timeout constants
   - A transient/flaky failure? → re-run once more to confirm before skipping
   - An external dependency issue (quota, network)? → mark SKIP with reason, move on

### Step 2 — Fix

Apply the minimal fix to the identified source file(s). Follow project conventions:
- Use `uv run ruff check --fix-only <changed_files>` and `uv run ruff format <changed_files>` on
  any modified Python files under `src/`
- Do NOT add unnecessary abstractions, comments, or refactoring beyond the fix
- If you only changed the test script (`scripts/local/test_e2e.py`) and no source code, skip the
  rebuild step entirely — just re-run the test

### Step 3 — Rebuild (if code changed)

Determine which components are affected by your changes and rebuild accordingly.

#### Backend changes (`src/ii_agent/`, `src/ii_server/`)

Rebuild and restart the backend:

```bash
./scripts/stack_control.sh rebuild backend 2>&1 | tail -15
echo "Exit code: $?"
```

If exit code is non-zero, the build failed — read the full output to diagnose. If the rebuild uses
cached layers and your fix isn't picked up, use `--no-cache`:

```bash
./scripts/stack_control.sh rebuild backend --no-cache 2>&1 | tail -15
echo "Exit code: $?"
```

Wait for the backend to become healthy before proceeding:

```bash
for i in $(seq 1 30); do
  curl -sf http://localhost:8000/health && echo " Backend ready" && break
  echo "  Waiting for backend... ($i/30)"
  sleep 2
done
curl -sf http://localhost:8000/health || echo "ERROR: Backend failed to start after 60s — check logs"
```

If the backend fails to start, check logs (`./scripts/stack_control.sh logs backend 2>&1 | tail -50`)
and fix the startup error before retesting.

#### Sandbox changes

Sandbox code lives in several locations. Use the appropriate rebuild mode:

| What changed | Rebuild command |
|---|---|
| Python source only (`src/ii_sandbox_server/`, `src/ii_agent_tools/`, `docker/sandbox/*.py`) | `./scripts/stack_control.sh build-sandbox --quick` |
| Dockerfile or system deps (`e2b.Dockerfile`, `docker/sandbox/start-services.sh`, `docker/sandbox/pyproject.toml`) | `./scripts/stack_control.sh build-sandbox` |
| Running sandbox containers need hot-patch (src-only, skip image rebuild) | `./scripts/stack_control.sh patch-sandbox` (copies + restarts services) |

**`--quick` mode** uses Docker layer cache and only rebuilds source layers — fast for Python-only
changes. **Full mode** (no flag) does `--no-cache` and rebuilds everything including system packages.

After a sandbox rebuild, existing sandbox containers use the old image. New sandboxes spawned by
subsequent agent queries will use the updated image automatically. The E2E tests create fresh
sessions, so each test run will get a new sandbox with the updated image — no manual action needed.

#### Both backend and sandbox changed

If your fix touches both backend and sandbox code, rebuild both. Choose the appropriate sandbox
mode based on what changed (see table above):

```bash
# Use --quick for src-only sandbox changes, omit for Dockerfile/system changes
./scripts/stack_control.sh build-sandbox --quick 2>&1 | tail -10
./scripts/stack_control.sh rebuild backend 2>&1 | tail -15
for i in $(seq 1 30); do
  curl -sf http://localhost:8000/health && echo " Backend ready" && break
  sleep 2
done
curl -sf http://localhost:8000/health || echo "ERROR: Backend failed to start"
```

### Step 4 — Retest the Single Fix

Re-run **only** the test you just fixed:

```bash
python3 scripts/local/test_e2e.py --test <TEST_ID> 2>&1
```

- If it **passes**: mark this failure as resolved, move to next failure in the inner loop
- If it **still fails**: return to Step 1 with the new error output. Do not loop more than
  3 attempts on the same test — if still failing after 3 fix attempts, log the issue and move on

### Step 5 — After All Failures Processed

Once every failure from the inner loop has been addressed (fixed or logged as unresolvable after
3 attempts), return to the **Outer Loop Re-entry** below.

## Outer Loop Re-entry

After the inner loop completes, re-run the full suite to catch any regressions from your fixes:

```bash
cd /home/mdear/workspaces/git/ii-agent
source ~/workspaces/venvs/ii-agent/bin/activate
python3 scripts/local/test_e2e.py --failed 2>&1
```

The `--failed` flag will:
1. Load `.e2e_last_results.json` (which was saved from the previous full run)
2. Run **only** tests that had FAIL or ERROR status
3. Save new results, overwriting the previous file
4. Show summary and any remaining failures

This catches regressions introduced by fixes. Parse the output and:

- **All failures now pass?** → Repeat outer loop one more time with `--clear` to ensure no other tests broke
- **Different failures than before?** → New bugs introduced. Return to inner loop
- **Same failures as before?** → Plateau reached, no progress. Stop and report stuck failures
- **After 5 outer loops?** → Limit reached. Report current state and stop

## Completion Criteria

The cycle is **complete** when ONE of these is true:

1. **All tests pass**: every test is PASS or SKIP-with-reason (no FAIL or ERROR)
2. **Plateau reached**: a full outer loop produces the exact same set of failures as the previous
   outer loop (no progress was made) — report the stuck failures and stop
3. **Max iterations reached**: after **5 outer loop iterations**, stop regardless and report current
   state — this prevents infinite see-saw regression cycles

## Output Format

After completion, report a summary table:

```
E2E Test Cycle Complete
═══════════════════════
Outer loop iterations: N
Total tests: X
  PASS:  Y
  SKIP:  Z (with reasons)
  FAIL:  W (with root cause notes)

Fixes applied:
  - <file>: <one-line description>

Unresolved issues:
  - <TEST_ID>: <why it could not be fixed>
```

## Environment Variables

The test script supports filtering:

| Variable | Purpose | Example |
|----------|---------|---------|
| `TEST_CATEGORY` | Run only one category | `TEST_CATEGORY=CHAT python3 scripts/local/test_e2e.py` |
| `TEST_ID` | Run a single test | `TEST_ID=IMG-01 python3 scripts/local/test_e2e.py` |
| `BACKEND_URL` | Override backend URL | Default: `http://localhost:8000` |
| `TOKEN` | Override auth token | Has default for local dev user |
| `E2E_SESSION_TTL` | Seconds until test sessions auto-delete | Default: `86400` (24 hours) |

## Automatic Session Cleanup

The test script automatically schedules every session it creates for deletion after `E2E_SESSION_TTL`
seconds (default: 24 hours). This uses the `POST /sessions/{session_id}/schedule-delete` endpoint
with `{"delete_after_seconds": <ttl>}`. The backend's orphan cleanup loop (60-second sweep) soft-deletes
expired sessions, which cascades to sandbox container teardown.

- Cleanup scheduling is **non-fatal** — a failure to schedule does not fail the test
- Set `E2E_SESSION_TTL=0` to disable automatic scheduling (sessions persist until manually deleted)
- The test summary prints how many sessions were scheduled for cleanup at the end of the run
- To inspect a session before auto-cleanup, use its session ID within the 24-hour window

If you need to manually trigger immediate deletion of a test session instead of waiting:

```bash
curl -sf -X DELETE "$BACKEND_URL/sessions/<SESSION_ID>" -H "Authorization: Bearer $TOKEN"
```

## Test Categories

| ID | Category | Tests |
|----|----------|-------|
| INF | Infrastructure | Health, models, sandbox readiness |
| CHAT | Chat Mode (REST) | Anthropic, OpenAI, multi-turn, web search, long response, stop |
| IMG | Image Attachments | Upload, chat attachment, agent attachment |
| WEB | Web Search & Browser | Agent web search, browser navigation |
| CODE | Code Execution | Single file, multi-file sandbox execution |
| SESS | Session Management | List, events, pin, fork |
| AGEN | Agent Multi-Turn | Context retention, tool use across turns |
| XFEAT | Cross-Feature | Agent web search + file, chat then agent on same session |
| HIST | Chat History | Message persistence and retrieval |
| CNCL | Council Mode | Basic, validation, billing events |
| A2A | A2A Backend | Config, chat/agent routing, council integration |

## Critical Rules

- **NEVER use raw `docker compose`** — always use `./scripts/stack_control.sh`
- **NEVER stop before all runnable tests have been executed and the outer loop is satisfied**
- **Run ruff** on any changed Python files under `src/` before rebuilding
- Keep fixes minimal — do not refactor or improve code beyond what the failing test requires
- If a test is SKIP due to external factors (API quota, missing credentials), document it and move on
- Do not modify test expectations to make tests pass — fix the underlying code instead
- Use `--failed` flag after first cycle to efficiently re-test only failures
- Use `--clear` flag only at the start (or to reset and try a different approach)
