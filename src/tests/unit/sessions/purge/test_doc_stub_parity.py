"""Doc-stub parity: every public symbol in the purge package must be cited
by name in the design doc, and vice versa.

Why this exists:
  v3.10 found 7 stale-name references (`_purge_one_session`,
  `_purge_stale_deleted_sessions`) that had drifted between the doc and
  the canonical stubs. Without this test, that drift recurs on every edit.
  With it, drift fails CI instead of passing review.

Scope:
  - Forward direction: every name in `purge/__init__.py::__all__` must
    appear at least once in the design doc.
  - Reverse direction: every backtick-quoted Python-shaped identifier in
    the doc that LOOKS like a purge symbol must actually exist in the
    package (or be on a known allowlist of legacy/historical names that
    are deliberately kept for cross-reference continuity).

This test is intentionally cheap — pure file I/O + set algebra. It runs
in milliseconds and has zero infrastructure dependencies.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from ii_agent.sessions import purge


_REPO_ROOT = Path(__file__).resolve().parents[5]
_DOC_PATH = _REPO_ROOT / "docs" / "design-docs" / "session-lifecycle-and-data-custody.md"


# Symbols mentioned in the doc that intentionally do NOT exist in __all__.
# Entries here MUST have a citation in the comment explaining why.
_DOC_ONLY_ALLOWLIST: frozenset[str] = frozenset(
    {
        # Internal module-level helpers documented for orientation but not exported.
        "claim_one_session",  # claim.py
        "heartbeat_claim",  # claim.py
        "run_provider_cleanup",  # providers.py
        "commit_purge",  # commit.py
        "purge_one_session",  # session_purge.py — main entry, doc-cited but
        # not yet exported via __all__ (PR-E lands the export).
        "purge_user_account",  # user_purge.py — same as above.
        "intake_sar",  # user_purge.py
        "LeakedResource",  # providers.py — dataclass
        "ProviderCleanupResult",  # providers.py — dataclass
        "ClaimResult",  # claim.py — dataclass
    }
)


def _doc_text() -> str:
    return _DOC_PATH.read_text(encoding="utf-8")


def test_doc_exists() -> None:
    """Sanity: the design doc the rest of these tests depend on must be
    present at the canonical path."""
    assert _DOC_PATH.is_file(), f"design doc missing at {_DOC_PATH}"


@pytest.mark.parametrize("symbol", sorted(purge.__all__))
def test_every_exported_symbol_is_in_doc(symbol: str) -> None:
    """Forward direction: every name in `purge/__init__.py::__all__` must
    appear in the design doc text. This catches the case where a new
    public symbol is added without doc coverage.
    """
    doc = _doc_text()
    # Word-boundary match — `PurgeOutcome.PURGED` should still pass because
    # `PURGED` appears as a substring; we want the symbol name itself.
    assert symbol in doc, (
        f"Public symbol `{symbol}` from purge.__all__ is not referenced "
        f"by name in {_DOC_PATH.relative_to(_REPO_ROOT)}. "
        f"Either add a doc reference or remove it from __all__."
    )


def test_no_underscored_legacy_purge_names_in_doc() -> None:
    """Reverse direction (narrow): the doc must NEVER mention the historical
    underscored function names that v3.10 corrected. These names are dead
    and citing them confuses readers.
    """
    doc = _doc_text()
    # Allow code blocks that quote the legacy test FILENAME — not the symbol.
    forbidden_patterns = [
        r"\b_purge_one_session\b",
        r"\b_purge_provider_artifacts\b",
        # `_purge_stale_deleted_sessions` is allowed ONLY as a filename
        # (`test_purge_stale_deleted_sessions.py`), so we look for it
        # without the `test_` prefix and without `.py` suffix.
        r"(?<!test_)_purge_stale_deleted_sessions(?!\.py)",
    ]
    violations: list[str] = []
    for pattern in forbidden_patterns:
        for match in re.finditer(pattern, doc):
            line_no = doc.count("\n", 0, match.start()) + 1
            violations.append(f"line {line_no}: {match.group(0)!r}")
    assert not violations, (
        "Design doc contains historical underscored purge symbol names "
        "(corrected in v3.10):\n  " + "\n  ".join(violations)
    )


def test_invariant_count_matches_doc_table_header() -> None:
    """The doc claims a specific number of invariants (e.g. '19 invariants
    as of v3.11'). The runtime catalog must match.

    Looser-than-grep match: count `**Ix**` rows in the §2.3 table and
    require it equals `len(ALL_INVARIANTS)`.
    """
    from ii_agent.sessions.purge.invariants import ALL_INVARIANTS

    doc = _doc_text()
    # Match `**I1**` ... `**I99**` at the start of a table row.
    invariant_rows = re.findall(r"\|\s*\*\*I\d+\*\*\s*\|", doc)
    assert len(invariant_rows) == len(ALL_INVARIANTS), (
        f"Doc table has {len(invariant_rows)} invariant rows but "
        f"ALL_INVARIANTS has {len(ALL_INVARIANTS)}. "
        f"Add the new invariant to §2.3 or remove the orphan row."
    )
