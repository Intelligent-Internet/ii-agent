"""Unit tests for agents/sessions/summary.py — pure logic, no LLM calls."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from ii_agent.agents.models.metrics import Metrics
from ii_agent.agents.sessions.summary import (
    DEFAULT_TOKEN_THRESHOLD,
    MODEL_TOKEN_THRESHOLDS,
    SessionSummary,
    SessionSummaryManager,
    SessionSummaryResponse,
)


# ---------------------------------------------------------------------------
# SessionSummary helpers
# ---------------------------------------------------------------------------

class TestSessionSummaryToDict:
    def test_only_content_when_no_optionals(self):
        s = SessionSummary(content="hello world")
        d = s.to_dict()
        assert d == {"content": "hello world"}

    def test_topics_included_when_set(self):
        s = SessionSummary(content="x", topics=["a", "b"])
        d = s.to_dict()
        assert d["topics"] == ["a", "b"]

    def test_updated_at_as_isoformat(self):
        dt = datetime(2024, 3, 15, 12, 0, 0, tzinfo=timezone.utc)
        s = SessionSummary(content="x", updated_at=dt)
        d = s.to_dict()
        assert d["updated_at"] == dt.isoformat()

    def test_metrics_included_when_set(self):
        m = Metrics(input_tokens=10, output_tokens=5)
        s = SessionSummary(content="x", metrics=m)
        d = s.to_dict()
        assert "metrics" in d

    def test_none_values_excluded(self):
        s = SessionSummary(content="x", topics=None, updated_at=None, metrics=None)
        d = s.to_dict()
        assert "topics" not in d
        assert "updated_at" not in d
        assert "metrics" not in d


class TestSessionSummaryFromDict:
    def test_roundtrip_content_only(self):
        s = SessionSummary(content="hello")
        d = s.to_dict()
        restored = SessionSummary.from_dict(d)
        assert restored.content == "hello"

    def test_updated_at_string_parsed(self):
        dt_str = "2024-06-01T10:00:00+00:00"
        data = {"content": "x", "updated_at": dt_str}
        s = SessionSummary.from_dict(data)
        assert isinstance(s.updated_at, datetime)

    def test_metrics_reconstructed(self):
        m = Metrics(input_tokens=100, output_tokens=50)
        data = {"content": "x", "metrics": m.to_dict()}
        s = SessionSummary.from_dict(data)
        assert s.metrics is not None
        assert s.metrics.input_tokens == 100

    def test_no_metrics_gives_none(self):
        data = {"content": "x"}
        s = SessionSummary.from_dict(data)
        assert s.metrics is None


# ---------------------------------------------------------------------------
# SessionSummaryResponse
# ---------------------------------------------------------------------------

class TestSessionSummaryResponse:
    def test_to_dict_basic(self):
        r = SessionSummaryResponse(summary="short summary")
        d = r.to_dict()
        assert d["summary"] == "short summary"

    def test_to_dict_excludes_none_topics(self):
        r = SessionSummaryResponse(summary="s", topics=None)
        d = r.to_dict()
        assert "topics" not in d

    def test_to_dict_includes_topics(self):
        r = SessionSummaryResponse(summary="s", topics=["A", "B"])
        d = r.to_dict()
        assert d["topics"] == ["A", "B"]

    def test_to_json_is_string(self):
        r = SessionSummaryResponse(summary="s")
        j = r.to_json()
        assert isinstance(j, str)
        assert "summary" in j


# ---------------------------------------------------------------------------
# SessionSummaryManager._get_token_threshold
# ---------------------------------------------------------------------------

class TestGetTokenThreshold:
    def _manager(self, token_threshold=None) -> SessionSummaryManager:
        m = SessionSummaryManager(token_threshold=token_threshold)
        return m

    def test_returns_explicit_threshold_if_set(self):
        mgr = self._manager(token_threshold=50_000)
        assert mgr._get_token_threshold("any-model") == 50_000

    def test_returns_model_specific_threshold(self):
        mgr = self._manager()
        threshold = mgr._get_token_threshold("claude-sonnet-4-6")
        assert threshold == MODEL_TOKEN_THRESHOLDS["claude-sonnet-4-6"]

    def test_returns_default_for_unknown_model(self):
        mgr = self._manager()
        assert mgr._get_token_threshold("unknown-model-xyz") == DEFAULT_TOKEN_THRESHOLD

    def test_gpt4o_threshold(self):
        mgr = self._manager()
        assert mgr._get_token_threshold("gpt-4o") == MODEL_TOKEN_THRESHOLDS["gpt-4o"]


# ---------------------------------------------------------------------------
# SessionSummaryManager._count_session_tokens
# ---------------------------------------------------------------------------

class TestCountSessionTokens:
    def _make_message(self, role: str, input_tok: int = 0, output_tok: int = 0):
        m = MagicMock()
        m.role = role
        m.metrics = Metrics(input_tokens=input_tok, output_tokens=output_tok)
        return m

    def test_empty_runs_returns_zero(self):
        mgr = SessionSummaryManager()
        session = MagicMock()
        session.runs = []
        assert mgr._count_session_tokens(session) == 0

    def test_run_with_no_messages_returns_zero(self):
        mgr = SessionSummaryManager()
        run = MagicMock()
        run.messages = []
        session = MagicMock()
        session.runs = [run]
        assert mgr._count_session_tokens(session) == 0

    def test_counts_from_last_assistant_message(self):
        mgr = SessionSummaryManager()
        msg_user = self._make_message("user", input_tok=10)
        msg_asst = self._make_message("assistant", input_tok=300, output_tok=50)
        run = MagicMock()
        run.messages = [msg_user, msg_asst]
        session = MagicMock()
        session.runs = [run]
        tokens = mgr._count_session_tokens(session)
        # total_input_tokens = input_tokens + cache_write + cache_read = 300+0+0 = 300
        # output_tokens = 50
        assert tokens == 350

    def test_skips_user_messages(self):
        mgr = SessionSummaryManager()
        # Only user messages — should return 0
        msg_user = self._make_message("user", input_tok=999)
        run = MagicMock()
        run.messages = [msg_user]
        session = MagicMock()
        session.runs = [run]
        assert mgr._count_session_tokens(session) == 0
