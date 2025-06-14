from pydantic import BaseModel, Field


class SandboxSettings(BaseModel):
    """Configuration for the execution sandbox"""

    image: str = Field("sandbox", description="Base image")
    system_shell: str = Field("system_shell", description="System shell")
    work_dir: str = Field("/workspace", description="Container working directory")
    memory_limit: str = Field("1024mb", description="Memory limit")
    cpu_limit: float = Field(1.0, description="CPU limit")
    timeout: int = Field(600, description="Default command timeout (seconds)")
    network_enabled: bool = Field(True, description="Whether network access is allowed")
    network_name: str = Field(
        "ii", description="Name of the Docker network to connect to"
    )
