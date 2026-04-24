# Pre-Warmed Sandbox Pool (Local Docker Mode)

**Status:** Draft / design sketch
**Date:** 2026-04-22
**Scope:** Local Docker sandbox provider only. E2B is out of scope (see §1).
**Author:** GitHub Copilot (sketch)
**Related:** [`sandbox-lifecycle-assessment.md`](sandbox-lifecycle-assessment.md), [`sandbox-accumulation-root-cause-analysis.md`](sandbox-accumulation-root-cause-analysis.md)

---

## 1. Motivation

A cold Docker sandbox start observed in production (session `abaeaca6`):

| Phase | Time |
|---|---|
| DB record + port allocation | ~1.5s |
| `docker run` (image already cached) | ~21s |
| `_wait_for_ready` (start-services.sh: Xvfb, MCP server, A2A adapter, code-server) | **~88s** |
| **Total to "sandbox ready"** | **~110s** |

That ~110s is wall-clock time the user stares at "starting" before the LLM stream opens. Once warm, the same sandbox is reused for the rest of the session and subsequent turns are sub-second.

**E2B note:** E2B uses Firecracker microVM snapshots (their "templates") and an internal warm pool — `Sandbox.create()` typically returns in 100-300ms. We do not need to pre-warm anything for the E2B provider; this design is gated on `SANDBOX_PROVIDER=docker`.

---

## 2. Goal

Maintain a configurable pool of N "blank" sandbox containers that are pre-booted (image started, `start-services.sh` complete, healthy) and waiting to be **claimed** by the next session. Default N=2. When a sandbox is claimed, immediately start replenishment to bring the pool back to N.

Pool containers are kept warm for **24 hours** before being retired as stale. When N > 1, retirement is **staggered** so the whole pool never expires at once (see §4.6).

**Non-goals:**
- Cross-tenant pooling (all containers run as the same Docker user; tenancy is enforced at the application layer).
- Pre-warming user-specific state (skills, MCP configs, uploaded media).
- Hot-swapping a running sandbox.

---

## 3. What can be pre-baked vs deferred

A sandbox today is configured at create time with several pieces of session-specific state. Splitting them into "pre-bakable" vs "must-defer" is the central design question.

| Piece of state | Set when | Pre-bakable? | Notes |
|---|---|---|---|
| Docker image | image build | ✅ already baked | |
| Tmpfs / read-only / cap_drop / mem_limit | `containers.run` | ✅ identical for all | |
| Volume `ii-sandbox-workspace-<sandbox_id>` | `containers.run` | ⚠️ **provisional** | Created with placeholder ID; renamed at claim time, OR we accept that pooled containers carry a throwaway volume name (see §6). |
| Allocated ports (6-7 from PortPoolManager) | `containers.run` | ✅ allocated during prewarm; reassigned to session at claim | |
| Labels: `ii-agent.session-id`, `ii-agent.sandbox-id` | `containers.run` | ❌ session-specific | Mutable post-create via `docker container update` — but labels are NOT mutable. Workaround: set placeholder label `ii-agent.pool=ready`; record real session-id in DB only. |
| Env: `SANDBOX_ID`, `SANDBOX_ADAPTER_ENABLED`, A2A backend creds | `containers.run` | ⚠️ partial | A2A creds are **process-wide** (same for all sessions); `SANDBOX_ID` is opaque inside the container and only used for logging. Pre-bake with a placeholder. |
| `start-services.sh` (Xvfb, MCP, A2A adapter, code-server) | container boot | ✅ this is the bulk of the 88s | |
| MCP config (`_configure_mcp` posts user's MCP servers to `:6060/mcp/configure`) | first turn | ❌ user-specific | Must run at claim time. Fast (~1-3s, single HTTP POST). |
| Media upload (`upload_media_to_sandbox`) | first turn | ❌ session-specific | Already runs only when needed; ~10s for the example session. Independent of pool. |
| AgentSandbox DB row | `init_sandbox` | ⚠️ pool rows exist with `session_id=NULL` | Requires schema change (see §6). |

**Net win:** moving Xvfb + MCP server + A2A adapter + code-server boot out of the critical path saves ~88s. The remaining `_configure_mcp` (~3s) and media upload (~10s) stay in the request path but they're parallelisable and small.

---

## 4. Architecture

### 4.1 Components

```text
                   +------------------------------+
                   |  SandboxPoolManager          |
                   |  (singleton, started in      |
                   |   app/lifespan.py step 8c)   |
                   +------------------------------+
                          |              ^
            claim()       |              | replenish() (background)
                          v              |
                   +------------------------------+
                   |  pool: deque[PooledSandbox]  |
                   +------------------------------+
                          |
                          v
                +------------------+
                | DockerSandbox    |
                | + container      |
                | + port_set       |
                | + DB row (pool)  |
                +------------------+
```

A `PooledSandbox` is just a fully-initialised `DockerSandbox` (post `_wait_for_ready`) plus the placeholder DB row.

### 4.2 Pool DB row shape

We extend `agent_sandboxes` with two nullable columns (or reuse existing `provider_data` JSON):

| Column | Type | Purpose |
|---|---|---|
| `pool_state` | `Enum('available', 'claimed', 'retiring')` nullable | NULL = legacy/session-bound row; non-NULL = pool-managed row |
| `claimed_at` | `TimestampColumn` nullable | Set at claim time; used to detect stuck claims |

`session_id` becomes nullable for pool rows. (Today it is `NOT NULL` — that constraint must be relaxed; alembic migration required.)

Alternative (no migration): use a sentinel UUID like `00000000-0000-0000-0000-000000000000` for "available" pool rows. Less clean but avoids schema churn.

### 4.3 Claim flow (`SandboxService.init_sandbox`)

```text
init_sandbox(session_id, user_id):
    1. Try to find existing sandbox for session_id (unchanged)
    2. If none: try pool.claim()  ────────────┐
       a. SELECT ... FOR UPDATE SKIP LOCKED   │  Postgres-side
          one row WHERE pool_state='available'│  exclusion
          LIMIT 1                             │
       b. UPDATE that row:                    │
          session_id = :session_id,           │
          pool_state = 'claimed',             │
          claimed_at = now()                  │
       c. Trigger pool.replenish_async()  ────┘
    3. If pool empty: fall back to current code path (synchronous create).
    4. Run _configure_mcp() on the claimed sandbox (3s).
    5. Return sandbox.
```

### 4.4 Replenish flow

```text
replenish_async():
    if len(available pool rows) >= target_size: return
    asyncio.create_task(_create_one_pool_sandbox())

_create_one_pool_sandbox():
    1. INSERT agent_sandboxes (session_id=NULL, pool_state='available',
       provider='docker', status='INITIALIZING', sandbox_id=uuid4())
    2. DockerSandbox.create(sandbox_id=row.id, session_id='__pool__', ...)
       ── this does the slow ~110s work in the background ──
    3. UPDATE row: status='RUNNING', provider_sandbox_id=container.id,
       expired_at=..., provider_data={...}
```

The replenish task runs **off the request path**. It races with claims; if N requests arrive simultaneously while pool=0, the first claim() sees empty pool, the others queue (or fall through to synchronous create — see §5).

### 4.5 Lifecycle integration

- **Startup** (`app/lifespan.py`): after `ApplicationContainer.init()`, if `SANDBOX_PROVIDER=docker` and `SANDBOX_PREWARM_POOL_SIZE > 0`, instantiate `SandboxPoolManager` and call `replenish_async()` to fill pool to N. **Initial fill is staggered** (see §4.6) so even at first startup the N containers don't all hit their max-age boundary at the same wall-clock minute 24h later.
- **Shutdown**: cancel pending replenish tasks; leave pool containers running (orphan_cleanup will reap them on next backend start if not re-adopted).
- **Cleanup loop integration** (`orphan_cleanup.py`):
  - Pool rows with `pool_state='available'` are **excluded** from `_pause_stale_sandboxes` (they are intentionally idle).
  - Pool rows with `pool_state='claimed'` and `claimed_at < now() - 5min` and no recent activity → revert to `'available'` or mark DELETED (defensive: catches partial-failure during claim).
  - Pool rows with `pool_state='retiring'` → soft-delete + container kill (for graceful pool shrink).
  - Pool rows with `pool_state='available'` and `created_at < now() - max_age` → mark `'retiring'` (one at a time per sweep — see §4.6).

### 4.6 Staggered retirement via slot enumeration (modulo)

**Problem:** If N=2 containers are both prewarmed at backend startup they share the same `created_at` to within milliseconds. 24h later they both hit max-age in the same cleanup sweep → both retire → pool empty → next two sessions pay full cold-start.

**Solution:** every pool row carries a `pool_slot` integer in `[0, N)` and a `retire_at` timestamp. The slot is the *enumeration*; `retire_at` is computed at row creation as:

```
stagger     = max_age / N                             # 86400 / 2 = 43200s = 12h
retire_at   = created_at + max_age - (slot * stagger) # bootstrap only
            = created_at + max_age                    # subsequent replacements
```

That is: at **first-ever** bootstrap (no prior pool rows), slot `i` gets a *shortened* lifetime so its first retirement happens `i * stagger` seconds before the others. Every replacement container thereafter gets a full `max_age` lifetime, so the slot offsets persist forever.

**Bootstrap** (cold start, no pool rows yet):

```
for slot i in 0..N-1:
    spawn container, retire_at = now + max_age - (i * stagger)
```

All N creates fire **in parallel** (the user wants the pool fully populated ASAP). With N=2:

| Slot | Bootstrap retire_at | Replacement retire_at |
|---|---|---|
| 0 | now + 24h | (replaced at 24h) → +24h = 48h, 72h, 96h, ... |
| 1 | now + 12h | (replaced at 12h) → +24h = 36h, 60h, 84h, ... |

Permanent 12h offset between slot 0 and slot 1 retirements. Pool never empties.

**Replacement rule** — when a slot's container is retired *or* claimed, the replacement immediately created in the same slot gets `retire_at = now + max_age`. Slot identity is preserved; the modulo offset is naturally maintained by the time when each slot last cycled.

**Cleanup loop** — every sweep:
1. For each pool row with `pool_state='available'` and `retire_at <= now()`: mark `'retiring'`.
2. For each `'retiring'` row: kill container + delete row + signal pool manager to replenish that slot.
3. For each slot `i` in `[0, N)` with no live `available`/`claimed`/`retiring` row: trigger a replenish-create for that slot.

Step 3 is the "create ASAP if missing" guarantee — works on backend startup AND any time a slot disappears for any reason.

**Edge cases:**
- **N=1:** stagger = max_age; bootstrap slot 0 gets `retire_at = now + max_age - 0 = now + 24h`. Single slot rotates every 24h with one cold-start window per cycle. Acceptable.
- **N>2:** offsets shrink linearly (`24h/3 ≈ 8h`, `24h/4 = 6h`). Containers churn more frequently but pool never empties.
- **Pool size change at runtime:** if the operator drops `SANDBOX_PREWARM_POOL_SIZE` from 3→2, slots ≥2 are marked `'retiring'` on next sweep. If raised 2→3, the cleanup loop's "missing slot" check (step 3) creates the new slot with the bootstrap formula, restoring stagger.
- **Replenish failure mid-cycle:** the slot stays empty until next sweep, which retries. No coordination needed.

---

## 5. Configuration

| Env var | Default | Notes |
|---|---|---|
| `SANDBOX_PREWARM_POOL_SIZE` | `2` | 0 disables the feature entirely. |
| `SANDBOX_PREWARM_MAX_AGE_SECONDS` | `86400` (24h) | Retire pool containers older than this; replenish replaces them. Prevents stale containers carrying day-old `start-services.sh` state. |
| `SANDBOX_PREWARM_RETIREMENT_STAGGER_SECONDS` | `auto` | When N > 1, spread retirements evenly across `max_age / N` so the pool never empties simultaneously (see §4.6). `auto` = `max_age / N`. Set explicitly to override. |
| `SANDBOX_PREWARM_REPLENISH_DELAY_MS` | `500` | Small jitter to avoid thundering-herd if N claims arrive at once. |
| `SANDBOX_PREWARM_ENABLED_PROVIDERS` | `docker` | Comma list. `e2b` not supported (no benefit). |

Settings live on `core/config/sandbox.py::SandboxSettings`.

`SANDBOX_PREWARM_POOL_SIZE` interacts with `SANDBOX_MAX_CONCURRENT_SANDBOXES`: pool containers count toward the cap. Document this explicitly. Effective per-user concurrency = `MAX_CONCURRENT_SANDBOXES - PREWARM_POOL_SIZE`.

---

## 6. Open issues / blast radius

### 6.1 Immutable per-container state

Three pieces of state are baked into the container at `docker run` time and **cannot be changed without recreating the container**:

| State | Used for | Risk if pre-baked |
|---|---|---|
| Docker container `name` (`ii-sandbox-<sandbox_id[:12]>`) | log filtering, debugging | Cosmetic mismatch — pool name ≠ DB row's eventual ID. **Fix:** name pool containers `ii-sandbox-pool-<uuid[:12]>` and just live with the label-doesn't-match-session-id reality. |
| Volume name `ii-sandbox-workspace-<sandbox_id>` | workspace persistence across sandbox restarts | Pool sandbox carries a throwaway volume name forever. Doesn't affect functionality but slightly muddles the orphan-volume cleanup heuristic in `_cleanup_orphaned_volumes`. **Fix:** use `ii-sandbox-pool-workspace-<pool_id>` and update the cleanup regex. |
| Labels (`session-id`, `created-at`) | `docker ps` filtering | Cosmetic; the source of truth is the DB row. |

**These are tolerable.** None of them break correctness; they just mean `docker ps` output is slightly less informative for pool-claimed containers.

### 6.2 Per-session env that's set at boot

A2A adapter env vars (`A2A_COPILOT_TIMEOUT`, etc.) are set at `containers.run` based on `cfg.agent.a2a_adapter_long_horizon_agent_kinds` and the `metadata['agent_kind']` of the **session being created**.

If a pool container was started for a generic session and is then claimed by a `deep_research` session that needs `A2A_COPILOT_TIMEOUT=3600`, **the env will not match**.

**Mitigations (pick one):**
- **Option A** — Always pre-bake with the long-horizon timeout (3600s). Worst case: short turns get a long timeout — harmless.
- **Option B** — Maintain two pools: "default" and "long-horizon". 2× container cost.
- **Option C** — Have the A2A adapter inside the sandbox accept per-request timeout overrides via a header. Cleanest, requires adapter change.

**Recommendation: Option A.** Long timeout is a maximum, not a default sleep. It costs nothing.

### 6.3 Race conditions

| Race | Mitigation |
|---|---|
| Two backends sharing a DB both try to claim the same pool row | `SELECT ... FOR UPDATE SKIP LOCKED` in claim query (Postgres). |
| Backend crashes between claim row-update and `_configure_mcp` | Cleanup loop reverts `claimed` → `available` after 5 min if `session_id` was set but session has no run activity. Or: simpler — if reverted-claim has any session activity, mark sandbox DELETED to be safe. |
| Pool replenish task crashes | Next claim sees pool empty, falls through to synchronous create (current behavior). Replenish retries on next claim. No silent degradation. |
| Pool container dies between prewarm and claim | Claim picks it up, `_connect_provider` fails with `SandboxNotFoundException`, current fallback path kicks in (mark DELETED, create fresh). User sees today's behavior. Pool replenish is triggered. |
| `start-services.sh` inside a pool container OOMs or hangs after prewarm | Periodic health check on idle pool containers (every 60s, hit `/health` on MCP port). Mark unhealthy as `retiring`; cleanup kills + replenish replaces. |

### 6.4 Resource cost

- **Memory:** each pool container is `mem_limit=3GB` reserved (cgroup hard cap, but actual RSS at idle is much lower — Xvfb+chrome+code-server+MCP+A2A adapter ≈ 400-700 MB). With N=1, ~700 MB extra reserved.
- **Disk:** one extra workspace volume per pool slot (~empty initially).
- **CPU:** idle steady-state, near zero. Cold prewarm bursts to ~1 vCPU for 90s.
- **Ports:** N × 7 ports out of `PortPoolManager`'s pool. Default port range is 30000-32767; this is plenty for any reasonable N.

### 6.5 Operational / observability

- **Metrics to add:**
  - `sandbox_pool_size{state}` (gauge: available/claimed/retiring)
  - `sandbox_pool_claim_hit_total` / `sandbox_pool_claim_miss_total` (counters)
  - `sandbox_pool_prewarm_duration_seconds` (histogram)
- **Logging:** emit at INFO when claim hits pool ("Claimed pool sandbox X for session Y, replenishing"), at WARNING on miss with empty pool ("Pool empty, falling back to synchronous create").
- **Admin endpoint:** `GET /admin/sandbox-pool` returning `{target, available, claimed, retiring, last_replenish_at}` for debugging. Gated behind admin auth.

### 6.6 What we are NOT changing

- Existing synchronous-create code path remains the fallback. **Pool is purely additive.** If `SANDBOX_PREWARM_POOL_SIZE=0` (or pool is empty mid-claim), the system behaves identically to today.
- E2B path untouched.
- Cleanup loop's existing 6 stages keep working; we add filters to skip pool rows in stage 3 (idle pause).

### 6.7 Failure modes ranked by severity

| Failure | Severity | Detection | Recovery |
|---|---|---|---|
| Pool container dies silently | LOW | Claim → connect fails → existing fallback path | Automatic |
| Replenish task throws unhandled | MEDIUM | Pool stays at 0; metrics show miss rate spike | Next claim retries replenish |
| Pool DB row stuck in `claimed` due to backend crash | MEDIUM | Cleanup loop reverts after 5 min | Automatic |
| `_wait_for_ready` regression makes prewarm itself slow | MEDIUM | Pool oscillates 0↔1 under load | Same as today (cold-start), no regression vs current |
| `agent_kind`-specific env mismatch (see §6.2) | LOW with Option A | N/A | N/A |
| Pool grows unbounded due to replenish bug | HIGH | Container count > target+2; cap via `MAX_CONCURRENT_SANDBOXES` | Hard cap prevents runaway |
| Pool container leaks across backend restart | LOW | Orphan cleanup catches via `_cleanup_docker_zombies` | Automatic — pool rows re-discovered on startup if labelled `ii-agent.pool=ready` |

---

## 7. Implementation phases

| Phase | Work | Verification |
|---|---|---|
| **1** | Add `SandboxSettings.prewarm_pool_size` etc. + alembic migration for `pool_state`/`claimed_at` (or reuse provider_data JSON to skip migration). | Settings load; migration up/down clean. |
| **2** | `SandboxPoolManager` class with `claim()` / `replenish_async()` / `health_check_loop()`. Wire into `app/lifespan.py`. | Backend boots, pool fills to N within ~110s. |
| **3** | Hook `SandboxService.init_sandbox` to try `pool.claim()` before falling through to synchronous create. | E2E test: 2nd session of the day starts in <5s end-to-end. |
| **4** | Cleanup integration: skip pool rows in `_pause_stale_sandboxes`; revert stuck-claim rows; max-age retirement. | Inject stuck row in test DB → verify revert. |
| **5** | Metrics + admin endpoint. | Hit endpoint, see counters. |
| **6** | Docs + AGENTS.md/CLAUDE.md update describing the pool. | — |

Phases 1-3 are the MVP. Phase 4 is required before going live; phases 5-6 are polish.

---

## 8. Decision points needing input

1. **Migration vs JSON sentinel** for pool state (§4.2). Migration is cleaner; JSON avoids alembic churn.
2. **Option A/B/C** for the long-horizon-timeout env mismatch (§6.2). Recommendation: A.
3. **Default pool size:** 2 (with 24h max-age + staggered retirement per §4.6). Should it be `0` until explicitly opted in for the first rollout? My take: default `0` during initial validation week, then flip to `2` once metrics confirm no regressions.
4. **Should the sandbox image build switch to a pre-snapshot model** (e.g. CRIU checkpoint of post-`start-services.sh` state)? Out of scope here — it's a separate, higher-risk optimization that would benefit even cold creates without needing a pool. Worth investigating in a follow-up.

---

## 9. Summary

A pre-warmed pool of N (default 1) Docker sandbox containers, kept "ready" off the request path, eliminates ~88s of `start-services.sh` boot from the user-visible session-start latency. The design is **purely additive** — the existing synchronous create path is the fallback and the failure mode for any pool issue is "current behavior". Blast radius is low: cleanup-loop integration and a ~5-line schema change are the only invasive bits.

**Recommended next step:** prototype phases 1-3 behind `SANDBOX_PREWARM_POOL_SIZE` (default 0 during validation, flip to 2 after one week of clean metrics; staggered retirement per §4.6 ensures the pool never empties simultaneously).
