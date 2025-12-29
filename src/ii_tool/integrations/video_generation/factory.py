from .config import VideoGenerateConfig
from .base import BaseVideoGenerationClient
from .duckduckgo import DuckDuckGoVideoGenerationClient
from .openai_sora import OpenAIVideoGenerationClient
from .vertex import VertexVideoGenerationClient


def create_video_generation_client(settings: VideoGenerateConfig) -> BaseVideoGenerationClient:
    """
    Factory function that creates a video generation client based on available configuration.

    Priority order:
    1. Vertex AI (Google Cloud) - if GCP project and location are configured
    2. OpenAI Sora - if OpenAI API key is configured
    3. DuckDuckGo - fallback video search (not AI generation)
    """
    if settings.gcp_project_id and settings.gcp_location:
        print("Using Vertex AI for video generation")
        return VertexVideoGenerationClient(
            project_id=settings.gcp_project_id,
            location=settings.gcp_location,
            output_bucket=settings.gcs_output_bucket,
        )

    openai_key = settings.get_openai_api_key()
    if openai_key:
        print("Using OpenAI Sora for video generation")
        return OpenAIVideoGenerationClient(api_key=openai_key)

    print("Falling back to DuckDuckGo video search for video requests")
    return DuckDuckGoVideoGenerationClient()
