from pydantic_settings import BaseSettings

# --- Search Config ---
class WebSearchConfig(BaseSettings):
    firecrawl_api_key: str | None = None
    serpapi_api_key: str | None = None
    jina_api_key: str | None = None
    tavily_api_key: str | None = None

    max_results: int = 5
    
    class Config:
        env_prefix = "WEB_SEARCH_"
        env_file = ".env"
        extra = "ignore"

# --- Image Search Config ---
class ImageSearchConfig(BaseSettings):
    serpapi_api_key: str | None = None

    max_results: int = 5

    class Config:
        env_prefix = "IMAGE_SEARCH_"
        env_file = ".env"
        extra = "ignore"


# --- Web Visit Config ---
class WebVisitConfig(BaseSettings):
    firecrawl_api_key: str | None = None
    jina_api_key: str | None = None
    tavily_api_key: str | None = None

    max_output_length: int = 40_000

    class Config:
        env_prefix = "WEB_VISIT_"
        env_file = ".env"
        extra = "ignore"