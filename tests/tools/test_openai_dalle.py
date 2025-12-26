"""Unit tests for OpenAI DALL-E image generation client."""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from ii_tool.integrations.image_generation.openai_dalle import (
    OpenAIImageGenerationClient,
    _ASPECT_RATIO_TO_SIZE,
    _DALLE3_STANDARD_COST,
)
from ii_tool.integrations.image_generation.base import (
    ImageGenerationError,
    ImageGenerationResult,
)

pytest_plugins = ('pytest_asyncio',)


class TestAspectRatioMapping:
    """Test aspect ratio to size mapping."""

    def test_square_aspect_ratio(self):
        assert _ASPECT_RATIO_TO_SIZE["1:1"] == "1024x1024"

    def test_landscape_aspect_ratio(self):
        assert _ASPECT_RATIO_TO_SIZE["16:9"] == "1792x1024"

    def test_portrait_aspect_ratio(self):
        assert _ASPECT_RATIO_TO_SIZE["9:16"] == "1024x1792"

    def test_4_3_maps_to_landscape(self):
        assert _ASPECT_RATIO_TO_SIZE["4:3"] == "1792x1024"

    def test_3_4_maps_to_portrait(self):
        assert _ASPECT_RATIO_TO_SIZE["3:4"] == "1024x1792"


class TestCostCalculation:
    """Test cost calculation for DALL-E 3."""

    def test_square_cost(self):
        assert _DALLE3_STANDARD_COST["1024x1024"] == 0.040

    def test_landscape_cost(self):
        assert _DALLE3_STANDARD_COST["1792x1024"] == 0.080

    def test_portrait_cost(self):
        assert _DALLE3_STANDARD_COST["1024x1792"] == 0.080


class TestOpenAIImageGenerationClient:
    """Test OpenAIImageGenerationClient class."""

    @patch("ii_tool.integrations.image_generation.openai_dalle.OpenAI")
    def test_init_default_params(self, mock_openai):
        """Test client initialization with default parameters."""
        client = OpenAIImageGenerationClient(api_key="test-key")

        mock_openai.assert_called_once_with(api_key="test-key")
        assert client._model == "dall-e-3"
        assert client._quality == "standard"
        assert client._style == "vivid"

    @patch("ii_tool.integrations.image_generation.openai_dalle.OpenAI")
    def test_init_custom_params(self, mock_openai):
        """Test client initialization with custom parameters."""
        client = OpenAIImageGenerationClient(
            api_key="test-key",
            model="dall-e-2",
            quality="hd",
            style="natural",
        )

        assert client._model == "dall-e-2"
        assert client._quality == "hd"
        assert client._style == "natural"

    @pytest.mark.asyncio
    @patch("ii_tool.integrations.image_generation.openai_dalle.OpenAI")
    async def test_generate_image_success(self, mock_openai):
        """Test successful image generation."""
        # Setup mock
        mock_client = MagicMock()
        mock_openai.return_value = mock_client

        mock_response = MagicMock()
        mock_response.data = [MagicMock(url="https://example.com/image.png", revised_prompt="A cat")]
        mock_client.images.generate.return_value = mock_response

        client = OpenAIImageGenerationClient(api_key="test-key")
        result = await client.generate_image(prompt="A cat", aspect_ratio="1:1")

        assert isinstance(result, ImageGenerationResult)
        assert result.url == "https://example.com/image.png"
        assert result.mime_type == "image/png"
        assert result.cost == 0.040  # Standard 1024x1024

    @pytest.mark.asyncio
    @patch("ii_tool.integrations.image_generation.openai_dalle.OpenAI")
    async def test_generate_image_hd_quality_doubles_cost(self, mock_openai):
        """Test that HD quality doubles the cost."""
        mock_client = MagicMock()
        mock_openai.return_value = mock_client

        mock_response = MagicMock()
        mock_response.data = [MagicMock(url="https://example.com/image.png", revised_prompt="A cat")]
        mock_client.images.generate.return_value = mock_response

        client = OpenAIImageGenerationClient(api_key="test-key", quality="hd")
        result = await client.generate_image(prompt="A cat", aspect_ratio="1:1")

        assert result.cost == 0.080  # HD doubles the cost

    @pytest.mark.asyncio
    @patch("ii_tool.integrations.image_generation.openai_dalle.OpenAI")
    async def test_generate_image_landscape_cost(self, mock_openai):
        """Test landscape image costs more."""
        mock_client = MagicMock()
        mock_openai.return_value = mock_client

        mock_response = MagicMock()
        mock_response.data = [MagicMock(url="https://example.com/image.png", revised_prompt="A landscape")]
        mock_client.images.generate.return_value = mock_response

        client = OpenAIImageGenerationClient(api_key="test-key")
        result = await client.generate_image(prompt="A landscape", aspect_ratio="16:9")

        assert result.cost == 0.080  # Landscape is more expensive

    @pytest.mark.asyncio
    @patch("ii_tool.integrations.image_generation.openai_dalle.OpenAI")
    async def test_generate_image_no_data_raises_error(self, mock_openai):
        """Test that empty response raises ImageGenerationError."""
        mock_client = MagicMock()
        mock_openai.return_value = mock_client

        mock_response = MagicMock()
        mock_response.data = []
        mock_client.images.generate.return_value = mock_response

        client = OpenAIImageGenerationClient(api_key="test-key")

        with pytest.raises(ImageGenerationError, match="DALL-E returned no image data"):
            await client.generate_image(prompt="A cat")

    @pytest.mark.asyncio
    @patch("ii_tool.integrations.image_generation.openai_dalle.OpenAI")
    async def test_generate_image_api_error_raises_error(self, mock_openai):
        """Test that API errors are wrapped in ImageGenerationError."""
        mock_client = MagicMock()
        mock_openai.return_value = mock_client
        mock_client.images.generate.side_effect = Exception("API Error")

        client = OpenAIImageGenerationClient(api_key="test-key")

        with pytest.raises(ImageGenerationError, match="DALL-E image generation failed"):
            await client.generate_image(prompt="A cat")

    @pytest.mark.asyncio
    @patch("ii_tool.integrations.image_generation.openai_dalle.OpenAI")
    async def test_generate_image_kwargs_override(self, mock_openai):
        """Test that kwargs can override default quality and style."""
        mock_client = MagicMock()
        mock_openai.return_value = mock_client

        mock_response = MagicMock()
        mock_response.data = [MagicMock(url="https://example.com/image.png", revised_prompt="A cat")]
        mock_client.images.generate.return_value = mock_response

        client = OpenAIImageGenerationClient(api_key="test-key", quality="standard", style="vivid")
        await client.generate_image(prompt="A cat", quality="hd", style="natural")

        # Verify the API was called with overridden values
        call_kwargs = mock_client.images.generate.call_args.kwargs
        assert call_kwargs["quality"] == "hd"
        assert call_kwargs["style"] == "natural"
