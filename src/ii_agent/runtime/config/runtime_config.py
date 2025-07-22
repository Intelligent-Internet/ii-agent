import os
from pydantic import BaseModel, Field


class RuntimeSettings(BaseModel):
    """Configuration for the execution runtime"""

    image: str = Field(
        default=f"{os.getenv('COMPOSE_PROJECT_NAME')}-sandbox", description="Base image"
    )  # Quick fix for now, should be refactored
    system_shell: str = Field(default="system_shell", description="System shell")
    work_dir: str = Field(
        default="/workspace", description="Container working directory"
    )
    memory_limit: str = Field(default="4096mb", description="Memory limit")
    cpu_limit: float = Field(default=1.0, description="CPU limit")
    timeout: int = Field(default=600, description="Default command timeout (seconds)")
    network_enabled: bool = Field(
        default=True, description="Whether network access is allowed"
    )
    network_name: str = Field(
        default=f"{os.getenv('COMPOSE_PROJECT_NAME')}_ii",
        description="Name of the Docker network to connect to",
    )
