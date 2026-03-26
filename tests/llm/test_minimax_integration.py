"""Integration tests for MiniMax LLM client (require MINIMAX_API_KEY)."""

import os
import pytest
from pydantic import SecretStr

from ii_agent.llm.minimax import MiniMaxDirectClient, _strip_think_tags
from ii_agent.llm.base import TextResult, ToolCall, TextPrompt, ToolParam
from ii_agent.core.config.llm_config import LLMConfig, APITypes

MINIMAX_API_KEY = os.environ.get("MINIMAX_API_KEY", "")

pytestmark = pytest.mark.skipif(
    not MINIMAX_API_KEY, reason="MINIMAX_API_KEY not set"
)


def _make_client(model: str = "MiniMax-M2.7") -> MiniMaxDirectClient:
    config = LLMConfig(
        model=model,
        api_key=SecretStr(MINIMAX_API_KEY),
        api_type=APITypes.MINIMAX,
    )
    return MiniMaxDirectClient(config)


class TestMiniMaxIntegration:
    """Integration tests against live MiniMax API."""

    def test_simple_text_generation(self):
        client = _make_client()
        messages = [[TextPrompt(text="Say 'hello' and nothing else.")]]
        outputs, metadata = client.generate(
            messages=messages,
            max_tokens=1024,
            temperature=0.01,
        )
        assert len(outputs) > 0
        assert isinstance(outputs[0], TextResult)
        # Verify no think tags leaked through
        assert "<think>" not in outputs[0].text
        assert metadata.get("input_tokens", 0) > 0

    def test_tool_calling(self):
        client = _make_client()
        tool = ToolParam(
            name="get_weather",
            description="Get weather for a city",
            input_schema={
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "City name"},
                },
                "required": ["city"],
                "additionalProperties": False,
            },
        )
        messages = [[TextPrompt(text="What's the weather in Tokyo?")]]
        outputs, metadata = client.generate(
            messages=messages,
            max_tokens=1024,
            tools=[tool],
            temperature=0.01,
        )
        assert len(outputs) > 0
        has_tool_call = any(isinstance(o, ToolCall) for o in outputs)
        assert has_tool_call, "Expected a tool call in response"
        tool_call = next(o for o in outputs if isinstance(o, ToolCall))
        assert tool_call.tool_name == "get_weather"
        assert "city" in tool_call.tool_input

    def test_highspeed_model(self):
        client = _make_client("MiniMax-M2.7-highspeed")
        messages = [[TextPrompt(text="Reply with the word 'fast'.")]]
        outputs, metadata = client.generate(
            messages=messages,
            max_tokens=1024,
            temperature=0.01,
        )
        assert len(outputs) > 0
        assert isinstance(outputs[0], TextResult)
        assert "<think>" not in outputs[0].text
