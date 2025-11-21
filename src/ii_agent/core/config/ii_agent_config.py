import os
import secrets
from typing import Optional, Dict, Any
from pathlib import Path

from pydantic import Field, PrivateAttr, computed_field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from ii_agent.core.config.llm_config import LLMConfig
from ii_agent.storage import BaseStorage, create_storage_client
from ii_agent.utils.constants import TOKEN_BUDGET

# Constants
MAX_OUTPUT_TOKENS_PER_TURN = 32000
MAX_TURNS = 200

II_AGENT_DIR = Path(__file__).parent.parent.parent


class ResearcherAgentConfig(BaseSettings):
    researcher: LLMConfig = Field(default_factory=LLMConfig)
    report_builder: LLMConfig = Field(default_factory=LLMConfig)
    final_report_builder: LLMConfig = Field(default_factory=LLMConfig)


class IIAgentConfig(BaseSettings):
    """
    Configuration for the IIAgent.

    Attributes:
        file_store: The type of file store to use.
        file_store_path: The path to the file store.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_nested_delimiter="__",
        nested_model_default_partial_update=True,
    )
    file_store: str = Field(default="local")
    file_store_path: str = Field(default="~/.ii_agent")
    use_container_workspace: bool = Field(default=False)
    minimize_stdout_logs: bool = False
    docker_container_id: Optional[str] = None
    max_output_tokens_per_turn: int = MAX_OUTPUT_TOKENS_PER_TURN
    max_turns: int = MAX_TURNS
    token_budget: int = TOKEN_BUDGET
    database_url: Optional[str] = None
    mcp_config: Optional[Dict[str, Any]] = None
    mcp_port: int = Field(default=6060)
    vscode_port: int = Field(default=9000)
    codex_port: int = Field(default=1324)
    mcp_timeout: int = Field(default=1800)
    # Storage configuration
    # File upload storage
    storage_provider: str = Field(default="gcs")
    file_upload_project_id: str | None = None
    file_upload_bucket_name: str | None = None
    file_upload_size_limit: int = Field(default=100 * 1024 * 1024)  # 100MB default
    # Avatar storage
    avatar_project_id: str | None = None
    avatar_bucket_name: str | None = None

    # Slide assets storage (for permanent URLs)
    slide_assets_project_id: str | None = None
    slide_assets_bucket_name: str | None = None

    # Custom domain for permanent URLs
    custom_domain: str | None = Field(
        default=None,
        description="Custom domain for permanent file URLs (e.g., 'files.yourdomain.com')",
    )
    _storage: BaseStorage | None = PrivateAttr(default=None)

    # TODO: LLM configuration
    llm_configs: dict[str, LLMConfig] = Field(default_factory=dict)
    researcher_agent_config: ResearcherAgentConfig = Field(default_factory=lambda: ResearcherAgentConfig())
    # Google OAuth configuration
    google_client_id: str = Field(default="")
    google_client_secret: str = Field(default="")
    google_redirect_uri: str = Field(
        default="http://localhost:8000/auth/oauth/google/callback"
    )
    google_picker_developer_key: str = Field(default="")

    # II OAuth configuration
    ii_client_id: str = Field(default="")
    ii_redirect_uri: str = Field(default="http://localhost:8000/auth/oauth/ii/callback")
    ii_auth_base: str = Field(default="https://ii.inc/hydra")
    ii_scope: str = Field(default="openid offline profile email")
    ii_use_userinfo: bool = Field(default=False)
    ii_userinfo_url: str | None = None
    session_secret_key: str = Field(default_factory=lambda: secrets.token_urlsafe(32))

    # Stripe configuration
    stripe_secret_key: str | None = None
    stripe_price_plus_monthly: str | None = None
    stripe_price_plus_annually: str | None = None
    stripe_price_pro_monthly: str | None = None
    stripe_price_pro_annually: str | None = None
    stripe_return_url: str | None = None
    stripe_success_url: str | None = None
    stripe_cancel_url: str | None = None
    stripe_webhook_secret: str | None = None
    stripe_portal_return_url: str | None = None

    # Credits configuration
    default_user_credits: float = Field(
        default=300.0,
        description="Default credits for new users",
        ge=0.0,  # Must be non-negative
    )

    default_subscription_plan: str = Field(
        default="free",
        description="Default subscription plan for new users",
    )

    default_plans_credits: Dict[str, float] = {
        "free": 300.0,
        "plus": 2000.0,
        "pro": 10000.0,
    }

    beta_program_enabled: bool = Field(
        default=True,
        description="Toggle for granting beta program bonus credits on login",
    )
    waitlist_enabled: bool = Field(
        default=False,
        description="Toggle for enabling waitlist program",
    )
    beta_program_bonus_credits: float = Field(
        default=2000.0,
        description="Bonus credits granted to beta program users",
        ge=0.0,
    )

    # Context Cliff Benchmark configuration
    # Opt-in ONLY - user permission required for cost
    cliff_benchmark_enabled: bool = Field(
        default=False,
        description="Enable context cliff benchmarking (opt-in, makes API calls)",
    )
    cliff_benchmark_mock_mode: bool = Field(
        default=True,
        description="Run cliff benchmarks in mock mode (zero cost, no API calls)",
    )
    cliff_benchmark_usage_threshold: int = Field(
        default=10,
        description="Run benchmarks after N model uses (cost-averse default)",
    )
    cliff_benchmark_interval_minutes: int = Field(
        default=60,
        description="Wait N minutes between benchmark runs",
    )
    cliff_benchmark_max_concurrent: int = Field(
        default=1,
        description="Maximum concurrent benchmarks (cost control)",
    )

    # Golden Band Context Optimization
    # Disabled by default - requires analysis first
    golden_band_optimization_enabled: bool = Field(
        default=False,
        description="Enable golden band breadcrumb optimization (requires band analysis)",
    )
    golden_band_learning_enabled: bool = Field(
        default=True,
        description="Learn golden bands from needle-in-haystack tests", flag=True,
    )
    golden_band_auto_optimize: bool = Field(
        default=False,
        description="Auto-place breadcrumbs in golden bands (opt-in for safety)",
    )
    golden_band_reduce_search_priority: bool = Field(
        default=True,
        description="Lower search priority for golden-band breadcrumbs (they're easier to find)",
    )

    # Per session config
    # TODO: move to a separate class
    session_id: Optional[str] = None
    auto_approve_tools: bool = False  # Global tool approval setting. If True, all tools will be automatically approved.
    allow_tools: set[str] = set()  # Tools that are confirmed by the user

    # Sandbox configuration
    sandbox_user: str = Field(
        default="/home/pn", description="Default user for sandbox environments"
    )
    workspace_path: str = Field(default="/workspace")  # workspace path in sandbox
    workspace_upload_subpath: str = Field(
        default="uploads"
    )  # upload subpath in workspace
    time_til_clean_up: int = Field(
        default=45 * 60,
        description="Time in seconds until sandbox cleanup (default 45 minutes)",
    )

    # Tool server configuration
    tool_server_url: str = Field(default="http://localhost:1236")
    # Sandbox server configuration
    sandbox_server_url: str = Field(default="http://localhost:8100")
    sandbox_template_id: str | None = Field(default=None)
    environment: str = Field(default="dev")
    redis_session_url: str = Field(default="redis://localhost:6379/0")
    redis_session_enabled: bool = Field(default=False)

    @model_validator(mode="after")
    def set_database_url(self) -> "IIAgentConfig":
        if self.database_url is None:
            # Default to DuckDB - better performance for local analytics
            # Set DATABASE_URL environment variable to opt-in to other databases
            db_path = os.path.expanduser("~/.ii_agent/ii_agent.duckdb")
            self.database_url = os.getenv(
                "DATABASE_URL",
                f"duckdb:///{db_path}",
            )

        return self

    @computed_field
    @property
    def sync_database_url(self) -> str:
        """Return the synchronous database URL."""
        # Convert async PostgreSQL URL to sync
        if "+asyncpg" in self.database_url:
            return self.database_url.replace("+asyncpg", "")
        # Handle DuckDB (already synchronous)
        elif "duckdb://" in self.database_url:
            return self.database_url
        # Keep backward compatibility for SQLite
        elif "+aiosqlite" in self.database_url:
            return self.database_url.replace("+aiosqlite", "")
        return self.database_url

    @property
    def is_redis_ssl(self) -> bool:
        """Check if the database connection uses SSL."""
        return config.redis_session_url.startswith("rediss://")

    @computed_field
    @property
    def logs_path(self) -> str:
        return os.path.join(self.file_store_path, "logs")

    @computed_field
    @property
    def workspace_upload_path(self) -> str:
        return os.path.join(self.workspace_path, self.workspace_upload_subpath)

    @computed_field
    @property
    def ii_auth_url(self) -> str:
        return f"{self.ii_auth_base.rstrip('/')}/oauth2/auth"

    @computed_field
    @property
    def ii_token_url(self) -> str:
        return f"{self.ii_auth_base.rstrip('/')}/oauth2/token"

    @computed_field
    @property
    def ii_revoke_url(self) -> str:
        return f"{self.ii_auth_base.rstrip('/')}/oauth2/revoke"

    @computed_field
    @property
    def ii_issuer(self) -> str:
        return self.ii_auth_base.rstrip("/")

    @field_validator("file_store_path")
    def expand_path(cls, v):
        if v.startswith("~"):
            return os.path.expanduser(v)
        return v

    def set_auto_approve_tools(self, value: bool) -> None:
        """Set the auto_approve_tools field value.

        Args:
            value: Whether to automatically approve tool executions in CLI mode
        """
        self.auto_approve_tools = value

    def _init_storage(self) -> BaseStorage:
        """Instantiate and cache the storage client."""
        if not self.file_upload_project_id or not self.file_upload_bucket_name:
            raise ValueError(
                "File upload storage is not configured. "
                "Set FILE_UPLOAD_PROJECT_ID and FILE_UPLOAD_BUCKET_NAME environment variables."
            )

        return create_storage_client(
            self.storage_provider,
            self.file_upload_project_id,
            self.file_upload_bucket_name,
            self.custom_domain,
        )

    @property
    def storage(self) -> BaseStorage:
        if self._storage is None:
            self._storage = self._init_storage()
        return self._storage


config = IIAgentConfig()
