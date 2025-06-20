from enum import Enum
from pydantic import BaseModel, Field, SecretStr, field_serializer, SerializationInfo
from pydantic.json import pydantic_encoder

class SearchConfig(BaseModel):
    """Configuration for the search.
    
    Attributes:
        firecrawl_api_key: The API key for Firecrawl.
        firecrawl_base_url: The base URL for Firecrawl.
        serpapi_api_key: The API key for SerpAPI.
        tavily_api_key: The API key for Tavily.
        jina_api_key: The API key for Jina.

    """
    firecrawl_api_key: SecretStr | None = Field(default=None)
    serpapi_api_key: SecretStr | None = Field(default=None)
    tavily_api_key: SecretStr | None = Field(default=None)
    jina_api_key: SecretStr | None = Field(default=None)

    @field_serializer('firecrawl_api_key', 'serpapi_api_key', 'tavily_api_key', 'jina_api_key')
    def api_key_serializer(self, api_key: SecretStr | None, info: SerializationInfo):
        """Custom serializer for API keys.

        To serialize the API key instead of ********, set expose_secrets to True in the serialization context.
        """
        if api_key is None:
            return None

        context = info.context
        if context and context.get('expose_secrets', False):
            return api_key.get_secret_value()

        return pydantic_encoder(api_key)
