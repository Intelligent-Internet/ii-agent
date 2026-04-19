"""Regression tests for ``ii_agent.agents.models.utils`` builder functions.

These tests pin down a failure mode that broke every deep-research session
using extended thinking:

    Anthropic rejects ``temperature`` with a 400
    ``invalid_request_error`` ("temperature may only be set to 1 when
    thinking is enabled") whenever the request body carries both a
    non-1 ``temperature`` and an ``enabled`` ``thinking`` block.

Both ``_build_anthropic_direct`` and ``_build_anthropic_vertex`` hardcode
``thinking={"type": "enabled", "budget_tokens": 16000}`` and therefore
must not forward ``llm_config.temperature``.  The native-LLM fallback
path relies on this invariant — a stray temperature value would make
every fallback attempt 400-loop until retries are exhausted.
"""

from __future__ import annotations

from ii_agent.agents.models.utils import (
    _build_anthropic_direct,
    _build_anthropic_vertex,
)
from ii_agent.core.config.llm_config import LLMConfig
from ii_agent.settings.llm import Provider
from ii_agent.settings.llm.types import ApiType


def _llm_config(temperature: float) -> LLMConfig:
    return LLMConfig(
        model="claude-sonnet-4-5-20250929",
        provider=Provider.ANTHROPIC,
        temperature=temperature,
        thinking_tokens=16000,
        max_retries=3,
    )


class TestBuildAnthropicDirect:
    def test_does_not_forward_non_one_temperature(self):
        cfg = _llm_config(temperature=0.7)
        model = _build_anthropic_direct(api_key="test-key", llm_config=cfg)
        # temperature must NOT be carried onto the model instance because
        # thinking is unconditionally enabled here.
        assert model.temperature is None

    def test_does_not_forward_zero_temperature(self):
        cfg = _llm_config(temperature=0.0)
        model = _build_anthropic_direct(api_key="test-key", llm_config=cfg)
        assert model.temperature is None

    def test_thinking_is_enabled(self):
        cfg = _llm_config(temperature=0.5)
        model = _build_anthropic_direct(api_key="test-key", llm_config=cfg)
        assert model.thinking == {"type": "enabled", "budget_tokens": 16_000}

    def test_request_params_have_no_temperature(self):
        cfg = _llm_config(temperature=0.9)
        model = _build_anthropic_direct(api_key="test-key", llm_config=cfg)
        params = model.get_request_params()
        assert "thinking" in params
        assert "temperature" not in params


class TestBuildAnthropicVertex:
    def _vertex_config(self, temperature: float) -> LLMConfig:
        return LLMConfig(
            model="claude-sonnet-4-5@20250929",
            provider=Provider.ANTHROPIC,
            api_type=ApiType.VERTEX_AI,
            temperature=temperature,
            thinking_tokens=16000,
            vertex_region="global",
            vertex_project_id="test-project",
            max_retries=3,
        )

    def test_does_not_forward_non_one_temperature(self):
        cfg = self._vertex_config(temperature=0.7)
        model = _build_anthropic_vertex(api_key=None, llm_config=cfg)
        assert model.temperature is None

    def test_thinking_is_enabled(self):
        cfg = self._vertex_config(temperature=0.5)
        model = _build_anthropic_vertex(api_key=None, llm_config=cfg)
        assert model.thinking == {"type": "enabled", "budget_tokens": 16_000}

    def test_request_params_have_no_temperature(self):
        cfg = self._vertex_config(temperature=0.9)
        model = _build_anthropic_vertex(api_key=None, llm_config=cfg)
        params = model.get_request_params()
        assert "thinking" in params
        assert "temperature" not in params
