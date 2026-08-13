# A2A Implementation Handoff Plan

> Status: Active remediation backlog for parallel coding session
> Scope: Implementation guidance only (no design re-derivation)
> Parent design: [a2a-copilot-cli-inner-loop-strategy.md](a2a-copilot-cli-inner-loop-strategy.md)
> Status tracking: [../impl-docs/a2a-copilot-cli-inner-loop-impl.md](../impl-docs/a2a-copilot-cli-inner-loop-impl.md)

## Purpose

This document guides the separate coding session that is remediating A2A runtime behavior while design review proceeds in parallel.

Use this as the source of truth for implementation order, acceptance criteria, and test expectations.

## Parallel Work Contract

1. This coding session owns runtime and test changes only.
2. Design decisions and protocol profile changes stay in the strategy document.
3. Any implementation deviation from this plan must be reflected in the strategy doc before merge.

## Canonical Compatibility Matrix (Single Source of Truth)

Use this table as the anti-divergence contract across strategy, implementation, and tests.

| Surface | Internal compatibility profile (current) | A2A 1.0 interop profile (target) | Owner track |
|---|---|---|---|
| Version negotiation (`A2A-Version`) | Optional/legacy-tolerant parsing for internal clients | Explicit request-time negotiation and deterministic rejection of unsupported versions | Track A |
| Stream envelope (`/message:stream`) | Internal SSE envelope (`type`/`data`) for ii-agent integration | Canonical `StreamResponse` wrappers (`task`, `statusUpdate`, `artifactUpdate`, `message`) | Track A |
| Sync envelope (`/message:send`) | Adapter task object compatible with internal runtime expectations | Canonical 1.0 response object shapes and enums | Track A |
| Auth enforcement | Enforced for protected routes in production bootstrap paths | Same, with interop-safe error semantics and auth metadata behavior | Track B |
| Authorization scoping | Task/resource ownership isolation for internal callers | Same, with no cross-tenant/cross-scope existence leakage | Track B |
| Core operation surface | Declared limited profile allowed if explicitly documented | Declared operations and capabilities fully aligned to published profile | Track C |
| Event translation | One canonical mapping implementation | Same canonical mapping path, interop wrappers added without split-brain logic | Track D |
| Compaction authority | ii-agent canonical persistence and fallback-safe reconciliation | Same guarantees plus explicit authority telemetry and diagnostics | Track E |

Production-usable for this repository means:

1. Internal ii-agent consistency is deterministic (routing, envelopes, auth, and fallback behavior are coherent).
2. Future-proofing is preserved (clear profile boundaries, additive compatibility path to strict interop, and no lock-in to undocumented behavior).
3. External A2A 1.0 interop is not claimed until the interop-profile cells above are complete.

## Remediation Tracks

### Track A: Protocol Envelope and Versioning

Goal:

Make runtime behavior explicit across two profiles:

1. Internal compatibility profile (current type/data stream envelope).
2. A2A 1.0 interop profile (canonical StreamResponse wrapper semantics).

Implementation tasks:

1. Add explicit request-time version handling for A2A-Version in HTTP paths.
2. Implement deterministic response behavior for unsupported versions.
3. Add canonical StreamResponse serialization mode for streaming and sync task responses.
4. Preserve internal envelope mode for existing internal consumers during migration.
5. Define a deterministic profile-switch contract (default profile, activation mechanism, and precedence when multiple signals are present).

Acceptance criteria:

1. Requests with supported versions are accepted and processed predictably.
2. Requests with unsupported versions return consistent error payloads and status codes.
3. Interop mode returns canonical StreamResponse wrappers for stream events.
4. Existing internal consumers continue to function under compatibility mode.
5. Profile selection behavior is deterministic and documented for every adapter entry path.

Required tests:

1. Header/metadata parsing tests for A2A-Version.
2. Unsupported version error contract tests.
3. StreamResponse shape tests for task, statusUpdate, and artifactUpdate events.
4. Backward-compatibility tests for legacy internal envelope mode.
5. Profile-switch precedence tests (for all supported selection signals).

### Track B: Auth Middleware Activation and Security Surface

Goal:

Ensure authentication middleware is actually enforced in production adapter app bootstrap paths.

Implementation tasks:

1. Wire auth middleware into adapter app construction for non-public endpoints.
2. Keep well-known discovery endpoint behavior aligned to design (public path rules).
3. Ensure unauthorized access produces consistent 401 behavior across supported routes.
4. Enforce authorization scoping for task-bound operations (Get/Cancel/Subscribe and any list surface in selected profile).

Acceptance criteria:

1. Protected endpoints deny requests without valid bearer credentials.
2. Public discovery endpoint behavior matches intended open/closed policy.
3. Route-level behavior is consistent between direct app creation and CLI main entrypoint.
4. Task/resource access is scoped to authorized callers and does not leak cross-scope existence details.

Required tests:

1. Unauthorized access tests for message and task endpoints.
2. Authorized access tests for the same endpoints.
3. Public endpoint bypass tests for discovery paths.
4. Authorization scoping tests for task ownership/visibility boundaries.

### Track C: Core Operation Completeness Profile

Goal:

Documented operation surface should match declared implementation profile.

Implementation tasks:

1. Either implement missing core operations for selected profile, or
2. Explicitly declare limited operation profile in agent metadata and docs.

Acceptance criteria:

1. Implemented endpoints and declared capabilities do not conflict.
2. Client expectations are clear for non-implemented operations.
3. Contract tests cover all declared operations.

Required tests:

1. Endpoint availability tests for all declared operations.
2. Consistent unsupported-operation responses where applicable.

Recommended completion checklist (required for Track C sign-off):

1. Agent Card capabilities and implemented endpoint surface match exactly for the selected profile.
2. Every declared operation has at least one contract test; every non-declared operation has deterministic unsupported behavior.
3. Unsupported operations return consistent status code and machine-readable error payload across both streaming and sync entry points.
4. The canonical compatibility matrix in this document is updated for any operation-surface change before code merge.
5. The implementation status document records which profile is being claimed and which operations remain intentionally out of scope.

### Track D: Event Translation Consolidation

Goal:

Avoid split-brain event translation logic by selecting one canonical translation path.

Implementation tasks:

1. Choose canonical translation layer for A2A event conversion.
2. Decommission or wrap alternate path to prevent drift.
3. Add single-source mapping table tests based on canonical path.

Acceptance criteria:

1. One canonical mapping source exists for runtime event translation.
2. No contradictory mappings remain in active runtime paths.
3. Mapping behavior is test-covered for success, interruption, and failure flows.

Required tests:

1. Golden mapping tests from runtime events to A2A events.
2. Ordering tests for status and artifact updates.
3. Regression tests for input_required and error transitions.

### Track E: Compaction Control and Telemetry

Goal:

Enforce anti-dueling compaction policy with measurable runtime signals.

Implementation tasks:

1. Expose compaction-related controls in backend configuration where supported.
2. Emit compaction authority and transition telemetry events.
3. Preserve context reconciliation guarantees after fallback events.

Acceptance criteria:

1. Compaction authority is attributable in telemetry.
2. Fallback and resume flows maintain canonical state precedence.
3. Long-running delegated sessions expose compaction behavior in diagnostics.

Required tests:

1. Context reconciliation tests after fallback and re-delegation.
2. Telemetry emission tests for compaction and reset events.
3. Session continuity tests under compaction pressure.

## Execution Order for the Coding Session

1. Track A first (protocol contract stability).
2. Track B second (security enforcement).
3. Track D third (translation consolidation).
4. Track C fourth (operation completeness/profile declaration).
5. Track E fifth (compaction observability and controls).

Rationale:

1. Protocol and auth contracts are highest-risk integration surfaces.
2. Consolidated event mapping reduces rework while adding operation coverage.
3. Compaction controls depend on stable protocol and session behavior.

## Handoff Reporting Template

The coding session should report updates in this format to the implementation status doc:

1. Completed items by track.
2. Acceptance evidence summary (tests, contract validation, behavior checks).
3. Backward-compatibility impact assessment.
4. Remaining open items and blockers.

## Non-Goals for This Handoff

1. No product-level reprioritization decisions.
2. No redesign of the overall A2A-first architecture.
3. No migration of unrelated non-A2A runtime components.
