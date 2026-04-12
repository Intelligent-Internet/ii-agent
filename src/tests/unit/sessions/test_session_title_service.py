"""Tests for ii_agent.sessions.title_service.SessionTitleService."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ii_agent.sessions.title_service import SessionTitleService, TITLE_PENDING_KEY


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _make_config(
    openai_api_key: str | None = None,
    enabled: bool = False,
    timeout: float = 5.0,
    semantic_min_query_length: int = 10,
) -> MagicMock:
    config = MagicMock()
    config.openai_api_key = openai_api_key
    config.enabled = enabled
    config.timeout = timeout
    config.semantic_min_query_length = semantic_min_query_length
    return config


def _make_service(openai_key=None, enabled=False) -> SessionTitleService:
    return SessionTitleService(config=_make_config(openai_api_key=openai_key, enabled=enabled))


# ---------------------------------------------------------------------------
# is_title_pending (static)
# ---------------------------------------------------------------------------


class TestIsTitlePending:
    def test_none_metadata_returns_false(self):
        assert SessionTitleService.is_title_pending(None) is False

    def test_empty_dict_returns_false(self):
        assert SessionTitleService.is_title_pending({}) is False

    def test_pending_true_returns_true(self):
        assert SessionTitleService.is_title_pending({TITLE_PENDING_KEY: True}) is True

    def test_pending_false_returns_false(self):
        assert SessionTitleService.is_title_pending({TITLE_PENDING_KEY: False}) is False

    def test_other_key_returns_false(self):
        assert SessionTitleService.is_title_pending({"other_key": True}) is False


# ---------------------------------------------------------------------------
# set_title_pending (static)
# ---------------------------------------------------------------------------


class TestSetTitlePending:
    def test_sets_pending_true(self):
        result = SessionTitleService.set_title_pending({}, True)
        assert result is not None
        assert result.get(TITLE_PENDING_KEY) is True

    def test_clears_pending(self):
        metadata = {TITLE_PENDING_KEY: True, "other": "value"}
        result = SessionTitleService.set_title_pending(metadata, False)
        assert result is not None
        assert TITLE_PENDING_KEY not in result
        assert result["other"] == "value"

    def test_none_metadata_with_pending_true(self):
        result = SessionTitleService.set_title_pending(None, True)
        assert result is not None
        assert result[TITLE_PENDING_KEY] is True

    def test_none_metadata_with_pending_false_returns_none(self):
        # When metadata is None and pending=False, the result dict is empty → returns None
        result = SessionTitleService.set_title_pending(None, False)
        assert result is None

    def test_existing_metadata_preserved(self):
        metadata = {"plan": {"summary": "test"}}
        result = SessionTitleService.set_title_pending(metadata, True)
        assert result["plan"] == {"summary": "test"}
        assert result[TITLE_PENDING_KEY] is True


# ---------------------------------------------------------------------------
# build_initial_title
# ---------------------------------------------------------------------------


class TestBuildInitialTitle:
    def test_empty_query_returns_untitled(self):
        svc = _make_service()
        title, pending = svc.build_initial_title("")
        assert title == "Untitled"
        assert pending is False

    def test_whitespace_only_returns_untitled(self):
        svc = _make_service()
        title, pending = svc.build_initial_title("   ")
        assert title == "Untitled"
        assert pending is False

    def test_short_query_without_llm_returns_truncated(self):
        svc = _make_service()
        title, pending = svc.build_initial_title("Hi there")
        assert title == "Hi there"
        assert pending is False

    def test_truncates_long_query(self):
        svc = _make_service()
        long_query = "x" * 200
        title, pending = svc.build_initial_title(long_query, max_length=80)
        # _truncate appends '...' when query is longer than max_length
        assert title == "x" * 80 + "..."
        assert pending is False

    def test_long_query_with_llm_returns_none_pending(self):
        """When LLM is enabled and query is long enough, returns None + pending=True."""
        svc = _make_service(openai_key="sk-test", enabled=True)
        query = "Build me a complete e-commerce website with React and FastAPI"
        title, pending = svc.build_initial_title(query)
        # With LLM enabled and long-enough query
        assert title is None
        assert pending is True


# ---------------------------------------------------------------------------
# generate_title
# ---------------------------------------------------------------------------


class TestGenerateTitle:
    @pytest.mark.asyncio
    async def test_empty_returns_untitled(self):
        svc = _make_service()
        result = await svc.generate_title("")
        assert result == "Untitled"

    @pytest.mark.asyncio
    async def test_whitespace_returns_untitled(self):
        svc = _make_service()
        result = await svc.generate_title("   ")
        assert result == "Untitled"

    @pytest.mark.asyncio
    async def test_truncation_fallback_when_no_llm(self):
        svc = _make_service()
        # _truncate appends '...' when the string is longer than max_length
        result = await svc.generate_title("Simple query", max_length=5)
        assert result == "Simpl..."

    @pytest.mark.asyncio
    async def test_llm_title_returned_on_success(self):
        svc = _make_service(openai_key="sk-test", enabled=True)
        # Patch the LLM call
        svc._call_llm = AsyncMock(return_value="  Generated Title  ")

        query = "A long query that exceeds semantic_min_query_length threshold in tests"
        result = await svc.generate_title(query)
        assert result == "Generated Title"

    @pytest.mark.asyncio
    async def test_falls_back_on_empty_llm_response(self):
        svc = _make_service(openai_key="sk-test", enabled=True)
        svc._call_llm = AsyncMock(return_value="")

        query = "A long query that exceeds the semantic_min_query_length threshold"
        result = await svc.generate_title(query, max_length=20)
        # _truncate(query, 20) = query[:20] + "..."
        assert result == query[:20] + "..."

    @pytest.mark.asyncio
    async def test_falls_back_on_llm_exception(self):
        svc = _make_service(openai_key="sk-test", enabled=True)
        svc._call_llm = AsyncMock(side_effect=Exception("LLM error"))

        query = "A long query that exceeds the semantic_min_query_length threshold"
        result = await svc.generate_title(query, max_length=20)
        assert result == query[:20] + "..."

    @pytest.mark.asyncio
    async def test_truncates_llm_title_to_max_length(self):
        svc = _make_service(openai_key="sk-test", enabled=True)
        svc._call_llm = AsyncMock(return_value="A" * 200)

        query = "A long query that exceeds the semantic_min_query_length threshold"
        result = await svc.generate_title(query, max_length=80)
        assert len(result) == 80


# ---------------------------------------------------------------------------
# _should_generate_semantic_title
# ---------------------------------------------------------------------------


class TestShouldGenerateSemanticTitle:
    def test_no_client_returns_false(self):
        svc = _make_service()
        assert svc._should_generate_semantic_title("any query") is False

    def test_short_query_returns_false_even_with_client(self):
        svc = _make_service(openai_key="sk-test", enabled=True)
        # semantic_min_query_length defaults to 10 in our test config
        assert svc._should_generate_semantic_title("hi") is False

    def test_long_query_with_client_returns_true(self):
        svc = _make_service(openai_key="sk-test", enabled=True)
        assert svc._should_generate_semantic_title("this is a longer query") is True
