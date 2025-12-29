"""Unit tests for image and video generation config and factory."""

import json
import os
import pytest
from unittest.mock import patch, MagicMock

from ii_tool.integrations.image_generation.config import ImageGenerateConfig, _extract_openai_key_from_llm_configs as img_extract_key
from ii_tool.integrations.image_generation.factory import create_image_generation_client
from ii_tool.integrations.image_generation.duckduckgo import DuckDuckGoImageGenerationClient
from ii_tool.integrations.image_generation.openai_dalle import OpenAIImageGenerationClient

from ii_tool.integrations.video_generation.config import VideoGenerateConfig, _extract_openai_key_from_llm_configs as vid_extract_key
from ii_tool.integrations.video_generation.factory import create_video_generation_client
from ii_tool.integrations.video_generation.duckduckgo import DuckDuckGoVideoGenerationClient
from ii_tool.integrations.video_generation.openai_sora import OpenAIVideoGenerationClient


class TestExtractOpenaiKeyFromLlmConfigs:
    """Test _extract_openai_key_from_llm_configs helper function."""

    def test_extracts_openai_key_from_json(self):
        """Test extracting key from LLM_CONFIGS JSON blob."""
        llm_configs = {
            "default": {"api_type": "openai", "model": "gpt-4o", "api_key": "sk-openai-key"},
            "anthropic": {"api_type": "anthropic", "model": "claude-3", "api_key": "sk-ant-key"}
        }
        with patch.dict(os.environ, {"LLM_CONFIGS": json.dumps(llm_configs)}):
            assert img_extract_key() == "sk-openai-key"
            assert vid_extract_key() == "sk-openai-key"

    def test_returns_none_when_no_openai_config(self):
        """Test returns None when no OpenAI config in JSON."""
        llm_configs = {
            "anthropic": {"api_type": "anthropic", "model": "claude-3", "api_key": "sk-ant-key"}
        }
        with patch.dict(os.environ, {"LLM_CONFIGS": json.dumps(llm_configs)}, clear=True):
            os.environ.pop("LLM_CONFIG__OPENAI_API_KEY", None)
            assert img_extract_key() is None
            assert vid_extract_key() is None

    def test_returns_none_when_llm_configs_not_set(self):
        """Test returns None when LLM_CONFIGS not in environment."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("LLM_CONFIGS", None)
            assert img_extract_key() is None
            assert vid_extract_key() is None

    def test_returns_none_on_invalid_json(self):
        """Test returns None when LLM_CONFIGS is invalid JSON."""
        with patch.dict(os.environ, {"LLM_CONFIGS": "not-valid-json"}):
            assert img_extract_key() is None
            assert vid_extract_key() is None

    def test_handles_openai_without_api_key(self):
        """Test handles config without api_key field."""
        llm_configs = {
            "default": {"api_type": "openai", "model": "gpt-4o"}  # No api_key
        }
        with patch.dict(os.environ, {"LLM_CONFIGS": json.dumps(llm_configs)}, clear=True):
            os.environ.pop("LLM_CONFIG__OPENAI_API_KEY", None)
            assert img_extract_key() is None


class TestImageGenerateConfig:
    """Test ImageGenerateConfig class."""

    def test_get_openai_api_key_explicit(self):
        """Test that explicit key takes precedence."""
        config = ImageGenerateConfig(openai_api_key="explicit-key")
        assert config.get_openai_api_key() == "explicit-key"

    def test_get_openai_api_key_fallback_env_var(self):
        """Test fallback to LLM_CONFIG__OPENAI_API_KEY."""
        with patch.dict(os.environ, {"LLM_CONFIG__OPENAI_API_KEY": "fallback-key"}, clear=True):
            os.environ.pop("LLM_CONFIGS", None)
            config = ImageGenerateConfig(openai_api_key=None)
            assert config.get_openai_api_key() == "fallback-key"

    def test_get_openai_api_key_fallback_llm_configs_json(self):
        """Test fallback to extracting from LLM_CONFIGS JSON."""
        llm_configs = {"default": {"api_type": "openai", "api_key": "json-key"}}
        with patch.dict(os.environ, {"LLM_CONFIGS": json.dumps(llm_configs)}, clear=True):
            os.environ.pop("LLM_CONFIG__OPENAI_API_KEY", None)
            config = ImageGenerateConfig(openai_api_key=None)
            assert config.get_openai_api_key() == "json-key"

    def test_get_openai_api_key_none(self):
        """Test returns None when no key is available."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("LLM_CONFIG__OPENAI_API_KEY", None)
            os.environ.pop("LLM_CONFIGS", None)
            config = ImageGenerateConfig(openai_api_key=None)
            assert config.get_openai_api_key() is None

    def test_get_openai_api_key_explicit_over_fallback(self):
        """Test that explicit key overrides all fallbacks."""
        llm_configs = {"default": {"api_type": "openai", "api_key": "json-key"}}
        with patch.dict(os.environ, {
            "LLM_CONFIG__OPENAI_API_KEY": "env-key",
            "LLM_CONFIGS": json.dumps(llm_configs)
        }):
            config = ImageGenerateConfig(openai_api_key="explicit-key")
            assert config.get_openai_api_key() == "explicit-key"

    def test_get_openai_api_key_env_var_over_json(self):
        """Test that LLM_CONFIG__OPENAI_API_KEY takes precedence over JSON."""
        llm_configs = {"default": {"api_type": "openai", "api_key": "json-key"}}
        with patch.dict(os.environ, {
            "LLM_CONFIG__OPENAI_API_KEY": "env-key",
            "LLM_CONFIGS": json.dumps(llm_configs)
        }):
            config = ImageGenerateConfig(openai_api_key=None)
            assert config.get_openai_api_key() == "env-key"


class TestVideoGenerateConfig:
    """Test VideoGenerateConfig class."""

    def test_get_openai_api_key_explicit(self):
        """Test that explicit key takes precedence."""
        config = VideoGenerateConfig(openai_api_key="explicit-key")
        assert config.get_openai_api_key() == "explicit-key"

    def test_get_openai_api_key_fallback_env_var(self):
        """Test fallback to LLM_CONFIG__OPENAI_API_KEY."""
        with patch.dict(os.environ, {"LLM_CONFIG__OPENAI_API_KEY": "fallback-key"}, clear=True):
            os.environ.pop("LLM_CONFIGS", None)
            config = VideoGenerateConfig(openai_api_key=None)
            assert config.get_openai_api_key() == "fallback-key"

    def test_get_openai_api_key_fallback_llm_configs_json(self):
        """Test fallback to extracting from LLM_CONFIGS JSON."""
        llm_configs = {"default": {"api_type": "openai", "api_key": "json-key"}}
        with patch.dict(os.environ, {"LLM_CONFIGS": json.dumps(llm_configs)}, clear=True):
            os.environ.pop("LLM_CONFIG__OPENAI_API_KEY", None)
            config = VideoGenerateConfig(openai_api_key=None)
            assert config.get_openai_api_key() == "json-key"

    def test_get_openai_api_key_none(self):
        """Test returns None when no key is available."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("LLM_CONFIG__OPENAI_API_KEY", None)
            os.environ.pop("LLM_CONFIGS", None)
            config = VideoGenerateConfig(openai_api_key=None)
            assert config.get_openai_api_key() is None


class TestImageGenerationFactory:
    """Test image generation factory function."""

    @patch("ii_tool.integrations.image_generation.factory.VertexImageGenerationClient")
    def test_vertex_takes_priority(self, mock_vertex):
        """Test that Vertex AI is used when GCP config is present."""
        config = ImageGenerateConfig(
            gcp_project_id="my-project",
            gcp_location="us-central1",
            openai_api_key="some-key",
        )

        client = create_image_generation_client(config)

        mock_vertex.assert_called_once()

    @patch("ii_tool.integrations.image_generation.factory.OpenAIImageGenerationClient")
    def test_openai_when_no_gcp(self, mock_openai):
        """Test that OpenAI is used when no GCP config but OpenAI key exists."""
        config = ImageGenerateConfig(
            gcp_project_id=None,
            gcp_location=None,
            openai_api_key="openai-key",
        )

        client = create_image_generation_client(config)

        mock_openai.assert_called_once_with(api_key="openai-key")

    def test_duckduckgo_fallback(self):
        """Test that DuckDuckGo is used when no other config exists."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("LLM_CONFIG__OPENAI_API_KEY", None)
            config = ImageGenerateConfig(
                gcp_project_id=None,
                gcp_location=None,
                openai_api_key=None,
            )

            client = create_image_generation_client(config)

            assert isinstance(client, DuckDuckGoImageGenerationClient)


class TestVideoGenerationFactory:
    """Test video generation factory function."""

    @patch("ii_tool.integrations.video_generation.factory.VertexVideoGenerationClient")
    def test_vertex_takes_priority(self, mock_vertex):
        """Test that Vertex AI is used when GCP config is present."""
        config = VideoGenerateConfig(
            gcp_project_id="my-project",
            gcp_location="us-central1",
            openai_api_key="some-key",
        )

        client = create_video_generation_client(config)

        mock_vertex.assert_called_once()

    @patch("ii_tool.integrations.video_generation.factory.OpenAIVideoGenerationClient")
    def test_openai_when_no_gcp(self, mock_openai):
        """Test that OpenAI Sora is used when no GCP config but OpenAI key exists."""
        config = VideoGenerateConfig(
            gcp_project_id=None,
            gcp_location=None,
            openai_api_key="openai-key",
        )

        client = create_video_generation_client(config)

        mock_openai.assert_called_once_with(api_key="openai-key")

    def test_duckduckgo_fallback(self):
        """Test that DuckDuckGo is used when no other config exists."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("LLM_CONFIG__OPENAI_API_KEY", None)
            config = VideoGenerateConfig(
                gcp_project_id=None,
                gcp_location=None,
                openai_api_key=None,
            )

            client = create_video_generation_client(config)

            assert isinstance(client, DuckDuckGoVideoGenerationClient)
