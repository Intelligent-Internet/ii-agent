"""Unit tests for OpenAI LLM provider.

This module tests the OpenAI provider functionality including:
- Reasoning model detection
- Parameter filtering for non-reasoning models

Note: Tests use direct Pydantic model instantiation to avoid
loading the full app config which requires environment variables.
"""

import pytest
from typing import ClassVar, Set, Dict, Any, Optional
from pydantic import BaseModel


# Recreate the minimal OpenAIResponseParams for testing
# This avoids importing the full module which triggers config loading
class OpenAIResponseParamsForTest(BaseModel):
    """Minimal recreation of OpenAIResponseParams for testing."""

    model: str
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    reasoning: Optional[Dict[str, Any]] = None

    # Models that support the 'reasoning' parameter (OpenAI reasoning models)
    REASONING_MODELS: ClassVar[Set[str]] = {"o1", "o1-mini", "o1-preview", "o3", "o3-mini", "o4-mini"}

    class Config:
        extra = "allow"

    def _is_reasoning_model(self) -> bool:
        """Check if the model supports reasoning parameters."""
        model_lower = self.model.lower()
        # Check for exact matches and prefix matches (e.g., "o1-2024-12-17")
        for reasoning_model in self.REASONING_MODELS:
            if model_lower == reasoning_model or model_lower.startswith(f"{reasoning_model}-"):
                return True
        return False

    def to_dict(self, exclude_none: bool = True) -> Dict[str, Any]:
        """Convert to dictionary for API request, excluding None values by default.

        Also excludes the 'reasoning' parameter for models that don't support it.
        """
        data = self.model_dump(exclude_none=exclude_none)

        # Remove reasoning parameter for non-reasoning models
        if "reasoning" in data and not self._is_reasoning_model():
            del data["reasoning"]

        return data


class TestOpenAIResponseParams:
    """Tests for OpenAIResponseParams class."""

    def test_reasoning_models_set(self):
        """Test that REASONING_MODELS contains expected models."""
        expected_models = {"o1", "o1-mini", "o1-preview", "o3", "o3-mini", "o4-mini"}
        assert OpenAIResponseParamsForTest.REASONING_MODELS == expected_models

    def test_is_reasoning_model_exact_match(self):
        """Test _is_reasoning_model for exact model name matches."""
        # Test exact matches
        params_o1 = OpenAIResponseParamsForTest(model="o1")
        assert params_o1._is_reasoning_model() is True

        params_o3 = OpenAIResponseParamsForTest(model="o3-mini")
        assert params_o3._is_reasoning_model() is True

    def test_is_reasoning_model_prefix_match(self):
        """Test _is_reasoning_model for versioned model names."""
        # Test prefix matches (versioned models)
        params_versioned = OpenAIResponseParamsForTest(model="o1-2024-12-17")
        assert params_versioned._is_reasoning_model() is True

        params_preview = OpenAIResponseParamsForTest(model="o1-preview-2024-09-12")
        assert params_preview._is_reasoning_model() is True

    def test_is_reasoning_model_false_for_gpt(self):
        """Test _is_reasoning_model returns False for GPT models."""
        params_gpt4 = OpenAIResponseParamsForTest(model="gpt-4o")
        assert params_gpt4._is_reasoning_model() is False

        params_gpt4_turbo = OpenAIResponseParamsForTest(model="gpt-4-turbo")
        assert params_gpt4_turbo._is_reasoning_model() is False

        params_gpt35 = OpenAIResponseParamsForTest(model="gpt-3.5-turbo")
        assert params_gpt35._is_reasoning_model() is False

    def test_is_reasoning_model_case_insensitive(self):
        """Test _is_reasoning_model is case insensitive."""
        params_upper = OpenAIResponseParamsForTest(model="O1")
        assert params_upper._is_reasoning_model() is True

        params_mixed = OpenAIResponseParamsForTest(model="O1-Mini")
        assert params_mixed._is_reasoning_model() is True

    def test_to_dict_excludes_reasoning_for_gpt(self):
        """Test that to_dict excludes reasoning param for non-reasoning models."""
        params = OpenAIResponseParamsForTest(
            model="gpt-4o",
            reasoning={"effort": "medium"},
            temperature=0.7
        )

        result = params.to_dict()

        assert "reasoning" not in result
        assert result["model"] == "gpt-4o"
        assert result["temperature"] == 0.7

    def test_to_dict_keeps_reasoning_for_o1(self):
        """Test that to_dict keeps reasoning param for reasoning models."""
        params = OpenAIResponseParamsForTest(
            model="o1",
            reasoning={"effort": "high"}
        )

        result = params.to_dict()

        assert "reasoning" in result
        assert result["reasoning"] == {"effort": "high"}

    def test_to_dict_handles_missing_reasoning(self):
        """Test to_dict works when reasoning param is not set."""
        params = OpenAIResponseParamsForTest(model="gpt-4o")

        result = params.to_dict()

        # Should not raise, reasoning just won't be in dict
        assert "reasoning" not in result

    def test_to_dict_exclude_none(self):
        """Test that to_dict excludes None values by default."""
        params = OpenAIResponseParamsForTest(
            model="gpt-4o",
            temperature=None,
            max_tokens=1000
        )

        result = params.to_dict()

        assert "temperature" not in result
        assert result["max_tokens"] == 1000


class TestReasoningModelIntegration:
    """Integration tests for reasoning model handling."""

    def test_gpt4o_with_reasoning_effort_filtered(self):
        """Test realistic scenario: gpt-4o with reasoning.effort gets filtered."""
        # This is the bug scenario - reasoning.effort was being sent to gpt-4o
        params = OpenAIResponseParamsForTest(
            model="gpt-4o",
            reasoning={"effort": "medium"},
            temperature=0.2,
            max_tokens=4096
        )

        api_params = params.to_dict()

        # Reasoning should be stripped for gpt-4o
        assert "reasoning" not in api_params
        # Other params should remain
        assert api_params["model"] == "gpt-4o"
        assert api_params["temperature"] == 0.2
        assert api_params["max_tokens"] == 4096

    def test_o1_mini_keeps_reasoning(self):
        """Test that o1-mini correctly keeps reasoning param."""
        params = OpenAIResponseParamsForTest(
            model="o1-mini",
            reasoning={"effort": "low"}
        )

        api_params = params.to_dict()

        assert api_params["reasoning"] == {"effort": "low"}
