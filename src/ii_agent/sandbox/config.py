import os
from pydantic import BaseModel, Field


class SandboxSettings(BaseModel):
    """Configuration for the execution sandbox"""

    image: str = Field(
        f"sandbox-{os.getenv('COMPOSE_PROJECT_NAME')}", description="Base image"
    )  # Quick fix for now, should be refactored
    system_shell: str = Field("system_shell", description="System shell")
    work_dir: str = Field("/workspace", description="Container working directory")
    memory_limit: str = Field("1024mb", description="Memory limit")
    cpu_limit: float = Field(1.0, description="CPU limit")
    timeout: int = Field(600, description="Default command timeout (seconds)")
    network_enabled: bool = Field(True, description="Whether network access is allowed")
    network_name: str = Field(
        f"ii-{os.getenv('COMPOSE_PROJECT_NAME')}",
        description="Name of the Docker network to connect to",
    )
