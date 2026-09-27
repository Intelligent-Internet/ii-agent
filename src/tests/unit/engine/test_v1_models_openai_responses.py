"""
Unit tests for src/ii_agent/agent/runtime/models/openai/responses.py

Tests cover:
- OpenAIResponses class defaults and instantiation
- OpenAIResponses._using_reasoning_model()
- OpenAIResponses._set_reasoning_request_param()
- OpenAIResponses._get_client_params()
- OpenAIResponses.get_request_params()
- OpenAIResponses._format_tool_params()
- OpenAIResponses._format_messages() – all role branches
- OpenAIResponses._parse_provider_response() – message, function_call, reasoning
- OpenAIResponses._parse_provider_response_delta() – streaming events
- OpenAIResponses.format_function_call_results()
- OpenAIResponses ainvoke error handling
- OpenAIResponses ainvoke happy path
"""

from typing import List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ii_agent.agents.models.openai.responses import OpenAIResponses
from ii_agent.agents.models.message import Message
from ii_agent.agents.models.response import ModelResponse
from ii_agent.agents.exceptions import (
    ModelAuthenticationError,
    ModelProviderError,
)
from ii_agent.settings.llm import Provider


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_openai_responses(**kwargs) -> OpenAIResponses:
    m = OpenAIResponses(**kwargs)
    mock_async = MagicMock()
    mock_async.is_closed.return_value = False
    mock_async.responses = MagicMock()
    m.async_client = mock_async

    mock_sync = MagicMock()
    mock_sync.is_closed.return_value = False
    m.client = mock_sync
    return m


def _make_response_output(type_, **fields):
    out = MagicMock()
    out.type = type_
    for k, v in fields.items():
        setattr(out, k, v)
    return out


def _make_usage(input_tokens=10, output_tokens=20, total_tokens=30, reasoning_tokens=5):
    u = MagicMock()
    u.input_tokens = input_tokens
    u.output_tokens = output_tokens
    u.total_tokens = total_tokens
    # output_tokens_details with reasoning_tokens
    u.output_tokens_details = MagicMock()
    u.output_tokens_details.reasoning_tokens = reasoning_tokens
    # input_tokens_details: set cached_tokens to None to avoid MagicMock arithmetic
    u.input_tokens_details = MagicMock()
    u.input_tokens_details.cached_tokens = None
    return u


def _make_api_response(outputs, usage=None, response_id="resp_123", error=None, output_text=""):
    resp = MagicMock()
    resp.id = response_id
    resp.output = outputs
    resp.output_text = output_text
    resp.error = error
    resp.usage = usage or _make_usage()
    return resp


# ---------------------------------------------------------------------------
# 1. Defaults
# ---------------------------------------------------------------------------


class TestOpenAIResponsesDefaults:
    def test_default_id(self):
        assert OpenAIResponses().id == "gpt-4o"

    def test_default_name(self):
        assert OpenAIResponses().name == "OpenAIResponses"

    def test_default_provider(self):
        assert OpenAIResponses().provider == Provider.OPENAI

    def test_default_supports_native_structured_outputs(self):
        assert OpenAIResponses().supports_native_structured_outputs is True

    def test_default_strict_output_true(self):
        assert OpenAIResponses().strict_output is True

    def test_default_temperature_none(self):
        assert OpenAIResponses().temperature is None

    def test_custom_id(self):
        assert OpenAIResponses(id="gpt-4-turbo").id == "gpt-4-turbo"

    def test_custom_api_key(self):
        assert OpenAIResponses(api_key="sk-test").api_key == "sk-test"

    def test_client_starts_none(self):
        assert OpenAIResponses().client is None

    def test_async_client_starts_none(self):
        assert OpenAIResponses().async_client is None

    def test_role_map_defaults(self):
        m = OpenAIResponses()
        assert m.role_map["system"] == "developer"
        assert m.role_map["user"] == "user"
        assert m.role_map["assistant"] == "assistant"


# ---------------------------------------------------------------------------
# 2. _using_reasoning_model
# ---------------------------------------------------------------------------


class TestOpenAIResponsesUsingReasoningModel:
    def test_gpt4o_is_not_reasoning(self):
        assert OpenAIResponses(id="gpt-4o")._using_reasoning_model() is False

    def test_o3_is_reasoning(self):
        assert OpenAIResponses(id="o3-mini")._using_reasoning_model() is True

    def test_o4_mini_is_reasoning(self):
        assert OpenAIResponses(id="o4-mini")._using_reasoning_model() is True

    def test_gpt5_is_reasoning(self):
        assert OpenAIResponses(id="gpt-5")._using_reasoning_model() is True

    def test_gpt4_is_not_reasoning(self):
        assert OpenAIResponses(id="gpt-4")._using_reasoning_model() is False


# ---------------------------------------------------------------------------
# 3. _set_reasoning_request_param
# ---------------------------------------------------------------------------


class TestOpenAIResponsesSetReasoningRequestParam:
    def test_sets_reasoning_key(self):
        m = OpenAIResponses(id="o3-mini")
        params = m._set_reasoning_request_param({})
        assert "reasoning" in params

    def test_effort_set_when_present(self):
        m = OpenAIResponses(id="o3-mini", reasoning_effort="high")
        params = m._set_reasoning_request_param({})
        assert params["reasoning"]["effort"] == "high"

    def test_summary_set_when_present(self):
        m = OpenAIResponses(id="o3-mini", reasoning_summary="concise")
        params = m._set_reasoning_request_param({})
        assert params["reasoning"]["summary"] == "concise"

    def test_empty_reasoning_when_no_effort_or_summary(self):
        # When reasoning_effort and reasoning_summary are both None,
        # _set_reasoning_request_param sets reasoning to self.reasoning or {}
        m = OpenAIResponses(id="o3-mini")
        m.reasoning = None
        params = m._set_reasoning_request_param({})
        # An empty dict is set for reasoning; since it's falsy, get_request_params
        # may filter it out, but the key is present at this stage
        assert "reasoning" in params
        assert params["reasoning"] == {}

    def test_non_reasoning_model_skips_reasoning(self):
        m = OpenAIResponses(id="gpt-4o")
        params = m._set_reasoning_request_param({})
        assert "reasoning" not in params


# ---------------------------------------------------------------------------
# 4. _get_client_params
# ---------------------------------------------------------------------------


class TestOpenAIResponsesGetClientParams:
    def test_api_key_included(self):
        m = OpenAIResponses(api_key="sk-key")
        params = m._get_client_params()
        assert params["api_key"] == "sk-key"

    def test_organization_included_when_set(self):
        m = OpenAIResponses(api_key="key", organization="org_abc")
        params = m._get_client_params()
        assert params["organization"] == "org_abc"

    def test_none_values_filtered(self):
        m = OpenAIResponses(api_key="key", organization=None)
        params = m._get_client_params()
        assert "organization" not in params

    @patch.dict("os.environ", {"OPENAI_API_KEY": "env_key"}, clear=False)
    def test_api_key_from_env(self):
        m = OpenAIResponses()
        m.api_key = None
        params = m._get_client_params()
        assert params["api_key"] == "env_key"

    @patch.dict("os.environ", {}, clear=True)
    def test_missing_api_key_raises(self):
        m = OpenAIResponses()
        m.api_key = None
        with pytest.raises(ModelAuthenticationError):
            m._get_client_params()

    def test_timeout_included(self):
        m = OpenAIResponses(api_key="key", timeout=30.0)
        params = m._get_client_params()
        assert params["timeout"] == 30.0

    def test_extra_client_params_merged(self):
        m = OpenAIResponses(api_key="key", client_params={"custom": True})
        params = m._get_client_params()
        assert params["custom"] is True


# ---------------------------------------------------------------------------
# 5. get_request_params
# ---------------------------------------------------------------------------


class TestOpenAIResponsesGetRequestParams:
    def test_temperature_included(self):
        m = _make_openai_responses(api_key="key", temperature=0.5)
        assert m.get_request_params()["temperature"] == 0.5

    def test_max_output_tokens_included(self):
        m = _make_openai_responses(api_key="key", max_output_tokens=1024)
        assert m.get_request_params()["max_output_tokens"] == 1024

    def test_top_p_included(self):
        m = _make_openai_responses(api_key="key", top_p=0.9)
        assert m.get_request_params()["top_p"] == 0.9

    def test_none_values_not_included(self):
        m = _make_openai_responses(api_key="key")
        params = m.get_request_params()
        assert "temperature" not in params
        assert "max_output_tokens" not in params

    def test_verbosity_in_text_param(self):
        m = _make_openai_responses(api_key="key", verbosity="high")
        params = m.get_request_params()
        assert "text" in params
        assert params["text"]["verbosity"] == "high"

    def test_deep_research_model_gets_web_search(self):
        m = _make_openai_responses(api_key="key", id="gpt-4o-deep-research")
        params = m.get_request_params(tools=[])
        tool_types = [t.get("type") for t in params.get("tools", [])]
        assert "web_search_preview" in tool_types

    def test_deep_research_no_duplicate_web_search(self):
        m = _make_openai_responses(api_key="key", id="gpt-4o-deep-research")
        params = m.get_request_params(tools=[{"type": "web_search_preview"}])
        web_count = sum(1 for t in params.get("tools", []) if t.get("type") == "web_search_preview")
        assert web_count == 1

    def test_reasoning_model_store_false_adds_encrypted_content(self):
        m = _make_openai_responses(api_key="key", id="o3-mini", store=False)
        msgs = [Message(role="user", content="hi")]
        params = m.get_request_params(messages=msgs)
        assert "reasoning.encrypted_content" in params.get("include", [])

    def test_reasoning_model_store_true_checks_previous_response(self):
        m = _make_openai_responses(api_key="key", id="o3-mini", store=True)
        msgs = [
            Message(
                role="assistant",
                content="old resp",
                provider_data={"response_id": "resp_old_123"},
            ),
            Message(role="user", content="continue"),
        ]
        params = m.get_request_params(messages=msgs)
        assert params.get("previous_response_id") == "resp_old_123"

    def test_request_params_merged(self):
        m = _make_openai_responses(api_key="key", request_params={"custom": "val"})
        assert m.get_request_params().get("custom") == "val"

    def test_tool_choice_included(self):
        m = _make_openai_responses(api_key="key")
        assert m.get_request_params(tool_choice="required").get("tool_choice") == "required"


# ---------------------------------------------------------------------------
# 6. _format_tool_params
# ---------------------------------------------------------------------------


class TestOpenAIResponsesFormatToolParams:
    def test_function_tool_reformatted(self):
        m = _make_openai_responses(api_key="key")
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "fn",
                    "description": "desc",
                    "parameters": {
                        "type": "object",
                        "properties": {"q": {"type": "string"}},
                    },
                },
            }
        ]
        result = m._format_tool_params(messages=[], tools=tools)
        assert result[0]["type"] == "function"
        assert result[0]["name"] == "fn"

    def test_non_function_tool_passed_through(self):
        m = _make_openai_responses(api_key="key")
        tools = [{"type": "web_search_preview"}]
        result = m._format_tool_params(messages=[], tools=tools)
        assert result[0] == {"type": "web_search_preview"}

    def test_list_type_converted_to_first_value(self):
        m = _make_openai_responses(api_key="key")
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "fn",
                    "description": "desc",
                    "parameters": {
                        "type": "object",
                        "properties": {"x": {"type": ["string", "null"]}},
                    },
                },
            }
        ]
        result = m._format_tool_params(messages=[], tools=tools)
        assert result[0]["parameters"]["properties"]["x"]["type"] == "string"

    def test_empty_tools_returns_empty(self):
        m = _make_openai_responses(api_key="key")
        assert m._format_tool_params(messages=[], tools=None) == []


# ---------------------------------------------------------------------------
# 7. _format_messages
# ---------------------------------------------------------------------------


class TestOpenAIResponsesFormatMessages:
    def test_user_message_formatted(self):
        m = _make_openai_responses(api_key="key")
        msgs = [Message(role="user", content="Hello")]
        result = m._format_messages(msgs)
        assert result[0]["role"] == "user"
        assert result[0]["content"] == "Hello"

    def test_system_message_formatted_as_developer(self):
        m = _make_openai_responses(api_key="key")
        msgs = [Message(role="system", content="Be helpful")]
        result = m._format_messages(msgs)
        assert result[0]["role"] == "developer"

    def test_tool_result_formatted_as_function_call_output(self):
        m = _make_openai_responses(api_key="key")
        msgs = [Message(role="tool", content="the result", tool_call_id="call_abc")]
        result = m._format_messages(msgs)
        assert result[0]["type"] == "function_call_output"
        assert result[0]["call_id"] == "call_abc"

    def test_assistant_tool_calls_formatted(self):
        m = _make_openai_responses(api_key="key")
        tool_calls = [
            {
                "id": "fc_1",
                "call_id": "call_1",
                "type": "function",
                "function": {"name": "search", "arguments": '{"q": "test"}'},
            }
        ]
        msgs = [Message(role="assistant", content="", tool_calls=tool_calls)]
        result = m._format_messages(msgs)
        fc_items = [r for r in result if r.get("type") == "function_call"]
        assert len(fc_items) == 1
        assert fc_items[0]["name"] == "search"

    def test_assistant_message_without_tool_calls(self):
        m = _make_openai_responses(api_key="key")
        msgs = [Message(role="assistant", content="Hello there")]
        result = m._format_messages(msgs)
        assert result[0]["role"] == "assistant"
        assert result[0]["content"] == "Hello there"

    def test_assistant_null_content_becomes_empty_string(self):
        m = _make_openai_responses(api_key="key")
        msgs = [Message(role="assistant", content=None)]
        result = m._format_messages(msgs)
        assert result[0]["content"] == ""

    def test_user_with_files(self):
        from pathlib import Path
        from ii_agent.agents.models.message import File

        m = _make_openai_responses(api_key="key")
        file_obj = File(filepath=Path("/tmp/doc.pdf"))
        msgs = [Message(role="user", content="See doc", files=[file_obj])]
        result = m._format_messages(msgs)
        assert "Attached files" in result[0]["content"]

    def test_reasoning_model_with_previous_response_id_filters_messages(self):
        m = _make_openai_responses(api_key="key", id="o3-mini", store=True)
        response_id = "resp_prev_123"
        msgs = [
            Message(role="user", content="First message"),
            Message(
                role="assistant",
                content="Old response",
                provider_data={"response_id": response_id},
            ),
            Message(role="user", content="New message"),
        ]
        result = m._format_messages(msgs)
        user_msgs = [r for r in result if r.get("role") == "user"]
        assert len(user_msgs) == 1

    def test_tool_call_id_translated_via_fc_map(self):
        m = _make_openai_responses(api_key="key")
        tool_calls = [
            {
                "id": "fc_original",
                "call_id": "call_translated",
                "type": "function",
                "function": {"name": "fn", "arguments": "{}"},
            }
        ]
        msgs = [
            Message(role="assistant", content="", tool_calls=tool_calls),
            Message(role="tool", content="result", tool_call_id="fc_original"),
        ]
        result = m._format_messages(msgs)
        fc_out = [r for r in result if r.get("type") == "function_call_output"]
        assert fc_out[0]["call_id"] == "call_translated"


# ---------------------------------------------------------------------------
# 8. _parse_provider_response
# ---------------------------------------------------------------------------


class TestOpenAIResponsesParseProviderResponse:
    def test_response_id_stored(self):
        m = _make_openai_responses(api_key="key")
        msg_output = _make_response_output(
            "message",
            content=[_make_response_output("output_text", text="Hello", annotations=[])],
        )
        resp = _make_api_response([msg_output], response_id="resp_test_123", output_text="Hello")
        mr = m._parse_provider_response(resp)
        assert mr.provider_data["response_id"] == "resp_test_123"

    def test_role_set_to_assistant(self):
        m = _make_openai_responses(api_key="key")
        msg_output = _make_response_output(
            "message",
            content=[_make_response_output("output_text", text="Hi", annotations=[])],
        )
        resp = _make_api_response([msg_output], output_text="Hi")
        mr = m._parse_provider_response(resp)
        assert mr.role == "assistant"

    def test_text_content_extracted(self):
        m = _make_openai_responses(api_key="key")
        msg_output = _make_response_output(
            "message",
            content=[_make_response_output("output_text", text="Content here", annotations=[])],
        )
        resp = _make_api_response([msg_output], output_text="Content here")
        mr = m._parse_provider_response(resp)
        assert mr.content == "Content here"

    def test_function_call_extracted(self):
        m = _make_openai_responses(api_key="key")
        fc_output = _make_response_output(
            "function_call",
            id="fc_1",
            call_id="call_1",
            name="search",
            arguments='{"q": "test"}',
        )
        resp = _make_api_response([fc_output], output_text="")
        mr = m._parse_provider_response(resp)
        assert len(mr.tool_calls) == 1
        assert mr.tool_calls[0]["function"]["name"] == "search"
        assert mr.tool_calls[0]["call_id"] == "call_1"

    def test_multiple_function_calls(self):
        m = _make_openai_responses(api_key="key")
        fc1 = _make_response_output(
            "function_call", id="fc_1", call_id="c1", name="fn1", arguments="{}"
        )
        fc2 = _make_response_output(
            "function_call", id="fc_2", call_id="c2", name="fn2", arguments="{}"
        )
        resp = _make_api_response([fc1, fc2], output_text="")
        mr = m._parse_provider_response(resp)
        assert len(mr.tool_calls) == 2

    def test_reasoning_output_stored_for_zdr_mode(self):
        m = _make_openai_responses(api_key="key", store=False)
        reasoning_output = _make_response_output("reasoning", summary=[])
        reasoning_output.model_dump = MagicMock(return_value={"type": "reasoning"})
        resp = _make_api_response([reasoning_output], output_text="")
        mr = m._parse_provider_response(resp)
        assert mr.provider_data is not None
        assert "reasoning_output" in mr.provider_data

    def test_reasoning_summary_text_extracted(self):
        m = _make_openai_responses(api_key="key")
        summary_item = MagicMock()
        summary_item.text = "I reasoned about this"
        reasoning_output = _make_response_output("reasoning", summary=[summary_item])
        resp = _make_api_response([reasoning_output], output_text="")
        mr = m._parse_provider_response(resp)
        assert mr.reasoning_content == "I reasoned about this"

    def test_url_citation_extracted(self):
        m = _make_openai_responses(api_key="key")
        annotation = MagicMock()
        annotation.type = "url_citation"
        annotation.url = "https://example.com"
        annotation.title = "Example"
        annotation.model_dump = MagicMock(return_value={"type": "url_citation"})
        content_item = _make_response_output(
            "output_text", text="Cited text", annotations=[annotation]
        )
        msg_output = _make_response_output("message", content=[content_item])
        resp = _make_api_response([msg_output], output_text="Cited text")
        mr = m._parse_provider_response(resp)
        assert mr.citations is not None
        assert mr.citations.urls is not None
        assert mr.citations.urls[0].url == "https://example.com"

    def test_usage_extracted(self):
        m = _make_openai_responses(api_key="key")
        usage = _make_usage()
        resp = _make_api_response([], usage=usage, output_text="")
        mr = m._parse_provider_response(resp)
        assert mr.response_usage is not None
        assert mr.response_usage.input_tokens == 10

    def test_error_in_response_raises_model_provider_error(self):
        m = _make_openai_responses(api_key="key")
        error_obj = MagicMock()
        error_obj.message = "Model returned an error"
        resp = MagicMock()
        resp.id = "r1"
        resp.output = []
        resp.error = error_obj
        resp.usage = _make_usage()
        with pytest.raises(ModelProviderError):
            m._parse_provider_response(resp)


# ---------------------------------------------------------------------------
# 9. _parse_provider_response_delta (streaming)
# ---------------------------------------------------------------------------


class TestOpenAIResponsesParseProviderResponseDelta:
    def _make_event(self, type_, **fields):
        evt = MagicMock()
        evt.type = type_
        for k, v in fields.items():
            setattr(evt, k, v)
        return evt

    def test_response_created_stores_id(self):
        m = _make_openai_responses(api_key="key")
        assistant_msg = Message(role="assistant", content="")
        response_stub = MagicMock()
        response_stub.id = "resp_stream_001"
        evt = self._make_event("response.created", response=response_stub)
        result, _ = m._parse_provider_response_delta(evt, assistant_msg, {})
        assert result.provider_data["response_id"] == "resp_stream_001"

    def test_output_text_delta(self):
        m = _make_openai_responses(api_key="key")
        assistant_msg = Message(role="assistant", content="")
        evt = self._make_event("response.output_text.delta", delta="Hello ")
        result, _ = m._parse_provider_response_delta(evt, assistant_msg, {})
        assert result.content == "Hello "
        assert result.is_delta is True

    def test_output_text_done(self):
        m = _make_openai_responses(api_key="key")
        assistant_msg = Message(role="assistant", content="")
        evt = self._make_event("response.output_text.done", text="Final text")
        result, _ = m._parse_provider_response_delta(evt, assistant_msg, {})
        assert result.content == "Final text"
        assert result.is_delta is False
        assert result.delta_status == "content_done"

    def test_reasoning_summary_started(self):
        m = _make_openai_responses(api_key="key")
        assistant_msg = Message(role="assistant", content="")
        evt = self._make_event("response.reasoning_summary_part.added")
        result, _ = m._parse_provider_response_delta(evt, assistant_msg, {})
        assert result.delta_status == "reasoning_started"

    def test_reasoning_summary_text_delta(self):
        m = _make_openai_responses(api_key="key")
        assistant_msg = Message(role="assistant", content="")
        evt = self._make_event("response.reasoning_summary_text.delta", delta="I reason")
        result, _ = m._parse_provider_response_delta(evt, assistant_msg, {})
        assert result.reasoning_content == "I reason"
        assert result.is_delta is True

    def test_reasoning_summary_text_done(self):
        m = _make_openai_responses(api_key="key")
        assistant_msg = Message(role="assistant", content="")
        evt = self._make_event("response.reasoning_summary_text.done", text="Full reasoning")
        result, _ = m._parse_provider_response_delta(evt, assistant_msg, {})
        assert result.reasoning_content == "Full reasoning"
        assert result.delta_status == "reasoning_done"
        assert result.is_delta is False

    def test_output_item_added_function_call(self):
        m = _make_openai_responses(api_key="key")
        assistant_msg = Message(role="assistant", content="")
        item = MagicMock()
        item.type = "function_call"
        item.id = "fc_1"
        item.call_id = "call_1"
        item.name = "search"
        item.arguments = ""
        evt = self._make_event("response.output_item.added", item=item)
        result, new_tool_use = m._parse_provider_response_delta(evt, assistant_msg, {})
        assert new_tool_use["function"]["name"] == "search"

    def test_function_call_arguments_delta(self):
        m = _make_openai_responses(api_key="key")
        assistant_msg = Message(role="assistant", content="")
        tool_use = {"function": {"name": "fn", "arguments": '{"q"'}}
        evt = self._make_event("response.function_call_arguments.delta", delta=': "test"}')
        result, new_tool_use = m._parse_provider_response_delta(evt, assistant_msg, tool_use)
        assert new_tool_use["function"]["arguments"] == '{"q": "test"}'

    def test_output_item_done_adds_tool_call(self):
        m = _make_openai_responses(api_key="key")
        assistant_msg = Message(role="assistant", content="")
        tool_use = {
            "id": "fc_1",
            "call_id": "c1",
            "type": "function",
            "function": {"name": "search", "arguments": '{"q": "test"}'},
        }
        evt = self._make_event("response.output_item.done")
        result, _ = m._parse_provider_response_delta(evt, assistant_msg, tool_use)
        assert len(result.tool_calls) == 1
        assert len(assistant_msg.tool_calls) == 1

    def test_citation_annotation_added(self):
        m = _make_openai_responses(api_key="key")
        assistant_msg = Message(role="assistant", content="")
        annotation = MagicMock()
        annotation.type = "url_citation"
        annotation.url = "https://source.example.com"
        annotation.title = "Source"
        evt = self._make_event("response.output_text.annotation.added", annotation=annotation)
        result, _ = m._parse_provider_response_delta(evt, assistant_msg, {})
        assert result.citations is not None
        assert result.citations.urls[0].url == "https://source.example.com"


# ---------------------------------------------------------------------------
# 10. format_function_call_results
# ---------------------------------------------------------------------------


class TestOpenAIResponsesFormatFunctionCallResults:
    def test_appends_messages_with_tool_call_ids(self):
        m = _make_openai_responses(api_key="key")
        messages: List[Message] = []
        r1 = Message(role="tool", content="output_1")
        r2 = Message(role="tool", content="output_2")
        m.format_function_call_results(messages, [r1, r2], ["tc_1", "tc_2"])
        assert len(messages) == 2
        assert messages[0].tool_call_id == "tc_1"
        assert messages[1].tool_call_id == "tc_2"

    def test_empty_results_no_messages_appended(self):
        m = _make_openai_responses(api_key="key")
        messages: List[Message] = []
        m.format_function_call_results(messages, [], [])
        assert len(messages) == 0


# ---------------------------------------------------------------------------
# 11. ainvoke error handling
# ---------------------------------------------------------------------------


class TestOpenAIResponsesAinvokeErrors:
    @pytest.mark.asyncio
    async def test_rate_limit_error_raises_model_provider_error(self):
        from openai import RateLimitError

        m = _make_openai_responses(api_key="key")
        err = MagicMock(spec=RateLimitError)
        err.__class__ = RateLimitError
        err.response = MagicMock()
        err.response.json.return_value = {"error": {"message": "Rate limited"}}
        err.response.status_code = 429
        m.async_client.responses.create = AsyncMock(side_effect=err)
        msgs = [Message(role="user", content="hi")]
        assistant = Message(role="assistant", content="")
        with pytest.raises(ModelProviderError):
            await m.ainvoke(msgs, assistant)

    @pytest.mark.asyncio
    async def test_api_connection_error_raises_model_provider_error(self):
        from openai import APIConnectionError

        m = _make_openai_responses(api_key="key")
        err = MagicMock(spec=APIConnectionError)
        err.__class__ = APIConnectionError
        err.args = ("connection failed",)
        m.async_client.responses.create = AsyncMock(side_effect=err)
        msgs = [Message(role="user", content="hi")]
        assistant = Message(role="assistant", content="")
        with pytest.raises(ModelProviderError):
            await m.ainvoke(msgs, assistant)

    @pytest.mark.asyncio
    async def test_generic_exception_raises_model_provider_error(self):
        m = _make_openai_responses(api_key="key")
        m.async_client.responses.create = AsyncMock(side_effect=RuntimeError("unexpected"))
        msgs = [Message(role="user", content="hi")]
        assistant = Message(role="assistant", content="")
        with pytest.raises(ModelProviderError):
            await m.ainvoke(msgs, assistant)

    @pytest.mark.asyncio
    async def test_httpx_timeout_raises_model_provider_error(self):
        import httpx

        m = _make_openai_responses(api_key="key")
        m.async_client.responses.create = AsyncMock(side_effect=httpx.TimeoutException("timed out"))
        msgs = [Message(role="user", content="hi")]
        assistant = Message(role="assistant", content="")
        with pytest.raises(ModelProviderError):
            await m.ainvoke(msgs, assistant)


# ---------------------------------------------------------------------------
# 12. ainvoke happy path
# ---------------------------------------------------------------------------


class TestOpenAIResponsesAinvokeHappyPath:
    @pytest.mark.asyncio
    async def test_ainvoke_returns_model_response(self):
        m = _make_openai_responses(api_key="test_key")

        msg_output = _make_response_output(
            "message",
            content=[
                _make_response_output("output_text", text="Hello from OpenAI!", annotations=[])
            ],
        )
        resp = _make_api_response(
            [msg_output],
            response_id="resp_happy",
            output_text="Hello from OpenAI!",
        )
        m.async_client.responses.create = AsyncMock(return_value=resp)

        msgs = [Message(role="user", content="Hi")]
        assistant = Message(role="assistant", content="")
        result = await m.ainvoke(msgs, assistant)
        assert isinstance(result, ModelResponse)
        assert result.role == "assistant"
        assert result.content == "Hello from OpenAI!"
