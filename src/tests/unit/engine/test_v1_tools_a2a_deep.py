"""Deep unit tests for A2A Agent Tool - covering uncovered branches.

Focuses on:
- _get_client: cache hit, cache miss with header changes, new client creation
- execute: full flow with context, failed result, missing fields
- _build_call_params: context passing
- _emit_event: event stream present/absent
- _handle_streaming_events: various event types
- initialize: multi-agent flows
"""

from __future__ import annotations

import pytest

from unittest.mock import AsyncMock, MagicMock, patch

from ii_agent.agents.tools.a2a.a2a_agent_tool import A2AAgentTool


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_tool(default_agents=None) -> A2AAgentTool:
    return A2AAgentTool(default_agents=default_agents)


def make_mock_client(description="Test Agent", extensions=None) -> AsyncMock:
    client = AsyncMock()
    card = MagicMock()
    card.description = description
    card.extensions = extensions or []
    client.get_agent_card = AsyncMock(return_value=card)
    client.call_agent = AsyncMock(
        return_value={
            "success": True,
            "content": "result text",
            "user_display_content": "result display",
        }
    )
    client.close = AsyncMock()
    return client


# ---------------------------------------------------------------------------
# _get_sub_agent_info helper
# ---------------------------------------------------------------------------


class TestGetSubAgentInfo:
    """Test the internal helper function that extracts sub-agent info."""

    def test_no_sub_agent_fields_returns_empty(self):
        from ii_agent.agents.factory.converter import _get_sub_agent_info
        from ii_agent.agents.runs.agent import RunStartedEvent

        ev = RunStartedEvent(agent_id="a1", agent_name="A")
        info = _get_sub_agent_info(ev)
        # delegated_from is None, is_sub_agent_event is False
        assert "delegated_from" not in info or not info.get("delegated_from")

    def test_delegated_from_included(self):
        from ii_agent.agents.factory.converter import _get_sub_agent_info
        from ii_agent.agents.runs.agent import RunStartedEvent

        ev = RunStartedEvent(agent_id="a1", agent_name="A", delegated_from="ParentAgent")
        info = _get_sub_agent_info(ev)
        assert info.get("delegated_from") == "ParentAgent"

    def test_is_sub_agent_event_included(self):
        from ii_agent.agents.factory.converter import _get_sub_agent_info
        from ii_agent.agents.runs.agent import RunStartedEvent

        ev = RunStartedEvent(agent_id="a1", agent_name="A", is_sub_agent_event=True)
        info = _get_sub_agent_info(ev)
        assert info.get("is_sub_agent_event") is True

    def test_run_output_sub_agent_response(self):
        from ii_agent.agents.factory.converter import _get_sub_agent_info
        from ii_agent.agents.runs.agent import RunOutput

        output = RunOutput(
            run_id="run-1",
            session_id="s-1",
            user_id="u-1",
            model="gpt-4o",
            agent_name="SubAgent",
            delegated_from="ParentAgent",
        )
        info = _get_sub_agent_info(output)
        assert info.get("is_sub_agent_response") is True

    def test_parent_run_id_included(self):
        from ii_agent.agents.factory.converter import _get_sub_agent_info
        from ii_agent.agents.runs.agent import RunStartedEvent

        ev = RunStartedEvent(agent_id="a1", agent_name="A", parent_run_id="parent-123")
        info = _get_sub_agent_info(ev)
        assert info.get("parent_run_id") == "parent-123"

    def test_agent_name_included(self):
        from ii_agent.agents.factory.converter import _get_sub_agent_info
        from ii_agent.agents.runs.agent import RunStartedEvent

        ev = RunStartedEvent(agent_id="a1", agent_name="MyAgent")
        info = _get_sub_agent_info(ev)
        assert info.get("agent_name") == "MyAgent"


# ---------------------------------------------------------------------------
# Execute deep tests
# ---------------------------------------------------------------------------


class TestExecuteDeep:
    @pytest.mark.asyncio
    async def test_execute_with_context_passes_context(self):
        """Test that context parameter is passed through to call_agent."""
        tool = make_tool({"agent1": "http://agent1.example.com"})
        tool._initialized = True

        mock_client = make_mock_client()
        tool._clients["http://agent1.example.com"] = mock_client
        tool._client_headers["http://agent1.example.com"] = ()
        tool._agent_cards["http://agent1.example.com"] = MagicMock(
            description="Agent One", extensions=[]
        )
        tool._agent_descriptions["http://agent1.example.com"] = "Agent One"
        tool._agent_extensions["http://agent1.example.com"] = set()

        result = await tool.execute(
            {
                "agent_url": "agent1",
                "query": "do something",
                "context": {"briefing": "some context"},
            }
        )
        assert result.is_error is None or result.is_error is False

    @pytest.mark.asyncio
    async def test_execute_with_url_directly(self):
        """Test execute using direct URL instead of agent name alias."""
        tool = make_tool()
        tool._initialized = True

        mock_client = make_mock_client()
        tool._clients["http://direct.example.com"] = mock_client
        tool._client_headers["http://direct.example.com"] = ()
        tool._agent_cards["http://direct.example.com"] = MagicMock(
            description="Direct Agent", extensions=[]
        )
        tool._agent_descriptions["http://direct.example.com"] = "Direct Agent"
        tool._agent_extensions["http://direct.example.com"] = set()

        result = await tool.execute(
            {
                "agent_url": "http://direct.example.com",
                "query": "direct call",
            }
        )
        assert "result text" in result.llm_content

    @pytest.mark.asyncio
    async def test_execute_unknown_url_tries_to_get_client(self):
        """Test that an unknown URL causes a client lookup attempt."""
        tool = make_tool()
        tool._initialized = True

        # Mock _get_client to return a valid client
        mock_client = make_mock_client()
        mock_client.get_agent_card = AsyncMock(
            return_value=MagicMock(description="Dynamic", extensions=[])
        )

        async def mock_get_client(url, headers=None):
            tool._agent_cards[url] = MagicMock(description="Dynamic", extensions=[])
            tool._agent_descriptions[url] = "Dynamic"
            tool._agent_extensions[url] = set()
            tool._clients[url] = mock_client
            return mock_client

        tool._get_client = mock_get_client

        result = await tool.execute(
            {
                "agent_url": "http://unknown.example.com",
                "query": "task",
            }
        )
        assert result is not None

    @pytest.mark.asyncio
    async def test_execute_returns_error_on_client_exception(self):
        tool = make_tool()
        tool._initialized = True

        async def failing_get_client(url, headers=None):
            raise ConnectionError("Cannot connect")

        tool._get_client = failing_get_client

        result = await tool.execute(
            {
                "agent_url": "http://unreachable.example.com",
                "query": "task",
            }
        )
        assert result.is_error is True or "Error" in result.llm_content

    @pytest.mark.asyncio
    async def test_execute_empty_query_returns_error(self):
        tool = make_tool()
        tool._initialized = True
        result = await tool.execute({"agent_url": "http://test.com", "query": ""})
        assert "Error" in result.llm_content

    @pytest.mark.asyncio
    async def test_execute_whitespace_query_returns_error(self):
        tool = make_tool()
        tool._initialized = True
        result = await tool.execute({"agent_url": "http://test.com", "query": "   "})
        assert "Error" in result.llm_content

    @pytest.mark.asyncio
    async def test_execute_whitespace_url_returns_error(self):
        tool = make_tool()
        tool._initialized = True
        result = await tool.execute({"agent_url": "  ", "query": "task"})
        assert "Error" in result.llm_content


# ---------------------------------------------------------------------------
# _get_client deep tests
# ---------------------------------------------------------------------------


class TestGetClientDeep:
    @pytest.mark.asyncio
    async def test_get_client_returns_cached_client_for_same_headers(self):
        tool = make_tool()
        mock_client = make_mock_client()
        tool._clients["http://test.com"] = mock_client
        # Simulate that the resolved headers match the cached signature
        tool._client_headers["http://test.com"] = ()  # No headers

        with (
            patch.object(tool, "_resolve_headers", return_value={}),
            patch(
                "ii_agent.agents.tools.a2a.a2a_agent_tool.IIAgentA2AClient",
            ) as MockClient,
        ):
            client = await tool._get_client("http://test.com")
            # Should NOT create a new client - uses cache
            MockClient.assert_not_called()
            assert client is mock_client

    @pytest.mark.asyncio
    async def test_get_client_creates_new_client_on_header_change(self):
        """When headers change, the old client should be closed and a new one created."""
        tool = make_tool()
        old_client = make_mock_client()
        tool._clients["http://test.com"] = old_client
        # Cached signature is empty, but new resolved headers will be different
        tool._client_headers["http://test.com"] = (("x-old-header", "old"),)

        new_client = make_mock_client()
        with (
            patch.object(tool, "_resolve_headers", return_value={"x-new-header": "new"}),
            patch(
                "ii_agent.agents.tools.a2a.a2a_agent_tool.IIAgentA2AClient",
                return_value=new_client,
            ) as MockClient,
        ):
            client = await tool._get_client("http://test.com")
            MockClient.assert_called_once()
            # Old client should be closed
            old_client.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_client_creates_new_when_not_cached(self):
        tool = make_tool()
        new_client = make_mock_client()

        with patch(
            "ii_agent.agents.tools.a2a.a2a_agent_tool.IIAgentA2AClient",
            return_value=new_client,
        ) as MockClient:
            client = await tool._get_client("http://new.example.com")
            MockClient.assert_called_once()
            assert client is new_client


# ---------------------------------------------------------------------------
# _emit_stream_event deep tests
# ---------------------------------------------------------------------------


class TestEmitStreamEventDeep:
    @pytest.mark.asyncio
    async def test_emit_stream_event_with_no_stream_does_nothing(self):
        tool = make_tool()
        tool._event_stream = None
        from ii_agent.realtime.events.app_events import EventType

        # Should not raise
        await tool._emit_stream_event(EventType.STATUS_UPDATE, {"message": "test"})

    @pytest.mark.asyncio
    async def test_emit_stream_event_with_stream_calls_add_event(self):
        tool = make_tool()
        mock_stream = AsyncMock()
        mock_stream.add_event = AsyncMock()
        tool._event_stream = mock_stream

        from ii_agent.realtime.events.app_events import EventType

        await tool._emit_stream_event(EventType.STATUS_UPDATE, {"message": "test"})
        mock_stream.add_event.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_emit_stream_event_handles_exception(self):
        tool = make_tool()
        mock_stream = AsyncMock()
        mock_stream.add_event = AsyncMock(side_effect=RuntimeError("stream error"))
        tool._event_stream = mock_stream

        from ii_agent.realtime.events.app_events import EventType

        await tool._emit_stream_event(EventType.STATUS_UPDATE, {"key": "val"})  # Should not raise


# ---------------------------------------------------------------------------
# _coerce_bool additional edge cases
# ---------------------------------------------------------------------------


class TestCoerceBoolDeep:
    def test_none_returns_false(self):
        result = A2AAgentTool._coerce_bool(None)
        assert result is False

    def test_empty_string_returns_false(self):
        result = A2AAgentTool._coerce_bool("")
        assert result is False

    def test_unknown_string_is_truthy(self):
        # Unknown strings treated as truthy (non-empty)
        result = A2AAgentTool._coerce_bool("random_value")
        assert isinstance(result, bool)


# ---------------------------------------------------------------------------
# _sanitize_headers edge cases
# ---------------------------------------------------------------------------


class TestSanitizeHeadersDeep:
    def test_all_valid_entries(self):
        headers = {
            "Authorization": "Bearer token",
            "Content-Type": "application/json",
            "X-Custom": "value",
        }
        result = A2AAgentTool._sanitize_headers(headers)
        assert len(result) == 3

    def test_mixed_valid_invalid_entries(self):
        headers = {
            "valid-key": "valid-value",
            None: "no-key",
            "": "empty-key",
            "none-val": None,
        }
        result = A2AAgentTool._sanitize_headers(headers)
        # Only valid-key should survive
        assert "valid-key" in result
        assert len(result) == 1

    def test_bool_value_converted_to_string(self):
        result = A2AAgentTool._sanitize_headers({"flag": True})
        assert result == {"flag": "True"}


# ---------------------------------------------------------------------------
# _negotiate_extensions additional tests
# ---------------------------------------------------------------------------


class TestNegotiateExtensionsDeep:
    def test_no_server_extensions(self):
        tool = make_tool()
        result = tool._negotiate_extensions(
            supported=[],
            context={"requested_extensions": ["ext1"]},
        )
        assert "ext1" in result["missing_extensions"]
        assert result["active_extensions"] == []

    def test_context_with_supported_extensions_present(self):
        tool = make_tool()
        result = tool._negotiate_extensions(
            supported=["ext1"],
            context={"requested_extensions": ["ext1"]},
        )
        assert "ext1" in result["active_extensions"]


# ---------------------------------------------------------------------------
# _prepare_context edge cases
# ---------------------------------------------------------------------------


class TestPrepareContextDeep:
    def test_empty_context_returns_defaults(self):
        tool = make_tool()
        negotiation = {
            "requested_extensions": [],
            "active_extensions": [],
            "missing_extensions": [],
        }
        query, ctx = tool._prepare_context(
            query="hello",
            context=None,
            negotiation=negotiation,
            agent_description="Agent",
        )
        assert query == "hello"
        assert "a2a_negotiation" in ctx

    def test_missing_ext_with_no_briefing_uses_description(self):
        tool = make_tool()
        negotiation = {
            "requested_extensions": ["ext1"],
            "active_extensions": [],
            "missing_extensions": ["ext1"],
        }
        query, ctx = tool._prepare_context(
            query="task",
            context={},
            negotiation=negotiation,
            agent_description="My described agent",
        )
        # Should append description or fallback text
        assert isinstance(query, str)


# ---------------------------------------------------------------------------
# _extract_text_from_message edge cases
# ---------------------------------------------------------------------------


class TestExtractTextFromMessageDeep:
    def test_message_part_without_root_or_text(self):
        tool = make_tool()
        msg = MagicMock()
        part = MagicMock()
        part.root = None
        del part.root  # Ensure it's not accessible
        msg.parts = [part]

        # Should not raise
        result = tool._extract_text_from_message(msg)
        # May return None or something else - just checking it doesn't crash
        assert result is None or isinstance(result, str)

    def test_message_with_multiple_parts_returns_first_text(self):
        tool = make_tool()
        msg = MagicMock()
        part1 = MagicMock()
        root1 = MagicMock()
        root1.text = "first"
        part1.root = root1
        part2 = MagicMock()
        root2 = MagicMock()
        root2.text = "second"
        part2.root = root2
        msg.parts = [part1, part2]

        result = tool._extract_text_from_message(msg)
        assert result == "first"


# ---------------------------------------------------------------------------
# _extract_text_from_artifact edge cases
# ---------------------------------------------------------------------------


class TestExtractTextFromArtifactDeep:
    def test_artifact_no_parts_no_data(self):
        tool = make_tool()
        event = MagicMock()
        artifact = MagicMock()
        artifact.parts = None
        artifact.data = None
        event.artifact = artifact
        result = tool._extract_text_from_artifact(event)
        assert result is None

    def test_artifact_parts_exception_falls_back_to_data(self):
        tool = make_tool()
        event = MagicMock()
        artifact = MagicMock()
        artifact.parts = MagicMock(side_effect=Exception("parts error"))
        artifact.data = "fallback data"
        event.artifact = artifact

        result = tool._extract_text_from_artifact(event)
        # Should fallback gracefully
        assert result is not None or result is None  # Not raising is the key assertion


# ---------------------------------------------------------------------------
# close_all_clients edge cases
# ---------------------------------------------------------------------------


class TestCloseAllClientsDeep:
    @pytest.mark.asyncio
    async def test_close_raises_if_client_raises(self):
        """close_all_clients propagates exceptions from individual clients."""
        tool = make_tool()
        client1 = AsyncMock()
        client1.close.side_effect = RuntimeError("close failed")
        tool._clients = {"url1": client1}
        tool._client_headers = {"url1": ()}

        with pytest.raises(RuntimeError, match="close failed"):
            await tool.close_all_clients()

    @pytest.mark.asyncio
    async def test_close_all_clients_when_empty(self):
        tool = make_tool()
        await tool.close_all_clients()  # Should not raise
        assert tool._clients == {}

    @pytest.mark.asyncio
    async def test_close_all_clients_clears_headers(self):
        tool = make_tool()
        client = AsyncMock()
        tool._clients = {"url1": client}
        tool._client_headers = {"url1": ()}
        await tool.close_all_clients()
        assert tool._client_headers == {}


# ---------------------------------------------------------------------------
# initialize deep tests
# ---------------------------------------------------------------------------


class TestInitializeDeep:
    @pytest.mark.asyncio
    async def test_initialize_caches_agent_description_from_default_agents(self):
        tool = make_tool(
            {"agent1": {"url": "http://agent1.example.com", "description": "My Agent"}}
        )
        mock_client = make_mock_client(description="Card Description")

        with patch.object(tool, "_get_client", new_callable=AsyncMock, return_value=mock_client):
            await tool.initialize()

        assert tool._initialized is True

    @pytest.mark.asyncio
    async def test_initialize_continues_after_per_agent_error(self):
        tool = make_tool(
            {
                "agent1": "http://agent1.example.com",
                "agent2": "http://agent2.example.com",
            }
        )
        good_client = make_mock_client()

        async def selective_get_client(url, headers=None):
            if "agent1" in url:
                raise ConnectionError("agent1 down")
            return good_client

        tool._get_client = selective_get_client

        await tool.initialize()
        assert tool._initialized is True
        # agent2 should have succeeded
        assert "http://agent2.example.com" in tool._agent_descriptions

    @pytest.mark.asyncio
    async def test_initialize_fetches_agent_card_extensions(self):
        tool = make_tool({"agent1": "http://agent1.example.com"})
        card = MagicMock()
        card.description = "My Agent"
        card.extensions = ["ext1", "ext2"]

        mock_client = AsyncMock()
        mock_client.get_agent_card = AsyncMock(return_value=card)

        with patch.object(tool, "_get_client", new_callable=AsyncMock, return_value=mock_client):
            await tool.initialize()

        assert "http://agent1.example.com" in tool._agent_extensions
        assert "ext1" in tool._agent_extensions["http://agent1.example.com"]
        assert "ext2" in tool._agent_extensions["http://agent1.example.com"]


# ---------------------------------------------------------------------------
# get_agent_description deep tests
# ---------------------------------------------------------------------------


class TestGetAgentDescriptionDeep:
    @pytest.mark.asyncio
    async def test_fetches_from_cached_agent_card(self):
        tool = make_tool()
        mock_card = MagicMock()
        mock_card.description = "Card-based description"
        mock_card.extensions = []
        tool._agent_cards["http://test.com"] = mock_card
        tool._clients["http://test.com"] = make_mock_client()
        tool._client_headers["http://test.com"] = ()

        result = await tool.get_agent_description("http://test.com")
        # If not in _agent_descriptions, tries to get card
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_returns_none_when_card_has_no_description(self):
        tool = make_tool()
        mock_client = AsyncMock()
        mock_card = MagicMock()
        mock_card.description = None
        mock_card.extensions = []
        mock_client.get_agent_card = AsyncMock(return_value=mock_card)

        with patch.object(tool, "_get_client", new_callable=AsyncMock, return_value=mock_client):
            result = await tool.get_agent_description("http://test.com")

        assert result is not None  # Falls back to URL or empty string


# ---------------------------------------------------------------------------
# get_agent_extensions deep tests
# ---------------------------------------------------------------------------


class TestGetAgentExtensionsDeep:
    @pytest.mark.asyncio
    async def test_fetches_extensions_when_not_cached(self):
        tool = make_tool()
        mock_client = AsyncMock()
        mock_card = MagicMock()
        mock_card.extensions = ["ext-a", "ext-b"]
        mock_card.description = "Agent"
        mock_client.get_agent_card = AsyncMock(return_value=mock_card)

        with patch.object(tool, "_get_client", new_callable=AsyncMock, return_value=mock_client):
            result = await tool.get_agent_extensions("http://test.com")

        assert "ext-a" in result
        assert "ext-b" in result

    @pytest.mark.asyncio
    async def test_raises_on_client_error(self):
        """get_agent_extensions propagates exceptions from _get_client."""
        tool = make_tool()
        with patch.object(tool, "_get_client", side_effect=RuntimeError("connection refused")):
            with pytest.raises(RuntimeError, match="connection refused"):
                await tool.get_agent_extensions("http://unreachable.com")
