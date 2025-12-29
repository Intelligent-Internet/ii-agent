from .config import ImageGenerateConfig
from .base import BaseImageGenerationClient
from .duckduckgo import DuckDuckGoImageGenerationClient
from .openai_dalle import OpenAIImageGenerationClient
from .vertex import VertexImageGenerationClient


def create_image_generation_client(settings: ImageGenerateConfig) -> BaseImageGenerationClient:
    """Factory function that creates an image generation client based on available configuration.

    Priority order:
    1. Vertex AI (Google Cloud) - if GCP project and location are configured
    2. OpenAI DALL-E 3 - if OpenAI API key is configured
    3. DuckDuckGo - fallback image search (not AI generation)
    """
    if settings.gcp_project_id and settings.gcp_location:
        print("Using Vertex AI for image generation")
        return VertexImageGenerationClient(
            project_id=settings.gcp_project_id,
            location=settings.gcp_location,
            output_bucket=settings.gcs_output_bucket,
        )

    openai_key = settings.get_openai_api_key()
    if openai_key:
        print("Using OpenAI DALL-E 3 for image generation")
        return OpenAIImageGenerationClient(api_key=openai_key)

    print("Falling back to DuckDuckGo image search for image generation")
    return DuckDuckGoImageGenerationClient()
