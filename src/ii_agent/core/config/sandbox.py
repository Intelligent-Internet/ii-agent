"""Sandbox configuration settings."""

from typing import Literal, Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


# Constants
_DEFAULT_SANDBOX_TIMEOUT_SECONDS = 7200  # 2 hours

# Type aliases
SandboxProvider = Literal["e2b", "docker", "local"]


class SandboxSettings(BaseSettings):
    """Sandbox environment configuration.

    Environment variables use SANDBOX_ prefix:
        SANDBOX_PROVIDER: Sandbox provider ("e2b", "docker", "local")
        SANDBOX_E2B_API_KEY: E2B API key
        SANDBOX_E2B_TEMPLATE_ID: E2B template ID
        SANDBOX_TIMEOUT_SECONDS: Sandbox timeout in seconds
        SANDBOX_AUTO_PAUSE: Whether to auto-pause on inactivity
        SANDBOX_USER: Default user path
        SANDBOX_SERVER_URL: Sandbox server URL

    Example .env:
        SANDBOX_PROVIDER=e2b
        SANDBOX_E2B_API_KEY=your-api-key
        SANDBOX_E2B_TEMPLATE_ID=base
        SANDBOX_TIMEOUT_SECONDS=7200
        SANDBOX_AUTO_PAUSE=true
    """

    model_config = SettingsConfigDict(
        env_prefix="SANDBOX_",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Provider settings
    provider: SandboxProvider = Field(
        default="e2b",
        description="Sandbox provider to use (e2b, docker, or local)",
    )

    timeout_seconds: int = Field(
        default=_DEFAULT_SANDBOX_TIMEOUT_SECONDS,
        description="Sandbox session timeout in seconds",
        gt=0,
    )

    # E2B-specific settings
    e2b_api_key: Optional[str] = Field(
        default=None,
        description="E2B API key (required when using E2B provider)",
    )

    e2b_template_id: str = Field(
        default="base",
        description="E2B template ID for custom sandbox environments",
    )

    e2b_domain: Optional[str] = Field(
        default=None,
        description="E2B custom domain (None uses E2B default)",
    )

    extended_timeout_seconds: int = Field(
        default=14400,
        description="Extended timeout for reconnecting paused sandboxes (4 hours)",
        gt=0,
    )

    auto_pause: bool = Field(
        default=True,
        description="Auto-pause sandbox on inactivity to save resources",
    )

    # Sandbox environment settings
    user: str = Field(
        default="/home/user",
        description="Default user home directory in sandbox",
    )

    template_id: Optional[str] = Field(
        default=None,
        description="Sandbox template ID (legacy field)",
    )

    server_url: str = Field(
        default="http://localhost:8100",
        description="Sandbox server URL for API communication",
    )

    time_til_clean_up: int = Field(
        default=45 * 60,
        description="Time in seconds until sandbox cleanup (default 45 minutes)",
        gt=0,
    )

    # Docker-specific settings
    docker_image: str = Field(
        default="ii-agent-sandbox:latest",
        description="Docker image for sandbox containers",
    )

    docker_network: str = Field(
        default="ii-agent-local_ii-network",
        description="Docker network for sandbox containers",
    )

    port_range_start: int = Field(
        default=30000,
        description="Start of port range for Docker sandbox port allocation",
    )

    port_range_end: int = Field(
        default=30999,
        description="End of port range for Docker sandbox port allocation",
    )

    local_mode: bool = Field(
        default=False,
        description="Enable local mode (disables cloud features, enables orphan cleanup)",
    )

    orphan_cleanup_enabled: bool = Field(
        default=True,
        description="Enable background cleanup of orphaned Docker sandbox containers",
    )

    orphan_cleanup_interval_seconds: int = Field(
        default=60,
        description="Interval in seconds between orphan cleanup sweeps",
        gt=0,
    )

    stale_sandbox_pause_seconds: int = Field(
        default=1800,
        description="Pause sandbox containers for sessions idle longer than this (in seconds, default 30 min)",
        gt=0,
    )

    max_concurrent_sandboxes: int = Field(
        default=0,
        description=(
            "Maximum number of concurrent sandbox containers allowed. "
            "0 disables the limit. When the limit is reached, new sandbox "
            "creation is rejected with a clear error."
        ),
        ge=0,
    )

    backend_url: str = Field(
        default="http://backend:8000",
        description="Backend URL for orphan cleanup session verification",
    )

    # Configurable well-known container ports
    mcp_server_port: int = Field(
        default=6060,
        description="Container port for the MCP server",
    )

    code_server_port: int = Field(
        default=9000,
        description="Container port for code-server (VS Code)",
    )

    novnc_port: int = Field(
        default=6080,
        description="Container port for noVNC (browser-based VNC)",
    )

    docker_host: str = Field(
        default="localhost",
        description=(
            "Host address for sandbox port URLs returned to the browser. "
            "Set to the Docker host's LAN IP (e.g. 192.168.2.2) when the "
            "browser runs on a different machine."
        ),
    )

    docker_socket_path: Optional[str] = Field(
        default=None,
        description=(
            "Path to the Docker daemon socket. When None (default), auto-detects "
            "from standard locations: /var/run/docker.sock, "
            "~/.colima/default/docker.sock, ~/.orbstack/run/docker.sock, "
            "$XDG_RUNTIME_DIR/podman/podman.sock. "
            "Set explicitly via SANDBOX_DOCKER_SOCKET_PATH when using a "
            "non-standard Docker installation."
        ),
    )

    def validate_for_provider(self) -> None:
        """Validate configuration for the selected provider.

        Raises:
            ValueError: If required configuration is missing for the provider.
        """
        if self.provider == "e2b" and not self.e2b_api_key:
            raise ValueError(
                "E2B API key is required when using E2B provider. "
                "Set SANDBOX_E2B_API_KEY environment variable."
            )
