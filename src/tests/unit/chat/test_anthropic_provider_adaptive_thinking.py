"""Tests for AnthropicProvider adaptive thinking parameters.

Verifies that _prepare_request_params correctly routes to adaptive thinking
for Opus 4.7+ models vs. legacy budget_tokens for older models.
"""

from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from pydantic import SecretStr

from ii_agent.chat.llm.anthropic.provider import AnthropicProvider
from ii_agent.settings.llm.schemas import ModelConfig, ModelParams

pytestmark = pytest.mark.unit


def _make_provider(model_id: str, thinking_tokens: int = 2048) -> AnthropicProvider:
    """Build a minimal AnthropicProvider with the given model and thinking config."""
    params = ModelParams(temperature=0.7, thinking_tokens=thinking_tokens)
    config = ModelConfig(
        id=uuid.uuid4(),
        model_id=model_id,
        provider="Anthropic",
        api_key=SecretStr("sk-test-key"),
        params=params,
    )
    with patch("anthropic.AsyncAnthropic"):
        return AnthropicProvider(llm_config=config)


def _minimal_messages():
    """Return a minimal messages list for _prepare_request_params."""
    from ii_agent.chat.types import Message, MessageRole, TextContent
    import uuid

    return [
        Message(
            id=uuid.uuid4(),
            role=MessageRole.USER,
            session_id=uuid.uuid4(),
            parts=[TextContent(text="Hello")],
        )
    ]


class TestAdaptiveThinkingParams:
    """Verify _prepare_request_params routes correctly based on model."""

    @pytest.mark.parametrize(
        "model_id",
        [
            "claude-opus-5",
            "claude-opus-4-8",
            "claude-opus-4-7",
            "claude-opus-4-7-20260415",
            "claude-fable-5",
        ],
    )
    @patch(
        "ii_agent.chat.llm.anthropic.provider.convert_to_anthropic_messages",
        return_value=("system", [{"role": "user", "content": "hi"}], []),
    )
    def test_adaptive_model_uses_adaptive_thinking(self, mock_convert, model_id: str):
        """Opus 4.7+ models use adaptive thinking with output_config.effort."""
        provider = _make_provider(model_id, thinking_tokens=2048)
        params, betas = provider._prepare_request_params(
            messages=_minimal_messages(),
            tools=[
                {
                    "type": "function",
                    "function": {"name": "tool1", "description": "a tool", "parameters": {}},
                }
            ],
        )

        assert params["thinking"] == {"type": "adaptive", "display": "summarized"}
        assert params["output_config"] == {"effort": "high"}
        assert params["max_tokens"] == 64_000
        # Adaptive models should NOT have interleaved-thinking beta
        assert "interleaved-thinking-2025-05-14" not in betas

    @patch(
        "ii_agent.chat.llm.anthropic.provider.convert_to_anthropic_messages",
        return_value=("system", [{"role": "user", "content": "hi"}], []),
    )
    def test_legacy_model_uses_budget_tokens(self, mock_convert):
        """Pre-Opus-4.7 models use enabled + budget_tokens."""
        provider = _make_provider("claude-sonnet-4-5", thinking_tokens=4096)
        params, betas = provider._prepare_request_params(
            messages=_minimal_messages(),
            tools=[
                {
                    "type": "function",
                    "function": {"name": "tool1", "description": "a tool", "parameters": {}},
                }
            ],
        )

        assert params["thinking"] == {"type": "enabled", "budget_tokens": 4096}
        assert "output_config" not in params
        assert "interleaved-thinking-2025-05-14" in betas

    @patch(
        "ii_agent.chat.llm.anthropic.provider.convert_to_anthropic_messages",
        return_value=("system", [{"role": "user", "content": "hi"}], []),
    )
    def test_adaptive_model_without_thinking_uses_temperature(self, mock_convert):
        """Adaptive model with thinking_tokens=0 (disabled) still gets temperature."""
        provider = _make_provider("claude-opus-5", thinking_tokens=0)
        params, betas = provider._prepare_request_params(
            messages=_minimal_messages(),
            tools=None,
        )

        assert "thinking" not in params
        assert "output_config" not in params
        assert params.get("temperature") == 0.7

    @patch(
        "ii_agent.chat.llm.anthropic.provider.convert_to_anthropic_messages",
        return_value=("system", [{"role": "user", "content": "hi"}], []),
    )
    def test_adaptive_model_thinking_below_threshold_uses_temperature(self, mock_convert):
        """Adaptive model with thinking_tokens < 1024 does not enable thinking."""
        provider = _make_provider("claude-opus-4-8", thinking_tokens=512)
        params, betas = provider._prepare_request_params(
            messages=_minimal_messages(),
            tools=None,
        )

        assert "thinking" not in params
        assert params.get("temperature") == 0.7
