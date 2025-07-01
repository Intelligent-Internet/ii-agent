from pydantic import BaseModel, Field, SecretStr, SerializationInfo, field_serializer
from pydantic.json import pydantic_encoder


class ThirdPartyIntegrationConfig(BaseModel):
    """Configuration for database tools.

    Attributes:
        neon_db_api_key: The Neon DB API key.
        openai_api_key: The OpenAI API key.
        vercel_api_key: The Vercel API key.
    """

    neon_db_api_key: SecretStr | None = Field(
        default=None, description="Neon DB API key"
    )
    openai_api_key: SecretStr | None = Field(default=None, description="OpenAI API key")
    vercel_api_key: SecretStr | None = Field(default=None, description="Vercel API key")

    @field_serializer("neon_db_api_key", "openai_api_key", "vercel_api_key")
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
