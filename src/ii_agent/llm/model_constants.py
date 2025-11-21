"""
Model-specific constants for context windows and performance thresholds.

Shared by context_manager and context_cliff_benchmark to avoid circular imports.
"""

# Model context window sizes (tokens)
CONTEXT_WINDOWS = {
    # Anthropic
    "claude-3-5-sonnet-20241022": 200_000,
    "claude-3-5-haiku-20241022": 200_000,
    "claude-3-opus-20240229": 200_000,
    "claude-3-sonnet-20240229": 200_000,
    "claude-3-haiku-20240307": 200_000,
    "claude-3-7-sonnet-20250219": 200_000,

    # OpenAI
    "gpt-4-turbo": 128_000,
    "gpt-4": 8_192,
    "gpt-3.5-turbo": 16_385,
    "gpt-4o": 128_000,
    "gpt-4o-mini": 128_000,
    "gpt-4.1": 1_000_000,

    # Google
    "gemini-1.5-pro": 1_000_000,
    "gemini-1.5-flash": 1_000_000,
    "gemini-2.5-pro": 1_000_000,
    "gemini-2.0-flash": 1_000_000,
    "gemini-pro": 32_768,

    # Llama
    "meta/llama-3.1-405b-instruct": 128_000,
    "meta/llama-3.1-70b-instruct": 128_000,
    "meta/llama-4-maverick": 1_000_000,
    "llama-4-scout": 10_000_000,  # 10M advertised, 256K trained

    # DeepSeek
    "deepseek/deepseek-chat-v3.1": 128_000,

    # Default
    "default": 128_000,
}


# Model performance cliffs - tokens where accuracy drops significantly
# Based on empirical testing: 30-50% of advertised is typically effective limit
PERFORMANCE_CLIFFS = {
    "Claude 3.5 Sonnet": {
        "early_degradation": 32_000,    # Copyright failures spike 3.7% → 21%
        "moderate_cliff": 64_000,       # Drops 91.7% → 81.3% accuracy
        "severe_cliff": 120_000,        # Severe degradation begins
    },
    "Claude 3.7 Sonnet": {
        "early_degradation": 8_000,     # 30-40% degradation on multi-hop reasoning
        "moderate_cliff": 40_000,       # Reasoning wall for complex tasks
        "severe_cliff": 64_000,
    },
    "GPT-4o": {
        "early_degradation": 15_000,    # Performance degrades despite good recall
        "moderate_cliff": 30_000,       # 24.2% accuracy drop even with perfect retrieval
        "severe_cliff": 64_000,
        "effective_limit": 30_000,      # ~30% of claimed 128K
    },
    "GPT-4.1": {
        "early_degradation": 100_000,   # Response time skyrockets 50x
        "moderate_cliff": 133_000,      # Accuracy drops 12-31% on reasoning
        "severe_cliff": 200_000,
        "effective_limit": 100_000,     # ~10% of claimed 1M
    },
    "Gemini 1.5 Pro/Flash": {
        "early_degradation": 400_000,   # Accuracy drops below 95%
        "moderate_cliff": 500_000,      # Falls to 87% accuracy
        "severe_cliff": 900_000,        # Drops to 84% accuracy
        "effective_limit": 500_000,     # 50% of claimed 1M (best in class)
    },
    "Gemini 2.5 Pro": {
        "early_degradation": 150_000,   # Still excellent at 128K (90.6% accuracy)
        "moderate_cliff": 200_000,      # Degradation begins on complex reasoning
        "severe_cliff": 400_000,
        "effective_limit": 200_000,     # 20% of claimed 1M
    },
    "Llama 3.1": {
        "early_degradation": 30_000,    # Shows 24.2% accuracy drop on reasoning
        "moderate_cliff": 50_000,
        "severe_cliff": 100_000,
        "effective_limit": 40_000,      # 30-40% of claimed 128K
    },
    "Llama 4 Maverick": {
        "early_degradation": 40_000,    # Performance degradation begins
        "moderate_cliff": 128_000,      # Steep cliff at claimed window
        "severe_cliff": 256_000,        # Beyond trained context
        "catastrophic": 300_000,        # Complete failure
        "effective_limit": 64_000,      # ~6% of claimed 1M
    },
    "Llama 4 Scout": {
        "early_degradation": 100_000,   # "Attention cliff" - retrieval fails
        "catastrophic": 256_000,        # Virtual context limit
        "effective_limit": 128_000,     # ~1.3% of claimed 10M (marketing)
        "notes": "Pre-filling works, retrieval fails. Advertised 10M is marketing fiction."
    },
    "Default": {
        "early_degradation": 30_000,    # Conservative default
        "moderate_cliff": 64_000,
        "severe_cliff": 100_000,
        "effective_limit": 40_000,      # ~40% of typical 128K claim
    },
}
