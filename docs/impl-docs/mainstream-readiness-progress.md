# Mainstream-Readiness Implementation Progress

**Scope:** Fix gaps identified in the post-main architecture audit so the A2A
inner loop, local Docker sandbox, and related changes are suitable for a wide
OSS community. Revised 2026-04-18 after plan evaluation against actual code.

**Status legend:** ⬜ not-started · 🟡 in-progress · ✅ done · ⏭ deferred (with reason)

---

## Phase 1 — Must-fix before community-facing tag

| # | Task | Files | Status | Notes |
|---|---|---|---|---|
| 1a | Move module-scope `from a2a.types import …` to `TYPE_CHECKING` or function-local in `multimodal.py`, `event_stream_adapter.py`, `as_client.py`, `a2a_turn_loop_service.py`, `agents/inner_loop.py`; **add `pytest.importorskip("a2a")` at top of every `src/tests/unit/integrations/test_a2a_*.py` and `test_copilot_*.py`** so test collection passes on default install | as listed + `src/tests/unit/integrations/test_a2a_*.py`, `test_copilot_*.py`, `test_claude_code_backend.py`, `test_codex_backend.py` | ✅ | **Prereq for 1b.** Without test-collection guard, CI on default install fails at import. |
| 1b | Move `a2a-sdk` and `github-copilot-sdk` to `[project.optional-dependencies.a2a]`; raise clear error when `AGENT_INNER_LOOP_MODE=a2a` and extras missing; update `.env.example` with all new A2A/Docker env vars and comments | `pyproject.toml`, `integrations/a2a/__init__.py`, `.env.example` | ✅ | **Do NOT touch `docker/sandbox/pyproject.toml`** — adapter image needs these unconditionally |
| 2 | Call `remove_session_lock(session_id)` from `SessionService._publish_session_deleted_event` (covers single + bulk soft-delete); add `try/finally` in `A2AChatTurnLoop._a2a_turn_loop` so lock is released on any exception | `sessions/service.py`, `chat/application/a2a_turn_loop_service.py` | ✅ | Orphan-cleanup raw-SQL soft-delete path is an accepted residual leak (idle `asyncio.Lock()` objects, cleared on restart) |
| 3 | **Refocused:** CLI presence check inside adapter process (`integrations/a2a/__main__.py`); surface per-session adapter health failures to UI via new `InnerLoopFallbackEvent` (reason, fallback_target); startup validation: when `inner_loop_mode=a2a`, log active backend + required credentials (`gh auth status` for copilot, API keys for others); reject `inner_loop_mode=a2a` + no `a2a_agent_url` + no `local_mode` at startup | `integrations/a2a/__main__.py`, `realtime/events/app_events.py`, `agents/agent.py::_wait_for_a2a_adapter`, `app/lifespan.py`, `core/config/agent.py` validator | ✅ | `_wait_for_a2a_adapter` already exists (20s, non-fatal). Default `a2a_backend="copilot"` is silent trap if user enables a2a without `gh` — validator surfaces early. |
| 4 | Enrich `/health` with `a2a_backend_reachable`, `sandbox_provider`, `docker_available`, `port_pool_free`, circuit-breaker state, adapter task-store size | `app/health.py` | ✅ | Only under `sandbox.local_mode`; cache Docker probe (30s) to avoid DoS |
| 5 | Create `docs/docs/a2a-inner-loop-guide.md` — what/when/why/setup/billing/troubleshooting | new doc | ⬜ | Cross-link from getting-started, llm-auth |
| 6 | Add `A2A Inner Loop` + `Docker Sandbox Architecture` sections to `CLAUDE.md`; paragraph in `AGENTS.md` | `CLAUDE.md`, `AGENTS.md` | ✅ | |
| 7a | Pre-archive link sweep (`grep -rn` file-name refs in `CLAUDE.md`, `AGENTS.md`, `docs/**/*.md`) for each file being moved | all docs | ⬜ | **Prereq for 7b** to avoid link breakage |
| 7b | Create `docs/rebase-analysis/README.md` (internal-only); create `docs/design-docs/index.md` with status tags; move superseded docs to `docs/design-docs/archive/` (preserve history) — NOT delete | `docs/rebase-analysis/`, `docs/design-docs/` | ⬜ | Candidates: `a2a-copilot-model-steering.md` (superseded by `-implemented`), any `claw-code-*` typo files, `copilot-sdk-integration-assessment.md` |
| 8 | Resolve `REVIEW_FINDINGS.md`: append resolution header with current test pass rate after T4 triage | `REVIEW_FINDINGS.md` | ⬜ | **Depends on T4** |
| 15 | **NEW** — Minimal CI: `.github/workflows/test.yml` runs `uv sync --extra a2a`, `ruff check`, `pytest src/tests/unit` on PRs | new file | ⬜ | Table-stakes for community contributions; blocks regressions from PRs |
| 16 | **NEW** — Document A2A API-key provisioning in guide: how `II_AGENT_A2A_API_KEYS` is generated and passed to sandbox adapter via env | `docs/docs/a2a-inner-loop-guide.md`, `scripts/stack_control.sh` (env pass-through verification) | ⬜ | Without this community users skip adapter auth (insecure) or fail to connect |
| 17 | **NEW** — Upgrade runbook: `docs/docs/upgrade-to-a2a.md` covering new env vars, optional-extra install, no-migration statement, rollback steps | new doc | ⬜ | For users pulling from main after this lands |

## Phase 2 — Durability for multi-worker / multi-tenant

| # | Task | Files | Status | Notes |
|---|---|---|---|---|
| 9 | ⏭ **DOWNGRADED** — Redis-backed `CompactionAuthority` dropped. Real defect (memory leak) is solved by #2. Socket.IO sticky-sessions already route one session to one worker, so split-brain is theoretical. Async-ifying `is_compaction_locked()` cascades into `context_service.py:215` and breaks `test_inner_loop.py:431` which imports module-global `_locks`. Instead: document "multi-worker = sticky sessions required" in guide; add one-line comment in `compaction_lock.py` | `compaction_lock.py` docstring, guide doc | ⬜ | Cost/benefit does not justify full refactor |
| 10 | Wire `A2AChatTurnLoop` creation in `lifespan.py` **after** pubsub init; attach to container via setter (mirror existing `container.*_service.set_pubsub(pubsub)` pattern); expose `A2AChatTurnLoopDep`; remove bare `a2a_loop=` kwarg from `ChatService` ctor | `lifespan.py`, `core/container.py`, `chat/application/dependencies.py`, `chat/application/chat_service.py` | ✅ | **Correction:** cannot live in `ApplicationContainer.init()` because pubsub is constructed after container |
| 11 | Distributed advisory lock around orphan-cleanup sweep (Redis `SET NX EX`, key `sandbox:cleanup:lock`, TTL 5 min); log warning when Redis disabled (don't silently skip) | `agents/sandboxes/orphan_cleanup.py`, new helper `core/redis/lock.py` or inline | ✅ | |
| 12 | ⏭ **DEFERRED** — Per-session temp dir for Copilot attachments. No multi-tenant community deployment uses Copilot backend yet; #14 documents "single-tenant only". Re-open when multi-tenant adapter architecture lands. | — | ⏭ | |
| 13 | `DOCKER_SOCK_PATH` env + auto-detect Colima/OrbStack/Podman sockets | `core/config/sandbox.py`, `agents/sandboxes/docker.py` | ✅ | Unblocks macOS users |
| 14 | Multi-tenant warning + startup log banner when `inner_loop_mode=a2a` + auth enabled | `docs/docs/a2a-inner-loop-guide.md`, `lifespan.py` | ⬜ | |
| 18 | **NEW** — Sandbox hardening: set `read_only=True` + tmpfs for `/tmp`, `/var/tmp`; keep workspace volume writable. Requires smoke-testing against existing tools (npm install, python build caches) | `agents/sandboxes/docker.py:337`, test: `src/tests/unit/sandboxes/` | ✅ | Current `read_only=False` is wider attack surface than needed |
| 19 | **NEW** — Docker-group diagnostic: at startup, if `docker_socket_path` exists but user lacks perms, log a single clear actionable error (don't wait for first sandbox request) | `app/lifespan.py`, `core/config/sandbox.py` | ✅ | Folds into #13 implementation |
| 20 | **NEW** — Scope cleanup-sweep distributed lock (#11) to cover the entire sweep including `_soft_delete_expired_sessions`, not just the container-removal phase | `agents/sandboxes/orphan_cleanup.py` | ✅ | Extends #11 |
| 21 | **NEW** — Functional-parity smoke test: with mocked adapter, run canned chat scenario twice (`inner_loop_mode=direct` vs `a2a`) and assert same `ModelUsageEvent` schema + final message content. Prevents silent divergence | `src/tests/unit/chat/test_inner_loop_parity.py` (new) | ✅ | Direct answer to user's "maintain functional parity" goal |
| 22 | **NEW** — Cap `_sessions` dict in `copilot_backend.py` (LRU, maxsize≈1000, matches `TaskStore` pattern) to prevent unbounded growth on high session churn | `integrations/a2a/copilot_backend.py` | ✅ | Complement to existing session reaper |
| 23 | **NEW** — Fallback billing dedup: when `a2a_fallback_to_native` triggers mid-turn, ensure tokens are billed exactly once. Add turn_id-keyed idempotency in `CreditUsageHandler` OR single `billing_backend` tag | `credits/usage/handler.py`, `chat/application/a2a_turn_loop_service.py` | ✅ | Prevents double-charge regression |
| 24 | **NEW** — Adapter log persistence: redirect tmux-hosted adapter stdout/stderr to rotated file `/workspace/.ii-agent/adapter.log` (or Docker log driver) inside sandbox. Currently lost when tmux pane dies | `docker/sandbox/start-services.sh:76` | ✅ | Table-stakes for community debuggability |
| 25 | **NEW** — Pin CLI versions in sandbox Dockerfile (`gh`, `claude`, `codex`) with comments referencing compatible SDK versions. Unpinned today → upstream breaking change silently breaks A2A on next rebuild | `docker/sandbox/Dockerfile` | ✅ | Directly protects functional parity |
| 26 | **NEW** — Graceful-shutdown sandbox drain: in `lifespan.py` shutdown, pause running sandbox containers (set short `timeout_at`) before redis/engine shutdown so rolling deploys don't hard-kill in-flight turns | `app/lifespan.py`, `agents/sandboxes/orphan_cleanup.py` (expose `flush_running_sandboxes()`) | ✅ | Zero-downtime deploys |
| 27 | **NEW (optional)** — `scripts/stack_control.sh doctor`: one-shot diagnostic for Docker daemon, socket perms, Postgres, Redis, env vars, `gh auth status`, `[a2a]` extras, sandbox image presence. Collapses community support surface | `scripts/stack_control.sh`, optional `src/ii_agent/scripts/doctor.py` | ⬜ | Nice-to-have, not a blocker; can ship in follow-up |

## Cross-cutting

| # | Task | Status | Notes |
|---|---|---|---|
| T1 | Unit tests for: `remove_session_lock` wired via `_publish_session_deleted_event`, try/finally releases lock on exception, health enrichment fields, adapter URL probe, orphan-cleanup lock no-op when Redis disabled, DOCKER_SOCK_PATH resolution, module-level A2A import safety (default install) | ⬜ | |
| T2 | **Baseline `uv run pytest src/tests/unit -q` BEFORE any code change** — capture full failure set | ✅ | Critical: distinguishes pre-existing failures from regressions we introduce |
| T3 | `uv run ruff check --fix-only <changed>` + `ruff format <changed>` + recheck, per changed-file batch | ✅ | |
| T4 | Full unit suite after all code changes; diff vs T2 baseline; fix regressions | ✅ | Feeds #8 |

---

## Migration / rollback notes for community users

- **Optional A2A extras (1b):** `uv sync --extra a2a` (or `pip install ii-agent[a2a]`) required when `AGENT_INNER_LOOP_MODE=a2a`. Document in release notes.
- **No DB schema changes** in this batch; no migrations.
- **Reversibility:** All changes are code-only; revert restores prior behavior.

## Out-of-scope (re-confirmed)

- Multi-node distributed port manager. Position: **single-node only**.
- Per-user GitHub-token for Copilot backend (multi-tenant SaaS).
- Redis-backed compaction authority (see #9 rationale).
- Kubernetes/gVisor deployment runbook.
- `architecture-local-to-cloud.md` Stage 2/3 rewrite.
- Shell-injection hardening beyond existing type validation in `docker_shell.py`.

## Risk log

- **Pre-existing test failures** (`REVIEW_FINDINGS.md`). Mitigation: T2 baseline before changes.
- **Module-scope A2A imports** block clean optional-dep split. Mitigation: 1a must land before 1b.
- **`test_inner_loop.py:431` imports module-global `_locks`**. Mitigation: keep `compaction_lock.py` module + globals intact; only add `remove_session_lock` call sites + try/finally.
- **Pubsub construction order** means A2A loop cannot live in `ApplicationContainer.init()`. Mitigation: setter pattern from `plan_service.set_pubsub`.
- **Frontend `compaction_locked` event contract** (`use-app-events.tsx:1671`) — do not change event payload schema.
- **Docker image rebuild not needed** for any Phase 1/2 fix (root and sandbox `pyproject.toml` are independent).
- **Doc-archive link breakage**. Mitigation: 7a link sweep; use archive-move not delete to preserve history.

## Execution order (concrete)

1. **T2** baseline `uv run pytest src/tests/unit -q` — capture pass/fail set.
2. **1a** import hygiene + test-collection guards (`importorskip`).
3. **1b** deps move to `[a2a]` extra + `.env.example` update.
4. **2** `remove_session_lock` wiring + try/finally.
5. **3** UI fallback event + adapter-side CLI check + config validator.
6. **4** `/health` enrichment (CB state, task-store size, 30s cache).
7. **11 + 20** distributed cleanup lock (full sweep scope).
8. **13 + 19** `DOCKER_SOCK_PATH` + permission diagnostic.
9. **18** sandbox `read_only=True` + tmpfs (smoke-test npm/pip paths first).
10. **24 + 25** adapter log persistence + pin CLI versions (sandbox image change — requires rebuild; schedule together).
11. **26** graceful-shutdown sandbox drain.
12. **10** A2A loop container wiring (setter post-pubsub).
13. **22** `_sessions` LRU cap in copilot backend.
14. **23** fallback billing dedup.
15. **21** functional-parity smoke test.
16. **Documentation push:** 5 → 17 → 16 → 14 → 6 → 7a → 7b.
17. **15** CI workflow.
18. **27** (optional) doctor command — follow-up PR.
19. **T3** ruff on every changed batch; **T4** full pytest; **8** REVIEW_FINDINGS resolution.

## Log

- 2026-04-18: Document created.
- 2026-04-18: Plan evaluated against code. Downgraded #9 (Redis CompactionAuthority — over-engineered for the actual defect). Split #1 into prereq 1a (import hygiene) + 1b (dep move). Corrected #3 (CLI check is adapter-side, main backend probes URL). Corrected #10 (construction order; setter pattern). Deferred #12 (per-session temp dir). Added T2 baseline run prereq. Added migration notes, link-sweep prereq 7a, archive-not-delete policy for 7b.
- 2026-04-18 (round 2): After deeper probe of adapter architecture and existing code: adapter server runs inside sandbox container (confirmed `docker/sandbox/start-services.sh:79`). `_wait_for_a2a_adapter` already exists at `agents/agent.py:510` (20s non-fatal). Adapter auth already gated by `II_AGENT_A2A_API_KEYS`. Sandbox hardening partial (cap_drop ALL, no-new-privs, mem_limit 3GB, pids_limit 512) but `read_only=False`. **Refocused #3** to surface adapter-health failures via new `InnerLoopFallbackEvent` rather than redundant startup probe. **Added #15 (CI)**, **#16 (A2A key provisioning docs)**, **#17 (upgrade runbook)**, **#18 (sandbox read_only)**, **#19 (docker perms diagnostic)**, **#20 (extend #11 lock scope)**. Added circuit-breaker state + task-store size to #4 health output.
- 2026-04-18 (round 3): Spotted test-collection regression risk (pytest imports A2A test modules; without `[a2a]` extra → ImportError). **Extended 1a** to add `pytest.importorskip("a2a")` guard in every A2A test module. **Extended 1b** to update `.env.example` with all new env vars (`AGENT_INNER_LOOP_MODE`, `AGENT_A2A_*`, `SANDBOX_PROVIDER`, `DOCKER_SOCK_PATH`). **Extended #3** with config validator for `inner_loop_mode=a2a` + missing `a2a_agent_url`/credentials trap. Added **#21 (functional-parity smoke test — direct vs a2a equivalence)**, **#22 (LRU cap on `_sessions` dict in copilot backend)**, **#23 (fallback billing dedup)**. Added concrete execution order section.
- 2026-04-18 (round 4 — final): Probed shutdown, quotas, CLI versions, log hygiene. Added **#24 (adapter log persistence — tmux-hosted logs currently lost)**, **#25 (pin CLI versions in sandbox Dockerfile — unpinned today, upstream break silently regresses parity)**, **#26 (graceful-shutdown sandbox drain — rolling deploys currently hard-kill in-flight turns)**, **#27 (optional doctor command — nice-to-have, follow-up PR)**. Confirmed diminishing returns: round 4 only surfaced 2 truly-missing blockers (24, 25) + 1 pre-production nice-to-have (26) + 1 follow-up (27). No round-4 finding invalidated a round-3 decision. **Plan is frozen; next step is execution.**
- 2026-04-18 (execution): Completed items 1a, 1b, 2, 3, 4, 6, 10, 11, 13, 18, 19, 20, 21, 22, 23, 24, 25, 26, T2, T3, T4. Test results: 5762 passed (5758 baseline + 4 new parity tests), 0 failures, 22 warnings. Ruff clean on all changed files.
