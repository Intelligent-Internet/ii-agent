"""Tests for A2A chat turn loop fallback edge cases.

Covers:
- P1: Cascading failure (A2A fails, then native also fails)
- P1: Fallback native error does not retry A2A
- P7: No billing for failed A2A attempt
- P7: Circuit breaker open skips billing
"""

from __future__ import annotations

import contextlib
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ii_agent.chat.application.a2a_turn_loop_service import A2AChatTurnLoop
from ii_agent.chat.types import TextContent
from ii_agent.integrations.a2a.as_client import A2AStreamEvent
from ii_agent.integrations.a2a.circuit_breaker import CircuitBreaker
from ii_agent.realtime.events.app_events import ModelUsageEvent

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Helpers (same pattern as test_chat_a2a_turn_loop.py)
# ---------------------------------------------------------------------------


def _event(event_type: str, data: dict | None = None) -> A2AStreamEvent:
    return A2AStreamEvent(event_type=event_type, data=data or {})


def _make_mock_client(events: list[A2AStreamEvent] | None = None):
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
    client = _make_mock_client(events)
    cb = CircuitBreaker(name="test-fallback", failure_threshold=3, cooldown_seconds=1.0)
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
    sid = session_id or uuid.uuid4()
    uid = user_id or uuid.uuid4()

    user_message = MagicMock()
    user_message.role = "user"
    user_message.parts = [TextContent(text="What is 3+5?")]
    user_message.id = uuid.uuid4()
    user_message.session_id = sid
    user_message.created_at = 0
    user_message.updated_at = 0

    model_config = MagicMock()
    model_config.id = uuid.uuid4()
    model_config.model_id = "gpt-4o"
    model_config.provider = "OpenAI"
    model_config.pricing = None
    model_config.is_user_model.return_value = False
    model_config.thinking_tokens = None

    chat_request = MagicMock()
    chat_request.model_id = "gpt-4o"

    return {
        "messages": [user_message],
        "provider": MagicMock(),
        "tool_registry": {},
        "tools_to_pass": [],
        "is_code_interpreter_enabled": False,
        "session_id": sid,
        "user_id": uid,
        "model_id": "gpt-4o",
        "user_message": user_message,
        "run_id": str(uuid.uuid4()),
        "model_config": model_config,
        "chat_request": chat_request,
        "tool_service": MagicMock(),
    }


@contextlib.contextmanager
def _patch_a2a_deps(messages):
    """Patch external dependencies that A2AChatTurnLoop.run() touches."""
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
                mock_cwm.compress_context_if_needed = AsyncMock(return_value=messages)
                mock_cwm.check_and_summarize_after_response = AsyncMock()
                yield


async def _consume(async_gen):
    """Fully consume an async generator, collecting all yielded items."""
    items = []
    async for item in async_gen:
        items.append(item)
    return items


# ===================================================================
# P1: Cascading double failure
# ===================================================================


@pytest.mark.asyncio
async def test_double_failure_a2a_then_native_propagates_error():
    """When A2A fails AND native fallback also raises, the error propagates
    to the caller. This matches the production case where A2A returned
    session.error then OpenAI returned quota exceeded."""
    # A2A stream raises session.error
    events = [_event("session.error", {"message": "Failed to list models: 400"})]
    loop, pubsub, fallback = _make_a2a_loop(events)
    kwargs = _make_run_kwargs()

    # Native fallback also fails (simulates OpenAI quota error)
    async def _failing_fallback(**kw):
        raise Exception("You exceeded your current quota")
        yield  # noqa: F841 — async generator

    fallback.run = _failing_fallback

    with pytest.raises(Exception, match="You exceeded your current quota"):
        with _patch_a2a_deps(kwargs["messages"]):
            await _consume(loop.run(**kwargs))


@pytest.mark.asyncio
async def test_double_failure_records_circuit_breaker_failure():
    """A2A failure should record a CB failure even when the fallback also fails."""
    events = [_event("session.error", {"message": "Failed to list models: 400"})]
    loop, pubsub, fallback = _make_a2a_loop(events)
    kwargs = _make_run_kwargs()

    async def _failing_fallback(**kw):
        raise Exception("OpenAI quota exceeded")
        yield  # noqa: F841

    fallback.run = _failing_fallback

    assert loop._circuit_breaker.failure_count == 0

    with pytest.raises(Exception):
        with _patch_a2a_deps(kwargs["messages"]):
            await _consume(loop.run(**kwargs))

    # A2A failure was recorded
    assert loop._circuit_breaker.failure_count == 1


@pytest.mark.asyncio
async def test_fallback_native_error_does_not_retry_a2a():
    """After falling back to native, if native fails, there should be NO
    attempt to re-enter the A2A loop."""
    client = AsyncMock()
    call_count = 0

    async def _counting_stream(**kwargs):
        nonlocal call_count
        call_count += 1
        raise ConnectionError("adapter down")
        yield  # noqa: F841

    client.astream = _counting_stream

    cb = CircuitBreaker(name="test", failure_threshold=3)
    fallback = MagicMock()
    message_service = AsyncMock()
    msg_mock = MagicMock()
    msg_mock.id = uuid.uuid4()
    message_service.create_message = AsyncMock(return_value=msg_mock)
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

    async def _failing_fallback(**kw):
        raise Exception("Native also failed")
        yield  # noqa: F841

    fallback.run = _failing_fallback
    kwargs = _make_run_kwargs()

    with pytest.raises(Exception, match="Native also failed"):
        with _patch_a2a_deps(kwargs["messages"]):
            await _consume(loop.run(**kwargs))

    # A2A was attempted exactly once (not retried after native failure)
    assert call_count == 1


# ===================================================================
# P7: Billing during fallback
# ===================================================================


@pytest.mark.asyncio
async def test_no_billing_for_failed_a2a_attempt():
    """When A2A fails before producing any usage, no ModelUsageEvent
    should be published for the A2A attempt."""
    events = [_event("session.error", {"message": "Failed to list models: 400"})]
    loop, pubsub, fallback = _make_a2a_loop(events)
    kwargs = _make_run_kwargs()

    async def _fallback_run(**kw):
        yield {"type": "content_start"}
        yield {"type": "content_delta", "content": "fallback response"}
        yield {"type": "content_stop"}
        yield {"type": "complete"}

    fallback.run = _fallback_run

    with _patch_a2a_deps(kwargs["messages"]):
        await _consume(loop.run(**kwargs))

    # No ModelUsageEvent should have been published for the failed A2A
    a2a_usage_calls = [
        c
        for c in pubsub.publish.call_args_list
        if isinstance(c.args[0] if c.args else None, ModelUsageEvent)
    ]
    assert len(a2a_usage_calls) == 0


@pytest.mark.asyncio
async def test_circuit_breaker_open_skips_billing():
    """When circuit breaker is open, we skip A2A entirely.
    No A2A billing event should be generated."""
    loop, pubsub, fallback = _make_a2a_loop()
    kwargs = _make_run_kwargs()

    # Force circuit breaker open
    for _ in range(5):
        await loop._circuit_breaker.record_failure()

    fallback_events = [
        {"type": "content_start"},
        {"type": "content_delta", "content": "direct response"},
        {"type": "complete"},
    ]

    async def _fallback_run(**kw):
        for ev in fallback_events:
            yield ev

    fallback.run = _fallback_run

    collected = await _consume(loop.run(**kwargs))
    assert len(collected) > 0  # Fallback actually produced events

    # No A2A ModelUsageEvent (only the fallback loop runs, which handles
    # its own billing via the standard native path)
    a2a_usage_calls = [
        c
        for c in pubsub.publish.call_args_list
        if isinstance(c.args[0] if c.args else None, ModelUsageEvent)
    ]
    assert len(a2a_usage_calls) == 0
