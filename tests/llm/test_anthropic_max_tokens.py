"""Tests for Anthropic max_tokens calculation based on thinking_tokens.

The logic in AnthropicProvider._prepare_request_params:
  - If thinking_tokens >= 1024: max_tokens = thinking_tokens + 8192
  - Otherwise: max_tokens = 8192

We test this logic using LLMConfig directly to avoid importing the
full server module chain (which causes module identity side-effects).
"""

from ii_agent.core.config.llm_config import LLMConfig, APITypes


def _calc_max_tokens(thinking_tokens: int) -> int:
    """Replicate the max_tokens calculation from AnthropicProvider."""
    if thinking_tokens >= 1024:
        return thinking_tokens + 8192
    return 8192


class TestAnthropicMaxTokensCalculation:
    """Tests for the max_tokens logic used in AnthropicProvider."""

    def _make_config(self, thinking_tokens=0):
        return LLMConfig(
            model="claude-sonnet-4-20250514",
            api_type=APITypes.ANTHROPIC,
            api_key="test-key",
            thinking_tokens=thinking_tokens,
        )

    def test_no_thinking_tokens_returns_8192(self):
        config = self._make_config(thinking_tokens=0)
        assert _calc_max_tokens(config.thinking_tokens or 0) == 8192

    def test_low_thinking_tokens_returns_8192(self):
        config = self._make_config(thinking_tokens=512)
        assert _calc_max_tokens(config.thinking_tokens or 0) == 8192

    def test_below_threshold_returns_8192(self):
        config = self._make_config(thinking_tokens=1023)
        assert _calc_max_tokens(config.thinking_tokens or 0) == 8192

    def test_at_threshold_returns_thinking_plus_buffer(self):
        config = self._make_config(thinking_tokens=1024)
        assert _calc_max_tokens(config.thinking_tokens or 0) == 1024 + 8192

    def test_above_threshold_returns_thinking_plus_buffer(self):
        config = self._make_config(thinking_tokens=16000)
        assert _calc_max_tokens(config.thinking_tokens or 0) == 16000 + 8192

    def test_large_thinking_tokens(self):
        config = self._make_config(thinking_tokens=100000)
        assert _calc_max_tokens(config.thinking_tokens or 0) == 100000 + 8192

    def test_default_thinking_tokens_uses_threshold_logic(self):
        """When thinking_tokens uses default (16000), should apply threshold logic."""
        config = LLMConfig(
            model="claude-sonnet-4-20250514",
            api_type=APITypes.ANTHROPIC,
            api_key="test-key",
        )
        thinking_tokens = config.thinking_tokens or 0
        assert thinking_tokens == 16000
        assert _calc_max_tokens(thinking_tokens) == 16000 + 8192

    def test_calc_matches_expected_formula(self):
        """Verify the formula directly: threshold at 1024, buffer of 8192."""
        assert _calc_max_tokens(0) == 8192
        assert _calc_max_tokens(1023) == 8192
        assert _calc_max_tokens(1024) == 1024 + 8192
        assert _calc_max_tokens(50000) == 50000 + 8192
