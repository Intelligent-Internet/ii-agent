"""Unit tests for MiniMax LLM client and related utilities."""

import pytest
from unittest.mock import patch, MagicMock
from pydantic import SecretStr

from ii_agent.llm.minimax import (
    _clamp_temperature,
    _strip_think_tags,
    _strip_think_tags_from_outputs,
    MiniMaxDirectClient,
    MINIMAX_TEMP_MIN,
    MINIMAX_TEMP_MAX,
)
from ii_agent.llm.base import TextResult, ToolCall
from ii_agent.core.config.llm_config import LLMConfig, APITypes
from ii_agent.utils.constants import (
    MINIMAX_API_BASE_URL,
    MINIMAX_DEFAULT_MODEL,
    is_minimax_family,
)


class TestClampTemperature:
    """Tests for _clamp_temperature()."""

    def test_zero_returns_min(self):
        assert _clamp_temperature(0.0) == MINIMAX_TEMP_MIN

    def test_negative_returns_min(self):
        assert _clamp_temperature(-1.0) == MINIMAX_TEMP_MIN

    def test_normal_value_unchanged(self):
        assert _clamp_temperature(0.5) == 0.5

    def test_max_value_unchanged(self):
        assert _clamp_temperature(1.0) == 1.0

    def test_above_max_clamped(self):
        assert _clamp_temperature(2.0) == MINIMAX_TEMP_MAX

    def test_small_positive_unchanged(self):
        assert _clamp_temperature(0.01) == 0.01


class TestStripThinkTags:
    """Tests for _strip_think_tags()."""

    def test_no_think_tags(self):
        assert _strip_think_tags("Hello world") == "Hello world"

    def test_single_think_tag(self):
        text = "<think>reasoning here</think>Final answer"
        assert _strip_think_tags(text) == "Final answer"

    def test_multiline_think_tag(self):
        text = "<think>\nStep 1\nStep 2\n</think>\nResult"
        assert _strip_think_tags(text) == "Result"

    def test_multiple_think_tags(self):
        text = "<think>first</think>A<think>second</think>B"
        assert _strip_think_tags(text) == "AB"

    def test_empty_think_tag(self):
        text = "<think></think>Content"
        assert _strip_think_tags(text) == "Content"

    def test_only_think_tag(self):
        text = "<think>only thinking</think>"
        assert _strip_think_tags(text) == ""

    def test_empty_string(self):
        assert _strip_think_tags("") == ""


class TestStripThinkTagsFromOutputs:
    """Tests for _strip_think_tags_from_outputs()."""

    def test_strips_from_text_results(self):
        outputs = [TextResult(text="<think>reasoning</think>answer")]
        result = _strip_think_tags_from_outputs(outputs)
        assert len(result) == 1
        assert isinstance(result[0], TextResult)
        assert result[0].text == "answer"

    def test_preserves_tool_calls(self):
        tool_call = ToolCall(
            tool_call_id="tc_1",
            tool_name="test_tool",
            tool_input={"key": "value"},
        )
        outputs = [tool_call]
        result = _strip_think_tags_from_outputs(outputs)
        assert len(result) == 1
        assert result[0] is tool_call

    def test_mixed_outputs(self):
        outputs = [
            TextResult(text="<think>think</think>clean text"),
            ToolCall(tool_call_id="tc_1", tool_name="tool", tool_input={}),
        ]
        result = _strip_think_tags_from_outputs(outputs)
        assert len(result) == 2
        assert isinstance(result[0], TextResult)
        assert result[0].text == "clean text"
        assert isinstance(result[1], ToolCall)

    def test_empty_list(self):
        assert _strip_think_tags_from_outputs([]) == []


class TestIsMiniMaxFamily:
    """Tests for is_minimax_family()."""

    def test_minimax_m27(self):
        assert is_minimax_family("MiniMax-M2.7") is True

    def test_minimax_m27_highspeed(self):
        assert is_minimax_family("MiniMax-M2.7-highspeed") is True

    def test_minimax_lowercase(self):
        assert is_minimax_family("minimax-m2.5") is True

    def test_non_minimax(self):
        assert is_minimax_family("gpt-4") is False

    def test_empty_string(self):
        assert is_minimax_family("") is False

    def test_none(self):
        assert is_minimax_family(None) is False


class TestMiniMaxDirectClient:
    """Tests for MiniMaxDirectClient initialization."""

    @patch("ii_agent.llm.openai.openai.OpenAI")
    def test_default_base_url(self, mock_openai_cls):
        config = LLMConfig(
            model="MiniMax-M2.7",
            api_key=SecretStr("test-key"),
            api_type=APITypes.MINIMAX,
        )
        client = MiniMaxDirectClient(config)
        assert client.model_name == "MiniMax-M2.7"
        mock_openai_cls.assert_called_once()
        call_kwargs = mock_openai_cls.call_args
        assert call_kwargs.kwargs["base_url"] == MINIMAX_API_BASE_URL

    @patch("ii_agent.llm.openai.openai.OpenAI")
    def test_custom_base_url_preserved(self, mock_openai_cls):
        custom_url = "https://custom.api.example.com/v1"
        config = LLMConfig(
            model="MiniMax-M2.7",
            api_key=SecretStr("test-key"),
            api_type=APITypes.MINIMAX,
            base_url=custom_url,
        )
        client = MiniMaxDirectClient(config)
        call_kwargs = mock_openai_cls.call_args
        assert call_kwargs.kwargs["base_url"] == custom_url


class TestMiniMaxConstants:
    """Tests for MiniMax constants."""

    def test_api_base_url(self):
        assert MINIMAX_API_BASE_URL == "https://api.minimax.io/v1"

    def test_default_model(self):
        assert MINIMAX_DEFAULT_MODEL == "MiniMax-M2.7"


class TestGetClientMiniMax:
    """Tests for get_client() with MiniMax config."""

    @patch("ii_agent.llm.openai.openai.OpenAI")
    def test_returns_minimax_client(self, mock_openai_cls):
        from ii_agent.llm import get_client

        config = LLMConfig(
            model="MiniMax-M2.7",
            api_key=SecretStr("test-key"),
            api_type=APITypes.MINIMAX,
        )
        client = get_client(config)
        assert isinstance(client, MiniMaxDirectClient)

    def test_minimax_in_api_types(self):
        assert hasattr(APITypes, "MINIMAX")
        assert APITypes.MINIMAX.value == "minimax"
