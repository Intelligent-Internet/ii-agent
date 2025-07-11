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
                if (
                    merged_configs[model_name].api_key is None
                    and model_name in settings.llm_configs
                ):
                    merged_configs[model_name].api_key = settings.llm_configs[
                        model_name
                    ].api_key
            self.llm_configs = merged_configs

        # Update all config attributes using a helper method
        config_attrs = [
            "search_config",
            "media_config",
            "audio_config",
            "sandbox_config",
            "client_config",
            "third_party_integration_config",
        ]

        for attr_name in config_attrs:
            self._update_config_attr(attr_name, settings)

    def _update_config_attr(self, attr_name: str, settings: Settings):
        """Helper method to update a config attribute"""
        current_config = getattr(self, attr_name)
        new_config = getattr(settings, attr_name)

        if current_config and new_config:
            current_config.update(new_config)
        elif current_config is None:
            setattr(self, attr_name, new_config)
