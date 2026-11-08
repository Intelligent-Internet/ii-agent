from pydantic import BaseModel


class WebVisitConfig(BaseModel):
    firecrawl_api_key: str | None = None
    gemini_api_key: str | None = None
    jina_api_key: str | None = None
    tavily_api_key: str | None = None
    outcrawl_api_key: str | None = None

    max_output_length: int = 40_000
