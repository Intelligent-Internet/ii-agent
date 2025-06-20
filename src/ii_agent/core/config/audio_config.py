from pydantic import BaseModel, Field, SecretStr


class AudioConfig(BaseModel):
    """Configuration for audio generation and transcription tools.
    
    Attributes:
        openai_api_key: The OpenAI API key for audio services.
        azure_endpoint: The Azure OpenAI endpoint for audio services.
        azure_api_version: The Azure API version for audio services.
    """
    openai_api_key: SecretStr | None = Field(default=None, description="OpenAI API key for audio services")
    azure_endpoint: str | None = Field(default=None, description="Azure OpenAI endpoint for audio services")
    azure_api_version: str | None = Field(default=None, description="Azure API version for audio services") 