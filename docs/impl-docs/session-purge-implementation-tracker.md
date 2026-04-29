# Session purge subsystem — implementation tracker

> Living document. Source of truth for "what's designed vs. what's built"
> in `src/ii_agent/sessions/purge/`. Update on every PR that touches the
> subsystem.

**Design doc**: [`docs/design-docs/session-lifecycle-and-data-custody.md`](../design-docs/session-lifecycle-and-data-custody.md)
**Last refresh**: 2026-04-28

## 1. Module-level status

| Module | Designed | Implemented | Wired in app | Notes |
|---|---|---|---|---|
| `__init__.py` | ✅ | ✅ | n/a | Re-exports public API |
| `types.py` | ✅ | ✅ | n/a | `PurgeOutcome`, `PurgeTrigger`, `PurgeResult`, `SARRequest`, `RetentionException*`, `UserPurgeReason` |
| `exceptions.py` | ✅ | ✅ | n/a | Full hierarchy |
| `db_models.py` | ✅ | ✅ | migrations 20260427_000008/000009 applied | `purge_dead_letter`, `sar_intake` |
| `claim.py` | ✅ | ✅ | called by `session_purge` | CTE form per Adversarial #5 |
| `commit.py` | ✅ | ✅ | called by `session_purge` | Re-check → strip → assert → audit → DELETE in one tx |
| `pii_strip.py` | ✅ | ✅ | called by `commit`, `user_purge` | Strip + `assert_strip_complete` defence-in-depth |
| `session_purge.py` | ✅ | ✅ | sole arbitration entry | I19 idempotency precheck included |
| `providers.py` | ✅ | ✅ orchestrator | called by `session_purge` | Hook registry, retry budget, dead-letter persistence |
| `hooks_openai.py` | ✅ | ✅ | registered in `app/lifespan.py` step 4c | OFF by default; flag `SESSIONS_OPENAI_PROVIDER_CLEANUP_ENABLED` |
| `cleanup_stage.py` | ✅ | ✅ | wired into `agents/sandboxes/orphan_cleanup.py` | Drain loop with wall-clock budget |
| `storage_reaper.py` | ✅ | ✅ | wired via `cleanup_loop_stage_storage_reaper` | OFF by default; flag `SESSIONS_STORAGE_REAPER_ENABLED` |
| `user_purge.py` | ✅ | ✅ | called by router | `purge_user_account`, `intake_sar` |
| `router.py` | ✅ | ✅ | registered in `app/routers.py` | `/v1/sessions/{id}/restore`, `/purge-now`, admin `/purge`, `/unblock-purge`, `/sar` |
| `orm_guards.py` | ✅ | ✅ | registered in `app/lifespan.py` step 4a | `before_insert` Session listener |
| `invariants.py` | ✅ | partial — see §2 | run by `check_runner` | 11 of 19 are DB queries; 8 are intentional structural skips |
| `check_runner.py` | ✅ (new) | ✅ | run by integration test + CLI | Maps invariants → pass/fail/skip/error report |

## 2. Invariant implementation status

The 19 invariants in `invariants.py::ALL_INVARIANTS` partition into
DB-checkable predicates (queries) and structural / cross-system
contracts (verified by tests / deployment, not queries). The design
explicitly classifies the latter group as "remain `NotImplementedError`".

### 2.1 DB-checkable invariants (11)

| ID | Description | Status |
|---|---|---|
| I1 | `purge_after IS NOT NULL ⟹ is_deleted=true` | ✅ implemented |
| I2 | dead-letter rows reference active deletion or vanished session | ✅ implemented |
| I4 | Art. 17 stripped rows have no leaked content keys | ✅ implemented |
| I10 | every dead-letter row has `user_id IS NOT NULL` | ✅ implemented |
| I11 | no PII keys in stripped audit rows | ✅ implemented |
| I12 | SAR pre-empts grace | ✅ implemented |
| I13 | SAR audit fields complete (lawyer memo §5, four fields) | ✅ implemented (this PR) |
| I15 | Art. 17(3) deferred SAR has disclosure event within 30 d | ✅ implemented (this PR) |
| I16 | restore blocked during active SAR | ✅ implemented |
| I18 | legal hold supersedes SAR (no SAR purge after legal-hold-set) | ✅ implemented (this PR) |
| I19 | `session.purge_committed` audit row is unique per session_id | ✅ implemented |

### 2.2 Structural / cross-system invariants (8) — intentional `NotImplementedError`

These cannot be (or should not be) reduced to a single SQL predicate.
Each is enforced elsewhere; the runner skips them and records the skip.

| ID | Why not a query | Where it IS enforced |
|---|---|---|
| I3 | `users.is_purging_set_at` not in schema; predicate would always pass with current model | `NotPurgingDep` on every mutation endpoint; ORM `before_insert` guard; `test_is_purging_gate_enumeration.py` |
| I5 | Requires correlating historic `legal_hold.set` audit events; those events not yet emitted by any code path. Implementing query would always return empty (false-negative risk). Add when legal-hold lifecycle audit events ship. | n/a today — gap flagged in §4 below |
| I6 | "exactly once per (session, claim_cycle)" — verified by integration test that two concurrent invocations only increment `purge_attempts` once | `test_user_purge_claim_arbitration.py` (per design §14.4 — see §4) |
| I7 | Phase-(c) re-checks `is_deleted=true` in same tx — purely structural code path | `commit.commit_purge` step 1 + `test_purge_phase_c_recheck_is_deleted.py` (per design §14.4 — see §4) |
| I8 | `purge_now`-vs-`user_purge` mutex — code-structural via `check_user_not_purging` | `check_user_not_purging` precondition; `PurgeBlockedError` raised by §4.7 step 1 |
| I9 | "every provider artefact ID is reachable" — requires reconciling with provider's own list endpoint via separate audit job | external provider audit job (design §4.5) |
| I14 | Cannot be checked post-hoc (CASCADE-dropped sessions are gone). | `purge_user_account` step 5/6 ordering + I14 precondition check inside `_drive_user_purge` |
| I17 | Deployment configuration: cleanup loop reads from primary, not replica | startup gate (design): assert `cleanup_db_url == primary_db_url` — see §4 |

## 3. Periodic check infrastructure (this PR)

| Artifact | Purpose |
|---|---|
| `src/ii_agent/sessions/purge/check_runner.py` | Runs every invariant in `ALL_INVARIANTS`, classifies each result as PASS / FAIL / SKIPPED_STRUCTURAL / ERROR. Caps logged rows at 50/invariant. |
| `src/tests/integration/test_invariants_in_prod.py` | The nightly job named in design §2.3. Auto-skips when DB unreachable (host CI without stack). Fails on any FAIL/ERROR with row UUIDs in the assertion message. |
| `scripts/local/check_purge_invariants.py` | Operator CLI. Loads `docker/.stack.env.local`, supports `--quiet` and `--json`. Exit code 0 ⟺ every DB-checkable invariant passes. |

### Nonconformance handling (per design §6.1 + §2.3)

The runner produces an `InvariantReport` with an `exit_code`:

* `0` — every DB-checkable invariant passed.
* `1` — at least one FAIL or ERROR.

The design specifies non-zero exit ⇒ **page** via the standard
Prometheus alert wired off the same gauge series in §6.1 (e.g.
`provider_cleanup_dead_letter_unresolved`, `sessions_purge_stuck`,
`sessions_purge_claim_stale`). Until the Prometheus exporter for the
invariant gauges is wired (see §4 below), the integration test failing
in nightly CI / cron is the operational backstop.

The runner does NOT auto-remediate. Every FAIL is operator-triaged:

1. Inspect the offending UUIDs in the alert payload (capped at 50/inv).
2. Identify root cause (code path that violated the invariant).
3. Land a fix that prevents future violations.
4. Either correct or accept the existing data depending on the
   invariant — never quietly delete to silence the alert.

## 4. Outstanding gaps (escalations)

These items remain undone after this PR. Each is flagged here so the
gap is visible rather than buried.

### 4.1 Live finding from the first runner execution

Running `scripts/local/check_purge_invariants.py` against the local
stack on 2026-04-28 produced:

```text
FAIL check_I11_no_pii_keys_in_stripped_rows: 50 violating row(s) (capped)
```

Drill-down (`content ? 'message'` is the only key that triggered;
other PII keys returned 0 rows):

| Key | Rows |
|---|---|
| `prompt` | 0 |
| `message` | 1,236 |
| `file_name` | 0 |
| `error_detail` | 0 |
| `email` | 0 |
| `ip_address` | 0 |
| **total stripped rows in DB** | 21,239 |
| **violating rows (any PII key)** | 1,236 (5.8 %) |

Violators by `event_type`:

| event_type | rows | message-value class |
|---|---|---|
| `agent.processing` | 1,211 | static status strings: `"Processing your message..."`, `"Agent resumed processing..."`, `"Resuming agent execution..."` — zero user data |
| `system.error` | 12 | stack traces / provider error envelopes (e.g. `"Error code: 400 - {'type': 'error', ...}"`, `"Unsupported parameter: ..."`, quota messages) |
| `agent.response.interrupted` | 10 | `"Run <uuid> was cancelled"` — run UUIDs only |
| `agent.tool.confirmation` | 2 | static: `"Agent is paused awaiting confirmation"` |
| `agent.continue` | 1 | static: `"Agent continuing..."` |

**Diagnosis: ~99 % false positive in the current denylist.** The I11
predicate flags the literal *presence* of the key `'message'` in
`content` regardless of value. In every audited stripped row sampled,
the `message` value is either a hard-coded UI status string, a run
UUID, or a provider error envelope — none of which carries user PII.
The `system.error` bucket (12 rows) is the only one warranting hand
inspection: stack-trace bodies CAN incidentally include user-supplied
filenames or parameter values. Sampled examples were API-side error
strings without user content.

Required follow-ups (not blocking pre-flip in their own right; this
is a denylist tuning issue, not a leak):

1. **Tighten I11 predicate** — distinguish PII *value* from PII *key*.
   Option A: drop `'message'` from the I11 denylist, treat
   `agent.processing` `message` values as bounded enum (assert by
   regex match against the known status strings); keep the key in the
   schema as a structured status field. Option B: rename the static
   status field to something other than `message` so it doesn't
   collide with the chat-side denylist.
2. **Audit `system.error` rows by hand** before pre-flip. 12 rows is
   small enough to eyeball. If any contain user inputs, add a strip
   step to the system-error event emitter.
3. Update the tracker once both of the above complete; this finding
   moves from "FAIL" to "PASS" without a data migration.

Investigation owner: TBD.

### 4.2 Prometheus exporter for invariant gauges

Design §6.1 lists `provider_cleanup_dead_letter_unresolved`,
`sessions_purge_stuck`, `sessions_purge_claim_stale` as paging gauges.
A companion gauge family `invariant_violations{name="check_I*"}` would
let Grafana render the periodic check results without parsing test
output. Not in this PR.

### 4.2a Paging-delivery before Prometheus lands (aspirational)

Until §4.2 ships, the runner produces a paging *signal* (non-zero
exit + `logger.error("INVARIANT FAIL ...")`) but no consumer of that
signal is wired. Today a FAIL goes to:

1. **stdout / loguru** — captured by Docker, viewable via
   `scripts/stack_control.sh logs backend`. In prod whatever stdout
   sink the deployment uses receives it (GCP Cloud Logging etc.).
   Nobody is alerting on the `INVARIANT FAIL` substring.
2. **process exit code** — `test_invariants_in_prod.py` and the CLI
   both exit 1 on any FAIL/ERROR. **Nothing is scheduled to run
   them** (no nightly cron, no CI workflow), so the exit code goes
   nowhere.
3. **pytest assertion message** — useful to a human reading a test
   failure, useless for paging.

Zero/low-code stopgaps that would deliver an actual page (track
here; do not implement until prioritised):

| Channel | Effort | Notes |
|---|---|---|
| Log-based alert in the existing log pipeline (GCP / Datadog / wherever backend stdout already ships) | console-config only; no code | Match `INVARIANT FAIL` on the backend logger. Lowest effort; matches prod reality. **Recommended interim**. |
| GitHub Actions nightly workflow | ~20 lines of YAML | `pip install` + run `scripts/local/check_purge_invariants.py --json` against staging on schedule; failure emails repo admins via GitHub default. |
| Cron + `MAILTO` on a backend host | ~5 lines | `MAILTO=oncall@...`; non-zero exit + stderr gets mailed. Requires SMTP on the host. |

Owner of the paging-delivery decision: TBD. Closing this gap is the
pre-requisite for treating §2.3 "page on any non-empty result" as
actually true in prod.

### 4.3 Tests named in design §14.4 not yet present

Per the design's test catalogue, several structural tests are
referenced but not implemented:

* `test_is_purging_gate_enumeration.py` (I3)
* `test_user_purge_claim_arbitration.py` (I6)
* `test_purge_phase_c_recheck_is_deleted.py` (I7)
* `test_audit_row_pii_strip.py` (I4/I11 — exists in spirit via `assert_strip_complete`, but no dedicated test)
* `test_sar_audit_completeness.py` (I13)
* `test_art17_3_disclosure.py` (I15)
* `test_purge_already_purged_idempotent.py` (I19)

These verify the structural invariants that `NotImplementedError`
checks decline to query. Their absence means the structural side of
the invariant contract is currently asserted only by code review.

### 4.4 Provider hooks beyond OpenAI

`providers.py` orchestration is generic. Only the OpenAI hook is
registered. GCS blob and Composio profile cleanup hooks are designed
in §4.5 but not implemented. Without hooks for those providers, phase
(b) silently leaks their per-session resources during purge (returns
0 leaks, not an error).

### 4.5 Audit events for legal-hold lifecycle

The design references `legal_hold.set` and `legal_hold.cleared`
`application_events.event_type` values (§14.3). No code path emits
these events today. Until that ships, I5 and I18 are checking against
a stream that's always empty — false-negative-only failure mode.

### 4.6 Legal hold custody mutation API

Sessions can be marked `custody='legal_hold'` per the schema, but no
admin endpoint or service exposes the transition. Today operators
would have to UPDATE the column directly. Add an admin endpoint that
performs the UPDATE and emits the `legal_hold.set` event in the same
tx (closes 4.5 above for the set path).

### 4.7 Art. 17(3) disclosure send-side

`intake_sar` flags sessions but does NOT enqueue the user
notification mandated by Art. 17(3) closing clause (lawyer memo §6).
The notification must be wired into a delivery channel (email or
in-app) AND emit `art17_3.disclosure` to satisfy I15 in production.

### 4.8 Cleanup-loop primary-DB assertion (I17)

Design says startup must assert `cleanup_db_url == primary_db_url`.
Today the cleanup loop uses `get_db_session_local()` which already
points at the primary, but no explicit assertion exists. A startup
gate that fails closed if a replica URL is detected would harden I17.
