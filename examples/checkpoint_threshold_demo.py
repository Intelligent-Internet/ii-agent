"""Demonstrate model-specific checkpoint thresholds."""

import math


def calculate_checkpoint_threshold(context_window: int) -> float:
    """
    Calculate checkpoint threshold based on context window size.

    Gradient scale:
    - 64K context → 90% threshold (aggressive checkpointing)
    - 1MB context → 15% threshold (relaxed checkpointing)
    """
    MIN_WINDOW = 64_000
    MAX_WINDOW = 1_000_000

    MIN_THRESHOLD = 0.90
    MAX_THRESHOLD = 0.15

    if context_window <= MIN_WINDOW:
        return MIN_THRESHOLD
    if context_window >= MAX_WINDOW:
        return MAX_THRESHOLD

    log_min = math.log(MIN_WINDOW)
    log_max = math.log(MAX_WINDOW)
    log_current = math.log(context_window)

    normalized = (log_current - log_min) / (log_max - log_min)
    threshold = MIN_THRESHOLD - (normalized * (MIN_THRESHOLD - MAX_THRESHOLD))

    return threshold


# Model context windows
MODELS = {
    "gpt-4": 8_192,
    "gpt-3.5-turbo": 16_385,
    "gpt-4-turbo": 128_000,
    "gpt-4o": 128_000,
    "claude-3-5-sonnet": 200_000,
    "claude-3-opus": 200_000,
    "gemini-pro": 32_768,
    "gemini-1.5-pro": 1_000_000,
}


print("Model-Specific Checkpoint Thresholds")
print("=" * 80)
print(f"{'Model':<25} {'Window':<12} {'Threshold':<12} {'Checkpoint at':<15}")
print("-" * 80)

for model_id, window in sorted(MODELS.items(), key=lambda x: x[1]):
    threshold_pct = calculate_checkpoint_threshold(window)
    checkpoint_tokens = int(window * threshold_pct)

    print(
        f"{model_id:<25} {window:>10,}  "
        f"{threshold_pct:>10.1%}  "
        f"{checkpoint_tokens:>12,} tokens"
    )

print("\n" + "=" * 80)
print("\nKey Insights:")
print("- Smaller windows (8K-64K) use 90% threshold - aggressive checkpointing")
print("- Medium windows (128K-200K) use 65-75% threshold - balanced")
print("- Large windows (1MB) use 15% threshold - relaxed checkpointing")
print("\nRationale:")
print("- Smaller windows need aggressive checkpointing to avoid hitting limits")
print("- Larger windows have more headroom for context pressure")
print("- Log-scale gradient accounts for exponential growth in model capabilities")
