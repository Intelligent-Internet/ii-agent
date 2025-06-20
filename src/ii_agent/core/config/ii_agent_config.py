from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class IIAgentConfig(BaseSettings):
    """
    Configuration for the IIAgent.

    Attributes:
        file_store: The type of file store to use.
        file_store_path: The path to the file store.
    """

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
    file_store: str = Field(default="local")
    file_store_path: str = Field(default="~/.ii_agent/file_store")
