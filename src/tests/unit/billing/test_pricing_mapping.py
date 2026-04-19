import pytest

from ii_agent.settings.llm import PricingInfo
from ii_agent.settings.llm import Provider

pytestmark = pytest.mark.unit


def test_pricing_exact_and_prefix_model_match():
    exact = PricingInfo.get_default_pricing("gpt-4o")
    prefix = PricingInfo.get_default_pricing("claude-sonnet-4-5-20250929")

    assert exact.input_price_per_million == 2.5
    assert prefix.input_price_per_million == 3.0


def test_pricing_provider_fallback_when_unknown_model():
    pricing = PricingInfo.get_default_pricing("unknown-model", provider=Provider.GOOGLE)

    assert pricing.input_price_per_million == 0.15
    assert pricing.is_fallback is True


def test_pricing_global_default_without_provider():
    pricing = PricingInfo.get_default_pricing("totally-unknown")

    assert pricing.input_price_per_million == 2.5
    assert pricing.output_price_per_million == 10.0


def test_pricing_case_insensitive():
    """Model IDs are normalized to lowercase for matching."""
    # Use a model whose pricing differs from the global default (2.5/10.0)
    # so the test distinguishes a real match from a fallback.
    pricing = PricingInfo.get_default_pricing("CLAUDE-SONNET-4-5")

    assert pricing.input_price_per_million == 3.0
    assert pricing.output_price_per_million == 15.0


@pytest.mark.parametrize(
    "model_id,expected_input,expected_output",
    [
        ("claude-opus-4-7", 5.0, 25.0),
        ("claude-opus-4-6", 5.0, 25.0),
        ("claude-opus-4-5", 5.0, 25.0),
        ("claude-sonnet-4-5", 3.0, 15.0),
        ("claude-sonnet-4", 3.0, 15.0),
        ("claude-opus-4", 15.0, 75.0),
        ("claude-3-5-haiku", 0.8, 4.0),
        ("gpt-4o", 2.5, 10.0),
        ("gpt-4o-mini", 0.15, 0.6),
        ("o1", 15.0, 60.0),
        ("o3", 10.0, 40.0),
        ("gemini-2.5-pro", 1.25, 10.0),
        ("gemini-2.0-flash", 0.1, 0.4),
        ("deepseek-reasoner", 0.55, 2.19),
        ("deepseek-chat", 0.27, 1.1),
    ],
)
def test_pricing_all_known_models(model_id, expected_input, expected_output):
    """Every known model ID returns correct input/output pricing."""
    pricing = PricingInfo.get_default_pricing(model_id)

    assert pricing.input_price_per_million == expected_input
    assert pricing.output_price_per_million == expected_output


def test_pricing_prefix_match_returns_correct_pricing():
    """Prefix-matched pricing returns the correct pricing values."""
    pricing = PricingInfo.get_default_pricing("claude-opus-4-5-20250101")

    assert pricing.input_price_per_million == 5.0
    assert pricing.output_price_per_million == 25.0
    assert pricing.is_fallback is False


def test_pricing_anthropic_has_cache_write():
    """Anthropic models have non-zero cache_write pricing."""
    pricing = PricingInfo.get_default_pricing("claude-sonnet-4-5")

    assert pricing.cache_write_price_per_million > 0
    assert pricing.cache_read_price_per_million > 0


def test_pricing_openai_no_cache_write():
    """OpenAI models have zero cache_write pricing."""
    pricing = PricingInfo.get_default_pricing("gpt-4o")

    assert pricing.cache_write_price_per_million == 0.0
    assert pricing.cache_read_price_per_million > 0


def test_pricing_provider_default_openai():
    """Unknown OpenAI model gets OpenAI provider defaults."""
    pricing = PricingInfo.get_default_pricing("gpt-future", provider=Provider.OPENAI)

    assert pricing.input_price_per_million == 2.5
    assert pricing.is_fallback is True


def test_pricing_provider_default_anthropic():
    """Unknown Anthropic model gets Anthropic provider defaults."""
    pricing = PricingInfo.get_default_pricing("claude-future", provider=Provider.ANTHROPIC)

    assert pricing.input_price_per_million == 3.0
    assert pricing.cache_write_price_per_million == 3.75
    assert pricing.is_fallback is True
