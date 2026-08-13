from enum import Enum

from ii_agent_tools.integrations.video_generation.config import VideoGenerateConfig
from ii_agent_tools.integrations.video_generation.base import BaseVideoGenerationClient
from ii_agent_tools.integrations.video_generation.vertex import (
    VertexVideoGenerationClient,
)
from ii_agent_tools.integrations.video_generation.gemini import (
    GeminiVideoGenerationClient,
)
from ii_agent_tools.integrations.video_generation.fal import (
    FalVideoGenerationClient,
)
from ii_agent_tools.integrations.video_generation.minimax import (
    MiniMaxVideoGenerationClient,
)
from ii_agent_tools.logger import get_logger

logger = get_logger(__name__)


class VideoGenerationProvider(Enum):
    """Supported video generation providers."""

    VERTEX = "vertex"
    GEMINI = "gemini"
    FAL = "fal"
    MINIMAX = "minimax"


# Alias mapping for provider names
PROVIDER_ALIASES: dict[str, VideoGenerationProvider] = {
    "vertex": VideoGenerationProvider.VERTEX,
    "gemini": VideoGenerationProvider.GEMINI,
    "fal": VideoGenerationProvider.FAL,
    "fal-ai": VideoGenerationProvider.FAL,
    "fal_ai": VideoGenerationProvider.FAL,
    "minimax": VideoGenerationProvider.MINIMAX,
    "minimax-ai": VideoGenerationProvider.MINIMAX,
    "minimax_ai": VideoGenerationProvider.MINIMAX,
    "minimaxi": VideoGenerationProvider.MINIMAX,
}


def create_video_generation_client(
    settings: VideoGenerateConfig,
    provider: str | None = None,
) -> BaseVideoGenerationClient:
    """
    Factory function that creates a video generation client based on available configuration.

    Args:
        settings: Video generation configuration
        provider: Optional provider to use (e.g., "vertex", "gemini")

    Returns:
        A video generation client instance
    """
    # Normalize provider name using alias mapping
    if provider and provider.lower() in PROVIDER_ALIASES:
        provider = PROVIDER_ALIASES[provider.lower()].value
    elif provider:
        provider = provider.lower()

    # If provider is specified, use that provider
    if provider == VideoGenerationProvider.GEMINI.value:
        if not settings.google_ai_studio_api_key:
            raise ValueError("Gemini provider requires google_ai_studio_api_key")
        logger.info(
            "Using Google AI Studio (Gemini) for video generation",
            extra={"provider": provider},
        )
        return GeminiVideoGenerationClient(
            api_key=settings.google_ai_studio_api_key,
            output_bucket=settings.gcs_output_bucket,
        )

    if provider == VideoGenerationProvider.VERTEX.value:
        if not settings.gcp_project_id or not settings.gcp_location:
            raise ValueError("Vertex AI provider requires gcp_project_id and gcp_location")
        logger.info(
            "Using Vertex AI for video generation",
            extra={"provider": provider},
        )
        return VertexVideoGenerationClient(
            project_id=settings.gcp_project_id,
            location=settings.gcp_location,
            output_bucket=settings.gcs_output_bucket,
            custom_domain=settings.custom_domain,
        )

    if provider == VideoGenerationProvider.FAL.value:
        if not settings.fal_api_key:
            raise ValueError("fal provider requires fal_api_key")
        logger.info(
            "Using fal for video generation",
            extra={"provider": provider},
        )
        return FalVideoGenerationClient(
            api_key=settings.fal_api_key,
            model_name=settings.fal_model_name,
            request_mode=settings.fal_request_mode,
            output_bucket=settings.gcs_output_bucket,
            project_id=settings.gcp_project_id,
        )

    if provider == VideoGenerationProvider.MINIMAX.value:
        if not settings.minimax_api_key:
            raise ValueError("minimax provider requires minimax_api_key")
        logger.info(
            "Using MiniMax for video generation",
            extra={"provider": provider},
        )
        return MiniMaxVideoGenerationClient(
            api_key=settings.minimax_api_key,
            model_name=settings.minimax_model_name,
            base_url=settings.minimax_base_url,
            group_id=settings.minimax_group_id,
            output_bucket=settings.gcs_output_bucket,
            project_id=settings.gcp_project_id,
            custom_domain=settings.custom_domain,
        )

    # Auto-select provider based on available configuration
    # Prefer Gemini if API key is available
    if settings.google_ai_studio_api_key:
        logger.info("Using Google AI Studio (Gemini) for video generation (auto-selected)")
        return GeminiVideoGenerationClient(
            api_key=settings.google_ai_studio_api_key,
            output_bucket=settings.gcs_output_bucket,
        )

    if settings.gcp_project_id and settings.gcp_location:
        logger.info("Using Vertex AI for video generation (auto-selected)")
        return VertexVideoGenerationClient(
            project_id=settings.gcp_project_id,
            location=settings.gcp_location,
            output_bucket=settings.gcs_output_bucket,
            custom_domain=settings.custom_domain,
        )

    if settings.fal_api_key:
        logger.info("Using fal for video generation (auto-selected)")
        return FalVideoGenerationClient(
            api_key=settings.fal_api_key,
            model_name=settings.fal_model_name,
            request_mode=settings.fal_request_mode,
            output_bucket=settings.gcs_output_bucket,
            project_id=settings.gcp_project_id,
        )

    if settings.minimax_api_key:
        logger.info("Using MiniMax for video generation (auto-selected)")
        return MiniMaxVideoGenerationClient(
            api_key=settings.minimax_api_key,
            model_name=settings.minimax_model_name,
            base_url=settings.minimax_base_url,
            group_id=settings.minimax_group_id,
            output_bucket=settings.gcs_output_bucket,
            project_id=settings.gcp_project_id,
            custom_domain=settings.custom_domain,
        )

    raise ValueError("No video generation client available")
