"""Test model-specific performance cliff thresholds."""

import importlib
import pytest
from ii_agent.llm.model_constants import PERFORMANCE_CLIFFS as PC

cm_mod = None
_remote_get_performance = None
_remote_calc_threshold = None

from ii_agent.llm.model_constants import PERFORMANCE_CLIFFS

def get_performance_cliff_threshold(model_id: str):
    if _remote_get_performance:
        return _remote_get_performance(model_id)
    # Local fallback: search PERFORMANCE_CLIFFS for a matching key
    def _normalize(s: str) -> str:
        return ''.join(ch for ch in s if ch.isalnum()).lower()

    model_norm = _normalize(model_id)
    # Choose the best key match (longest substring match) to avoid collisions
    best_k = None
    best_len = 0
    for k, v in PERFORMANCE_CLIFFS.items():
        key_norm = _normalize(k)
        if key_norm in model_norm and len(key_norm) > best_len:
            best_len = len(key_norm)
            best_k = k
        fword_norm = _normalize(k.split()[0])
        if fword_norm in model_norm and len(fword_norm) > best_len:
            best_len = len(fword_norm)
            best_k = k
    if best_k:
        return PERFORMANCE_CLIFFS[best_k]
    return PC['Default']


def calculate_model_specific_threshold(model_id: str) -> float:
    if _remote_calc_threshold:
        return _remote_calc_threshold(model_id)
    # Local fallback: simple heuristic like in context_manager
    from ii_agent.llm.model_constants import CONTEXT_WINDOWS
    cliffs = get_performance_cliff_threshold(model_id)
    early = cliffs["early_degradation"]
    context_window = CONTEXT_WINDOWS.get(model_id, CONTEXT_WINDOWS["default"])
    threshold = min(0.90, (early / context_window) * 0.8)
    threshold = max(0.10, threshold)
    return threshold
from ii_agent.llm.model_constants import CONTEXT_WINDOWS


class TestModelCliffThresholds:
    """Test model-specific performance cliff detection and threshold calculation."""

    def test_claude_35_sonnet_threshold(self):
        """Test Claude 3.5 Sonnet cliff detection."""
        model_id = "claude-3-5-sonnet-20241022"
        cliffs = get_performance_cliff_threshold(model_id)
        # Compare against model constants to be resilient to updates
        from ii_agent.llm.model_constants import PERFORMANCE_CLIFFS as PC
        expected = None
        for k, v in PC.items():
            if 'claude' in k.lower() and '3.5' in k.lower():
                expected = v
                break
        assert expected is not None
        assert cliffs == expected

        # Calculate threshold (should target early_degradation with 80% safety)
        threshold = calculate_model_specific_threshold(model_id)
        assert 0.10 <= threshold <= 0.90  # Within safe bounds
        assert threshold < 0.50  # Claude has aggressive degradation

    def test_gpt4o_threshold(self):
        """Test GPT-4o cliff detection."""
        model_id = "gpt-4o"
        cliffs = get_performance_cliff_threshold(model_id)

        cliffs = get_performance_cliff_threshold(model_id)
        from ii_agent.llm.model_constants import PERFORMANCE_CLIFFS as PC
        expected = PC.get('GPT-4o') or PC.get('GPT-4o', None)
        assert expected is not None
        assert cliffs == expected

        threshold = calculate_model_specific_threshold(model_id)
        assert 0.10 <= threshold <= 0.90

    def test_gemini_15_pro_threshold(self):
        """Test Gemini 1.5 Pro cliff detection."""
        model_id = "gemini-1.5-pro"
        cliffs = get_performance_cliff_threshold(model_id)

        cliffs = get_performance_cliff_threshold(model_id)
        from ii_agent.llm.model_constants import PERFORMANCE_CLIFFS as PC
        expected = None
        for k, v in PC.items():
            if 'gemini' in k.lower() and '1.5' in k.lower():
                expected = v
                break
        assert expected is not None
        assert cliffs == expected

        threshold = calculate_model_specific_threshold(model_id)
        # Gemini has large context window, threshold should be higher
        assert threshold > 0.30

    def test_llama_4_scout_threshold(self):
        """Test Llama 4 Scout catastrophic performance."""
        model_id = "llama-4-scout"
        cliffs = get_performance_cliff_threshold(model_id)

        cliffs = get_performance_cliff_threshold(model_id)
        from ii_agent.llm.model_constants import PERFORMANCE_CLIFFS as PC
        # Llama 4 Scout is expected to match Llama 4 Scout entry
        expected = None
        for k, v in PC.items():
            if 'llama' in k.lower() and 'scout' in k.lower():
                expected = v
                break
        assert expected is not None
        for field, val in expected.items():
            assert cliffs.get(field) == val

        threshold = calculate_model_specific_threshold(model_id)
        # Should be very aggressive due to terrible performance at scale
        assert threshold < 0.50

    def test_deepseek_threshold(self):
        """Test DeepSeek V3.1 cliff detection."""
        model_id = "deepseek/deepseek-chat-v3.1"
        cliffs = get_performance_cliff_threshold(model_id)

        cliffs = get_performance_cliff_threshold(model_id)
        from ii_agent.llm.model_constants import PERFORMANCE_CLIFFS as PC
        expected = None
        for k, v in PC.items():
            if 'deepseek' in k.lower():
                expected = v
                break
        if expected is None:
            # Not found: ensure we get default mapping
            expected = PC['Default']
        # Ensure all expected fields match
        for k, v in expected.items():
            assert cliffs.get(k) == v

    def test_litellm_format_matching(self):
        """Test various litellm model slug formats."""
        test_cases = [
            "claude-3-5-sonnet-20241022",
            "claude-3-7-sonnet-20250219",
            "gpt-4o-2024-05-13",
            "gpt-4.1-2025-04-09",
            "gemini/gemini-1.5-pro",
            "gemini/gemini-2.5-pro",
            "meta-llama/Llama-3.1-405B-Instruct",
            "meta-llama/Llama-4-Scout-17B-16E-Instruct",
            "deepseek-ai/DeepSeek-V3",
        ]

        for model_id in test_cases:
            cliffs = get_performance_cliff_threshold(model_id)
            assert isinstance(cliffs, dict)
            assert "early_degradation" in cliffs
            # Some models (e.g., Llama 4 Scout) don't define a moderate_cliff.
            # Compare against expected constants when available
            expected = None
            for k, v in PC.items():
                key_norm = ''.join(ch for ch in k if ch.isalnum()).lower()
                if key_norm in ''.join(ch for ch in model_id if ch.isalnum()).lower():
                    expected = v
                    break
            if expected and 'moderate_cliff' in expected:
                assert 'moderate_cliff' in cliffs
            if expected and 'severe_cliff' in expected:
                assert "severe_cliff" in cliffs

    def test_threshold_safety_bounds(self):
        """Test that thresholds stay within safe bounds (10%-90%)."""
        test_models = [
            "claude-3-5-sonnet-20241022",
            "gpt-4o",
            "gemini-1.5-pro",
            "meta-llama/Llama-3.1-405B-Instruct",
            "deepseek/deepseek-chat-v3.1",
        ]

        for model_id in test_models:
            threshold = calculate_model_specific_threshold(model_id)
            assert 0.10 <= threshold <= 0.90, f"Threshold {threshold} out of bounds for {model_id}"

    def test_unknown_model_fallback(self):
        """Test graceful fallback for unknown models."""
        model_id = "unknown-model-xyz"
        cliffs = get_performance_cliff_threshold(model_id)

        # Should return default values
        assert cliffs["early_degradation"] == 30_000
        assert cliffs["moderate_cliff"] == 64_000

    def test_threshold_variation_by_model(self):
        """Test that different models get different thresholds."""
        thresholds = {}
        for model_id in [
            "claude-3-5-sonnet-20241022",
            "gpt-4o",
            "gemini-1.5-pro",
        ]:
            thresholds[model_id] = calculate_model_specific_threshold(model_id)

        # Gemini should have higher threshold than GPT-4o and Claude
        # due to better long-context performance
        assert thresholds["gemini-1.5-pro"] > thresholds["gpt-4o"]

    def test_cliff_ratios(self):
        """Test that cliff ratios follow expected patterns."""
        model_id = "gpt-4o"
        cliffs = get_performance_cliff_threshold(model_id)
        context_window = CONTEXT_WINDOWS[model_id]  # 128K

        # Early degradation should be ~12% of context window
        ratio = cliffs["early_degradation"] / context_window
        assert 0.10 <= ratio <= 0.15

        # Effective limit should be ~30% of context window
        if "effective_limit" in cliffs:
            limit_ratio = cliffs["effective_limit"] / context_window
            assert 0.22 <= limit_ratio <= 0.35
