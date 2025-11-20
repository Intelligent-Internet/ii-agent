"""Test model-specific checkpoint thresholds."""

from ii_agent.server.chat.context_manager import (
    calculate_checkpoint_threshold,
    CONTEXT_WINDOWS,
)


def test_checkpoint_threshold_gradient():
    """Test threshold gradient from 64K (90%) to 1MB (15%)."""

    # Test bounds
    assert calculate_checkpoint_threshold(64_000) == 0.90
    assert calculate_checkpoint_threshold(1_000_000) == 0.15

    # Test below minimum
    assert calculate_checkpoint_threshold(32_000) == 0.90

    # Test above maximum
    assert calculate_checkpoint_threshold(2_000_000) == 0.15

    # Test intermediate values (log-scale interpolation)
    threshold_128k = calculate_checkpoint_threshold(128_000)
    threshold_200k = calculate_checkpoint_threshold(200_000)
    threshold_500k = calculate_checkpoint_threshold(500_000)

    # Verify decreasing thresholds
    assert threshold_128k < 0.90
    assert threshold_200k < threshold_128k
    assert threshold_500k < threshold_200k
    assert threshold_500k > 0.15

    print(f"\n64K:   {calculate_checkpoint_threshold(64_000):.1%}")
    print(f"128K:  {threshold_128k:.1%}")
    print(f"200K:  {threshold_200k:.1%}")
    print(f"500K:  {threshold_500k:.1%}")
    print(f"1MB:   {calculate_checkpoint_threshold(1_000_000):.1%}")


def test_model_specific_thresholds():
    """Test threshold calculation for specific models."""

    # GPT-4 (8K context - very small)
    gpt4_threshold = calculate_checkpoint_threshold(CONTEXT_WINDOWS["gpt-4"])
    assert gpt4_threshold == 0.90  # Below minimum, use 90%

    # GPT-4o (128K context)
    gpt4o_threshold = calculate_checkpoint_threshold(CONTEXT_WINDOWS["gpt-4o"])
    assert 0.60 < gpt4o_threshold < 0.90

    # Claude (200K context)
    claude_threshold = calculate_checkpoint_threshold(CONTEXT_WINDOWS["claude-3-5-sonnet-20241022"])
    assert 0.50 < claude_threshold < 0.80

    # Gemini 1.5 (1MB context)
    gemini_threshold = calculate_checkpoint_threshold(CONTEXT_WINDOWS["gemini-1.5-pro"])
    assert gemini_threshold == 0.15  # At maximum, use 15%

    print(f"\nModel-specific thresholds:")
    print(f"GPT-4 (8K):           {gpt4_threshold:.1%}")
    print(f"GPT-4o (128K):        {gpt4o_threshold:.1%}")
    print(f"Claude (200K):        {claude_threshold:.1%}")
    print(f"Gemini 1.5 (1MB):     {gemini_threshold:.1%}")


def test_checkpoint_token_calculations():
    """Test actual token thresholds for different models."""

    test_models = [
        ("gpt-4", 8_192),
        ("gpt-4o", 128_000),
        ("claude-3-5-sonnet-20241022", 200_000),
        ("gemini-1.5-pro", 1_000_000),
    ]

    print(f"\nCheckpoint token thresholds:")
    print(f"{'Model':<30} {'Window':<10} {'Threshold %':<15} {'Checkpoint at':<15}")
    print("-" * 75)

    for model_id, window in test_models:
        threshold_pct = calculate_checkpoint_threshold(window)
        checkpoint_tokens = int(window * threshold_pct)

        print(f"{model_id:<30} {window:<10} {threshold_pct:.1%}{'':>11} {checkpoint_tokens:>10,} tokens")


if __name__ == "__main__":
    test_checkpoint_threshold_gradient()
    test_model_specific_thresholds()
    test_checkpoint_token_calculations()
