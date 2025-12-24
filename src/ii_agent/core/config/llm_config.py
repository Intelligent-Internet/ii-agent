from enum import Enum
from typing import Literal
from pydantic import BaseModel, Field, SecretStr, SerializationInfo, field_serializer
from pydantic.json import pydantic_encoder

from ii_agent.utils.constants import DEFAULT_MODEL


class APITypes(str, Enum):
    """Types of API keys."""

    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"
    CUSTOM = "custom"


class LLMConfig(BaseModel):
    """Configuration for the LLM.

    Attributes:
        model: The actual model identifier used by LLM API endpoints.
        application_model_name: The application config key/identifier for this model. (optional)
        api_key: The API key to use. (optional)
        base_url: The base URL for the API. This is necessary for local LLMs. (optional)
        num_retries: The number of retries to use. (optional)
        max_message_chars: The maximum number of characters in a message. (optional)
        temperature: The temperature to use. (optional)
        vertex_region: The region to use for Vertex AI. (optional)
        vertex_project_id: The project ID to use for Vertex AI. (optional)
        api_type: The type of API to use.
        thinking_tokens: The number of tokens to use for thinking. (optional)
        azure_endpoint: The endpoint to use for Azure. (optional)
        azure_api_version: The API version to use for Azure. (optional)
        cot_model: Whether cot model or not. (optional)
    """
    # present if user's settings
    setting_id: str | None = Field(default=None)
    model: str = Field(default=DEFAULT_MODEL)
    application_model_name: str | None = Field(
        default=None, description="Application config key/identifier for this model"
    )
    tokenizer: str | None = Field(default=None)
    api_key: SecretStr | None = Field(default=None)
    base_url: str | None = Field(default=None)
    max_retries: int = Field(default=10)
    max_message_chars: int = Field(default=30_000)
    temperature: float = Field(default=0.0)
    vertex_region: str | None = Field(default=None)
    vertex_project_id: str | None = Field(default=None)
    api_type: APITypes = Field(default=APITypes.ANTHROPIC)
    thinking_tokens: int = Field(default=16000)
    azure_endpoint: str | None = Field(default=None)
    azure_api_version: str | None = Field(default=None)
    cot_model: bool = Field(default=False)
    enable_extended_context: bool = Field(
        default=False,
        description="Enable 1M token context window for Anthropic models (may increase costs)"
    )
    config_type: Literal["system", "user"] | None = Field(
        default="system", description="system or user"
    )

    def get_max_context_tokens(self) -> int:
        """Get the maximum context window size for this model configuration.

        Returns:
            Maximum context tokens (1M if extended context enabled and Anthropic, otherwise 200K for Anthropic, 128K default)
        """
        if self.api_type == APITypes.ANTHROPIC:
            if self.enable_extended_context:
                return 1_000_000  # 1M context window with beta header
            return 200_000  # Standard Anthropic context window
        # Default for other models
        return 128_000

    @field_serializer("api_key")
    def api_key_serializer(self, api_key: SecretStr | None, info: SerializationInfo):
        """Custom serializer for API keys.

        To serialize the API key instead of ********, set expose_secrets to True in the serialization context.
        """
        if api_key is None:
            return None

        context = info.context
        if context and context.get("expose_secrets", False):
            return api_key.get_secret_value()

        return pydantic_encoder(api_key)

    def is_user_model(self) -> bool:
        """Check if the model is a user model."""
        return self.config_type == "user"
