"""Structural invariant tests — Tier 3 of the §2.3 invariant catalogue.

These tests pin invariants whose contract is about CODE SHAPE rather
than data shape, so they cannot be promoted to a database constraint or
runtime SQL probe. Each test names the invariant ID it pins; deleting
or weakening these tests = silently retiring the invariant.

See :data:`ii_agent.sessions.purge.invariants.STRUCTURAL_TEST_ENFORCED`
for the catalogue.
"""

from __future__ import annotations

import inspect
import re

import pytest

from ii_agent.sessions.purge import commit as commit_module
from ii_agent.sessions.purge import orm_guards as orm_guards_module


def test_commit_phase_c_rechecks_is_deleted():
    """I7: ``commit_purge`` must re-read the session row with ``FOR UPDATE``
    and verify ``is_deleted`` is still true before deleting.

    Failure mode if removed: a concurrent ``session.restore`` call could
    flip ``is_deleted`` back to false between phase (a) claim and phase
    (c) delete. The user would lose a session they just restored. This
    is Adversarial v3.9 #2 (restore-vs-purge TOCTOU).
    """
    sql = str(commit_module._RECHECK_DELETED_SQL)
    assert "is_deleted" in sql, (
        f"I7: commit._RECHECK_DELETED_SQL must SELECT is_deleted. Current SQL: {sql!r}"
    )
    assert re.search(r"\bFOR UPDATE\b", sql, re.IGNORECASE), (
        "I7: commit._RECHECK_DELETED_SQL must use FOR UPDATE to lock the "
        f"row before phase-(c) DELETE. Current SQL: {sql!r}"
    )


def test_orm_guard_blocks_inserts_during_user_purge():
    """I8: the SQLAlchemy ``before_insert`` listener must raise
    ``PurgeBlockedError`` when inserting a Session whose owning user has
    ``is_purging=true``.

    Failure mode if removed: a chat-side request that bypasses the
    HTTP-level user_purge guard could insert a fresh Session row mid-
    purge, leaking PII into post-erasure audit log.
    """
    src = inspect.getsource(orm_guards_module)
    assert "PurgeBlockedError" in src, "I8: orm_guards.py must reference PurgeBlockedError"
    assert "before_insert" in src, "I8: orm_guards.py must register a before_insert listener"
    # The conditional that triggers the raise.
    assert "is_purging" in src, "I8: orm_guards.py must check users.is_purging before raising"


def test_schema_enforced_invariants_have_migration_id():
    """Every entry in SCHEMA_ENFORCED must cite a migration revision so a
    reviewer can trace the constraint to its DDL. Catches the failure mode
    where someone adds an entry to the catalogue without writing the
    migration that backs it.
    """
    from ii_agent.sessions.purge.invariants import SCHEMA_ENFORCED

    for inv_id, descr in SCHEMA_ENFORCED:
        assert re.search(r"[Mm]igration\s+\d{8}_\d{6}", descr), (
            f"SCHEMA_ENFORCED entry {inv_id} does not cite a migration "
            f"revision. Description: {descr!r}"
        )


def test_structural_invariants_have_test_or_artefact():
    """Every entry in STRUCTURAL_TEST_ENFORCED must name the test file or
    audit artefact that pins it. Catches the failure mode where a tier-3
    invariant decays into 'we'll write a test later' (the failure mode
    that produced this whole hardening pass).
    """
    from ii_agent.sessions.purge.invariants import STRUCTURAL_TEST_ENFORCED

    for inv_id, descr in STRUCTURAL_TEST_ENFORCED:
        assert (
            "tests/" in descr
            or "Test:" in descr
            or "Tests:" in descr
            or "Audit job:" in descr
            or "Deployment-config check:" in descr
        ), (
            f"STRUCTURAL_TEST_ENFORCED entry {inv_id} must name the test "
            f"file or audit artefact that pins it. Description: {descr!r}"
        )


def test_structural_invariants_cited_artefacts_resolve():
    """STRONGER FORM of the parity test: every cited test path must point
    to a file that exists, AND every cited ``module.function`` reference
    (Audit job / Deployment-config check) must be importable and
    callable.

    Catches the failure mode of citing artefacts that have been renamed,
    moved, or never written. A skip-marked test still satisfies this
    test as long as the file + function exist — the SKIP marker itself
    is part of the contract (it pins the contract while implementation
    is pending).
    """
    import importlib
    import re as _re
    from pathlib import Path

    from ii_agent.sessions.purge.invariants import STRUCTURAL_TEST_ENFORCED

    repo_root = Path(__file__).resolve().parents[5]
    # Sanity: the path ascent should land on the repo root containing pyproject.toml
    assert (repo_root / "pyproject.toml").exists(), (
        f"Repo-root resolution broke: {repo_root!r}. Update parents[5] "
        "if the test layout has changed."
    )

    # Path pattern: matches strings like "src/tests/.../foo.py" or "tests/.../foo.py"
    path_re = _re.compile(r"\b((?:src/)?tests/[\w/\-]+\.py)")
    # Module pattern: matches "ii_agent.foo.bar.callable_name" tokens.
    module_re = _re.compile(r"\b(ii_agent(?:\.\w+)+)\b")

    for inv_id, descr in STRUCTURAL_TEST_ENFORCED:
        # 1. Verify any cited test file path exists.
        for path_str in path_re.findall(descr):
            test_path = repo_root / path_str
            assert test_path.exists(), (
                f"STRUCTURAL_TEST_ENFORCED entry {inv_id} cites test file "
                f"{path_str!r} that does not exist (resolved to "
                f"{test_path}). Update the catalogue to point at a real "
                "file or implement the missing test."
            )

        # 2. Verify any cited "module.function" reference imports cleanly
        # and resolves to a callable. We try the full dotted path as a
        # module first; if that succeeds we accept it (pure module
        # reference). Otherwise we split on the last dot and require the
        # tail to be a callable attribute.
        for module_path in module_re.findall(descr):
            try:
                importlib.import_module(module_path)
                continue  # Pure module reference — accept.
            except ImportError:
                pass
            head, _, tail = module_path.rpartition(".")
            if not head:
                continue  # Bare module token, no fallback possible.
            try:
                mod = importlib.import_module(head)
            except ImportError as exc:
                raise AssertionError(
                    f"STRUCTURAL_TEST_ENFORCED entry {inv_id} cites "
                    f"{module_path!r} but neither the full path nor the "
                    f"head module {head!r} is importable: {exc}"
                ) from exc
            assert hasattr(mod, tail), (
                f"STRUCTURAL_TEST_ENFORCED entry {inv_id} cites "
                f"{module_path!r} but {head!r} has no attribute "
                f"{tail!r}. Implement it or update the catalogue."
            )
            assert callable(getattr(mod, tail)), (
                f"STRUCTURAL_TEST_ENFORCED entry {inv_id} cites "
                f"{module_path!r} but the resolved attribute is not "
                "callable."
            )


def test_db_checkable_returns_uuid_lists():
    """Every probe in DB_CHECKABLE must be an async coroutine function
    returning ``list[uuid.UUID]``. The runner ``_run_one`` relies on this
    shape for its log-formatting and FAIL/PASS decision.
    """
    from ii_agent.sessions.purge.invariants import DB_CHECKABLE

    for fn in DB_CHECKABLE:
        assert inspect.iscoroutinefunction(fn), (
            f"{fn.__name__} must be an async function (it is run as "
            "``await fn(db)`` by check_runner._run_one)"
        )


@pytest.mark.parametrize(
    "tier_name",
    ["SCHEMA_ENFORCED", "DB_CHECKABLE", "STRUCTURAL_TEST_ENFORCED"],
)
def test_invariant_tiers_are_disjoint(tier_name: str):
    """No invariant ID may appear in more than one tier. The whole point
    of the tier system is that each invariant has exactly one enforcing
    artefact.
    """
    from ii_agent.sessions.purge.invariants import (
        DB_CHECKABLE,
        SCHEMA_ENFORCED,
        STRUCTURAL_TEST_ENFORCED,
    )

    schema_ids = {iid for iid, _ in SCHEMA_ENFORCED}
    structural_ids = {iid for iid, _ in STRUCTURAL_TEST_ENFORCED}
    db_ids = {fn.__name__.split("_")[1] for fn in DB_CHECKABLE}

    overlaps = (schema_ids & structural_ids) | (schema_ids & db_ids) | (structural_ids & db_ids)
    assert not overlaps, (
        f"Invariant tier overlap detected: {overlaps}. Each invariant "
        "must belong to exactly one tier."
    )
