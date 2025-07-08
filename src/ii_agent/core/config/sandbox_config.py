from pydantic import BaseModel, Field, SecretStr, SerializationInfo, field_serializer
from pydantic.json import pydantic_encoder

from ii_agent.utils.constants import WorkSpaceMode


class SandboxConfig(BaseModel):
    """Configuration for the sandbox."""

    mode: WorkSpaceMode = Field(default=WorkSpaceMode.DOCKER)
    template_id: str | None = Field(default=None)
    sandbox_api_key: SecretStr | None = Field(default=None)
    service_port: int = Field(default=17300)

    @field_serializer("sandbox_api_key")
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

    def update(self, settings: "SandboxConfig"):
        if settings.sandbox_api_key and self.sandbox_api_key is None:
            self.sandbox_api_key = settings.sandbox_api_key
        if settings.service_port and self.service_port is None:
            self.service_port = settings.service_port
        if settings.mode and self.mode is None:
            self.mode = settings.mode
        if settings.template_id and self.template_id is None:
            self.template_id = settings.template_id
