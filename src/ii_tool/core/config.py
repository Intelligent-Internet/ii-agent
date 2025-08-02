from pydantic_settings import BaseSettings
from pydantic import ConfigDict

# --- Web Search Config ---
class WebSearchConfig(BaseSettings):
    firecrawl_api_key: str | None = None
    serpapi_api_key: str | None = None
    jina_api_key: str | None = None
    tavily_api_key: str | None = None

    max_results: int = 5
    
    model_config = ConfigDict(
        env_prefix="WEB_SEARCH_",
        env_file=".env",
        extra="ignore"
    )

# --- Image Search Config ---
class ImageSearchConfig(BaseSettings):
    serpapi_api_key: str | None = None

    max_results: int = 5

    model_config = ConfigDict(
        env_prefix="IMAGE_SEARCH_",
        env_file=".env",
        extra="ignore"
    )


# --- Web Visit Config ---
class WebVisitConfig(BaseSettings):
    firecrawl_api_key: str | None = None
    jina_api_key: str | None = None
    tavily_api_key: str | None = None

    max_output_length: int = 40_000

    model_config = ConfigDict(
        env_prefix="WEB_VISIT_",
        env_file=".env",
        extra="ignore"
    )

# --- Video Generate Config ---
class VideoGenerateConfig(BaseSettings):
    gcp_project_id: str | None = None
    gcp_location: str | None = None
    gcs_output_bucket: str | None = None
    google_ai_studio_api_key: str | None = None

    model_config = ConfigDict(
        env_prefix="VIDEO_GENERATE_",
        env_file=".env",
        extra="ignore"
    )

# --- Image Generate Config ---
class ImageGenerateConfig(BaseSettings):
    gcp_project_id: str | None = None
    gcp_location: str | None = None
    gcs_output_bucket: str | None = None
    google_ai_studio_api_key: str | None = None

    model_config = ConfigDict(
        env_prefix="IMAGE_GENERATE_",
        env_file=".env",
        extra="ignore"
    )

# --- Full Stack Dev Config ---
class FullStackDevConfig(BaseSettings):
    template_path: str = ".templates/react-tailwind-python"
    
    model_config = ConfigDict(
        env_prefix="FULLSTACK_DEV_",
        env_file=".env",
        extra="ignore"
    )
