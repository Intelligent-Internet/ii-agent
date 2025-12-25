"""Configuration for the sandbox server."""

from typing import Any, Dict, Optional
from pydantic import BaseModel, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class SandboxServerConfig(BaseModel):
    """Configuration for the sandbox server."""

    # Server settings
    host: str = Field(default="0.0.0.0", description="Server host")
    port: int = Field(default=8100, description="Server port")
    database_url: str = Field(
        default="postgresql://postgres:postgres@localhost:5432/ii_sandbox",
        description="Database URL"
    )


class SandboxConfig(BaseSettings):
    """Configuration for sandbox management.

    Loads configuration from environment variables and .env file.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Sandbox provider settings
    provider_type: str = Field(
        default="e2b",
        validation_alias="SANDBOX_PROVIDER",
        description="Type of sandbox provider to use (e.g., 'e2b', 'docker', 'local')",
    )

    # Timeout settings
    timeout_seconds: int = Field(
        default=60 * 60 * 2,
        ge=1,
        le=60 * 60 * 24,  # Max 24 hours
        description="Default timeout for sandboxes in seconds",
    )
    pause_before_timeout_seconds: int = Field(
        default=60 * 10,
        ge=1,
        le=60 * 60 * 24,  # Max 24 hours
        description="Pause before timeout for sandboxes in seconds",
    )
    timeout_buffer_seconds: int = Field(
        default=60 * 10,
        ge=1,
        le=60 * 60 * 24,  # Max 24 hours
        description="Buffer after scheduled pause for sandboxes in seconds",
    )

    # Redis queue settings
    redis_url: str = Field(
        default="redis://localhost:6379",
        description="Redis connection URL for message queue",
    )

    redis_tls_ca_path: Optional[str] = Field(
        default=None, description="Path to the CA certificate for SSL"
    )

    queue_name: str = Field(
        default="sandbox_lifecycle",
        description="Name of the Redis queue for lifecycle events",
    )

    max_retries: int = Field(
        default=3,
        ge=0,
        le=10,
        description="Maximum number of retries for failed operations",
    )

    # Optional queue provider type (for future extensibility)
    queue_provider: Optional[str] = Field(
        default="redis",
        description="Type of message queue provider ('redis', 'gcp_pubsub', or None)",
    )

    # E2B specific settings (if using E2B provider)
    e2b_api_key: Optional[str] = Field(
        default=None, description="API key for E2B sandbox provider"
    )

    e2b_template_id: Optional[str] = Field(
        default="default", description="Default E2B template to use for sandboxes"
    )

    # Docker specific settings (if using Docker provider)
    docker_image: Optional[str] = Field(
        default="ii-agent-sandbox:latest",
        description="Docker image to use for local sandboxes"
    )

    docker_network: Optional[str] = Field(
        default="bridge",
        description="Docker network mode for sandboxes"
    )

    # Resource limits defaults
    default_cpu_limit: int = Field(
        default=1000, ge=100, le=8000, description="Default CPU limit in millicores"
    )

    default_memory_limit: int = Field(
        default=512, ge=128, le=16384, description="Default memory limit in MB"
    )

    default_disk_limit: int = Field(
        default=1024, ge=256, le=102400, description="Default disk limit in MB"
    )

    default_network_enabled: bool = Field(
        default=True, description="Whether network access is enabled by default"
    )

    # Local mode settings
    local_mode: bool = Field(
        default=False,
        description="Enable local mode features like orphan sandbox cleanup. "
                   "Set to True when running docker-compose.local-only.yaml"
    )

    orphan_cleanup_enabled: bool = Field(
        default=True,
        description="Enable automatic cleanup of orphan sandboxes (only applies when local_mode=True)"
    )

    orphan_cleanup_interval_seconds: int = Field(
        default=300,  # 5 minutes
        ge=60, le=3600,
        description="Interval between orphan sandbox cleanup checks (seconds)"
    )

    backend_url: str = Field(
        default="http://backend:8000",
        description="URL of the ii-agent backend server for session verification"
    )

    @model_validator(mode="after")
    def validate_queue_settings(self) -> "SandboxConfig":
        """Validate queue-related settings based on provider type."""
        if self.queue_provider == "redis" and not self.redis_url:
            raise ValueError("redis_url is required when queue_provider is 'redis'")

        # Only require E2B API key when using E2B provider
        if self.provider_type == "e2b" and not self.e2b_api_key:
            raise ValueError(
                "E2B API key is required when using E2B provider. "
                "Set E2B_API_KEY environment variable or use SANDBOX_PROVIDER=docker for local sandboxes."
            )

        return self

    @property
    def has_queue_provider(self) -> bool:
        """Check if a queue provider is configured."""
        return self.queue_provider is not None

    @property
    def sandbox_provider(self) -> str:
        """Alias for provider_type for backward compatibility."""
        return self.provider_type

    def get_provider_config(self) -> Dict[str, Any]:
        """Get provider-specific configuration."""
        if self.provider_type == "e2b":
            return {
                "api_key": self.e2b_api_key,
                "template": self.e2b_template_id,
            }
        if self.provider_type in ("docker", "local"):
            return {
                "image": self.docker_image,
                "network": self.docker_network,
            }
        # Add other provider configs as needed
        return {}

    def get_queue_config(self) -> Optional[Dict[str, Any]]:
        """Get queue provider configuration."""
        if not self.queue_provider:
            return None

        if self.queue_provider == "redis":
            return {
                "redis_url": self.redis_url,
                "queue_name": self.queue_name,
                "max_retries": self.max_retries,
            }

        # Add other queue provider configs as needed (e.g., GCP Pub/Sub)
        return None
