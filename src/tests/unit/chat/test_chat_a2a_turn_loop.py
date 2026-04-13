"""Tests for A2A chat turn-loop integration.

Covers:
- ChatA2AEventTranslator (event mapping, finalization, usage)
- A2AChatTurnLoop (streaming, tool bridging, circuit breaker, fallback, billing)
- ChatService._select_turn_loop (routing logic)
"""

from __future__ import annotations

import uuid
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ii_agent.billing.schemas import TokenUsage
from ii_agent.chat.application.a2a_event_translator import ChatA2AEventTranslator
from ii_agent.chat.application.a2a_turn_loop_service import A2AChatTurnLoop
from ii_agent.chat.types import (
    TextContent,
    TextResultContent,
    ToolResult,
    BinaryContent,
    ImageURLContent,
)
from ii_agent.integrations.a2a.as_client import A2AStreamEvent
from ii_agent.integrations.a2a.circuit_breaker import CircuitBreaker, CircuitBreakerOpenError

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _event(event_type: str, data: Dict[str, Any] | None = None) -> A2AStreamEvent:
    return A2AStreamEvent(event_type=event_type, data=data or {})


def _tool_output_mock(output_text: str = "result", cost: float = 0.0) -> ToolResult:
    output = TextResultContent(value=output_text)
    return ToolResult(
        tool_call_id="tc-1",
        name="web_search",
        output=output,
        cost_usd=cost,
    )


# ===================================================================
# ChatA2AEventTranslator tests
# ===================================================================


class TestChatA2AEventTranslator:
    def test_content_delta_first_produces_start_and_delta(self):
        t = ChatA2AEventTranslator()
        events = t.translate(_event("assistant.message_delta", {"delta": "Hello"}))
        assert len(events) == 2
        assert events[0] == {"type": "content_start"}
        assert events[1] == {"type": "content_delta", "content": "Hello"}

    def test_content_delta_subsequent_produces_only_delta(self):
        t = ChatA2AEventTranslator()
        t.translate(_event("assistant.message_delta", {"delta": "A"}))
        events = t.translate(_event("assistant.message_delta", {"delta": "B"}))
        assert len(events) == 1
        assert events[0] == {"type": "content_delta", "content": "B"}

    def test_empty_delta_produces_no_events(self):
        t = ChatA2AEventTranslator()
        events = t.translate(_event("assistant.message_delta", {"delta": ""}))
        assert events == []

    def test_reasoning_delta_first_produces_start_and_delta(self):
        t = ChatA2AEventTranslator()
        events = t.translate(_event("assistant.reasoning_delta", {"delta": "think"}))
        assert len(events) == 2
        assert events[0] == {"type": "thinking_start"}
        assert events[1] == {"type": "thinking_delta", "thinking": "think"}

    def test_reasoning_done_produces_stop(self):
        t = ChatA2AEventTranslator()
        t.translate(_event("assistant.reasoning_delta", {"delta": "x"}))
        events = t.translate(_event("assistant.reasoning"))
        assert events == [{"type": "thinking_stop"}]

    def test_reasoning_done_without_start_produces_nothing(self):
        t = ChatA2AEventTranslator()
        events = t.translate(_event("assistant.reasoning"))
        assert events == []

    def test_message_complete_produces_stop(self):
        t = ChatA2AEventTranslator()
        t.translate(_event("assistant.message_delta", {"delta": "hi"}))
        events = t.translate(_event("assistant.message", {"content": "hi"}))
        assert events == [{"type": "content_stop"}]

    def test_usage_event_translated(self):
        t = ChatA2AEventTranslator()
        events = t.translate(_event("assistant.usage", {"input_tokens": 10, "output_tokens": 20}))
        assert len(events) == 1
        assert events[0]["type"] == "usage"

    def test_error_event_translated(self):
        t = ChatA2AEventTranslator()
        events = t.translate(_event("session.error", {"message": "boom"}))
        assert events == [{"type": "error", "message": "boom"}]

    def test_heartbeat_ignored(self):
        t = ChatA2AEventTranslator()
        assert t.translate(_event("heartbeat")) == []

    def test_tool_execution_request_ignored(self):
        t = ChatA2AEventTranslator()
        assert t.translate(_event("tool.execution_request", {"name": "foo"})) == []

    def test_session_task_id_ignored(self):
        t = ChatA2AEventTranslator()
        assert t.translate(_event("session.task_id", {"value": "abc"})) == []

    def test_finalize_emits_pending_stops(self):
        t = ChatA2AEventTranslator()
        t.translate(_event("assistant.reasoning_delta", {"delta": "r"}))
        t.translate(_event("assistant.message_delta", {"delta": "c"}))
        events = t.finalize()
        assert {"type": "thinking_stop"} in events
        assert {"type": "content_stop"} in events

    def test_finalize_with_no_pending_is_empty(self):
        t = ChatA2AEventTranslator()
        assert t.finalize() == []

    def test_accumulated_content_tracking(self):
        t = ChatA2AEventTranslator()
        t.translate(_event("assistant.message_delta", {"delta": "Hello "}))
        t.translate(_event("assistant.message_delta", {"delta": "world"}))
        assert t.accumulated_content == "Hello world"

    def test_accumulated_thinking_tracking(self):
        t = ChatA2AEventTranslator()
        t.translate(_event("assistant.reasoning_delta", {"delta": "step1 "}))
        t.translate(_event("assistant.reasoning_delta", {"delta": "step2"}))
        assert t.accumulated_thinking == "step1 step2"

    def test_build_usage_token_usage(self):
        t = ChatA2AEventTranslator()
        usage = t.build_usage_token_usage(
            {
                "input_tokens": 100,
                "output_tokens": 200,
                "cache_read_tokens": 50,
                "reasoning_tokens": 30,
                "cost": 0.05,
            }
        )
        assert isinstance(usage, TokenUsage)
        assert usage.input_tokens == 100
        assert usage.output_tokens == 200
        assert usage.cache_read_tokens == 50
        assert usage.reasoning_tokens == 30
        assert usage.cost_usd == 0.05

    def test_alternate_event_names_text_delta(self):
        t = ChatA2AEventTranslator()
        events = t.translate(_event("text_delta", {"text": "alt"}))
        assert len(events) == 2
        assert events[1]["content"] == "alt"

    def test_alternate_event_names_reasoning_delta(self):
        t = ChatA2AEventTranslator()
        events = t.translate(_event("reasoning_delta", {"text": "think"}))
        assert len(events) == 2
        assert events[1]["thinking"] == "think"

    def test_finish_reason_extracted_from_message(self):
        t = ChatA2AEventTranslator()
        t.translate(_event("assistant.message_delta", {"delta": "hi"}))
        t.translate(_event("assistant.message", {"content": "hi", "finish_reason": "max_tokens"}))
        assert t.finish_reason == "max_tokens"

    def test_finish_reason_from_stop_reason(self):
        t = ChatA2AEventTranslator()
        t.translate(_event("assistant.message_delta", {"delta": "hi"}))
        t.translate(_event("assistant.message", {"content": "hi", "stop_reason": "end_turn"}))
        assert t.finish_reason == "end_turn"

    def test_finish_reason_none_by_default(self):
        t = ChatA2AEventTranslator()
        t.translate(_event("assistant.message_delta", {"delta": "hi"}))
        assert t.finish_reason is None

    def test_finish_reason_error(self):
        t = ChatA2AEventTranslator()
        t.translate(_event("session.error", {"message": "boom"}))
        assert t.finish_reason == "error"


# ===================================================================
# A2AChatTurnLoop tests
# ===================================================================


def _make_mock_client(events: list[A2AStreamEvent] | None = None):
    """Create a mock IIAgentA2AClient that yields events from astream."""
    client = AsyncMock()

    async def _astream(**kwargs):
        for ev in events or []:
            yield ev

    client.astream = _astream
    client.post_tool_result = AsyncMock(return_value=True)
    return client


def _make_a2a_loop(
    events: list[A2AStreamEvent] | None = None,
    fallback_to_native: bool = True,
    a2a_backend: str = "copilot",
) -> tuple[A2AChatTurnLoop, AsyncMock, MagicMock]:
    """Build a complete A2AChatTurnLoop with mocks."""
    client = _make_mock_client(events)
    cb = CircuitBreaker(name="test", failure_threshold=3, cooldown_seconds=1.0)
    fallback_loop = MagicMock()
    message_service = AsyncMock()
    msg_mock = MagicMock()
    msg_mock.id = uuid.uuid4()
    message_service.create_message = AsyncMock(return_value=msg_mock)
    pubsub = AsyncMock()

    loop = A2AChatTurnLoop(
        client=client,
        circuit_breaker=cb,
        fallback_loop=fallback_loop,
        fallback_to_native=fallback_to_native,
        context_reuse=True,
        a2a_backend=a2a_backend,
        message_service=message_service,
        pubsub=pubsub,
    )
    return loop, pubsub, fallback_loop


def _make_run_kwargs(
    session_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
) -> dict:
    """Minimal kwargs for A2AChatTurnLoop.run()."""
    sid = session_id or uuid.uuid4()
    uid = user_id or uuid.uuid4()
    user_message = MagicMock()
    user_message.id = uuid.uuid4()
    user_message.parts = [TextContent(text="hello")]

    model_config = MagicMock()
    model_config.id = uuid.uuid4()
    model_config.model_id = "claude-sonnet-4-20250514"
    model_config.provider = "Anthropic"
    model_config.pricing = None
    model_config.is_user_model.return_value = False
    model_config.thinking_tokens = None

    chat_request = MagicMock()
    chat_request.model_id = "claude-sonnet-4-20250514"

    return {
        "messages": [user_message],
        "provider": MagicMock(),
        "tool_registry": {},
        "tools_to_pass": [],
        "is_code_interpreter_enabled": False,
        "session_id": sid,
        "user_id": uid,
        "model_id": "claude-sonnet-4-20250514",
        "user_message": user_message,
        "run_id": str(uuid.uuid4()),
        "model_config": model_config,
        "chat_request": chat_request,
        "tool_service": MagicMock(),
    }


@pytest.mark.asyncio
async def test_a2a_loop_streams_basic_content():
    """Basic content streaming produces expected SSE events."""
    events = [
        _event("assistant.message_delta", {"delta": "Hello"}),
        _event("assistant.message_delta", {"delta": " world"}),
        _event("assistant.message", {"content": "Hello world"}),
        _event("assistant.usage", {"input_tokens": 10, "output_tokens": 5}),
    ]
    loop, pubsub, _ = _make_a2a_loop(events)
    kwargs = _make_run_kwargs()

    collected = []
    with patch("ii_agent.chat.application.a2a_turn_loop_service.cancel") as mock_cancel:
        mock_cancel.raise_if_cancelled = AsyncMock()
        with patch(
            "ii_agent.chat.application.a2a_turn_loop_service.get_db_session_local"
        ) as mock_db:
            mock_db.return_value.__aenter__ = AsyncMock(return_value=AsyncMock())
            mock_db.return_value.__aexit__ = AsyncMock(return_value=False)
            with patch(
                "ii_agent.chat.application.a2a_turn_loop_service.ContextWindowManager"
            ) as mock_cwm:
                mock_cwm.compress_context_if_needed = AsyncMock(return_value=kwargs["messages"])
                mock_cwm.check_and_summarize_after_response = AsyncMock()
                async for ev in loop.run(**kwargs):
                    collected.append(ev)

    types = [e["type"] for e in collected]
    assert "content_start" in types
    assert "content_delta" in types
    assert "content_stop" in types
    assert "usage" in types
    assert "complete" in types


@pytest.mark.asyncio
async def test_a2a_loop_fallback_on_circuit_breaker_open():
    """When circuit breaker is open, falls back to direct loop."""
    loop, _, fallback = _make_a2a_loop()
    kwargs = _make_run_kwargs()

    # Force circuit breaker open
    for _ in range(5):
        await loop._circuit_breaker.record_failure()

    fallback_events = [{"type": "content_start"}, {"type": "complete"}]

    async def _fallback_run(**kw):
        for ev in fallback_events:
            yield ev

    fallback.run = _fallback_run

    collected = []
    async for ev in loop.run(**kwargs):
        collected.append(ev)

    assert [e["type"] for e in collected] == ["content_start", "complete"]


@pytest.mark.asyncio
async def test_a2a_loop_fallback_on_stream_error():
    """When A2A stream errors, falls back to direct loop."""
    client = AsyncMock()

    async def _failing_stream(**kwargs):
        raise ConnectionError("adapter down")
        yield  # noqa: F841 — makes this an async generator

    client.astream = _failing_stream

    cb = CircuitBreaker(name="test", failure_threshold=3)
    fallback = MagicMock()
    message_service = AsyncMock()
    pubsub = AsyncMock()

    loop = A2AChatTurnLoop(
        client=client,
        circuit_breaker=cb,
        fallback_loop=fallback,
        fallback_to_native=True,
        context_reuse=True,
        a2a_backend="copilot",
        message_service=message_service,
        pubsub=pubsub,
    )

    async def _fallback_run(**kw):
        yield {"type": "complete"}

    fallback.run = _fallback_run
    kwargs = _make_run_kwargs()

    collected = []
    async for ev in loop.run(**kwargs):
        collected.append(ev)

    assert collected == [{"type": "complete"}]


@pytest.mark.asyncio
async def test_a2a_loop_no_fallback_raises():
    """Without fallback, circuit breaker open raises."""
    loop, _, _ = _make_a2a_loop(fallback_to_native=False)
    kwargs = _make_run_kwargs()

    for _ in range(5):
        await loop._circuit_breaker.record_failure()

    with pytest.raises(CircuitBreakerOpenError):
        async for _ in loop.run(**kwargs):
            pass


@pytest.mark.asyncio
async def test_a2a_loop_tool_bridging():
    """Tool execution requests are bridged and results posted back."""
    events = [
        _event(
            "tool.execution_request",
            {"tool_call_id": "tc-1", "name": "web_search", "input": {"query": "test"}},
        ),
        _event("assistant.message_delta", {"delta": "result"}),
        _event("assistant.message", {"content": "result"}),
        _event("assistant.usage", {"input_tokens": 10, "output_tokens": 5}),
    ]
    loop, pubsub, _ = _make_a2a_loop(events)
    kwargs = _make_run_kwargs()

    tool_result = _tool_output_mock("search result", cost=0.01)
    kwargs["tool_service"] = AsyncMock()
    kwargs["tool_service"].execute_tool = AsyncMock(return_value=tool_result)

    collected = []
    with patch("ii_agent.chat.application.a2a_turn_loop_service.cancel") as mock_cancel:
        mock_cancel.raise_if_cancelled = AsyncMock()
        with patch(
            "ii_agent.chat.application.a2a_turn_loop_service.get_db_session_local"
        ) as mock_db:
            mock_db.return_value.__aenter__ = AsyncMock(return_value=AsyncMock())
            mock_db.return_value.__aexit__ = AsyncMock(return_value=False)
            with patch(
                "ii_agent.chat.application.a2a_turn_loop_service.ContextWindowManager"
            ) as mock_cwm:
                mock_cwm.compress_context_if_needed = AsyncMock(return_value=kwargs["messages"])
                mock_cwm.check_and_summarize_after_response = AsyncMock()
                async for ev in loop.run(**kwargs):
                    collected.append(ev)

    types = [e["type"] for e in collected]
    assert "tool_result" in types
    # Tool billing event published
    assert pubsub.publish.call_count >= 1


@pytest.mark.asyncio
async def test_a2a_loop_billing_backend_set():
    """ModelUsageEvent has correct billing_backend for A2A."""
    events = [
        _event("assistant.message_delta", {"delta": "ok"}),
        _event("assistant.message", {"content": "ok"}),
        _event("assistant.usage", {"input_tokens": 50, "output_tokens": 25}),
    ]
    loop, pubsub, _ = _make_a2a_loop(events, a2a_backend="claude-code")
    kwargs = _make_run_kwargs()

    with patch("ii_agent.chat.application.a2a_turn_loop_service.cancel") as mock_cancel:
        mock_cancel.raise_if_cancelled = AsyncMock()
        with patch(
            "ii_agent.chat.application.a2a_turn_loop_service.get_db_session_local"
        ) as mock_db:
            mock_db.return_value.__aenter__ = AsyncMock(return_value=AsyncMock())
            mock_db.return_value.__aexit__ = AsyncMock(return_value=False)
            with patch(
                "ii_agent.chat.application.a2a_turn_loop_service.ContextWindowManager"
            ) as mock_cwm:
                mock_cwm.compress_context_if_needed = AsyncMock(return_value=kwargs["messages"])
                mock_cwm.check_and_summarize_after_response = AsyncMock()
                async for _ in loop.run(**kwargs):
                    pass

    # Find the ModelUsageEvent in pubsub calls
    from ii_agent.realtime.events.app_events import ModelUsageEvent

    usage_calls = [
        c
        for c in pubsub.publish.call_args_list
        if isinstance(c.args[0] if c.args else None, ModelUsageEvent)
    ]
    assert len(usage_calls) == 1
    event = usage_calls[0].args[0]
    assert event.billing_backend == "a2a:claude-code"


# ===================================================================
# ChatService._select_turn_loop tests
# ===================================================================


class TestSelectTurnLoop:
    def _make_chat_service(self, a2a_loop=None):
        from ii_agent.chat.application.chat_service import ChatService

        return ChatService(
            file_processor=MagicMock(),
            tool_service=MagicMock(),
            llm_loop=MagicMock(),
            message_history=MagicMock(),
            message_service=MagicMock(),
            session_repo=MagicMock(),
            model_setting_service=MagicMock(),
            credit_service=MagicMock(),
            container=MagicMock(),
            title_service=MagicMock(),
            a2a_loop=a2a_loop,
        )

    def _make_model_config(self, provider: str = "Anthropic", is_user: bool = False):
        mc = MagicMock()
        mc.provider = provider
        mc.is_user_model.return_value = is_user
        return mc

    def _make_chat_request(self, council_enabled: bool = False, media_type: str | None = None):
        req = MagicMock()
        if council_enabled:
            req.council_preferences = MagicMock()
            req.council_preferences.enabled = True
        else:
            req.council_preferences = None
        if media_type:
            req.media_preferences = MagicMock()
            req.media_preferences.type = media_type
        else:
            req.media_preferences = None
        return req

    def test_no_a2a_loop_returns_direct(self):
        svc = self._make_chat_service(a2a_loop=None)
        result = svc._select_turn_loop(
            model_config=self._make_model_config(),
            chat_request=self._make_chat_request(),
        )
        assert result is svc._llm_loop

    def test_a2a_loop_returns_a2a(self):
        a2a = MagicMock()
        svc = self._make_chat_service(a2a_loop=a2a)
        result = svc._select_turn_loop(
            model_config=self._make_model_config(),
            chat_request=self._make_chat_request(),
        )
        assert result is a2a

    def test_council_mode_returns_direct(self):
        a2a = MagicMock()
        svc = self._make_chat_service(a2a_loop=a2a)
        result = svc._select_turn_loop(
            model_config=self._make_model_config(),
            chat_request=self._make_chat_request(council_enabled=True),
        )
        assert result is svc._llm_loop

    def test_byok_routes_through_a2a_in_local_mode(self):
        """BYOK (user) models route through A2A in local deployment.

        In local/self-hosted mode (ENVIRONMENT=local) the operator owns
        all API keys, so the system/user distinction is irrelevant —
        all compatible models route through A2A.
        """
        a2a = MagicMock()
        svc = self._make_chat_service(a2a_loop=a2a)
        mock_settings = MagicMock()
        mock_settings.environment = "local"
        with patch(
            "ii_agent.chat.application.chat_service.get_settings",
            return_value=mock_settings,
        ):
            result = svc._select_turn_loop(
                model_config=self._make_model_config(is_user=True),
                chat_request=self._make_chat_request(),
            )
        assert result is a2a

    def test_byok_returns_direct_in_cloud_mode(self):
        """BYOK (user) models go direct in cloud deployments.

        In cloud/multitenant mode the user pays their own API bill —
        routing through the platform's A2A adapter would charge the
        platform subscription instead of the user's key.
        """
        a2a = MagicMock()
        svc = self._make_chat_service(a2a_loop=a2a)
        mock_settings = MagicMock()
        mock_settings.environment = "production"
        with patch(
            "ii_agent.chat.application.chat_service.get_settings",
            return_value=mock_settings,
        ):
            result = svc._select_turn_loop(
                model_config=self._make_model_config(is_user=True),
                chat_request=self._make_chat_request(),
            )
        assert result is svc._llm_loop

    def test_custom_provider_returns_direct(self):
        a2a = MagicMock()
        svc = self._make_chat_service(a2a_loop=a2a)
        result = svc._select_turn_loop(
            model_config=self._make_model_config(provider="Custom"),
            chat_request=self._make_chat_request(),
        )
        assert result is svc._llm_loop

    def test_storybook_media_returns_direct(self):
        a2a = MagicMock()
        svc = self._make_chat_service(a2a_loop=a2a)
        result = svc._select_turn_loop(
            model_config=self._make_model_config(),
            chat_request=self._make_chat_request(media_type="storybook"),
        )
        assert result is svc._llm_loop

    def test_image_media_returns_a2a(self):
        a2a = MagicMock()
        svc = self._make_chat_service(a2a_loop=a2a)
        result = svc._select_turn_loop(
            model_config=self._make_model_config(),
            chat_request=self._make_chat_request(media_type="image"),
        )
        assert result is a2a


# ===================================================================
# A2AChatTurnLoop message conversion tests
# ===================================================================


class TestA2AMessageConversion:
    def test_build_a2a_messages_extracts_text(self):
        msg = MagicMock()
        msg.role = "user"
        msg.parts = [TextContent(text="hello world")]

        result = A2AChatTurnLoop._build_a2a_messages([msg])
        assert len(result) == 1
        assert result[0] == {"role": "user", "content": "hello world"}

    def test_build_a2a_messages_skips_tool_role(self):
        tool_msg = MagicMock()
        tool_msg.role = "tool"
        tool_msg.parts = [TextContent(text="tool output")]

        result = A2AChatTurnLoop._build_a2a_messages([tool_msg])
        assert result == []

    def test_extract_system_prompt(self):
        sys_msg = MagicMock()
        sys_msg.role = "system"
        sys_msg.parts = [TextContent(text="You are helpful")]
        user_msg = MagicMock()
        user_msg.role = "user"
        user_msg.parts = [TextContent(text="hi")]

        result = A2AChatTurnLoop._extract_system_prompt([sys_msg, user_msg])
        assert result == "You are helpful"

    def test_extract_system_prompt_none(self):
        user_msg = MagicMock()
        user_msg.role = "user"
        user_msg.parts = [TextContent(text="hi")]

        result = A2AChatTurnLoop._extract_system_prompt([user_msg])
        assert result is None

    def test_serialize_chat_tools(self):
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "web_search",
                    "description": "Search the web",
                    "parameters": {"type": "object", "properties": {"q": {"type": "string"}}},
                },
            }
        ]
        result = A2AChatTurnLoop._serialize_chat_tools(tools)
        assert len(result) == 1
        assert result[0]["name"] == "web_search"
        assert result[0]["description"] == "Search the web"

    def test_serialize_chat_tools_flat_format(self):
        tools = [
            {
                "name": "code_interpreter",
                "description": "Run code",
                "parameters": {"type": "object"},
            }
        ]
        result = A2AChatTurnLoop._serialize_chat_tools(tools)
        assert len(result) == 1
        assert result[0]["name"] == "code_interpreter"

    def test_build_a2a_messages_binary_content_produces_images(self):
        """BinaryContent parts are converted to A2A Image objects."""
        msg = MagicMock()
        msg.role = "user"
        msg.parts = [
            TextContent(text="What is in this image?"),
            BinaryContent(path="photo.png", mime_type="image/png", data=b"\x89PNG"),
        ]

        result = A2AChatTurnLoop._build_a2a_messages([msg])
        assert len(result) == 1
        assert result[0]["role"] == "user"
        assert result[0]["content"] == "What is in this image?"
        assert "images" in result[0]
        assert len(result[0]["images"]) == 1
        img = result[0]["images"][0]
        assert img.content == b"\x89PNG"
        assert img.mime_type == "image/png"

    def test_build_a2a_messages_image_url_content(self):
        """ImageURLContent parts are converted to A2A Image objects with URL."""
        msg = MagicMock()
        msg.role = "user"
        msg.parts = [
            TextContent(text="Describe this"),
            ImageURLContent(url="https://example.com/img.jpg"),
        ]

        result = A2AChatTurnLoop._build_a2a_messages([msg])
        assert len(result) == 1
        assert "images" in result[0]
        assert len(result[0]["images"]) == 1
        img = result[0]["images"][0]
        assert img.url == "https://example.com/img.jpg"

    def test_build_a2a_messages_text_only_no_images_key(self):
        """Text-only messages should not have an 'images' key."""
        msg = MagicMock()
        msg.role = "user"
        msg.parts = [TextContent(text="hello")]

        result = A2AChatTurnLoop._build_a2a_messages([msg])
        assert len(result) == 1
        assert "images" not in result[0]


# ===================================================================
# Context ID tests
# ===================================================================


class TestContextId:
    def test_context_reuse_stable_id(self):
        loop, _, _ = _make_a2a_loop()
        loop._context_reuse = True
        sid = uuid.uuid4()
        id1 = loop._build_context_id(sid)
        id2 = loop._build_context_id(sid)
        assert id1 == id2
        assert id1 == f"chat-{sid}"

    def test_no_context_reuse_unique_id(self):
        loop, _, _ = _make_a2a_loop()
        loop._context_reuse = False
        sid = uuid.uuid4()
        id1 = loop._build_context_id(sid)
        id2 = loop._build_context_id(sid)
        assert id1 != id2
        assert id1.startswith(f"chat-{sid}-")


# ===================================================================
# Shared A2A resources (circuit breaker singleton) tests
# ===================================================================


class TestSharedA2AResources:
    """Verify the dependency factory shares CB + client across calls."""

    def test_shared_resources_returns_same_instances(self):
        """Multiple calls to _get_shared_a2a_resources return the same objects."""
        import ii_agent.chat.api.dependencies as deps

        # Reset module-level singletons
        deps._a2a_chat_client = None
        deps._a2a_chat_circuit_breaker = None

        mock_settings = MagicMock()
        mock_settings.agent.chat_inner_loop_mode = "a2a"
        mock_settings.agent.a2a_agent_url = "http://adapter:18100"
        mock_settings.agent.a2a_timeout_seconds = 60

        with patch("ii_agent.core.config.settings.get_settings", return_value=mock_settings):
            with patch("ii_agent.integrations.a2a.as_client.IIAgentA2AClient") as mock_client_cls:
                with patch(
                    "ii_agent.integrations.a2a.circuit_breaker.CircuitBreaker"
                ) as mock_cb_cls:
                    mock_client_cls.return_value = MagicMock()
                    mock_cb_cls.return_value = MagicMock()

                    client1, cb1 = deps._get_shared_a2a_resources()
                    client2, cb2 = deps._get_shared_a2a_resources()

                    assert client1 is client2
                    assert cb1 is cb2
                    # Only one instance created
                    mock_client_cls.assert_called_once()
                    mock_cb_cls.assert_called_once()

        # Cleanup
        deps._a2a_chat_client = None
        deps._a2a_chat_circuit_breaker = None

    def test_shared_resources_returns_none_when_direct_mode(self):
        """When mode is 'direct', returns (None, None)."""
        import ii_agent.chat.api.dependencies as deps

        deps._a2a_chat_client = None
        deps._a2a_chat_circuit_breaker = None

        mock_settings = MagicMock()
        mock_settings.agent.chat_inner_loop_mode = "direct"

        with patch("ii_agent.core.config.settings.get_settings", return_value=mock_settings):
            client, cb = deps._get_shared_a2a_resources()
            assert client is None
            assert cb is None


# ===================================================================
# Metadata construction tests
# ===================================================================


class TestMetadataConstruction:
    """Verify metadata keys match what the adapter server expects."""

    @pytest.mark.asyncio
    async def test_metadata_uses_native_tool_schemas_key(self):
        """Metadata must use 'native_tool_schemas' (not 'tool_schemas')
        because the adapter reads: metadata.get('native_tool_schemas')."""
        events = [
            _event("assistant.message_delta", {"delta": "ok"}),
            _event("assistant.message", {"content": "ok"}),
            _event("assistant.usage", {"input_tokens": 1, "output_tokens": 1}),
        ]
        client = _make_mock_client(events)

        # Capture what metadata astream receives
        captured_metadata = {}
        original_astream = client.astream

        async def _capturing_astream(**kwargs):
            captured_metadata.update(kwargs.get("metadata", {}))
            async for ev in original_astream(**kwargs):
                yield ev

        client.astream = _capturing_astream

        cb = CircuitBreaker(name="test", failure_threshold=3, cooldown_seconds=1.0)
        message_service = AsyncMock()
        msg_mock = MagicMock()
        msg_mock.id = uuid.uuid4()
        message_service.create_message = AsyncMock(return_value=msg_mock)
        pubsub = AsyncMock()

        loop = A2AChatTurnLoop(
            client=client,
            circuit_breaker=cb,
            fallback_loop=MagicMock(),
            fallback_to_native=True,
            context_reuse=True,
            a2a_backend="copilot",
            message_service=message_service,
            pubsub=pubsub,
        )

        kwargs = _make_run_kwargs()
        kwargs["tools_to_pass"] = [
            {
                "type": "function",
                "function": {
                    "name": "web_search",
                    "description": "Search",
                    "parameters": {"type": "object"},
                },
            }
        ]

        with patch("ii_agent.chat.application.a2a_turn_loop_service.cancel") as mock_cancel:
            mock_cancel.raise_if_cancelled = AsyncMock()
            with patch(
                "ii_agent.chat.application.a2a_turn_loop_service.get_db_session_local"
            ) as mock_db:
                mock_db.return_value.__aenter__ = AsyncMock(return_value=AsyncMock())
                mock_db.return_value.__aexit__ = AsyncMock(return_value=False)
                with patch(
                    "ii_agent.chat.application.a2a_turn_loop_service.ContextWindowManager"
                ) as mock_cwm:
                    mock_cwm.compress_context_if_needed = AsyncMock(return_value=kwargs["messages"])
                    mock_cwm.check_and_summarize_after_response = AsyncMock()
                    async for _ in loop.run(**kwargs):
                        pass

        assert "native_tool_schemas" in captured_metadata
        assert "tool_schemas" not in captured_metadata
        assert len(captured_metadata["native_tool_schemas"]) == 1
        assert captured_metadata["native_tool_schemas"][0]["name"] == "web_search"

    @pytest.mark.asyncio
    async def test_metadata_includes_thinking_tokens(self):
        """thinking_tokens from model config should be forwarded in metadata."""
        events = [
            _event("assistant.message_delta", {"delta": "ok"}),
            _event("assistant.message", {"content": "ok"}),
        ]
        client = _make_mock_client(events)
        captured_metadata = {}
        original_astream = client.astream

        async def _capturing_astream(**kwargs):
            captured_metadata.update(kwargs.get("metadata", {}))
            async for ev in original_astream(**kwargs):
                yield ev

        client.astream = _capturing_astream

        cb = CircuitBreaker(name="test", failure_threshold=3, cooldown_seconds=1.0)
        message_service = AsyncMock()
        msg_mock = MagicMock()
        msg_mock.id = uuid.uuid4()
        message_service.create_message = AsyncMock(return_value=msg_mock)

        loop = A2AChatTurnLoop(
            client=client,
            circuit_breaker=cb,
            fallback_loop=MagicMock(),
            fallback_to_native=True,
            context_reuse=True,
            a2a_backend="copilot",
            message_service=message_service,
            pubsub=AsyncMock(),
        )

        kwargs = _make_run_kwargs()
        kwargs["model_config"].thinking_tokens = 16000

        with patch("ii_agent.chat.application.a2a_turn_loop_service.cancel") as mock_cancel:
            mock_cancel.raise_if_cancelled = AsyncMock()
            with patch(
                "ii_agent.chat.application.a2a_turn_loop_service.get_db_session_local"
            ) as mock_db:
                mock_db.return_value.__aenter__ = AsyncMock(return_value=AsyncMock())
                mock_db.return_value.__aexit__ = AsyncMock(return_value=False)
                with patch(
                    "ii_agent.chat.application.a2a_turn_loop_service.ContextWindowManager"
                ) as mock_cwm:
                    mock_cwm.compress_context_if_needed = AsyncMock(return_value=kwargs["messages"])
                    mock_cwm.check_and_summarize_after_response = AsyncMock()
                    async for _ in loop.run(**kwargs):
                        pass

        assert captured_metadata.get("thinking_tokens") == 16000
