from pydantic import Field, SecretStr, SerializationInfo, field_serializer
from pydantic.json import pydantic_encoder

from ii_agent.core.config.llm_config import LLMConfig
from ii_agent.prompts.researcher_system_prompt import ConfigConstants


class ResearcherConfig(LLMConfig):
    """Configuration for the researcher.

    Attributes:
        model: The model to use.
        api_key: The API key to use. (optional)
        base_url: The base URL for the API. This is necessary for local LLMs.
        stop_sequence: The stop sequence to use.
    """

    model: str = Field(default="r1")
    api_key: SecretStr | None = Field(default=SecretStr("sk-dummy"))
    base_url: str | None = Field(default="http://localhost:4000")
    stop_sequence: list[str] = Field(default=ConfigConstants.DEFAULT_STOP_SEQUENCE)

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
