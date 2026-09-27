"""Unit tests for LLMTurnLoopService._publish_llm_usage and _publish_tool_usage."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from ii_agent.billing.schemas import TokenUsage
from ii_agent.chat.application.turn_loop_service import LLMTurnLoopService
from ii_agent.chat.types import FinishReason, ToolResult
from ii_agent.realtime.events.app_events import ModelUsageEvent, ToolUsageEvent
from ii_agent.settings.llm.schemas import ModelConfig
from ii_agent.settings.llm.types import Provider


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_model_config() -> ModelConfig:
    return ModelConfig(
        id=uuid.uuid4(),
        model_id="claude-3-5-sonnet-20241022",
        provider=Provider.ANTHROPIC,
        pricing=None,
    )


def _make_run_response(
    input_tokens: int = 10,
    output_tokens: int = 20,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
    reasoning_tokens: int = 0,
) -> SimpleNamespace:
    usage = TokenUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_read_tokens=cache_read_tokens,
        cache_write_tokens=cache_write_tokens,
    )
    return SimpleNamespace(
        usage=usage,
        finish_reason=FinishReason.END_TURN,
        content=[],
        files=[],
        provider_metadata=None,
    )


def _make_svc(pubsub=None) -> LLMTurnLoopService:
    msg_svc = MagicMock()
    return LLMTurnLoopService(
        message_service=msg_svc,
        pubsub=pubsub,
    )


# ---------------------------------------------------------------------------
# _publish_llm_usage
# ---------------------------------------------------------------------------


class TestPublishLlmUsage:
    @pytest.mark.asyncio
    async def test_does_nothing_when_pubsub_is_none(self):
        svc = _make_svc(pubsub=None)
        run_response = _make_run_response()
        model_config = _make_model_config()
        # Should not raise
        await svc._publish_llm_usage(
            run_response=run_response,
            session_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            run_id=uuid.uuid4(),
            model_config=model_config,
        )

    @pytest.mark.asyncio
    async def test_does_nothing_when_usage_is_none(self):
        pubsub = MagicMock()
        pubsub.publish = AsyncMock()
        svc = _make_svc(pubsub=pubsub)

        run_response = _make_run_response()
        run_response.usage = None

        await svc._publish_llm_usage(
            run_response=run_response,
            session_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            run_id=uuid.uuid4(),
            model_config=_make_model_config(),
        )
        pubsub.publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_publishes_model_usage_event(self):
        pubsub = MagicMock()
        published_events = []
        pubsub.publish = AsyncMock(side_effect=published_events.append)

        svc = _make_svc(pubsub=pubsub)
        run_response = _make_run_response(
            input_tokens=100,
            output_tokens=50,
            cache_read_tokens=10,
            cache_write_tokens=5,
        )
        model_config = _make_model_config()
        session_id = uuid.uuid4()
        user_id = uuid.uuid4()
        run_id = uuid.uuid4()

        await svc._publish_llm_usage(
            run_response=run_response,
            session_id=session_id,
            user_id=user_id,
            run_id=run_id,
            model_config=model_config,
        )

        assert len(published_events) == 1
        event = published_events[0]
        assert isinstance(event, ModelUsageEvent)
        assert event.session_id == session_id
        assert event.user_id == user_id
        assert event.run_id == run_id
        assert event.model_id == "claude-3-5-sonnet-20241022"
        assert event.input_tokens == 100
        assert event.output_tokens == 50
        assert event.cache_read_tokens == 10
        assert event.cache_write_tokens == 5

    @pytest.mark.asyncio
    async def test_marks_user_key_false_for_system_model(self):
        pubsub = MagicMock()
        published_events = []
        pubsub.publish = AsyncMock(side_effect=published_events.append)

        svc = _make_svc(pubsub=pubsub)
        model_config = _make_model_config()  # default config_type=SYSTEM
        run_response = _make_run_response()

        await svc._publish_llm_usage(
            run_response=run_response,
            session_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            run_id=uuid.uuid4(),
            model_config=model_config,
        )

        assert not published_events[0].is_user_key

    @pytest.mark.asyncio
    async def test_swallows_exception_from_pubsub(self):
        pubsub = MagicMock()
        pubsub.publish = AsyncMock(side_effect=RuntimeError("pubsub broken"))

        svc = _make_svc(pubsub=pubsub)
        run_response = _make_run_response()

        # Should not propagate the exception
        await svc._publish_llm_usage(
            run_response=run_response,
            session_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            run_id=uuid.uuid4(),
            model_config=_make_model_config(),
        )


# ---------------------------------------------------------------------------
# _publish_tool_usage
# ---------------------------------------------------------------------------


def _make_tool_result(cost_usd: float | None = 0.05) -> ToolResult:
    """Build a ToolResult with the given cost."""
    from ii_agent.chat.types import TextResultContent

    return ToolResult(
        tool_call_id="call_abc",
        name="search_web",
        output=TextResultContent(value="result"),
        cost_usd=cost_usd,
    )


class TestPublishToolUsage:
    @pytest.mark.asyncio
    async def test_does_nothing_when_pubsub_is_none(self):
        svc = _make_svc(pubsub=None)
        tool_result = _make_tool_result(cost_usd=0.10)
        # Should not raise
        await svc._publish_tool_usage(
            tool_result=tool_result,
            session_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            run_id=uuid.uuid4(),
        )

    @pytest.mark.asyncio
    async def test_does_nothing_when_cost_is_none(self):
        pubsub = MagicMock()
        pubsub.publish = AsyncMock()
        svc = _make_svc(pubsub=pubsub)
        tool_result = _make_tool_result(cost_usd=None)

        await svc._publish_tool_usage(
            tool_result=tool_result,
            session_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            run_id=uuid.uuid4(),
        )
        pubsub.publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_does_nothing_when_cost_is_zero(self):
        pubsub = MagicMock()
        pubsub.publish = AsyncMock()
        svc = _make_svc(pubsub=pubsub)
        tool_result = _make_tool_result(cost_usd=0.0)

        await svc._publish_tool_usage(
            tool_result=tool_result,
            session_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            run_id=uuid.uuid4(),
        )
        pubsub.publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_does_nothing_when_cost_is_negative(self):
        pubsub = MagicMock()
        pubsub.publish = AsyncMock()
        svc = _make_svc(pubsub=pubsub)
        tool_result = _make_tool_result(cost_usd=-0.01)

        await svc._publish_tool_usage(
            tool_result=tool_result,
            session_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            run_id=uuid.uuid4(),
        )
        pubsub.publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_publishes_tool_usage_event(self):
        pubsub = MagicMock()
        published_events = []
        pubsub.publish = AsyncMock(side_effect=published_events.append)

        svc = _make_svc(pubsub=pubsub)
        session_id = uuid.uuid4()
        user_id = uuid.uuid4()
        run_id = uuid.uuid4()
        tool_result = _make_tool_result(cost_usd=0.07)

        await svc._publish_tool_usage(
            tool_result=tool_result,
            session_id=session_id,
            user_id=user_id,
            run_id=run_id,
        )

        assert len(published_events) == 1
        event = published_events[0]
        assert isinstance(event, ToolUsageEvent)
        assert event.session_id == session_id
        assert event.user_id == user_id
        assert event.run_id == run_id
        assert event.tool_name == "search_web"
        assert event.cost_usd == pytest.approx(0.07)

    @pytest.mark.asyncio
    async def test_swallows_exception_from_pubsub(self):
        pubsub = MagicMock()
        pubsub.publish = AsyncMock(side_effect=Exception("network error"))

        svc = _make_svc(pubsub=pubsub)
        tool_result = _make_tool_result(cost_usd=0.05)

        # Should not propagate
        await svc._publish_tool_usage(
            tool_result=tool_result,
            session_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            run_id=uuid.uuid4(),
        )
