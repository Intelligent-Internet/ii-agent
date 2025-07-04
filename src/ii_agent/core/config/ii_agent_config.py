import os
from typing import Optional
from pydantic import Field, computed_field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from ii_agent.utils.constants import TOKEN_BUDGET
from pathlib import Path

from ii_agent.utils.constants import WorkSpaceMode

# Constants
MAX_OUTPUT_TOKENS_PER_TURN = 32000
MAX_TURNS = 200

II_AGENT_DIR = Path(__file__).parent.parent.parent


class IIAgentConfig(BaseSettings):
    """
    Configuration for the IIAgent.

    Attributes:
        file_store: The type of file store to use.
        file_store_path: The path to the file store.
    """

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )
    file_store: str = Field(default="local")
    file_store_path: str = Field(default="/.ii_agent")
    host_workspace_path: str = Field(default="~/.ii_agent/workspace")
    use_container_workspace: WorkSpaceMode = Field(default=WorkSpaceMode.DOCKER)
    minimize_stdout_logs: bool = False
    max_output_tokens_per_turn: int = MAX_OUTPUT_TOKENS_PER_TURN
    max_turns: int = MAX_TURNS
    token_budget: int = TOKEN_BUDGET
    database_url: Optional[str] = None

    @model_validator(mode="after")
    def set_database_url(self) -> "IIAgentConfig":
        if self.database_url is None:
            self.database_url = (
                f"sqlite:///{os.path.expanduser(self.file_store_path)}/ii_agent.db"
            )

        return self

    @computed_field
    @property
    def workspace_root(self) -> str:
        return os.path.join(self.file_store_path, "workspace")

    @computed_field
    @property
    def host_workspace(self) -> str:
        return os.path.expanduser(self.host_workspace_path)

    @computed_field
    @property
    def logs_path(self) -> str:
        return os.path.join(self.file_store_path, "logs")

    @field_validator("file_store_path")
    def expand_path(cls, v):
        if v.startswith("~"):
            return os.path.expanduser(v)
        return v


if __name__ == "__main__":
    config = IIAgentConfig()
    print(config.workspace_root)
