from enum import Enum
from pydantic import BaseModel, Field, SecretStr, SerializationInfo, field_serializer
from pydantic.json import pydantic_encoder

from ii_agent.utils.constants import DEFAULT_MODEL

class APITypes(Enum):
    """Types of API keys."""
    OPENAI = 'openai'
    ANTHROPIC = 'anthropic'
    GEMINI = 'gemini'

class LLMConfig(BaseModel):
    """Configuration for the LLM.
    
    Attributes:
        model: The model to use.
        api_key: The API key to use.
        base_url: The base URL for the API. This is necessary for local LLMs.
        num_retries: The number of retries to use.
        max_message_chars: The maximum number of characters in a message.
    """
    model: str = Field(default=DEFAULT_MODEL)
    api_key: SecretStr | None = Field(default=None)
    base_url: str | None = Field(default=None)
    max_retries: int = Field(default=3)
    max_message_chars: int = Field(default=30_000)
    temperature: float = Field(default=0.0)
    vertex_region: str | None = Field(default=None)
    vertex_project_id: str | None = Field(default=None)
    api_type: APITypes = Field(default=APITypes.ANTHROPIC)
    thinking_tokens: int = Field(default=0)
    azure_endpoint: str | None = Field(default=None)
    azure_api_version: str | None = Field(default=None)
    cot_model: bool = Field(default=False)


    @field_serializer('api_key')
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

