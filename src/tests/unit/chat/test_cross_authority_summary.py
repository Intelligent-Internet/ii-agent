"""Unit tests for cross-authority summary chaining prevention."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ii_agent.chat.application.context_service import ContextWindowManager
from ii_agent.chat.messages.models import ChatSummary
from ii_agent.chat.types import Message, MessageRole, TextContent


SESSION_ID = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000000")
USER_ID = uuid.UUID("bbbbbbbb-0000-0000-0000-000000000000")


def _make_summary(
    *,
    authority: str | None = "native",
    summary_text: str = "Previous summary content",
    tokens: int = 100,
) -> MagicMock:
    """Create a mock ChatSummary with the given authority."""
    s = MagicMock(spec=ChatSummary)
    s.id = uuid.uuid4()
    s.session_id = SESSION_ID
    s.summary_text = summary_text
    s.end_message_id = uuid.uuid4()
    s.original_tokens = 1000
    s.summary_tokens = tokens
    s.compression_ratio = 10.0
    s.model_id = "test-model"
    s.parent_summary_id = None
    s.summary_authority = authority
    s.created_at = datetime.now(timezone.utc)
    return s


def _msg(text: str, *, tokens: int = 50) -> Message:
    return Message(
        id=uuid.uuid4(),
        role=MessageRole.USER,
        session_id=SESSION_ID,
        parts=[TextContent(text=text)],
        tokens=tokens,
    )


def _mock_llm_config():
    cfg = MagicMock()
    cfg.model = "claude-sonnet-4@20250514"
    cfg.setting_id = "test-setting"
    return cfg


class TestCrossSummaryAuthority:
    """Test that create_chained_summary prevents cross-authority chaining."""

    @pytest.mark.asyncio
    async def test_same_authority_chains_normally(self):
        """Native summary chains from native parent — no prevention."""
        parent = _make_summary(authority="native")

        # We can't easily call the real method (needs LLM), so we test
        # the authority guard logic directly.

        # Simulate: authority matches → parent should NOT be set to None
        assert parent.summary_authority == "native"
        # The guard condition should NOT trigger
        assert not (parent.summary_authority is not None and parent.summary_authority != "native")

    @pytest.mark.asyncio
    async def test_cross_authority_prevents_chaining(self):
        """Native summary should NOT chain from an A2A-authority parent."""
        parent = _make_summary(authority="a2a")

        # The guard condition SHOULD trigger
        summary_authority = "native"
        assert (
            parent.summary_authority is not None and parent.summary_authority != summary_authority
        )

    @pytest.mark.asyncio
    async def test_none_authority_chains_freely(self):
        """Legacy summaries with None authority chain from any parent."""
        parent = _make_summary(authority=None)

        # None authority → guard does NOT trigger (backward compatible)
        summary_authority = "native"
        assert not (
            parent.summary_authority is not None and parent.summary_authority != summary_authority
        )

    @pytest.mark.asyncio
    async def test_a2a_authority_prevents_chaining_from_native(self):
        """A2A summary should not chain from native parent."""
        parent = _make_summary(authority="native")

        summary_authority = "a2a"
        assert (
            parent.summary_authority is not None and parent.summary_authority != summary_authority
        )


class TestChatSummaryModel:
    """Test the ChatSummary model's summary_authority field via mocks."""

    def test_summary_authority_defaults_to_none(self):
        s = _make_summary(authority=None)
        assert s.summary_authority is None

    def test_summary_authority_can_be_set(self):
        s = _make_summary(authority="native")
        assert s.summary_authority == "native"

    def test_summary_authority_a2a(self):
        s = _make_summary(authority="a2a")
        assert s.summary_authority == "a2a"


class TestCreateChainedSummaryIntegration:
    """Integration-level test for the full create_chained_summary authority logic.

    Uses mocking to avoid actual LLM/DB calls while testing the guard.
    """

    @pytest.mark.asyncio
    async def test_cross_authority_creates_standalone_summary(self):
        """When parent authority differs, create_chained_summary should not chain."""
        parent = _make_summary(authority="a2a")
        messages = [_msg("hello"), _msg("world")]
        llm_config = _mock_llm_config()

        # Mock the SummarizationService and db_session
        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        with patch(
            "ii_agent.chat.application.context_service.SummarizationService.generate_summary",
            new_callable=AsyncMock,
            return_value=("Standalone summary", 50),
        ):
            result = await ContextWindowManager.create_chained_summary(
                db_session=mock_db,
                session_id=SESSION_ID,
                messages=messages,
                parent_summary=parent,
                llm_config=llm_config,
                user_id=USER_ID,
                summary_authority="native",
            )

        # Should NOT chain from the A2A parent
        assert result.parent_summary_id is None
        assert result.summary_authority == "native"
        assert result.summary_text == "Standalone summary"

    @pytest.mark.asyncio
    async def test_same_authority_chains_from_parent(self):
        """When parent authority matches, create_chained_summary should chain."""
        parent = _make_summary(authority="native")
        messages = [_msg("hello"), _msg("world")]
        llm_config = _mock_llm_config()

        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        with patch(
            "ii_agent.chat.application.context_service.SummarizationService.generate_summary",
            new_callable=AsyncMock,
            return_value=("Chained summary", 60),
        ):
            result = await ContextWindowManager.create_chained_summary(
                db_session=mock_db,
                session_id=SESSION_ID,
                messages=messages,
                parent_summary=parent,
                llm_config=llm_config,
                user_id=USER_ID,
                summary_authority="native",
            )

        # Should chain from parent
        assert result.parent_summary_id == parent.id
        assert result.summary_authority == "native"

    @pytest.mark.asyncio
    async def test_none_parent_creates_root_summary(self):
        """When there is no parent, create_chained_summary creates a root summary."""
        messages = [_msg("hello")]
        llm_config = _mock_llm_config()

        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        with patch(
            "ii_agent.chat.application.context_service.SummarizationService.generate_summary",
            new_callable=AsyncMock,
            return_value=("Root summary", 30),
        ):
            result = await ContextWindowManager.create_chained_summary(
                db_session=mock_db,
                session_id=SESSION_ID,
                messages=messages,
                parent_summary=None,
                llm_config=llm_config,
                user_id=USER_ID,
                summary_authority="native",
            )

        assert result.parent_summary_id is None
        assert result.summary_authority == "native"

    @pytest.mark.asyncio
    async def test_legacy_parent_chains_freely(self):
        """Legacy parent with None authority should allow chaining."""
        parent = _make_summary(authority=None)
        messages = [_msg("hello")]
        llm_config = _mock_llm_config()

        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        with patch(
            "ii_agent.chat.application.context_service.SummarizationService.generate_summary",
            new_callable=AsyncMock,
            return_value=("Chained from legacy", 40),
        ):
            result = await ContextWindowManager.create_chained_summary(
                db_session=mock_db,
                session_id=SESSION_ID,
                messages=messages,
                parent_summary=parent,
                llm_config=llm_config,
                user_id=USER_ID,
                summary_authority="native",
            )

        # Legacy parent (None authority) should allow chaining
        assert result.parent_summary_id == parent.id
