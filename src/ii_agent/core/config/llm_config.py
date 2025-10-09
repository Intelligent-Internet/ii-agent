from enum import Enum
from pydantic import (
    BaseModel,
    Field,
    SecretStr,
    SerializationInfo,
    field_serializer,
    field_validator,
)
from pydantic_core import PydanticUndefined
from pydantic.json import pydantic_encoder

from ii_agent.utils.constants import DEFAULT_MODEL

class APITypes(Enum):
    """Types of API keys."""
    OPENAI = 'openai'
    ANTHROPIC = 'anthropic'
    GEMINI = 'gemini'
    XAI = 'xai'

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

    @field_validator("api_type", mode="before")
    @classmethod
    def _normalize_api_type(cls, api_type: APITypes | str | None) -> APITypes:
        """Ensure api_type values are coerced into the APITypes enum."""
        if api_type is None or api_type is PydanticUndefined:
            return APITypes.ANTHROPIC
        if isinstance(api_type, APITypes):
            return api_type
        if isinstance(api_type, str):
            normalized = api_type.strip().lower()
            try:
                return APITypes(normalized)
            except ValueError as exc:
                raise ValueError(f"Unsupported api_type '{api_type}'") from exc
        raise ValueError(f"Unsupported api_type type '{type(api_type)}'")

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
