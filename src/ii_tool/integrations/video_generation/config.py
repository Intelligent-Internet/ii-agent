import json
import os
from pydantic_settings import BaseSettings


def _extract_openai_key_from_llm_configs() -> str | None:
    """Extract OpenAI API key from LLM_CONFIGS JSON blob."""
    llm_configs_str = os.environ.get("LLM_CONFIGS")
    if not llm_configs_str:
        return None
    try:
        llm_configs = json.loads(llm_configs_str)
        # Look for an OpenAI config entry
        for config_name, config_data in llm_configs.items():
            if isinstance(config_data, dict):
                api_type = config_data.get("api_type", "").lower()
                if api_type == "openai" and config_data.get("api_key"):
                    return config_data["api_key"]
        return None
    except (json.JSONDecodeError, TypeError):
        return None


class VideoGenerateConfig(BaseSettings):
    gcp_project_id: str | None = None
    gcp_location: str | None = None
    gcs_output_bucket: str | None = None
    google_ai_studio_api_key: str | None = None
    openai_api_key: str | None = None

    def get_openai_api_key(self) -> str | None:
        """Get OpenAI API key, falling back to LLM config if not set explicitly."""
        if self.openai_api_key:
            return self.openai_api_key
        # Fallback to LLM_CONFIG__OPENAI_API_KEY env var
        key = os.environ.get("LLM_CONFIG__OPENAI_API_KEY")
        if key:
            return key
        # Fallback to extracting from LLM_CONFIGS JSON blob
        return _extract_openai_key_from_llm_configs()

    class Config:
        env_prefix = "VIDEO_GENERATE_"
        env_file = ".env"
        extra = "ignore"