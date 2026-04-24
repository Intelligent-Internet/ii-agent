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

    max_paused_age_seconds: int = Field(
        default=72 * 3600,
        description=(
            "Maximum age of a paused session-attached sandbox before it is "
            "marked DELETED by the cleanup sweep. Prevents indefinite "
            "accumulation of stale paused rows whose underlying networks or "
            "volumes may no longer be valid (e.g. after host reboot). "
            "Default 72h."
        ),
        gt=0,
    )

    stale_deleted_purge_age_seconds: int = Field(
        default=30 * 24 * 3600,
        description=(
            "Delete rows from agent_sandboxes where status='deleted' and "
            "updated_at is older than this. Keeps the table compact. "
            "Default 30 days."
        ),
        gt=0,
    )

    max_sandbox_restart_failures: int = Field(
        default=3,
        description=(
            "Per-sandbox circuit breaker: after this many consecutive "
            "reconnect/restart failures within the failure window, the "
            "sandbox is auto-marked DELETED and further reconnects are "
            "refused until the next cleanup sweep creates a fresh one."
        ),
        gt=0,
    )

    sandbox_failure_window_seconds: int = Field(
        default=300,
        description=(
            "Sliding window (in seconds) for counting consecutive sandbox "
            "reconnect failures used by the circuit breaker."
        ),
        gt=0,
    )

    sandbox_status_cache_seconds: int = Field(
        default=15,
        description=(
            "How long the sandbox_status WebSocket handler caches a successful "
            "response per-session. Prevents frontend polling from saturating "
            "the Docker API. Error responses are cached for half this value."
        ),
        ge=0,
    )

    docker_call_timeout_seconds: float = Field(
        default=8.0,
        description=(
            "Timeout for Docker API calls made in request/WebSocket hot paths. "
            "Keeps the event loop responsive when the Docker daemon is slow."
        ),
        gt=0.0,
    )

    docker_executor_max_workers: int = Field(
        default=8,
        description=(
            "Maximum worker threads in the dedicated Docker executor. "
            "Isolates Docker API calls from the default asyncio executor so "
            "slow Docker operations cannot starve database I/O."
        ),
        gt=0,
    )

    event_loop_slow_callback_seconds: float = Field(
        default=0.5,
        description=(
            "Threshold above which asyncio logs slow callbacks (in seconds). "
            "Useful for spotting blocking I/O. Set to 0 to disable."
        ),
        ge=0.0,
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

    sandbox_concurrent_create_limit: int = Field(
        default=2,
        description=(
            "Maximum number of in-flight sandbox provider create() calls "
            "allowed concurrently. Protects the kernel from veth/bridge "
            "allocation bursts that drive high-order page fragmentation "
            "(observed in the 2026-04-23 WSL2 force-reboot). Pool warming "
            "and user traffic both pass through this gate. Set to 0 to "
            "disable (not recommended on WSL2 / constrained hosts)."
        ),
        ge=0,
    )

    sandbox_create_wait_log_threshold_ms: int = Field(
        default=500,
        description=(
            "Log at INFO when a sandbox create call waits longer than this "
            "many milliseconds for the concurrent-create semaphore. Helps "
            "detect sustained contention."
        ),
        ge=0,
    )

    # ── Host resource monitor (Phase 2) ───────────────────────────────────
    # Integrated /proc-based monitor that watches kernel memory
    # fragmentation, docker-daemon latency, and triggers backpressure
    # before the host wedges. Design: docs/runtime-docs/host-resource-monitoring.md

    host_monitor_enabled: bool = Field(
        default=True,
        description=(
            "Enable the in-backend host resource monitor. Samples /proc "
            "every orphan_cleanup_interval_seconds, evaluates fragmentation "
            "and dockerd health, and applies backpressure (pool warming, "
            "sandbox creation refusal) when the host is under memory "
            "pressure. Set to false to disable entirely."
        ),
    )

    host_monitor_proc_root: str = Field(
        default="/proc",
        description=(
            "Root path to /proc. Overridable for tests with synthetic "
            "fixtures. Production: always /proc."
        ),
    )

    baseline_capture_enabled: bool = Field(
        default=True,
        description=(
            "Maintain a sliding-window ring buffer of host samples so "
            "evaluate() can derive percentile thresholds instead of "
            "relying on hardcoded numbers that would false-alarm on "
            "healthy fluctuation."
        ),
    )

    baseline_capture_retention_hours: int = Field(
        default=48,
        description=(
            "Hours of samples kept in the ring buffer. At 60s sampling "
            "this is ~2880 samples (~230 KB)."
        ),
        gt=0,
    )

    baseline_capture_interval_seconds: int = Field(
        default=60,
        description=(
            "Sampling interval. Aligned with orphan-cleanup interval by "
            "default so sampling piggy-backs on the existing loop."
        ),
        gt=0,
    )

    baseline_capture_persist_path: str = Field(
        default="",
        description=(
            "If non-empty, write a JSON percentile summary to this path on "
            "orderly backend shutdown. Strictly for post-incident "
            "forensics; history is NOT reloaded across restarts."
        ),
    )

    host_monitor_order7_warn_floor: int = Field(
        default=2,
        description=(
            "Hard WARN floor for /proc/buddyinfo Normal zone order-7 free "
            "blocks. Applied in addition to percentile-derived thresholds "
            "to prevent silent drift during a slow leak."
        ),
        ge=0,
    )

    host_monitor_order7_crit_floor: int = Field(
        default=0,
        description=(
            "Hard CRIT floor for order-7 free blocks. At 0, any allocation "
            "of an order-7 page requires compaction first."
        ),
        ge=0,
    )

    host_monitor_mem_available_warn_mb: int = Field(
        default=1024,
        description="Hard WARN floor for MemAvailable (MB).",
        gt=0,
    )

    host_monitor_mem_available_crit_mb: int = Field(
        default=512,
        description="Hard CRIT floor for MemAvailable (MB).",
        gt=0,
    )

    host_monitor_docker_p99_watch_s: float = Field(
        default=2.0,
        description=(
            "docker_call p99 duration threshold (seconds) that triggers "
            "WATCH state. Symptom of a slowing Docker daemon."
        ),
        gt=0.0,
    )

    host_monitor_docker_p99_warn_s: float = Field(
        default=4.0,
        description="docker_call p99 duration threshold (seconds) for WARN.",
        gt=0.0,
    )

    host_monitor_transition_sticky_seconds: int = Field(
        default=120,
        description=(
            "Hysteresis: a state must be violated for this many seconds "
            "before transitioning. Prevents thrashing on transient spikes."
        ),
        gt=0,
    )

    host_monitor_bootstrap_fraction: float = Field(
        default=0.25,
        description=(
            "Fraction of baseline_capture_retention_hours that must elapse "
            "before percentile-based thresholds engage. Before this the "
            "monitor uses only hardcoded floors. 0.25 * 48h = 12h."
        ),
        gt=0.0,
        le=1.0,
    )

    host_monitor_docker_latency_window: int = Field(
        default=60,
        description=(
            "Rolling window (number of most recent docker_call samples) "
            "used to compute p50/p95/p99. At 1 call/sec this is 1 minute."
        ),
        gt=0,
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

    # Pre-warmed sandbox pool (Docker provider, local mode only)
    prewarm_pool_size: int = Field(
        default=0,
        description=(
            "Number of pre-warmed sandbox containers kept on standby for fast "
            "session start. 0 disables the feature. Only effective when "
            "provider='docker' AND local_mode=true. Counts toward "
            "max_concurrent_sandboxes."
        ),
        ge=0,
        le=16,
    )

    prewarm_max_age_seconds: int = Field(
        default=86400,  # 24h
        description=(
            "Maximum lifetime of a pool container before retirement. "
            "Retirement is staggered across slots via the modulo formula "
            "retire_at = created_at + max_age - (slot * max_age/N) so the pool "
            "never empties simultaneously. Replacements get full max_age."
        ),
        gt=0,
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
