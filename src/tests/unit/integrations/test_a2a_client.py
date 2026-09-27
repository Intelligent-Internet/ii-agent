"""Tests for IIAgentA2AClient — targeting line/branch coverage gaps."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from ii_agent.agents.models.message import Message
from ii_agent.integrations.a2a.as_client import IIAgentA2AClient

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _user_msg(text: str) -> Message:
    return Message(role="user", content=text)


def _sse_line(event_type: str, data: dict) -> str:
    payload = json.dumps({"type": event_type, "data": data})
    return f"data: {payload}"


def _make_streaming_response(lines: list[str]):
    """Build a mock httpx streaming response that yields the given SSE lines."""
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()

    async def _aiter_lines():
        for line in lines:
            yield line

    mock_resp.aiter_lines = _aiter_lines
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)
    return mock_resp


# ---------------------------------------------------------------------------
# URL resolution
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_static_url_resolves_immediately():
    client = IIAgentA2AClient(agent_url="http://localhost:18100")
    assert client.agent_url == "http://localhost:18100"


@pytest.mark.asyncio
async def test_url_factory_resolves_lazily():
    factory_calls = []

    async def factory() -> str:
        factory_calls.append(1)
        return "http://dynamic:18100"

    client = IIAgentA2AClient(url_factory=factory)
    assert client.agent_url is None  # not resolved yet
    url = await client._resolve_url()
    assert url == "http://dynamic:18100"
    assert client._resolved_url == "http://dynamic:18100"
    # Second call must NOT invoke the factory again.
    await client._resolve_url()
    assert len(factory_calls) == 1


@pytest.mark.asyncio
async def test_static_url_stripping():
    client = IIAgentA2AClient(agent_url="http://host:18100/")
    url = await client._resolve_url()
    assert url == "http://host:18100"


# ---------------------------------------------------------------------------
# Timeout handling
# ---------------------------------------------------------------------------


def test_default_timeout_used_when_none():
    client = IIAgentA2AClient(agent_url="http://test")
    assert client._timeout == IIAgentA2AClient._DEFAULT_STREAM_TIMEOUT
    assert client._timeout.read == 120.0


def test_float_timeout_preserves_read_timeout():
    """A float config value should only affect connect, not read."""
    client = IIAgentA2AClient(agent_url="http://test", timeout=30.0)
    assert client._timeout.connect == 30.0
    assert client._timeout.read == 120.0  # preserved from default
    assert client._timeout.write == 30.0
    assert client._timeout.pool == 30.0


def test_httpx_timeout_used_directly():
    custom = httpx.Timeout(connect=5.0, read=60.0, write=10.0, pool=15.0)
    client = IIAgentA2AClient(agent_url="http://test", timeout=custom)
    assert client._timeout is custom


# ---------------------------------------------------------------------------
# astream — basic event yielding
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_astream_yields_events():
    lines = [
        _sse_line("assistant.message_delta", {"delta": "hello"}),
        _sse_line("assistant.usage", {"input_tokens": 5, "output_tokens": 3}),
        "data: [DONE]",
        "",  # blank line
    ]

    mock_resp = _make_streaming_response(lines)
    mock_client = MagicMock()
    mock_client.stream = MagicMock(return_value=mock_resp)
    mock_client.aclose = AsyncMock()

    client = IIAgentA2AClient(agent_url="http://test", httpx_client=mock_client)
    events = []
    async for event in client.astream(messages=[_user_msg("hi")], context_id="ctx-1"):
        events.append(event)

    assert len(events) == 2
    assert events[0].event_type == "assistant.message_delta"
    assert events[0].data["delta"] == "hello"
    assert events[1].event_type == "assistant.usage"


@pytest.mark.asyncio
async def test_astream_creates_and_closes_owned_client():
    """When no httpx_client is provided, astream must create and close its own."""
    lines = [_sse_line("assistant.message", {"content": "done"}), "data: [DONE]"]
    mock_resp = _make_streaming_response(lines)

    mock_http_client = MagicMock()
    mock_http_client.stream = MagicMock(return_value=mock_resp)
    mock_http_client.aclose = AsyncMock()

    with patch(
        "ii_agent.integrations.a2a.as_client.httpx.AsyncClient",
        return_value=mock_http_client,
    ):
        client = IIAgentA2AClient(agent_url="http://test")  # no httpx_client
        events = []
        async for event in client.astream(messages=[_user_msg("hello")], context_id="ctx"):
            events.append(event)

    mock_http_client.aclose.assert_called_once()
    assert any(e.event_type == "assistant.message" for e in events)


# ---------------------------------------------------------------------------
# _parse_stream_line edge cases
# ---------------------------------------------------------------------------


def test_parse_empty_line_returns_none():
    assert IIAgentA2AClient._parse_stream_line("") is None
    assert IIAgentA2AClient._parse_stream_line("   ") is None


def test_parse_done_sentinel_returns_none():
    assert IIAgentA2AClient._parse_stream_line("data: [DONE]") is None
    assert IIAgentA2AClient._parse_stream_line("done") is None


def test_parse_non_json_returns_none():
    assert IIAgentA2AClient._parse_stream_line("not json at all") is None


def test_parse_json_without_type_returns_none():
    line = "data: " + json.dumps({"foo": "bar"})
    assert IIAgentA2AClient._parse_stream_line(line) is None


def test_parse_data_dict_extracted():
    payload = {"type": "assistant.message", "data": {"content": "hi"}}
    event = IIAgentA2AClient._parse_stream_line("data: " + json.dumps(payload))
    assert event is not None
    assert event.event_type == "assistant.message"
    assert event.data["content"] == "hi"


def test_parse_non_dict_data_wrapped_in_value():
    payload = {"type": "usage", "data": 42}
    event = IIAgentA2AClient._parse_stream_line(json.dumps(payload))
    assert event is not None
    assert event.data == {"value": 42}


def test_parse_uses_event_key_as_fallback():
    payload = {"event": "my_event", "data": {"x": 1}}
    event = IIAgentA2AClient._parse_stream_line(json.dumps(payload))
    assert event is not None
    assert event.event_type == "my_event"


def test_parse_non_dict_payload_returns_none():
    assert IIAgentA2AClient._parse_stream_line(json.dumps([1, 2, 3])) is None


# ---------------------------------------------------------------------------
# get_agent_card
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_agent_card_returns_card_object():
    card_data = {
        "name": "test-agent",
        "description": "A test agent",
        "extensions": [{"uri": "urn:test"}],
    }
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = card_data

    mock_http_client = MagicMock()
    mock_http_client.get = AsyncMock(return_value=mock_resp)
    mock_http_client.aclose = AsyncMock()

    client = IIAgentA2AClient(agent_url="http://agent", httpx_client=mock_http_client)
    card = await client.get_agent_card()

    mock_http_client.get.assert_called_once_with("http://agent/.well-known/agent-card.json")
    assert card.description == "A test agent"
    assert card.extensions == [{"uri": "urn:test"}]
    assert card["name"] == "test-agent"
    assert card.get("name") == "test-agent"
    assert card.get("missing", "default") == "default"


@pytest.mark.asyncio
async def test_get_agent_card_creates_and_closes_client():
    card_data = {"name": "x", "description": ""}
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = card_data

    mock_http_client = MagicMock()
    mock_http_client.get = AsyncMock(return_value=mock_resp)
    mock_http_client.aclose = AsyncMock()

    with patch(
        "ii_agent.integrations.a2a.as_client.httpx.AsyncClient",
        return_value=mock_http_client,
    ):
        client = IIAgentA2AClient(agent_url="http://agent")  # no external client
        await client.get_agent_card()

    mock_http_client.aclose.assert_called_once()


@pytest.mark.asyncio
async def test_get_agent_card_returns_raw_when_not_dict():
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = ["list", "response"]

    mock_http = MagicMock()
    mock_http.get = AsyncMock(return_value=mock_resp)
    mock_http.aclose = AsyncMock()

    client = IIAgentA2AClient(agent_url="http://agent", httpx_client=mock_http)
    result = await client.get_agent_card()
    assert result == ["list", "response"]


# ---------------------------------------------------------------------------
# call_agent
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_call_agent_collects_message_delta_and_message():
    lines = [
        _sse_line("assistant.message_delta", {"delta": "hello "}),
        _sse_line("assistant.message", {"content": "hello world"}),
        "data: [DONE]",
    ]
    mock_resp = _make_streaming_response(lines)
    mock_http = MagicMock()
    mock_http.stream = MagicMock(return_value=mock_resp)
    mock_http.aclose = AsyncMock()

    client = IIAgentA2AClient(agent_url="http://agent", httpx_client=mock_http)
    result = await client.call_agent(messages=[_user_msg("say hello")], context_id="ctx-call")

    assert result["success"] is True
    assert "hello" in result["content"]


@pytest.mark.asyncio
async def test_call_agent_returns_failure_on_error_event():
    lines = [
        _sse_line("session.error", {"message": "something broke"}),
        "data: [DONE]",
    ]
    mock_resp = _make_streaming_response(lines)
    mock_http = MagicMock()
    mock_http.stream = MagicMock(return_value=mock_resp)
    mock_http.aclose = AsyncMock()

    client = IIAgentA2AClient(agent_url="http://agent", httpx_client=mock_http)
    result = await client.call_agent(messages=[_user_msg("hi")], context_id="ctx-err")

    assert result["success"] is False
    assert "something broke" in result["content"]


@pytest.mark.asyncio
async def test_call_agent_returns_failure_on_exception():
    mock_http = MagicMock()
    mock_http.stream = MagicMock(side_effect=Exception("network failure"))
    mock_http.aclose = AsyncMock()

    client = IIAgentA2AClient(agent_url="http://agent", httpx_client=mock_http)
    result = await client.call_agent(messages=[_user_msg("hi")], context_id="ctx-exc")

    assert result["success"] is False
    assert "network failure" in result["content"]


# ---------------------------------------------------------------------------
# close
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_close_calls_aclose_on_external_client():
    mock_http = MagicMock()
    mock_http.aclose = AsyncMock()

    client = IIAgentA2AClient(agent_url="http://agent", httpx_client=mock_http)
    await client.close()
    mock_http.aclose.assert_called_once()


@pytest.mark.asyncio
async def test_close_is_noop_without_external_client():
    client = IIAgentA2AClient(agent_url="http://agent")
    await client.close()  # must not raise
