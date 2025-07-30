from __future__ import annotations
from typing import Dict

from pydantic import (
    BaseModel, 
    Field,
)

from ii_agent.core.config.llm_config import LLMConfig
from ii_agent.core.config.cli_config import CliConfig
from ii_tool.core.config import WebSearchConfig, WebVisitConfig, ImageSearchConfig, VideoGenerateConfig, ImageGenerateConfig, FullStackDevConfig


class Settings(BaseModel):
    """
    Persisted settings for II_AGENT sessions
    """

    llm_configs: Dict[str, LLMConfig] = Field(default_factory=dict)
    web_search_config: WebSearchConfig = Field(default_factory=WebSearchConfig)
    web_visit_config: WebVisitConfig = Field(default_factory=WebVisitConfig)
    fullstack_dev_config: FullStackDevConfig = Field(default_factory=FullStackDevConfig)
    image_search_config: ImageSearchConfig | None = Field(default=None)
    video_generate_config: VideoGenerateConfig | None = Field(default=None)
    image_generate_config: ImageGenerateConfig | None = Field(default=None)
    cli_config: CliConfig | None = Field(default=None)

    model_config = {
        'validate_assignment': True,
    }