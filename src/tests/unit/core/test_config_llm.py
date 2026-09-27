"""Tests for ii_agent.core.config.llm_config — LLMConfig api_key_serializer + is_user_model."""

from __future__ import annotations


class TestLLMConfig:
    def _make_config(self, **kwargs):
        from ii_agent.core.config.llm_config import LLMConfig

        return LLMConfig(**kwargs)

    def test_api_key_serializer_with_none_api_key(self):
        """Branch [61, 62]: api_key is None → returns None."""
        config = self._make_config()
        d = config.model_dump()
        assert d["api_key"] is None

    def test_api_key_serializer_without_expose_secrets(self):
        """Branch [61, 64] and [65, 68]: api_key is set, no expose_secrets."""
        from pydantic import SecretStr

        config = self._make_config(api_key=SecretStr("test-api-key"))
        d = config.model_dump()
        # The serializer should return the pydantic_encoder result (obscured)
        assert d["api_key"] is not None

    def test_api_key_serializer_with_expose_secrets(self):
        """Branch [65, 66]: context has expose_secrets=True → raw value."""
        from pydantic import SecretStr

        config = self._make_config(api_key=SecretStr("my-secret"))
        d = config.model_dump(context={"expose_secrets": True})
        assert d["api_key"] == "my-secret"

    def test_is_user_model_false_for_system(self):
        """Line 72: config_type='system' → False."""
        config = self._make_config(config_type="system")
        assert config.is_user_model() is False

    def test_is_user_model_true_for_user(self):
        """Line 72: config_type='user' → True."""
        config = self._make_config(config_type="user")
        assert config.is_user_model() is True

    def test_is_user_model_none_config_type(self):
        """Line 72: config_type=None → False."""
        config = self._make_config(config_type=None)
        assert config.is_user_model() is False
