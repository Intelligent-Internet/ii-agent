from __future__ import annotations
from typing import Dict

from pydantic import (
    BaseModel,
    Field,
)

from ii_agent.core.config.client_config import ClientConfig
from ii_agent.core.config.database_config import ThirdPartyIntegrationConfig
from ii_agent.core.config.sandbox_config import SandboxConfig
from ii_agent.core.config.search_config import SearchConfig
from ii_agent.core.config.media_config import MediaConfig
from ii_agent.core.config.audio_config import AudioConfig
from ii_agent.core.config.llm_config import LLMConfig


class Settings(BaseModel):
    """
    Persisted settings for II_AGENT sessions
    """

    llm_configs: Dict[str, LLMConfig] = Field(default_factory=dict)
    search_config: SearchConfig | None = Field(default=None)
    media_config: MediaConfig | None = Field(default=None)
    audio_config: AudioConfig | None = Field(default=None)
    sandbox_config: SandboxConfig | None = Field(default=None)
    client_config: ClientConfig | None = Field(default=None)
    third_party_integration_config: ThirdPartyIntegrationConfig | None = Field(
        default=None
    )

    model_config = {
        "validate_assignment": True,
    }

    def update(self, settings: Settings):
        if self.llm_configs and settings.llm_configs:
            merged_configs = self.llm_configs.copy()

            for model_name in merged_configs.keys():
                if merged_configs[model_name].api_key is None:
                    merged_configs[model_name].api_key = settings.llm_configs[
                        model_name
                    ].api_key
            self.llm_configs = merged_configs

        if self.search_config and settings.search_config:
            self.search_config.update(settings.search_config)
        elif self.search_config is None:
            self.search_config = settings.search_config

        if self.media_config and settings.media_config:
            self.media_config.update(settings.media_config)
        elif self.media_config is None:
            self.media_config = settings.media_config

        if self.audio_config and settings.audio_config:
            self.audio_config.update(settings.audio_config)
        elif self.audio_config is None:
            self.audio_config = settings.audio_config

        if self.sandbox_config and settings.sandbox_config:
            self.sandbox_config.update(settings.sandbox_config)
        elif self.sandbox_config is None:
            self.sandbox_config = settings.sandbox_config

        if self.client_config and settings.client_config:
            self.client_config.update(settings.client_config)
        elif self.client_config is None:
            self.client_config = settings.client_config

        if (
            self.third_party_integration_config
            and settings.third_party_integration_config
        ):
            self.third_party_integration_config.update(
                settings.third_party_integration_config
            )
        elif self.third_party_integration_config is None:
            self.third_party_integration_config = (
                settings.third_party_integration_config
            )
