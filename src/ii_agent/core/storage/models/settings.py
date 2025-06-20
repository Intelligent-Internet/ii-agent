from __future__ import annotations
from typing import Dict

from pydantic import (
    BaseModel, 
    Field,
)

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

    model_config = {
        'validate_assignment': True,
    }