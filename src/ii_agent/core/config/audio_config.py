from pydantic import BaseModel, Field, SecretStr


class AudioConfig(BaseModel):
    """Configuration for audio generation and transcription tools.

    Attributes:
        openai_api_key: The OpenAI API key for audio services.
        azure_endpoint: The Azure OpenAI endpoint for audio services.
        azure_api_version: The Azure API version for audio services.
    """

    openai_api_key: SecretStr | None = Field(
        default=None, description="OpenAI API key for audio services"
    )
    azure_endpoint: str | None = Field(
        default=None, description="Azure OpenAI endpoint for audio services"
    )
    azure_api_version: str | None = Field(
        default=None, description="Azure API version for audio services"
    )

    def update(self, settings: "AudioConfig"):
        if settings.openai_api_key:
            self.openai_api_key = settings.openai_api_key
        if settings.azure_endpoint:
            self.azure_endpoint = settings.azure_endpoint
        if settings.azure_api_version:
            self.azure_api_version = settings.azure_api_version
