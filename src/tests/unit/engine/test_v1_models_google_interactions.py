"""
Unit tests for src/ii_agent/agent/runtime/models/google/interactions.py

Tests cover:
- GeminiInteractions dataclass defaults and instantiation
- _normalize_function_definition utility (interactions version)
- format_function_definitions (interactions version – returns list)
- format_image_for_message (interactions version)
- prepare_response_schema
- GeminiInteractions.get_request_params()
- GeminiInteractions._format_messages() – all role branches
- GeminiInteractions.format_function_call_results()
- GeminiInteractions._parse_provider_response() – text, function_call, thought, usage
- GeminiInteractions._parse_provider_response_delta() – all streaming events
- GeminiInteractions._get_metrics()
- GeminiInteractions.__deepcopy__()
- ainvoke error handling paths
- ainvoke happy path
"""

import copy
import json
from typing import List
from unittest.mock import AsyncMock, MagicMock

import pytest

pytest.skip("google.genai.interactions was removed during refactoring", allow_module_level=True)

from pydantic import BaseModel

from ii_agent.agents.models.google.interactions import (
    GeminiInteractions,
    _normalize_function_definition,
    format_function_definitions,
    format_image_for_message,
    prepare_response_schema,
)
from ii_agent.agents.models.message import Message, File
from ii_agent.agents.models.response import ModelResponse
from ii_agent.agents.exceptions import ModelProviderError
from ii_agent.files.media import Image
from ii_agent.settings.llm import Provider

# Import streaming event types – some may only exist as stubs injected by conftest.py.
# Use getattr() to avoid ImportError when the installed SDK lacks these names.
import google.genai.interactions as _gi_module

ContentStart = getattr(_gi_module, "ContentStart", type("ContentStart", (), {}))
ContentDelta = getattr(_gi_module, "ContentDelta", type("ContentDelta", (), {}))
ContentStop = getattr(_gi_module, "ContentStop", type("ContentStop", (), {}))
InteractionUsage = getattr(_gi_module, "Usage", type("Usage", (), {}))
Interaction = getattr(_gi_module, "Interaction", type("Interaction", (), {}))
InteractionStartEvent = getattr(
    _gi_module, "InteractionStartEvent", type("InteractionStartEvent", (), {})
)
InteractionCompleteEvent = getattr(
    _gi_module, "InteractionCompleteEvent", type("InteractionCompleteEvent", (), {})
)
InteractionEvent = getattr(
    _gi_module, "InteractionEvent", (InteractionStartEvent, InteractionCompleteEvent)
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_gi(**kwargs) -> GeminiInteractions:
    gi = GeminiInteractions(**kwargs)
    mock_client = MagicMock()
    mock_client.aio = MagicMock()
    mock_client.aio.interactions = MagicMock()
    gi.client = mock_client
    return gi


def _make_interaction(id_="int_001", role="model", outputs=None, usage=None):
    interaction = MagicMock(spec=Interaction)
    interaction.id = id_
    interaction.role = role
    interaction.outputs = outputs or []
    interaction.usage = usage
    return interaction


def _make_text_output(text="Hello"):
    out = MagicMock()
    out.type = "text"
    out.text = text
    out.annotations = None
    return out


def _make_thought_output(signature="sig_abc", summary="I thought"):
    out = MagicMock()
    out.type = "thought"
    out.signature = signature
    out.summary = summary
    return out


def _make_function_call_output(name="search", call_id="call_1", args=None):
    out = MagicMock()
    out.type = "function_call"
    out.id = call_id
    out.name = name
    out.arguments = args or {"query": "test"}
    return out


def _make_usage(input_t=10, output_t=20, total_t=30, cached_t=0, thought_t=5):
    u = MagicMock(spec=InteractionUsage)
    u.total_input_tokens = input_t
    u.total_output_tokens = output_t
    u.total_tokens = total_t
    u.total_cached_tokens = cached_t
    u.total_thought_tokens = thought_t
    u.model_dump = MagicMock(return_value={"total_input_tokens": input_t})
    return u


# ---------------------------------------------------------------------------
# 1. GeminiInteractions defaults
# ---------------------------------------------------------------------------


class TestGeminiInteractionsDefaults:
    def test_default_id(self):
        assert GeminiInteractions().id == "gemini-3-flash-preview"

    def test_default_name(self):
        assert GeminiInteractions().name == "GeminiInteractions"

    def test_default_provider(self):
        assert GeminiInteractions().provider == Provider.GOOGLE

    def test_default_search_false(self):
        assert GeminiInteractions().search is False

    def test_default_grounding_false(self):
        assert GeminiInteractions().grounding is False

    def test_default_vertexai_false(self):
        assert GeminiInteractions().vertexai is False

    def test_default_supports_native_structured_outputs(self):
        assert GeminiInteractions().supports_native_structured_outputs is True

    def test_custom_id(self):
        assert GeminiInteractions(id="gemini-ultra-preview").id == "gemini-ultra-preview"

    def test_custom_temperature(self):
        assert GeminiInteractions(temperature=0.3).temperature == 0.3

    def test_client_starts_none(self):
        assert GeminiInteractions().client is None

    def test_role_map_model_to_assistant(self):
        assert GeminiInteractions().role_map["model"] == "assistant"

    def test_reverse_role_map_assistant(self):
        assert GeminiInteractions().reverse_role_map["assistant"] == "model"

    def test_reverse_role_map_tool(self):
        assert GeminiInteractions().reverse_role_map["tool"] == "user"


# ---------------------------------------------------------------------------
# 2. _normalize_function_definition
# ---------------------------------------------------------------------------


class TestInteractionsNormalizeFunctionDefinition:
    def test_none_returns_none(self):
        assert _normalize_function_definition(None) is None

    def test_dict_with_function_key(self):
        tool = {"type": "function", "function": {"name": "fn", "description": "d"}}
        assert _normalize_function_definition(tool) == {"name": "fn", "description": "d"}

    def test_plain_dict_returned(self):
        assert _normalize_function_definition({"name": "plain"}) == {"name": "plain"}

    def test_object_with_to_dict(self):
        obj = MagicMock()
        obj.to_dict.return_value = {"name": "from_to_dict"}
        del obj.model_dump
        assert _normalize_function_definition(obj) == {"name": "from_to_dict"}

    def test_object_with_model_dump(self):
        obj = MagicMock(spec=[])
        obj.model_dump = MagicMock(return_value={"name": "from_model_dump"})
        assert _normalize_function_definition(obj) == {"name": "from_model_dump"}

    def test_unrecognised_returns_none(self):
        assert _normalize_function_definition(object()) is None


# ---------------------------------------------------------------------------
# 3. format_function_definitions (interactions version)
# ---------------------------------------------------------------------------


class TestInteractionsFormatFunctionDefinitions:
    def test_empty_list_returns_empty_list(self):
        assert format_function_definitions([]) == []

    def test_none_returns_empty_list(self):
        assert format_function_definitions(None) == []

    def test_valid_tool_produces_declaration(self):
        tool = {"type": "function", "function": {"name": "search", "description": "Search"}}
        result = format_function_definitions([tool])
        assert len(result) == 1
        assert result[0]["name"] == "search"

    def test_tool_without_name_skipped(self):
        tool = {"type": "function", "function": {"description": "no name"}}
        result = format_function_definitions([tool])
        assert result == []

    def test_multiple_tools(self):
        tools = [
            {"type": "function", "function": {"name": "fn_a", "description": "A"}},
            {"type": "function", "function": {"name": "fn_b", "description": "B"}},
        ]
        result = format_function_definitions(tools)
        names = [d["name"] for d in result]
        assert "fn_a" in names
        assert "fn_b" in names

    def test_tool_has_type_field(self):
        tools = [{"type": "function", "function": {"name": "my_fn", "description": "desc"}}]
        result = format_function_definitions(tools)
        assert result[0]["type"] == "function"


# ---------------------------------------------------------------------------
# 4. format_image_for_message (interactions version)
# ---------------------------------------------------------------------------


class TestInteractionsFormatImageForMessage:
    def test_url_image_returns_uri_dict(self):
        img = MagicMock(spec=Image)
        img.url = "https://example.com/img.png"
        img.content = None
        img.mime_type = "image/png"
        result = format_image_for_message(img)
        assert result is not None
        assert result["uri"] == "https://example.com/img.png"
        assert result["type"] == "image"

    def test_bytes_image_returns_data_dict(self):
        img = MagicMock(spec=Image)
        img.url = None
        img.content = b"\x89PNG\r\n"
        img.mime_type = "image/png"
        result = format_image_for_message(img)
        assert result is not None
        assert "data" in result
        assert result["type"] == "image"

    def test_no_url_no_content_returns_none(self):
        img = MagicMock(spec=Image)
        img.url = None
        img.content = None
        img.mime_type = None
        result = format_image_for_message(img)
        assert result is None


# ---------------------------------------------------------------------------
# 5. prepare_response_schema
# ---------------------------------------------------------------------------


class TestInteractionsPrepareResponseSchema:
    def test_returns_json_schema(self):
        class Schema(BaseModel):
            field_a: str
            field_b: int

        schema = prepare_response_schema(Schema)
        assert "properties" in schema
        assert "field_a" in schema["properties"]


# ---------------------------------------------------------------------------
# 6. get_request_params
# ---------------------------------------------------------------------------


class TestGeminiInteractionsGetRequestParams:
    def test_temperature_in_generation_config(self):
        gi = _make_gi(temperature=0.7)
        params = gi.get_request_params()
        assert params["generation_config"]["temperature"] == 0.7

    def test_max_output_tokens_in_generation_config(self):
        gi = _make_gi(max_output_tokens=1024)
        params = gi.get_request_params()
        assert params["generation_config"]["max_output_tokens"] == 1024

    def test_seed_in_generation_config(self):
        gi = _make_gi(seed=7)
        params = gi.get_request_params()
        assert params["generation_config"]["seed"] == 7

    def test_top_p_in_generation_config(self):
        gi = _make_gi(top_p=0.9)
        params = gi.get_request_params()
        assert params["generation_config"]["top_p"] == 0.9

    def test_stop_sequences_in_generation_config(self):
        gi = _make_gi(stop_sequences=["END"])
        params = gi.get_request_params()
        assert params["generation_config"]["stop_sequences"] == ["END"]

    def test_thinking_level_in_generation_config(self):
        gi = _make_gi(thinking_level="low")
        params = gi.get_request_params()
        assert params["generation_config"]["thinking_level"] == "low"

    def test_timeout_set_directly(self):
        gi = _make_gi(timeout=45.0)
        params = gi.get_request_params()
        assert params["timeout"] == 45.0

    def test_request_params_merged(self):
        gi = _make_gi(request_params={"extra_key": "extra_val"})
        params = gi.get_request_params()
        assert params.get("extra_key") == "extra_val"

    def test_tool_choice_in_generation_config(self):
        gi = _make_gi()
        params = gi.get_request_params(tool_choice="required")
        assert params["generation_config"]["tool_choice"] == "required"

    def test_thinking_summaries_in_generation_config(self):
        gi = _make_gi(thinking_summaries="enabled")
        params = gi.get_request_params()
        assert params["generation_config"]["thinking_summaries"] == "enabled"


# ---------------------------------------------------------------------------
# 7. _format_messages
# ---------------------------------------------------------------------------


class TestGeminiInteractionsFormatMessages:
    def test_system_message_extracted(self):
        gi = _make_gi()
        msgs = [Message(role="system", content="Be helpful")]
        formatted, system = gi._format_messages(msgs)
        assert system == "Be helpful"
        assert formatted == []

    def test_developer_treated_as_system(self):
        gi = _make_gi()
        msgs = [Message(role="developer", content="Dev instructions")]
        formatted, system = gi._format_messages(msgs)
        assert system == "Dev instructions"

    def test_user_text_message(self):
        gi = _make_gi()
        msgs = [Message(role="user", content="Hello")]
        formatted, _ = gi._format_messages(msgs)
        assert len(formatted) == 1
        assert formatted[0]["role"] == "user"

    def test_assistant_message_mapped_to_model(self):
        # An assistant message with tool_calls maps role to "model".
        # Without tool_calls, the source skips assistant messages (no user-side parts).
        gi = _make_gi()
        tool_calls = [
            {
                "id": "tc_a",
                "type": "function",
                "function": {"name": "echo", "arguments": "{}"},
            }
        ]
        msgs = [Message(role="assistant", content="", tool_calls=tool_calls)]
        formatted, _ = gi._format_messages(msgs)
        assert any(m.get("role") == "model" for m in formatted)

    def test_assistant_with_tool_calls(self):
        gi = _make_gi()
        tool_calls = [
            {
                "id": "call_1",
                "type": "function",
                "function": {"name": "search_fn", "arguments": '{"query": "test"}'},
            }
        ]
        msgs = [Message(role="assistant", content="", tool_calls=tool_calls)]
        formatted, _ = gi._format_messages(msgs)
        func_call_msgs = [
            m
            for m in formatted
            if isinstance(m.get("content"), dict) and m["content"].get("type") == "function_call"
        ]
        assert len(func_call_msgs) >= 1

    def test_tool_result_single(self):
        gi = _make_gi()
        msgs = [
            Message(role="tool", content="the result", tool_name="my_tool", tool_call_id="tc_99")
        ]
        formatted, _ = gi._format_messages(msgs)
        assert len(formatted) == 1
        fn_results = formatted[0]["content"]
        assert fn_results[0]["type"] == "function_result"
        assert fn_results[0]["name"] == "my_tool"

    def test_tool_result_multiple(self):
        gi = _make_gi()
        tool_calls_data = [
            {"id": "tc_1", "tool_name": "fn_a"},
            {"id": "tc_2", "tool_name": "fn_b"},
        ]
        msgs = [Message(role="tool", content=["res_a", "res_b"], tool_calls=tool_calls_data)]
        formatted, _ = gi._format_messages(msgs)
        fn_results = formatted[0]["content"]
        assert len(fn_results) == 2

    def test_user_with_url_image(self):
        gi = _make_gi()
        img = MagicMock(spec=Image)
        img.url = "https://img.example.com/photo.png"
        img.content = None
        img.mime_type = "image/png"
        msgs = [Message(role="user", content="Look!", images=[img])]
        formatted, _ = gi._format_messages(msgs)
        parts = formatted[0]["content"]
        assert len(parts) >= 2

    def test_user_with_files(self):
        gi = _make_gi()
        from pathlib import Path

        file_obj = File(filepath=Path("/tmp/report.pdf"))
        msgs = [Message(role="user", content="See attached", files=[file_obj])]
        formatted, _ = gi._format_messages(msgs)
        parts = formatted[0]["content"]
        texts = [p["text"] for p in parts if p.get("type") == "text"]
        assert any("Attached files" in t for t in texts)

    def test_previous_interaction_id_filters_messages(self):
        gi = _make_gi()
        iid = "int_abc"
        msgs = [
            Message(role="user", content="Old message"),
            Message(
                role="assistant", content="Old response", provider_data={"interaction_id": iid}
            ),
            Message(role="user", content="New message"),
        ]
        formatted, _ = gi._format_messages(msgs, previous_interaction_id=iid)
        assert len(formatted) == 1

    def test_thought_signature_in_tool_call_message(self):
        gi = _make_gi()
        tool_calls = [
            {
                "id": "call_2",
                "type": "function",
                "function": {"name": "fn_y", "arguments": "{}"},
            }
        ]
        msgs = [
            Message(
                role="assistant",
                content="thinking text",
                tool_calls=tool_calls,
                reasoning_content="I am reasoning",
                provider_data={"thought_signature": "sig_xyz"},
            )
        ]
        formatted, _ = gi._format_messages(msgs)
        thought_msgs = [
            m
            for m in formatted
            if isinstance(m.get("content"), dict) and m["content"].get("type") == "thought"
        ]
        assert len(thought_msgs) >= 1


# ---------------------------------------------------------------------------
# 8. format_function_call_results
# ---------------------------------------------------------------------------


class TestGeminiInteractionsFormatFunctionCallResults:
    def test_appends_user_message(self):
        gi = _make_gi()
        messages: List[Message] = []
        results = [Message(role="tool", content="result", tool_name="fn_a", tool_call_id="tc_1")]
        gi.format_function_call_results(messages, results)
        assert len(messages) == 1
        assert messages[0].role == "user"

    def test_content_is_list_of_results(self):
        gi = _make_gi()
        messages: List[Message] = []
        results = [
            Message(role="tool", content="r1", tool_name="fn_a", tool_call_id="tc_1"),
            Message(role="tool", content="r2", tool_name="fn_b", tool_call_id="tc_2"),
        ]
        gi.format_function_call_results(messages, results)
        assert isinstance(messages[0].content, list)
        assert messages[0].content == ["r1", "r2"]

    def test_empty_results_no_message(self):
        gi = _make_gi()
        messages: List[Message] = []
        gi.format_function_call_results(messages, [])
        assert messages == []


# ---------------------------------------------------------------------------
# 9. _parse_provider_response
# ---------------------------------------------------------------------------


class TestGeminiInteractionsParseProviderResponse:
    def test_interaction_id_stored(self):
        gi = _make_gi()
        interaction = _make_interaction(id_="int_xyz")
        resp = gi._parse_provider_response(interaction)
        assert resp.provider_data["interaction_id"] == "int_xyz"

    def test_role_mapped_to_assistant(self):
        gi = _make_gi()
        interaction = _make_interaction(role="model")
        resp = gi._parse_provider_response(interaction)
        assert resp.role == "assistant"

    def test_text_content_extracted(self):
        gi = _make_gi()
        interaction = _make_interaction(outputs=[_make_text_output("Hello world")])
        resp = gi._parse_provider_response(interaction)
        assert resp.content == "Hello world"

    def test_multiple_text_outputs_concatenated(self):
        gi = _make_gi()
        interaction = _make_interaction(
            outputs=[
                _make_text_output("Part 1 "),
                _make_text_output("Part 2"),
            ]
        )
        resp = gi._parse_provider_response(interaction)
        assert resp.content == "Part 1 Part 2"

    def test_thought_output_stored_in_reasoning(self):
        gi = _make_gi()
        interaction = _make_interaction(
            outputs=[
                _make_thought_output(signature="sig_abc", summary="reasoning here"),
            ]
        )
        resp = gi._parse_provider_response(interaction)
        assert resp.reasoning_content == "reasoning here"
        assert resp.provider_data["thought_signature"] == "sig_abc"

    def test_function_call_produces_tool_call(self):
        gi = _make_gi()
        interaction = _make_interaction(
            outputs=[
                _make_function_call_output("search", "call_99", {"q": "python"}),
            ]
        )
        resp = gi._parse_provider_response(interaction)
        assert len(resp.tool_calls) == 1
        tc = resp.tool_calls[0]
        assert tc["function"]["name"] == "search"
        assert tc["id"] == "call_99"

    def test_function_call_args_serialized_to_json(self):
        gi = _make_gi()
        interaction = _make_interaction(
            outputs=[
                _make_function_call_output("fn", "c1", {"key": "val"}),
            ]
        )
        resp = gi._parse_provider_response(interaction)
        args_str = resp.tool_calls[0]["function"]["arguments"]
        assert json.loads(args_str) == {"key": "val"}

    def test_function_call_no_id_generates_uuid(self):
        gi = _make_gi()
        out = MagicMock()
        out.type = "function_call"
        out.id = None
        out.name = "fn"
        out.arguments = {}
        interaction = _make_interaction(outputs=[out])
        resp = gi._parse_provider_response(interaction)
        assert resp.tool_calls[0]["id"] is not None

    def test_usage_metrics_extracted(self):
        gi = _make_gi()
        usage = _make_usage()
        interaction = _make_interaction(usage=usage)
        resp = gi._parse_provider_response(interaction)
        assert resp.response_usage is not None
        assert resp.response_usage.output_tokens == 20

    def test_no_outputs_sets_empty_content(self):
        gi = _make_gi()
        interaction = _make_interaction(outputs=[], role="model")
        resp = gi._parse_provider_response(interaction)
        assert resp.content == ""

    def test_annotations_stored(self):
        gi = _make_gi()
        out = MagicMock()
        out.type = "text"
        out.text = "Annotated"
        out.annotations = [{"url": "https://example.com"}]
        interaction = _make_interaction(outputs=[out])
        resp = gi._parse_provider_response(interaction)
        assert "annotations" in resp.provider_data


# ---------------------------------------------------------------------------
# 10. _parse_provider_response_delta
# ---------------------------------------------------------------------------


class TestGeminiInteractionsParseProviderResponseDelta:
    def test_content_start_text_sets_state(self):
        gi = _make_gi()
        event = MagicMock(spec=ContentStart)
        event.content = MagicMock()
        event.content.type = "text"
        event_state = {"state": None}
        accumulators = {"reasoning_content": "", "content": ""}

        resp = gi._parse_provider_response_delta(event, event_state, accumulators)
        assert event_state["state"] == "content_delta"
        assert resp.delta_status == "content_started"

    def test_content_start_thought_sets_reasoning_state(self):
        gi = _make_gi()
        event = MagicMock(spec=ContentStart)
        event.content = MagicMock()
        event.content.type = "thought"
        event_state = {"state": None}
        accumulators = {"reasoning_content": "", "content": ""}

        resp = gi._parse_provider_response_delta(event, event_state, accumulators)
        assert event_state["state"] == "reasoning_delta"
        assert resp.delta_status == "reasoning_started"

    def test_content_start_function_call_sets_state(self):
        gi = _make_gi()
        event = MagicMock(spec=ContentStart)
        event.content = MagicMock()
        event.content.type = "function_call"
        event_state = {"state": None}
        accumulators = {"reasoning_content": "", "content": ""}

        gi._parse_provider_response_delta(event, event_state, accumulators)
        assert event_state["state"] == "function_call_delta"

    def test_content_stop_with_content_sets_done(self):
        gi = _make_gi()
        event = MagicMock(spec=ContentStop)
        event_state = {"state": "content_delta"}
        accumulators = {"reasoning_content": "", "content": "accumulated content"}

        resp = gi._parse_provider_response_delta(event, event_state, accumulators)
        assert resp.delta_status == "content_done"
        assert resp.content == "accumulated content"
        assert event_state["state"] is None

    def test_content_stop_with_reasoning_sets_done(self):
        gi = _make_gi()
        event = MagicMock(spec=ContentStop)
        event_state = {"state": "reasoning_delta"}
        accumulators = {"reasoning_content": "thought content", "content": ""}

        resp = gi._parse_provider_response_delta(event, event_state, accumulators)
        assert resp.delta_status == "reasoning_done"
        assert resp.reasoning_content == "thought content"

    def test_content_delta_text_updates_accumulator(self):
        gi = _make_gi()
        delta_event = MagicMock(spec=ContentDelta)
        delta_event.delta = MagicMock()
        delta_event.delta.type = "text"
        delta_event.delta.text = " world"
        event_state = {"state": "content_delta"}
        accumulators = {"reasoning_content": "", "content": "hello"}

        resp = gi._parse_provider_response_delta(delta_event, event_state, accumulators)
        assert resp.content == " world"
        assert accumulators["content"] == "hello world"
        assert resp.is_delta is True

    def test_content_delta_thought_summary_updates_reasoning(self):
        gi = _make_gi()
        delta_event = MagicMock(spec=ContentDelta)
        delta_event.delta = MagicMock()
        delta_event.delta.type = "thought_summary"
        inner_delta = MagicMock()
        inner_delta.type = "text"
        inner_delta.text = "I think therefore I am"
        delta_event.delta.content = inner_delta
        event_state = {"state": "reasoning_delta"}
        accumulators = {"reasoning_content": "", "content": ""}

        resp = gi._parse_provider_response_delta(delta_event, event_state, accumulators)
        assert resp.reasoning_content == "I think therefore I am"

    def test_content_delta_thought_signature_stored(self):
        gi = _make_gi()
        delta_event = MagicMock(spec=ContentDelta)
        delta_event.delta = MagicMock()
        delta_event.delta.type = "thought_signature"
        delta_event.delta.signature = "enc_sig_xyz"
        event_state = {"state": None}
        accumulators = {"reasoning_content": "", "content": ""}

        resp = gi._parse_provider_response_delta(delta_event, event_state, accumulators)
        assert resp.provider_data is not None
        assert resp.provider_data["thought_signature"] == "enc_sig_xyz"

    def test_content_delta_function_call(self):
        gi = _make_gi()
        delta_event = MagicMock(spec=ContentDelta)
        delta_event.delta = MagicMock()
        delta_event.delta.type = "function_call"
        delta_event.delta.name = "my_fn"
        delta_event.delta.arguments = {"param": "value"}
        delta_event.delta.id = "call_99"
        event_state = {"state": "function_call_delta"}
        accumulators = {"reasoning_content": "", "content": ""}

        resp = gi._parse_provider_response_delta(delta_event, event_state, accumulators)
        assert len(resp.tool_calls) == 1
        assert resp.tool_calls[0]["function"]["name"] == "my_fn"
        assert resp.tool_calls[0]["id"] == "call_99"


# ---------------------------------------------------------------------------
# 11. _get_metrics
# ---------------------------------------------------------------------------


class TestGeminiInteractionsGetMetrics:
    def test_input_tokens(self):
        gi = _make_gi()
        assert gi._get_metrics(_make_usage(input_t=50)).input_tokens == 50

    def test_output_tokens(self):
        gi = _make_gi()
        assert gi._get_metrics(_make_usage(output_t=100)).output_tokens == 100

    def test_total_tokens(self):
        gi = _make_gi()
        assert gi._get_metrics(_make_usage(total_t=150)).total_tokens == 150

    def test_reasoning_tokens(self):
        gi = _make_gi()
        assert gi._get_metrics(_make_usage(thought_t=12)).reasoning_tokens == 12

    def test_cache_read_tokens(self):
        gi = _make_gi()
        assert gi._get_metrics(_make_usage(cached_t=30)).cache_read_tokens == 30

    def test_cache_read_tokens_none(self):
        gi = _make_gi()
        assert gi._get_metrics(_make_usage(cached_t=None)).cache_read_tokens == 0

    def test_additional_metrics_populated(self):
        gi = _make_gi()
        assert gi._get_metrics(_make_usage()).additional_metrics is not None


# ---------------------------------------------------------------------------
# 12. __deepcopy__
# ---------------------------------------------------------------------------


class TestGeminiInteractionsDeepcopy:
    def test_client_set_to_none(self):
        gi = GeminiInteractions(api_key="key_abc")
        gi.client = MagicMock(name="live_client")
        gi_copy = copy.deepcopy(gi)
        assert gi_copy.client is None

    def test_config_preserved(self):
        gi = GeminiInteractions(id="gemini-preview", temperature=0.6, max_output_tokens=512)
        gi_copy = copy.deepcopy(gi)
        assert gi_copy.id == "gemini-preview"
        assert gi_copy.temperature == 0.6
        assert gi_copy.max_output_tokens == 512

    def test_copy_is_independent(self):
        gi = GeminiInteractions(stop_sequences=["DONE"])
        gi_copy = copy.deepcopy(gi)
        gi_copy.stop_sequences.append("STOP")
        assert gi.stop_sequences == ["DONE"]


# ---------------------------------------------------------------------------
# 13. ainvoke error handling
# ---------------------------------------------------------------------------


class TestGeminiInteractionsAinvokeErrors:
    @pytest.mark.asyncio
    async def test_generic_exception_raises_model_provider_error(self):
        gi = _make_gi()
        gi.client.aio.interactions.create = AsyncMock(side_effect=ValueError("unexpected"))
        msgs = [Message(role="user", content="hi")]
        assistant = Message(role="assistant", content="")
        with pytest.raises(ModelProviderError):
            await gi.ainvoke(msgs, assistant)

    @pytest.mark.asyncio
    async def test_httpx_timeout_raises_model_provider_error(self):
        import httpx

        gi = _make_gi()
        gi.client.aio.interactions.create = AsyncMock(
            side_effect=httpx.TimeoutException("timed out")
        )
        msgs = [Message(role="user", content="hi")]
        assistant = Message(role="assistant", content="")
        with pytest.raises(ModelProviderError):
            await gi.ainvoke(msgs, assistant)

    @pytest.mark.asyncio
    async def test_client_error_raises_model_provider_error(self):
        from google.genai.errors import ClientError

        gi = _make_gi()
        err = MagicMock(spec=ClientError)
        err.__class__ = ClientError
        err.args = ("bad request",)
        err.code = 400
        err.response = MagicMock()
        err.response.json.return_value = {"error": {"message": "Bad Request"}}
        gi.client.aio.interactions.create = AsyncMock(side_effect=err)
        msgs = [Message(role="user", content="hi")]
        assistant = Message(role="assistant", content="")
        with pytest.raises(ModelProviderError):
            await gi.ainvoke(msgs, assistant)


# ---------------------------------------------------------------------------
# 14. ainvoke happy path
# ---------------------------------------------------------------------------


class TestGeminiInteractionsAinvokeHappyPath:
    @pytest.mark.asyncio
    async def test_ainvoke_returns_model_response(self):
        gi = _make_gi()
        interaction = _make_interaction(
            id_="int_happy",
            role="model",
            outputs=[_make_text_output("Response from GeminiInteractions")],
            usage=_make_usage(),
        )
        gi.client.aio.interactions.create = AsyncMock(return_value=interaction)

        msgs = [Message(role="user", content="Hello")]
        assistant = Message(role="assistant", content="")
        result = await gi.ainvoke(msgs, assistant)
        assert isinstance(result, ModelResponse)
        assert result.role == "assistant"
        assert result.content == "Response from GeminiInteractions"
