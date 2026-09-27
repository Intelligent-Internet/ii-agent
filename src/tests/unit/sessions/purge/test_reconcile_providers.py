"""Unit tests for I9 external-provider reconciliation.

These tests pin the behavioural contract of
:mod:`ii_agent.sessions.purge.reconcile_providers` without exercising
PostgreSQL-specific SQL (``gen_random_uuid()``, ``ON CONFLICT``-style
predicates, JSONB casts). The :class:`AsyncSession` collaborator is
replaced with a recording mock so we can assert the SQL text and
parameters that would be sent to the database.

Bugs caught during the v3.10 review pass that these tests pin:

  1. ``_record_orphan`` previously wrote into non-existent columns
     ``provider_resource_id`` / ``reason``; the canonical schema
     (migration ``20260427_000008``) has ``resource_id`` /
     ``error_message``.
  2. ``_record_orphan`` previously claimed idempotency via ``ON CONFLICT
     DO NOTHING`` although no UNIQUE constraint exists on
     ``purge_dead_letter`` for (provider, resource_kind, resource_id).
     The fix is an explicit ``WHERE NOT EXISTS`` guard scoped to
     unresolved rows.
  3. ``reconcile_openai_files`` previously read tracked IDs from
     ``chat_provider_files`` without a provider filter, polluting the
     OpenAI tracked set with Anthropic / Gemini IDs and producing
     false-positive orphans.

Each test below is named for the contract it pins; deleting one =
silently retiring that contract.
"""

from __future__ import annotations

import dataclasses
import re
from unittest.mock import AsyncMock, MagicMock

import pytest

from ii_agent.sessions.purge import reconcile_providers


# --------------------------------------------------------------------- helpers


@dataclasses.dataclass
class _FakeFile:
    """Minimal duck-type for objects returned by ``openai.files.list``."""

    id: str
    created_at: int  # unix seconds
    bytes: int = 0


def _make_recording_session() -> tuple[AsyncMock, list[tuple[str, dict]]]:
    """Return an AsyncSession-shaped mock and a list that captures every
    ``execute`` call as ``(sql_text, params_dict)``.

    The first call (the tracked-set SELECT) returns an empty result by
    default; subsequent calls (the dead-letter INSERT) return a no-op
    result. Tests can monkey-patch the first response via
    ``_set_tracked_ids``.
    """
    captured: list[tuple[str, dict]] = []

    tracked_result = MagicMock()
    tracked_result.all = MagicMock(return_value=[])
    insert_result = MagicMock()

    async def _execute(stmt, params=None):
        captured.append((str(stmt), dict(params or {})))
        # First call is the tracked-set SELECT; the rest are INSERTs.
        if len(captured) == 1:
            return tracked_result
        return insert_result

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=_execute)
    db._tracked_result = tracked_result  # expose for tests
    return db, captured


# ----------------------------------------------------------- contract: I9 SQL


def test_record_orphan_uses_canonical_column_names():
    """The dead-letter INSERT must reference the schema-correct columns
    ``resource_id`` / ``error_message`` (NOT the v3.9-era misnames
    ``provider_resource_id`` / ``reason``).

    Failure mode if regressed: ``UndefinedColumn`` at runtime when the
    operator first runs reconciliation, masking real provider orphans.
    """
    import inspect

    src = inspect.getsource(reconcile_providers._record_orphan)
    # Canonical names present.
    assert re.search(r"\bresource_id\b", src), (
        "Dead-letter INSERT must reference column 'resource_id' (see migration 20260427_000008)."
    )
    assert re.search(r"\berror_message\b", src), (
        "Dead-letter INSERT must reference column 'error_message' (see migration 20260427_000008)."
    )
    # Misnamed columns absent from the SQL body. We tolerate the
    # ``provider_resource_id`` kwarg in the Python signature (it's a
    # local naming choice), but the SQL must not reference such a
    # column. Inspect the triple-quoted SQL block specifically.
    sql_match = re.search(r'"""(.*?)"""', src, re.DOTALL)
    assert sql_match, "Could not extract SQL body from _record_orphan"
    sql_body = sql_match.group(1)
    assert "provider_resource_id" not in sql_body, (
        "Dead-letter INSERT SQL must NOT reference column "
        "'provider_resource_id' — that column does not exist on "
        "purge_dead_letter."
    )
    assert re.search(r"[(,]\s*reason\s*[,)]", sql_body) is None, (
        "Dead-letter INSERT SQL must NOT use a 'reason' column — the "
        "canonical name is 'error_message'."
    )


def test_record_orphan_idempotency_guard_uses_not_exists():
    """The INSERT must guard against duplicate unresolved rows via
    ``WHERE NOT EXISTS`` (NOT ``ON CONFLICT DO NOTHING``, which is a
    placebo here because no matching unique constraint exists).

    Failure mode if regressed: each reconcile run inserts a fresh row
    for every unresolved orphan, polluting the dead-letter table.
    """
    import inspect

    src = inspect.getsource(reconcile_providers._record_orphan)
    assert re.search(r"WHERE\s+NOT\s+EXISTS", src, re.IGNORECASE), (
        "Idempotency must be enforced by 'WHERE NOT EXISTS' against "
        "unresolved purge_dead_letter rows."
    )
    assert re.search(r"resolved_at\s+IS\s+NULL", src, re.IGNORECASE), (
        "Idempotency guard must scope to unresolved rows "
        "(resolved_at IS NULL); otherwise resolved orphans block "
        "re-entry of regressing artefacts."
    )
    assert "ON CONFLICT" not in src.upper(), (
        "ON CONFLICT DO NOTHING is a placebo — no unique constraint "
        "exists on (provider, resource_kind, resource_id). Use "
        "WHERE NOT EXISTS instead."
    )


# ---------------------------------------- contract: tracked-set provider scope


@pytest.mark.asyncio
async def test_reconcile_openai_files_filters_tracked_set_by_provider():
    """The tracked-set SELECT must scope ``chat_provider_files`` rows to
    ``provider = 'openai'`` so that Anthropic / Gemini file IDs don't
    pollute the OpenAI orphan-detection set.

    Failure mode if regressed: every Anthropic file ID would be treated
    as 'tracked' against the OpenAI list, falsely suppressing real
    OpenAI orphans (and inversely, every OpenAI listing would be
    falsely-orphaned against an Anthropic-only tracked snapshot once
    the providers diverge).
    """
    db, captured = _make_recording_session()

    await reconcile_providers.reconcile_openai_files(
        db,
        list_files=lambda: [],
        horizon_seconds=0,
    )

    assert captured, "execute was never called"
    tracked_sql, _params = captured[0]
    assert "chat_provider_files" in tracked_sql, (
        "First execute must be the tracked-set SELECT against "
        "chat_provider_files; got: " + tracked_sql
    )
    assert re.search(r"provider\s*=\s*'openai'", tracked_sql, re.IGNORECASE), (
        "Tracked-set SELECT must filter WHERE provider = 'openai' "
        "(chat_provider_files is a multi-provider table). SQL was: " + tracked_sql
    )


# ---------------------------------- contract: orphan detection / horizon logic


@pytest.mark.asyncio
async def test_reconcile_openai_files_skips_tracked_and_recent_files():
    """Files whose ID is in the tracked set OR whose ``created_at`` is
    inside the horizon window must be skipped (no dead-letter row).
    Only old + untracked files become orphans.
    """
    import time

    now = int(time.time())
    horizon = 30 * 24 * 3600  # 30 days

    db, captured = _make_recording_session()
    # Pretend two file IDs are already tracked.
    db._tracked_result.all = MagicMock(return_value=[("file-tracked-1",), ("file-tracked-2",)])

    files = [
        _FakeFile(id="file-tracked-1", created_at=now - horizon - 1),  # old, tracked → skip
        _FakeFile(id="file-recent-orphan", created_at=now - 100),  # recent, untracked → skip
        _FakeFile(id="file-real-orphan", created_at=now - horizon - 1),  # old, untracked → orphan
        _FakeFile(id="file-no-timestamp", created_at=None),  # no created_at → skip
    ]

    report = await reconcile_providers.reconcile_openai_files(
        db,
        list_files=lambda: files,
        horizon_seconds=horizon,
    )

    assert report.listed == 4
    assert report.tracked == 2
    assert report.orphaned == 1
    assert report.dead_letter_rows_inserted == 1

    # First call is the tracked-set SELECT; subsequent calls are INSERTs.
    insert_calls = captured[1:]
    assert len(insert_calls) == 1, (
        f"Expected exactly one INSERT for the single real orphan, got "
        f"{len(insert_calls)}: {[s for s, _ in insert_calls]}"
    )
    insert_sql, params = insert_calls[0]
    assert "purge_dead_letter" in insert_sql
    assert params["rid"] == "file-real-orphan", (
        f"INSERT params must reference the real-orphan id; got {params!r}"
    )
    assert params["provider"] == "openai"
    assert params["kind"] == "file"


# --------------------------------------- contract: I10 sentinel user_id fallback


@pytest.mark.asyncio
async def test_record_orphan_uses_sentinel_user_id_when_unresolved():
    """When the owning user can't be resolved, ``_record_orphan`` must
    fall back to the zero-UUID sentinel (NOT pass NULL — that would
    violate I10's NOT NULL column constraint).
    """
    import uuid

    db, captured = _make_recording_session()

    await reconcile_providers._record_orphan(
        db,
        provider="openai",
        resource_kind="file",
        provider_resource_id="file-x",
        user_id=None,
        session_id=None,
    )

    assert len(captured) == 1
    _sql, params = captured[0]
    assert params["user_id"] == uuid.UUID(int=0), (
        "Unresolved orphan must use zero-UUID sentinel for user_id "
        "(I10 forbids NULL); got " + repr(params["user_id"])
    )
