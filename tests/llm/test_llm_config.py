"""Unit tests for LLMConfig class.

Tests the configuration helpers including get_max_output_tokens and get_max_context_tokens.
"""

import pytest
from ii_agent.core.config.llm_config import LLMConfig, APITypes


class TestLLMConfigGetMaxOutputTokens:
    """Tests for LLMConfig.get_max_output_tokens method."""

    # Anthropic models
    def test_anthropic_claude_4_returns_64k(self):
        """Claude 4.x models should return 64K output tokens."""
        config = LLMConfig(
            model="claude-sonnet-4-20250514",
            api_type=APITypes.ANTHROPIC,
        )
        assert config.get_max_output_tokens() == 65536

    def test_anthropic_claude_opus_4_returns_64k(self):
        """Claude Opus 4 should return 64K output tokens."""
        config = LLMConfig(
            model="claude-opus-4-20250514",
            api_type=APITypes.ANTHROPIC,
        )
        assert config.get_max_output_tokens() == 65536

    def test_anthropic_claude_3_returns_4k(self):
        """Claude 3.x models should return 4K output tokens."""
        config = LLMConfig(
            model="claude-3-sonnet-20240229",
            api_type=APITypes.ANTHROPIC,
        )
        assert config.get_max_output_tokens() == 4096

    def test_anthropic_claude_35_returns_4k(self):
        """Claude 3.5 models should return 4K output tokens (still claude-3 family)."""
        config = LLMConfig(
            model="claude-3-5-sonnet-20241022",
            api_type=APITypes.ANTHROPIC,
        )
        assert config.get_max_output_tokens() == 4096

    # OpenAI models
    def test_openai_o1_preview_returns_32k(self):
        """o1-preview should return 32K output tokens."""
        config = LLMConfig(
            model="o1-preview",
            api_type=APITypes.OPENAI,
        )
        assert config.get_max_output_tokens() == 32768

    def test_openai_o1_returns_100k(self):
        """o1 should return 100K output tokens."""
        config = LLMConfig(
            model="o1",
            api_type=APITypes.OPENAI,
        )
        assert config.get_max_output_tokens() == 100000

    def test_openai_o1_mini_returns_100k(self):
        """o1-mini should return 100K output tokens."""
        config = LLMConfig(
            model="o1-mini",
            api_type=APITypes.OPENAI,
        )
        assert config.get_max_output_tokens() == 100000

    def test_openai_o3_mini_returns_16k(self):
        """o3-mini should return 16K output tokens."""
        config = LLMConfig(
            model="o3-mini",
            api_type=APITypes.OPENAI,
        )
        assert config.get_max_output_tokens() == 16384

    def test_openai_o4_mini_returns_16k(self):
        """o4-mini should return 16K output tokens."""
        config = LLMConfig(
            model="o4-mini",
            api_type=APITypes.OPENAI,
        )
        assert config.get_max_output_tokens() == 16384

    def test_openai_gpt4o_returns_16k(self):
        """GPT-4o should return 16K output tokens."""
        config = LLMConfig(
            model="gpt-4o",
            api_type=APITypes.OPENAI,
        )
        assert config.get_max_output_tokens() == 16384

    def test_openai_gpt4_turbo_returns_16k(self):
        """GPT-4-turbo should return 16K output tokens."""
        config = LLMConfig(
            model="gpt-4-turbo",
            api_type=APITypes.OPENAI,
        )
        assert config.get_max_output_tokens() == 16384

    def test_openai_gpt35_returns_4k(self):
        """GPT-3.5 should return default 4K output tokens."""
        config = LLMConfig(
            model="gpt-3.5-turbo",
            api_type=APITypes.OPENAI,
        )
        assert config.get_max_output_tokens() == 4096

    # Gemini models
    def test_gemini_returns_8k(self):
        """Gemini models should return 8K output tokens."""
        config = LLMConfig(
            model="gemini-1.5-pro",
            api_type=APITypes.GEMINI,
        )
        assert config.get_max_output_tokens() == 8192

    # Custom/unknown models
    def test_custom_returns_4k_default(self):
        """Custom/unknown API types should return conservative 4K default."""
        config = LLMConfig(
            model="some-custom-model",
            api_type=APITypes.CUSTOM,
        )
        assert config.get_max_output_tokens() == 4096


class TestLLMConfigGetMaxContextTokens:
    """Tests for LLMConfig.get_max_context_tokens method."""

    def test_anthropic_standard_context(self):
        """Standard Anthropic models should return 200K context."""
        config = LLMConfig(
            model="claude-sonnet-4-20250514",
            api_type=APITypes.ANTHROPIC,
            enable_extended_context=False,
        )
        assert config.get_max_context_tokens() == 200_000

    def test_anthropic_extended_context(self):
        """Anthropic with extended context should return 1M context."""
        config = LLMConfig(
            model="claude-sonnet-4-20250514",
            api_type=APITypes.ANTHROPIC,
            enable_extended_context=True,
        )
        assert config.get_max_context_tokens() == 1_000_000

    def test_openai_default_context(self):
        """OpenAI models should return 128K default context."""
        config = LLMConfig(
            model="gpt-4o",
            api_type=APITypes.OPENAI,
        )
        assert config.get_max_context_tokens() == 128_000

    def test_gemini_default_context(self):
        """Gemini models should return 128K default context."""
        config = LLMConfig(
            model="gemini-1.5-pro",
            api_type=APITypes.GEMINI,
        )
        assert config.get_max_context_tokens() == 128_000


class TestLLMConfigEnableExtendedContext:
    """Tests for the enable_extended_context field."""

    def test_enable_extended_context_default_false(self):
        """enable_extended_context should default to False."""
        config = LLMConfig(model="test-model")
        assert config.enable_extended_context is False

    def test_enable_extended_context_can_be_set_true(self):
        """enable_extended_context can be set to True."""
        config = LLMConfig(model="test-model", enable_extended_context=True)
        assert config.enable_extended_context is True
