"""Unit tests for OpenAI Sora video generation client."""

import pytest
from unittest.mock import patch, MagicMock

from ii_tool.integrations.video_generation.openai_sora import (
    OpenAIVideoGenerationClient,
    _ASPECT_RATIO_TO_SIZE,
    _ASPECT_RATIO_TO_SIZE_PRO,
    _SORA_COST_PER_SECOND,
    _VALID_DURATIONS,
)
from ii_tool.integrations.video_generation.base import (
    VideoGenerationError,
    VideoGenerationResult,
)

pytest_plugins = ('pytest_asyncio',)


class TestAspectRatioMapping:
    """Test aspect ratio to size mapping."""

    def test_landscape_standard(self):
        assert _ASPECT_RATIO_TO_SIZE["16:9"] == "1280x720"

    def test_portrait_standard(self):
        assert _ASPECT_RATIO_TO_SIZE["9:16"] == "720x1280"

    def test_landscape_pro_high_res(self):
        assert _ASPECT_RATIO_TO_SIZE_PRO["16:9"] == "1792x1024"

    def test_portrait_pro_high_res(self):
        assert _ASPECT_RATIO_TO_SIZE_PRO["9:16"] == "1024x1792"


class TestValidDurations:
    """Test valid duration values."""

    def test_valid_durations(self):
        assert _VALID_DURATIONS == [4, 8, 12]


class TestCostCalculation:
    """Test cost calculation for Sora models."""

    def test_sora_2_landscape_cost(self):
        assert _SORA_COST_PER_SECOND["sora-2"]["1280x720"] == 0.10

    def test_sora_2_portrait_cost(self):
        assert _SORA_COST_PER_SECOND["sora-2"]["720x1280"] == 0.10

    def test_sora_2_pro_standard_cost(self):
        assert _SORA_COST_PER_SECOND["sora-2-pro"]["1280x720"] == 0.30

    def test_sora_2_pro_high_res_cost(self):
        assert _SORA_COST_PER_SECOND["sora-2-pro"]["1792x1024"] == 0.50


class TestOpenAIVideoGenerationClient:
    """Test OpenAIVideoGenerationClient class."""

    @patch("ii_tool.integrations.video_generation.openai_sora.OpenAI")
    def test_init_default_params(self, mock_openai):
        """Test client initialization with default parameters."""
        client = OpenAIVideoGenerationClient(api_key="test-key")

        mock_openai.assert_called_once_with(api_key="test-key")
        assert client._model == "sora-2"
        assert client._poll_interval == 10.0
        assert client._max_wait_seconds == 600.0
        assert client._use_high_res is False

    @patch("ii_tool.integrations.video_generation.openai_sora.OpenAI")
    def test_init_custom_params(self, mock_openai):
        """Test client initialization with custom parameters."""
        client = OpenAIVideoGenerationClient(
            api_key="test-key",
            model="sora-2-pro",
            poll_interval=5.0,
            max_wait_seconds=300.0,
            use_high_res=True,
        )

        assert client._model == "sora-2-pro"
        assert client._poll_interval == 5.0
        assert client._max_wait_seconds == 300.0
        assert client._use_high_res is True


class TestDurationMapping:
    """Test duration mapping to valid values."""

    @patch("ii_tool.integrations.video_generation.openai_sora.OpenAI")
    def test_get_nearest_duration_low(self, mock_openai):
        """Test that low durations map to 4."""
        client = OpenAIVideoGenerationClient(api_key="test-key")
        assert client._get_nearest_duration(1) == 4
        assert client._get_nearest_duration(4) == 4
        assert client._get_nearest_duration(5) == 4
        assert client._get_nearest_duration(6) == 4

    @patch("ii_tool.integrations.video_generation.openai_sora.OpenAI")
    def test_get_nearest_duration_medium(self, mock_openai):
        """Test that medium durations map to 8."""
        client = OpenAIVideoGenerationClient(api_key="test-key")
        assert client._get_nearest_duration(7) == 8
        assert client._get_nearest_duration(8) == 8
        assert client._get_nearest_duration(9) == 8
        assert client._get_nearest_duration(10) == 8

    @patch("ii_tool.integrations.video_generation.openai_sora.OpenAI")
    def test_get_nearest_duration_high(self, mock_openai):
        """Test that high durations map to 12."""
        client = OpenAIVideoGenerationClient(api_key="test-key")
        assert client._get_nearest_duration(11) == 12
        assert client._get_nearest_duration(12) == 12
        assert client._get_nearest_duration(20) == 12
        assert client._get_nearest_duration(100) == 12


class TestVideoGeneration:
    """Test video generation functionality."""

    @pytest.mark.asyncio
    @patch("ii_tool.integrations.video_generation.openai_sora.OpenAI")
    async def test_generate_video_success(self, mock_openai):
        """Test successful video generation."""
        mock_client = MagicMock()
        mock_openai.return_value = mock_client

        # Mock video creation
        mock_create_response = MagicMock()
        mock_create_response.id = "video_123"
        mock_client.videos.create.return_value = mock_create_response

        # Mock status polling (immediately completed)
        mock_status_response = MagicMock()
        mock_status_response.status = "completed"
        mock_client.videos.retrieve.return_value = mock_status_response

        client = OpenAIVideoGenerationClient(api_key="test-key")
        result = await client.generate_video(prompt="A cat walking", aspect_ratio="16:9", duration_seconds=5)

        assert isinstance(result, VideoGenerationResult)
        assert "video_123" in result.url
        assert result.mime_type == "video/mp4"
        # Duration 5 -> 4, cost = 0.10 * 4 = 0.40
        assert result.cost == 0.40

    @pytest.mark.asyncio
    @patch("ii_tool.integrations.video_generation.openai_sora.OpenAI")
    async def test_generate_video_cost_calculation_8_seconds(self, mock_openai):
        """Test cost calculation for 8-second video."""
        mock_client = MagicMock()
        mock_openai.return_value = mock_client

        mock_create_response = MagicMock()
        mock_create_response.id = "video_123"
        mock_client.videos.create.return_value = mock_create_response

        mock_status_response = MagicMock()
        mock_status_response.status = "completed"
        mock_client.videos.retrieve.return_value = mock_status_response

        client = OpenAIVideoGenerationClient(api_key="test-key")
        result = await client.generate_video(prompt="A cat", duration_seconds=8)

        # Duration 8 -> 8, cost = 0.10 * 8 = 0.80
        assert result.cost == 0.80

    @pytest.mark.asyncio
    @patch("ii_tool.integrations.video_generation.openai_sora.OpenAI")
    async def test_generate_video_pro_model_cost(self, mock_openai):
        """Test cost calculation for sora-2-pro model."""
        mock_client = MagicMock()
        mock_openai.return_value = mock_client

        mock_create_response = MagicMock()
        mock_create_response.id = "video_123"
        mock_client.videos.create.return_value = mock_create_response

        mock_status_response = MagicMock()
        mock_status_response.status = "completed"
        mock_client.videos.retrieve.return_value = mock_status_response

        client = OpenAIVideoGenerationClient(api_key="test-key", model="sora-2-pro")
        result = await client.generate_video(prompt="A cat", duration_seconds=4)

        # Duration 4, pro model cost = 0.30 * 4 = 1.20
        assert result.cost == 1.20

    @pytest.mark.asyncio
    @patch("ii_tool.integrations.video_generation.openai_sora.OpenAI")
    async def test_generate_video_pro_high_res_cost(self, mock_openai):
        """Test cost calculation for sora-2-pro with high resolution."""
        mock_client = MagicMock()
        mock_openai.return_value = mock_client

        mock_create_response = MagicMock()
        mock_create_response.id = "video_123"
        mock_client.videos.create.return_value = mock_create_response

        mock_status_response = MagicMock()
        mock_status_response.status = "completed"
        mock_client.videos.retrieve.return_value = mock_status_response

        client = OpenAIVideoGenerationClient(api_key="test-key", model="sora-2-pro", use_high_res=True)
        result = await client.generate_video(prompt="A cat", duration_seconds=4)

        # Duration 4, pro high-res cost = 0.50 * 4 = 2.00
        assert result.cost == 2.00

    @pytest.mark.asyncio
    @patch("ii_tool.integrations.video_generation.openai_sora.OpenAI")
    async def test_generate_video_failed_status(self, mock_openai):
        """Test that failed status raises VideoGenerationError."""
        mock_client = MagicMock()
        mock_openai.return_value = mock_client

        mock_create_response = MagicMock()
        mock_create_response.id = "video_123"
        mock_client.videos.create.return_value = mock_create_response

        mock_status_response = MagicMock()
        mock_status_response.status = "failed"
        mock_status_response.error = "Content policy violation"
        mock_client.videos.retrieve.return_value = mock_status_response

        client = OpenAIVideoGenerationClient(api_key="test-key")

        with pytest.raises(VideoGenerationError, match="Sora video generation failed"):
            await client.generate_video(prompt="A cat")

    @pytest.mark.asyncio
    @patch("ii_tool.integrations.video_generation.openai_sora.OpenAI")
    async def test_generate_video_api_error(self, mock_openai):
        """Test that API errors are wrapped in VideoGenerationError."""
        mock_client = MagicMock()
        mock_openai.return_value = mock_client
        mock_client.videos.create.side_effect = Exception("API Error")

        client = OpenAIVideoGenerationClient(api_key="test-key")

        with pytest.raises(VideoGenerationError, match="Sora video generation failed"):
            await client.generate_video(prompt="A cat")

    @pytest.mark.asyncio
    @patch("ii_tool.integrations.video_generation.openai_sora.OpenAI")
    async def test_generate_video_correct_api_params(self, mock_openai):
        """Test that correct parameters are passed to the API."""
        mock_client = MagicMock()
        mock_openai.return_value = mock_client

        mock_create_response = MagicMock()
        mock_create_response.id = "video_123"
        mock_client.videos.create.return_value = mock_create_response

        mock_status_response = MagicMock()
        mock_status_response.status = "completed"
        mock_client.videos.retrieve.return_value = mock_status_response

        client = OpenAIVideoGenerationClient(api_key="test-key", model="sora-2")
        await client.generate_video(prompt="A cat walking", aspect_ratio="9:16", duration_seconds=10)

        # Verify API was called with correct params
        mock_client.videos.create.assert_called_once_with(
            model="sora-2",
            prompt="A cat walking",
            size="720x1280",  # 9:16 portrait
            seconds="8",  # 10 maps to 8
        )
