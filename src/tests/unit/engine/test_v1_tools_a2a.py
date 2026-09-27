"""Unit tests for A2A Agent Tool."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ii_agent.agents.tools.a2a.a2a_agent_tool import A2AAgentTool


# ---------------------------------------------------------------------------
# Fixtures
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
# __init__ tests
# ---------------------------------------------------------------------------


class TestA2AAgentToolInit:
    def test_init_no_agents(self):
        tool = make_tool()
        assert tool.default_agents == {}
        assert tool._clients == {}
        assert tool._initialized is False
        assert tool._event_stream is None

    def test_init_with_string_url_agents(self):
        tool = make_tool({"agent1": "http://agent1.example.com"})
        assert "agent1" in tool.default_agents
        assert tool.default_agents["agent1"]["url"] == "http://agent1.example.com"
        assert tool.default_agents["agent1"]["name"] == "agent1"

    def test_init_with_dict_config_agents(self):
        tool = make_tool(
            {
                "agent1": {
                    "url": "http://agent1.example.com",
                    "name": "Agent One",
                    "description": "Test agent",
                }
            }
        )
        assert tool.default_agents["agent1"]["url"] == "http://agent1.example.com"
        assert tool.default_agents["agent1"]["name"] == "Agent One"
        assert tool.default_agents["agent1"]["description"] == "Test agent"

    def test_init_skips_empty_url_string(self):
        tool = make_tool({"bad_agent": ""})
        assert "bad_agent" not in tool.default_agents

    def test_init_skips_dict_missing_url(self):
        tool = make_tool({"bad_agent": {"name": "no url"}})
        assert "bad_agent" not in tool.default_agents

    def test_init_skips_unsupported_type(self):
        tool = make_tool({"bad_agent": 12345})
        assert "bad_agent" not in tool.default_agents

    def test_class_attributes(self):
        tool = make_tool()
        assert tool.name == "a2a_agent"
        assert tool.display_name == "A2A Agent"
        assert tool.read_only is True
        assert "agent_url" in tool.input_schema["properties"]
        assert "query" in tool.input_schema["properties"]

    def test_init_with_headers_in_dict_config(self):
        tool = make_tool(
            {
                "agent1": {
                    "url": "http://agent1.example.com",
                    "headers": {"Authorization": "Bearer token"},
                }
            }
        )
        assert "headers" in tool.default_agents["agent1"]
        assert tool.default_agents["agent1"]["headers"]["Authorization"] == "Bearer token"

    def test_init_with_metadata_in_dict_config(self):
        tool = make_tool(
            {
                "agent1": {
                    "url": "http://agent1.example.com",
                    "metadata": {"timeout_seconds": 30},
                }
            }
        )
        assert tool.default_agents["agent1"]["metadata"]["timeout_seconds"] == 30


# ---------------------------------------------------------------------------
# _normalize_agent_config tests
# ---------------------------------------------------------------------------


class TestNormalizeAgentConfig:
    def test_string_url_returns_normalized(self):
        result = A2AAgentTool._normalize_agent_config("agent1", "http://example.com")
        assert result == {"url": "http://example.com", "name": "agent1"}

    def test_empty_string_returns_none(self):
        result = A2AAgentTool._normalize_agent_config("agent1", "  ")
        assert result is None

    def test_dict_with_url_returns_normalized(self):
        result = A2AAgentTool._normalize_agent_config("agent1", {"url": "http://example.com"})
        assert result["url"] == "http://example.com"
        assert result["name"] == "agent1"

    def test_dict_with_custom_name_preserves_name(self):
        result = A2AAgentTool._normalize_agent_config(
            "agent1", {"url": "http://example.com", "name": "Custom"}
        )
        assert result["name"] == "Custom"

    def test_dict_with_description_includes_it(self):
        result = A2AAgentTool._normalize_agent_config(
            "agent1", {"url": "http://example.com", "description": "My desc"}
        )
        assert result["description"] == "My desc"

    def test_dict_without_url_returns_none(self):
        result = A2AAgentTool._normalize_agent_config("agent1", {"name": "no url"})
        assert result is None

    def test_invalid_type_returns_none(self):
        result = A2AAgentTool._normalize_agent_config("agent1", 42)
        assert result is None

    def test_dict_with_bad_headers_type_ignores_headers(self):
        result = A2AAgentTool._normalize_agent_config(
            "agent1", {"url": "http://example.com", "headers": "not-a-dict"}
        )
        assert "headers" not in result

    def test_dict_with_valid_headers_sanitized(self):
        result = A2AAgentTool._normalize_agent_config(
            "agent1", {"url": "http://example.com", "headers": {"X-Token": "abc"}}
        )
        assert result["headers"] == {"X-Token": "abc"}


# ---------------------------------------------------------------------------
# _sanitize_headers tests
# ---------------------------------------------------------------------------


class TestSanitizeHeaders:
    def test_non_dict_returns_empty(self):
        assert A2AAgentTool._sanitize_headers("not-a-dict") == {}
        assert A2AAgentTool._sanitize_headers(None) == {}
        assert A2AAgentTool._sanitize_headers([]) == {}

    def test_valid_dict_sanitized(self):
        result = A2AAgentTool._sanitize_headers({"Authorization": "Bearer tok"})
        assert result == {"Authorization": "Bearer tok"}

    def test_none_key_skipped(self):
        result = A2AAgentTool._sanitize_headers({None: "value"})
        assert result == {}

    def test_empty_key_skipped(self):
        result = A2AAgentTool._sanitize_headers({"   ": "value"})
        assert result == {}

    def test_none_value_skipped(self):
        result = A2AAgentTool._sanitize_headers({"key": None})
        assert result == {}

    def test_numeric_values_converted_to_string(self):
        result = A2AAgentTool._sanitize_headers({"key": 123})
        assert result == {"key": "123"}


# ---------------------------------------------------------------------------
# _canonicalize_headers tests
# ---------------------------------------------------------------------------


class TestCanonicalizeHeaders:
    def test_empty_returns_empty_tuple(self):
        assert A2AAgentTool._canonicalize_headers({}) == ()

    def test_headers_sorted_by_lowercase_key(self):
        result = A2AAgentTool._canonicalize_headers({"Z-Header": "z", "A-Header": "a"})
        assert result[0][0] == "a-header"
        assert result[1][0] == "z-header"

    def test_single_header_canonicalized(self):
        result = A2AAgentTool._canonicalize_headers({"Authorization": "Bearer tok"})
        assert result == (("authorization", "Bearer tok"),)


# ---------------------------------------------------------------------------
# _coerce_bool tests
# ---------------------------------------------------------------------------


class TestCoerceBool:
    def test_bool_true(self):
        assert A2AAgentTool._coerce_bool(True) is True

    def test_bool_false(self):
        assert A2AAgentTool._coerce_bool(False) is False

    def test_string_true_variants(self):
        for v in ["true", "1", "yes", "on", "TRUE", "YES"]:
            assert A2AAgentTool._coerce_bool(v) is True

    def test_string_false_variants(self):
        for v in ["false", "0", "no", "off", "FALSE", "OFF"]:
            assert A2AAgentTool._coerce_bool(v) is False

    def test_integer_nonzero_is_true(self):
        assert A2AAgentTool._coerce_bool(42) is True

    def test_integer_zero_is_false(self):
        assert A2AAgentTool._coerce_bool(0) is False


# ---------------------------------------------------------------------------
# _coerce_timeout tests
# ---------------------------------------------------------------------------


class TestCoerceTimeout:
    def test_none_returns_none(self):
        assert A2AAgentTool._coerce_timeout(None) is None

    def test_int_returns_float(self):
        result = A2AAgentTool._coerce_timeout(30)
        assert result == 30.0

    def test_float_returns_float(self):
        result = A2AAgentTool._coerce_timeout(3.5)
        assert result == 3.5

    def test_string_seconds_suffix(self):
        result = A2AAgentTool._coerce_timeout("30s")
        assert result == 30.0

    def test_string_milliseconds_suffix(self):
        result = A2AAgentTool._coerce_timeout("500ms")
        assert abs(result - 0.5) < 0.0001

    def test_string_no_suffix(self):
        result = A2AAgentTool._coerce_timeout("10")
        assert result == 10.0

    def test_invalid_string_returns_none(self):
        result = A2AAgentTool._coerce_timeout("not-a-number")
        assert result is None

    def test_unsupported_type_returns_none(self):
        result = A2AAgentTool._coerce_timeout([1, 2, 3])
        assert result is None


# ---------------------------------------------------------------------------
# _negotiate_extensions tests
# ---------------------------------------------------------------------------


class TestNegotiateExtensions:
    def test_no_requested_extensions(self):
        tool = make_tool()
        result = tool._negotiate_extensions(["ext1", "ext2"], {})
        assert result["requested_extensions"] == []
        assert result["active_extensions"] == []
        assert result["missing_extensions"] == []

    def test_all_extensions_supported(self):
        tool = make_tool()
        result = tool._negotiate_extensions(
            ["ext1", "ext2"],
            {"requested_extensions": ["ext1", "ext2"]},
        )
        assert set(result["active_extensions"]) == {"ext1", "ext2"}
        assert result["missing_extensions"] == []

    def test_some_extensions_missing(self):
        tool = make_tool()
        result = tool._negotiate_extensions(
            ["ext1"],
            {"requested_extensions": ["ext1", "ext2"]},
        )
        assert "ext1" in result["active_extensions"]
        assert "ext2" in result["missing_extensions"]

    def test_none_context_treated_as_empty(self):
        tool = make_tool()
        result = tool._negotiate_extensions(["ext1"], None)
        assert result["requested_extensions"] == []


# ---------------------------------------------------------------------------
# _prepare_context tests
# ---------------------------------------------------------------------------


class TestPrepareContext:
    def test_no_missing_extensions_context_unchanged(self):
        tool = make_tool()
        negotiation = {
            "requested_extensions": [],
            "active_extensions": [],
            "missing_extensions": [],
        }
        query, ctx = tool._prepare_context(
            query="hello",
            context={"key": "value"},
            negotiation=negotiation,
            agent_description="My Agent",
        )
        assert query == "hello"
        assert "a2a_negotiation" in ctx

    def test_missing_extensions_appends_fallback_to_query(self):
        tool = make_tool()
        negotiation = {
            "requested_extensions": ["ext1"],
            "active_extensions": [],
            "missing_extensions": ["ext1"],
        }
        query, ctx = tool._prepare_context(
            query="base query",
            context={"fallback_briefing": "fallback info"},
            negotiation=negotiation,
            agent_description="My Agent",
        )
        assert "fallback info" in query
        assert "Fallback Context" in query

    def test_missing_extensions_uses_briefing_when_no_fallback_briefing(self):
        tool = make_tool()
        negotiation = {
            "requested_extensions": ["ext1"],
            "active_extensions": [],
            "missing_extensions": ["ext1"],
        }
        query, ctx = tool._prepare_context(
            query="base query",
            context={"briefing": "briefing text"},
            negotiation=negotiation,
            agent_description="My Agent",
        )
        assert "briefing text" in query


# ---------------------------------------------------------------------------
# _find_agent_defaults_by_url tests
# ---------------------------------------------------------------------------


class TestFindAgentDefaultsByUrl:
    def test_returns_agent_defaults_when_url_matches(self):
        tool = make_tool({"agent1": "http://agent1.example.com"})
        result = tool._find_agent_defaults_by_url("http://agent1.example.com")
        assert result is not None
        assert result["url"] == "http://agent1.example.com"

    def test_returns_none_when_url_not_found(self):
        tool = make_tool({"agent1": "http://agent1.example.com"})
        result = tool._find_agent_defaults_by_url("http://other.example.com")
        assert result is None


# ---------------------------------------------------------------------------
# _resolve_timeout_seconds tests
# ---------------------------------------------------------------------------


class TestResolveTimeoutSeconds:
    def test_no_agent_defaults_returns_none(self):
        tool = make_tool()
        result = tool._resolve_timeout_seconds("http://unknown.example.com")
        assert result is None

    def test_metadata_with_timeout_seconds(self):
        tool = make_tool(
            {
                "agent1": {
                    "url": "http://agent1.example.com",
                    "metadata": {"timeout_seconds": 60},
                }
            }
        )
        result = tool._resolve_timeout_seconds("http://agent1.example.com")
        assert result == 60.0

    def test_metadata_with_timeout_key(self):
        tool = make_tool(
            {
                "agent1": {
                    "url": "http://agent1.example.com",
                    "metadata": {"timeout": "120s"},
                }
            }
        )
        result = tool._resolve_timeout_seconds("http://agent1.example.com")
        assert result == 120.0

    def test_no_metadata_returns_none(self):
        tool = make_tool({"agent1": "http://agent1.example.com"})
        result = tool._resolve_timeout_seconds("http://agent1.example.com")
        assert result is None

    def test_zero_timeout_returns_none(self):
        tool = make_tool(
            {
                "agent1": {
                    "url": "http://agent1.example.com",
                    "metadata": {"timeout_seconds": 0},
                }
            }
        )
        result = tool._resolve_timeout_seconds("http://agent1.example.com")
        assert result is None


# ---------------------------------------------------------------------------
# set_event_stream tests
# ---------------------------------------------------------------------------


class TestSetEventStream:
    def test_sets_event_stream(self):
        tool = make_tool()
        mock_stream = MagicMock()
        tool.set_event_stream(mock_stream)
        assert tool._event_stream is mock_stream

    def test_can_set_to_none(self):
        tool = make_tool()
        tool._event_stream = MagicMock()
        tool.set_event_stream(None)
        assert tool._event_stream is None


# ---------------------------------------------------------------------------
# _map_task_state tests
# ---------------------------------------------------------------------------


class TestMapTaskState:
    def test_working_state_maps_to_processing(self):
        from a2a.types import TaskState
        from ii_agent.realtime.events.app_events import EventType

        tool = make_tool()
        result = tool._map_task_state(TaskState.working)
        assert result == EventType.PROCESSING

    def test_other_state_maps_to_status_update(self):
        from a2a.types import TaskState
        from ii_agent.realtime.events.app_events import EventType

        tool = make_tool()
        result = tool._map_task_state(TaskState.completed)
        assert result == EventType.STATUS_UPDATE


# ---------------------------------------------------------------------------
# _extract_text_from_message tests
# ---------------------------------------------------------------------------


class TestExtractTextFromMessage:
    def test_none_message_returns_none(self):
        tool = make_tool()
        result = tool._extract_text_from_message(None)
        assert result is None

    def test_message_with_root_text_part(self):
        tool = make_tool()
        msg = MagicMock()
        part = MagicMock()
        root = MagicMock()
        root.text = "hello"
        part.root = root
        msg.parts = [part]
        result = tool._extract_text_from_message(msg)
        assert result == "hello"

    def test_message_with_dict_text_part(self):
        tool = make_tool()
        msg = MagicMock()
        msg.parts = [{"text": "dict text"}]
        result = tool._extract_text_from_message(msg)
        assert result == "dict text"

    def test_message_with_no_parts_returns_none(self):
        tool = make_tool()
        msg = MagicMock()
        msg.parts = []
        result = tool._extract_text_from_message(msg)
        assert result is None


# ---------------------------------------------------------------------------
# _extract_text_from_artifact tests
# ---------------------------------------------------------------------------


class TestExtractTextFromArtifact:
    def test_no_artifact_returns_none(self):
        tool = make_tool()
        event = MagicMock()
        event.artifact = None
        result = tool._extract_text_from_artifact(event)
        assert result is None

    def test_artifact_with_text_part(self):
        tool = make_tool()
        event = MagicMock()
        artifact = MagicMock()
        part = MagicMock()
        root = MagicMock()
        root.text = "artifact text"
        part.root = root
        artifact.parts = [part]
        artifact.data = None
        event.artifact = artifact
        result = tool._extract_text_from_artifact(event)
        assert result == "artifact text"

    def test_artifact_with_data_fallback(self):
        tool = make_tool()
        event = MagicMock()
        artifact = MagicMock()
        artifact.parts = None
        artifact.data = "data content"
        event.artifact = artifact
        result = tool._extract_text_from_artifact(event)
        assert result == "data content"

    def test_artifact_dict_part_with_text(self):
        tool = make_tool()
        event = MagicMock()
        artifact = MagicMock()
        artifact.parts = [{"text": "dict part text"}]
        artifact.data = None
        event.artifact = artifact
        result = tool._extract_text_from_artifact(event)
        assert result == "dict part text"


# ---------------------------------------------------------------------------
# get_agent_description tests
# ---------------------------------------------------------------------------


class TestGetAgentDescription:
    @pytest.mark.asyncio
    async def test_returns_cached_description(self):
        tool = make_tool()
        tool._agent_descriptions["http://test.com"] = "Cached Description"
        result = await tool.get_agent_description("http://test.com")
        assert result == "Cached Description"

    @pytest.mark.asyncio
    async def test_returns_description_from_default_agents(self):
        tool = make_tool({"agent1": {"url": "http://test.com", "description": "Default Desc"}})
        result = await tool.get_agent_description("http://test.com")
        assert result == "Default Desc"

    @pytest.mark.asyncio
    async def test_fallback_description_on_client_error(self):
        tool = make_tool()

        async def mock_get_client(url):
            raise RuntimeError("connection failed")

        tool._get_client = mock_get_client
        result = await tool.get_agent_description("http://unreachable.com")
        assert "http://unreachable.com" in result


# ---------------------------------------------------------------------------
# get_agent_extensions tests
# ---------------------------------------------------------------------------


class TestGetAgentExtensions:
    @pytest.mark.asyncio
    async def test_returns_cached_extensions(self):
        tool = make_tool()
        tool._agent_extensions["http://test.com"] = {"ext1", "ext2"}
        result = await tool.get_agent_extensions("http://test.com")
        assert sorted(result) == ["ext1", "ext2"]

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_extensions(self):
        tool = make_tool()
        mock_client = make_mock_client(extensions=[])
        tool._clients["http://test.com"] = mock_client
        tool._agent_cards["http://test.com"] = MagicMock(extensions=[])
        tool._agent_extensions["http://test.com"] = set()
        result = await tool.get_agent_extensions("http://test.com")
        assert result == []


# ---------------------------------------------------------------------------
# close_all_clients tests
# ---------------------------------------------------------------------------


class TestCloseAllClients:
    @pytest.mark.asyncio
    async def test_closes_all_clients(self):
        tool = make_tool()
        client1 = AsyncMock()
        client2 = AsyncMock()
        tool._clients = {"url1": client1, "url2": client2}
        tool._client_headers = {"url1": (), "url2": ()}

        await tool.close_all_clients()

        client1.close.assert_awaited_once()
        client2.close.assert_awaited_once()
        assert tool._clients == {}
        assert tool._client_headers == {}


# ---------------------------------------------------------------------------
# execute tests (high-level integration of methods)
# ---------------------------------------------------------------------------


class TestExecute:
    @pytest.mark.asyncio
    async def test_execute_missing_agent_url_returns_error(self):
        tool = make_tool()
        tool._initialized = True
        result = await tool.execute({"query": "hello"})
        assert "Error" in result.llm_content

    @pytest.mark.asyncio
    async def test_execute_missing_query_returns_error(self):
        tool = make_tool()
        tool._initialized = True
        result = await tool.execute({"agent_url": "http://test.com"})
        assert "Error" in result.llm_content

    @pytest.mark.asyncio
    async def test_execute_successful_call(self):
        tool = make_tool({"agent1": "http://agent1.example.com"})
        tool._initialized = True

        mock_client = make_mock_client(description="Agent One")
        tool._clients["http://agent1.example.com"] = mock_client
        tool._agent_cards["http://agent1.example.com"] = MagicMock(
            description="Agent One", extensions=[]
        )
        tool._agent_descriptions["http://agent1.example.com"] = "Agent One"
        tool._agent_extensions["http://agent1.example.com"] = set()

        result = await tool.execute(
            {
                "agent_url": "agent1",
                "query": "do something",
            }
        )
        assert result.is_error is None or result.is_error is False
        assert "result text" in result.llm_content

    @pytest.mark.asyncio
    async def test_execute_uses_agent_name_as_identifier(self):
        tool = make_tool({"agent1": "http://agent1.example.com"})
        tool._initialized = True

        mock_client = make_mock_client()
        tool._clients["http://agent1.example.com"] = mock_client
        tool._agent_cards["http://agent1.example.com"] = MagicMock(description="A1", extensions=[])
        tool._agent_descriptions["http://agent1.example.com"] = "A1"
        tool._agent_extensions["http://agent1.example.com"] = set()

        result = await tool.execute({"agent_url": "agent1", "query": "task"})
        assert "result text" in result.llm_content

    @pytest.mark.asyncio
    async def test_execute_handles_exception_gracefully(self):
        tool = make_tool()
        tool._initialized = True
        tool._get_client = AsyncMock(side_effect=RuntimeError("boom"))
        result = await tool.execute({"agent_url": "http://test.com", "query": "hello"})
        assert "Error" in result.llm_content

    @pytest.mark.asyncio
    async def test_execute_initializes_if_not_initialized(self):
        tool = make_tool()
        tool._initialized = False

        with patch.object(tool, "initialize", new_callable=AsyncMock) as mock_init:
            mock_init.side_effect = lambda: setattr(tool, "_initialized", True) or None
            tool._get_client = AsyncMock(side_effect=RuntimeError("no url"))
            await tool.execute({"agent_url": "http://test.com", "query": "go"})
            mock_init.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_execute_failed_result_returns_error_content(self):
        tool = make_tool()
        tool._initialized = True

        mock_client = AsyncMock()
        mock_client.call_agent = AsyncMock(
            return_value={
                "success": False,
                "content": "error from agent",
                "user_display_content": "agent failed",
            }
        )
        mock_client.get_agent_card = AsyncMock(
            return_value=MagicMock(description="A", extensions=[])
        )

        tool._agent_cards["http://test.com"] = MagicMock(description="A", extensions=[])
        tool._agent_descriptions["http://test.com"] = "A"
        tool._agent_extensions["http://test.com"] = set()
        tool._clients["http://test.com"] = mock_client
        tool._client_headers["http://test.com"] = ()

        result = await tool.execute({"agent_url": "http://test.com", "query": "fail me"})
        assert result.llm_content == "error from agent"


# ---------------------------------------------------------------------------
# initialize tests
# ---------------------------------------------------------------------------


class TestInitialize:
    @pytest.mark.asyncio
    async def test_initialize_marks_initialized(self):
        tool = make_tool({"agent1": "http://agent1.example.com"})
        mock_client = make_mock_client()

        with patch.object(tool, "_get_client", new_callable=AsyncMock, return_value=mock_client):
            await tool.initialize()

        assert tool._initialized is True

    @pytest.mark.asyncio
    async def test_initialize_skips_if_already_initialized(self):
        tool = make_tool({"agent1": "http://agent1.example.com"})
        tool._initialized = True

        with patch.object(tool, "_get_client", new_callable=AsyncMock) as mock_get:
            await tool.initialize()
            mock_get.assert_not_called()

    @pytest.mark.asyncio
    async def test_initialize_handles_connection_error_gracefully(self):
        tool = make_tool({"agent1": "http://agent1.example.com"})

        with patch.object(tool, "_get_client", side_effect=RuntimeError("connection refused")):
            await tool.initialize()

        assert tool._initialized is True
        assert "http://agent1.example.com" in tool._agent_descriptions
