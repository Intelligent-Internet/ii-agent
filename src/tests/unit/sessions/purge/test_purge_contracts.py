"""Test contract for the purge subsystem — §14.4 of the design doc.

This file is the executable equivalent of §14.4's test table. Every test
name here matches a row in the doc; the body is `pytest.skip("PR-E")`
until the corresponding implementation lands.

Why this exists:
  Without skip-stubs, "28 tests required for PR-D/PR-E acceptance" stays
  a number in a heading. With skip-stubs, `pytest --collect-only` returns
  a checklist that CI counts. Reviewers can grep this file against the
  doc table and confirm parity.

Convention:
  - One test function per row in the §14.4 table.
  - The skip reason cites the PR that is expected to implement it
    (PR-D, PR-E, PR-F, PR-G — see `purge/__init__.py` module docstring).
  - When PR-E lands, replace the skip with the actual test body. Do NOT
    delete the skip stub before its implementation lands — losing it
    silently shrinks the contract.

Cross-reference: `src/ii_agent/sessions/purge/invariants.py::ALL_INVARIANTS`
(19 invariants as of v3.11). Every invariant must be cited by at least one
test in this file via the (Ix) suffix in the skip reason.
"""

from __future__ import annotations

import pytest


# ─── PR-A / PR-C: schema + FK migrations ────────────────────────────────────


@pytest.mark.skip(reason="PR-C: not yet implemented")
def test_session_fk_cascade() -> None:
    """Each of the 9 new FKs cascades or sets NULL correctly per §3.1."""


@pytest.mark.skip(reason="PR-C: not yet implemented")
def test_session_fk_not_valid_pattern() -> None:
    """NOT VALID + VALIDATE migration completes online (no ACCESS EXCLUSIVE
    held during VALIDATE)."""


# ─── PR-D / PR-E: per-session purge pipeline ────────────────────────────────


@pytest.mark.skip(reason="PR-E: cleanup-loop purge stage not yet implemented")
def test_cleanup_loop_purge_stage() -> None:
    """Single-session purge runs phases A→C in order; legal_hold skipped;
    sandboxes-not-DELETED gate; ephemeral grace honoured.
    Doc row: `test_purge_stale_deleted_sessions.py` (legacy filename retained)."""


@pytest.mark.skip(reason="PR-F: purge_now endpoint not yet implemented")
def test_purge_now_endpoint() -> None:
    """Synchronous sandbox tear-down (§4.7); 423 on legal_hold; audit row written."""


@pytest.mark.skip(reason="PR-E: legal-hold audit not yet implemented")
def test_legal_hold_audit() -> None:
    """Set/clear writes audit rows with required fields (I5)."""


@pytest.mark.skip(reason="PR-E: storage reaper not yet implemented")
def test_storage_reaper_idempotent() -> None:
    """Reaper handles already-deleted blobs without crashing (§14.2)."""


@pytest.mark.skip(reason="PR-E: provider cleanup not yet implemented")
def test_provider_cleanup_404_swallow_skipped() -> None:
    """Legacy skip-stub kept so the contract list does not shrink."""


def test_provider_cleanup_404_swallow() -> None:
    """OpenAI 404 silent; non-404 logs warning (§14.2).

    The OpenAI hook in `purge/hooks_openai.py::_delete_one` must:
      * treat a 404 (NotFoundError) as a successful delete and return None;
      * treat 5xx / 408 / 425 / 429 / timeout / connection-error as transient;
      * treat other 4xx as permanent.
    """
    import asyncio

    from ii_agent.sessions.purge.hooks_openai import _classify, _delete_one

    class FakeNotFound(Exception):
        status_code = 404

    class FakeStatus500(Exception):
        status_code = 500

    class FakeStatus400(Exception):
        status_code = 400

    class FakeTimeout(Exception):
        pass

    # Patch the openai module names that _classify isinstance-checks against.
    import openai

    monkey = {
        "NotFoundError": openai.NotFoundError,
        "APIStatusError": openai.APIStatusError,
        "APITimeoutError": openai.APITimeoutError,
        "APIConnectionError": openai.APIConnectionError,
    }
    openai.NotFoundError = FakeNotFound  # type: ignore[misc, assignment]
    openai.APIStatusError = (FakeStatus500, FakeStatus400)  # type: ignore[misc, assignment]
    openai.APITimeoutError = FakeTimeout  # type: ignore[misc, assignment]
    openai.APIConnectionError = FakeTimeout  # type: ignore[misc, assignment]
    try:
        # 404 → (transient=False, status=404) → caller swallows.
        transient, status = _classify(FakeNotFound())
        assert status == 404 and transient is False

        # 500 → transient=True
        e500 = FakeStatus500()
        assert _classify(e500) == (True, 500)

        # 400 → transient=False (permanent)
        e400 = FakeStatus400()
        assert _classify(e400) == (False, 400)

        # Timeout → transient=True, no status
        et = FakeTimeout()
        assert _classify(et) == (True, None)
    finally:
        openai.NotFoundError = monkey["NotFoundError"]
        openai.APIStatusError = monkey["APIStatusError"]
        openai.APITimeoutError = monkey["APITimeoutError"]
        openai.APIConnectionError = monkey["APIConnectionError"]

    # Now exercise _delete_one with a fake client whose .containers.delete raises 404.
    class _FakeContainers:
        async def delete(self, _rid: str) -> None:
            raise FakeNotFound()

    class _FakeFiles:
        async def delete(self, _rid: str) -> None:
            raise FakeStatus500()

    class _FakeClient:
        def __init__(self) -> None:
            self.containers = _FakeContainers()
            self.files = _FakeFiles()

    openai.NotFoundError = FakeNotFound  # type: ignore[misc, assignment]
    openai.APIStatusError = (FakeStatus500, FakeStatus400)  # type: ignore[misc, assignment]
    openai.APITimeoutError = FakeTimeout  # type: ignore[misc, assignment]
    openai.APIConnectionError = FakeTimeout  # type: ignore[misc, assignment]
    try:
        client = _FakeClient()
        # 404 on container.delete → None (success, swallowed).
        out = asyncio.run(
            _delete_one(client=client, resource_kind="container", resource_id="cnt_1")
        )
        assert out is None
        # 500 on files.delete → LeakedResource with transient=True.
        leaked = asyncio.run(_delete_one(client=client, resource_kind="file", resource_id="file_1"))
        assert leaked is not None
        assert leaked.transient is True
        assert leaked.resource_kind == "file"
        assert leaked.resource_id == "file_1"
    finally:
        openai.NotFoundError = monkey["NotFoundError"]
        openai.APIStatusError = monkey["APIStatusError"]
        openai.APITimeoutError = monkey["APITimeoutError"]
        openai.APIConnectionError = monkey["APIConnectionError"]


@pytest.mark.skip(reason="PR-F: PITR runbook not yet implemented")
def test_dr_pitr_drill() -> None:
    """PITR restore runbook executable end-to-end (§15)."""


@pytest.mark.skip(reason="PR-E: crash-recovery semantics not yet implemented")
def test_purge_crash_recovery() -> None:
    """Process killed between phase (a) and (c) → claim honoured by next sweep;
    no double-delete (D16)."""


@pytest.mark.skip(reason="PR-E: large-session load test")
def test_purge_load_largest_session() -> None:
    """50k chat_messages + 100k application_events: phase (c) within budget;
    replica lag under p95 SLO."""


@pytest.mark.skip(reason="PR-F: purge_now lock isolation")
def test_purge_now_no_lock_contention() -> None:
    """`purge_now` does not block on `sandbox:cleanup:lock`."""


@pytest.mark.skip(reason="PR-E: dead-letter mechanics not yet implemented")
def test_provider_dead_letter() -> None:
    """5xx for `max_attempts` → dead-letter row, claim retained, paging
    gauge increments (I2)."""


# ─── PR-G: user-account purge ───────────────────────────────────────────────


@pytest.mark.skip(reason="PR-G: user-account purge not yet implemented")
def test_purge_user_account_pipeline() -> None:
    """`purge_user_account` drives every owned session through pipeline
    BEFORE user-CASCADE (I14)."""


@pytest.mark.skip(reason="PR-G: user-account purge not yet implemented")
def test_purge_user_account_dead_letter_blocks() -> None:
    """Unresolved dead-letter (by user_id) → `UserPurgeBlockedError`;
    user row NOT deleted (I10)."""


@pytest.mark.skip(reason="PR-G: user-account purge not yet implemented")
def test_purge_user_account_partial_failure() -> None:
    """One transient session failure does NOT cancel sibling purges;
    user not deleted."""


# ─── PR-D: ORM cascade hygiene ──────────────────────────────────────────────


@pytest.mark.skip(reason="PR-D: ORM cascade audit not yet implemented")
def test_relationship_cascade_consistency_skipped() -> None:
    """Legacy skip-stub kept so the contract list does not shrink."""


def test_relationship_cascade_consistency() -> None:
    """Every `Session.*` ORM cascade matches DB FK policy (§7).

    Specifically: `Session.events` MUST NOT carry `cascade='all, delete-orphan'`
    because the underlying FK is `ON DELETE SET NULL` per §3.1. A divergent
    cascade here would cause the ORM to delete audit rows the FK is configured
    to retain, silently violating the audit-retention contract.
    """
    from ii_agent.sessions.models import Session

    rel = Session.__mapper__.relationships["events"]
    # `viewonly` makes the relationship read-only; cascade settings on a
    # viewonly rel are inert but still get serialised onto the relationship.
    # We assert both: viewonly is set AND no destructive cascade is configured,
    # so flipping viewonly off in the future cannot accidentally re-introduce
    # the cascade.
    assert rel.viewonly is True, "Session.events must remain viewonly per §7"
    cascade = rel.cascade
    for token in ("delete", "delete-orphan", "all"):
        assert token not in cascade, (
            f"Session.events relationship must not configure cascade='{token}' "
            f"— application_events.session_id is ON DELETE SET NULL (§3.1). "
            f"Current cascade: {cascade!r}"
        )


# ─── PR-E: PII strip + audit invariants ─────────────────────────────────────


@pytest.mark.skip(reason="PR-E: PII strip not yet implemented")
def test_audit_row_pii_strip() -> None:
    """After Art. 17 paths, audit `content` reduced to billing-safe;
    `user_id` nulled (I4, I11)."""


@pytest.mark.skip(reason="PR-E: grace-purge billing preservation")
def test_grace_purge_preserves_billing() -> None:
    """Grace-expired purge does NOT apply Art. 17 strip — operational
    forensics preserved (I4)."""


# ─── PR-E: claim arbitration + concurrency ──────────────────────────────────


@pytest.mark.skip(reason="PR-E: claim arbitration not yet implemented")
def test_user_purge_claim_arbitration() -> None:
    """Concurrent user-purge + orphan-loop sweep → single claim per session (I6)."""


@pytest.mark.skip(reason="PR-E: dead-letter retention not yet implemented")
def test_dead_letter_retention() -> None:
    """Resolved rows reaped after retention; unresolved never reaped."""


@pytest.mark.skip(reason="PR-G: is_purging gate enumeration not yet implemented")
def test_is_purging_gate_enumeration() -> None:
    """Every endpoint in `NotPurgingDep` registry returns 423 when
    `is_purging=true` (I3)."""


# ─── PR-G: SAR fast-track ───────────────────────────────────────────────────


@pytest.mark.skip(reason="PR-G: SAR intake not yet implemented")
def test_sar_preempts_grace() -> None:
    """Verified SAR fast-tracks all user's `is_deleted` sessions (I12)."""


@pytest.mark.skip(reason="PR-G: SAR audit completeness")
def test_sar_audit_completeness() -> None:
    """Every `request_type='SAR'` audit row has all four memo §5 fields (I13)."""


@pytest.mark.skip(reason="PR-G: user-delete audit ordering")
def test_user_delete_audits_first() -> None:
    """`DELETE FROM users` only after audit + dead-letter clean (I14)."""


@pytest.mark.skip(reason="PR-G: Art. 17(3) deferred-disclosure not yet implemented")
def test_art17_3_disclosure() -> None:
    """Art. 17(3) deferred sessions get disclosure event within 30d (I15)."""


@pytest.mark.skip(reason="PR-F: restore endpoint SAR-block not yet implemented")
def test_restore_rejected_during_sar() -> None:
    """Restore endpoint returns 423 when active SAR exists (I16)."""


@pytest.mark.skip(reason="PR-E: grace-sweep primary-only assertion")
def test_grace_sweep_primary_only() -> None:
    """Cleanup loop binds writer engine; startup assertion fires on
    replica binding (I17)."""


@pytest.mark.skip(reason="PR-G: legal-hold-supersedes-SAR")
def test_legal_hold_supersedes_sar() -> None:
    """SAR on legal_hold session → `RetentionException.LEGAL_HOLD` audit;
    no purge (I18)."""


# ─── PR-E: phase-(c) TOCTOU + I8 + I10 + I19 ────────────────────────────────


@pytest.mark.skip(reason="PR-E: phase-(c) re-check not yet implemented")
def test_purge_phase_c_recheck_is_deleted() -> None:
    """Phase (c) re-checks `is_deleted=true` to defend TOCTOU vs restore (I7)."""


@pytest.mark.skip(reason="PR-F: per-session purge_now blocked during user-purge")
def test_purge_now_rejects_during_user_purge() -> None:
    """Per-session `purge_now` returns 423 when user has `is_purging=true` (I8)."""


@pytest.mark.skip(reason="PR-E: dead-letter user_id required")
def test_dead_letter_user_id_required() -> None:
    """`LeakedResource.user_id` is non-Optional; insert without user_id fails (I10)."""


@pytest.mark.skip(reason="PR-E: ALREADY_PURGED idempotency not yet implemented")
def test_purge_already_purged_idempotent() -> None:
    """`purge_one_session` returns `ALREADY_PURGED` on terminal-state retry;
    never two `session.purge_committed` rows for one session_id (I19)."""
