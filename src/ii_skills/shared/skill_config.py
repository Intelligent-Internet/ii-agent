"""
Unified Configuration for Skills

Centralizes access to:
- API credentials (NewsAPI, WHOOP, etc.)
- Email settings (Gmail)
- Database settings
- Storage settings
- User preferences

Skills can use this instead of maintaining separate config files.
"""

import os
import logging
from typing import Optional, Dict, Any
from pathlib import Path
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class EmailConfig:
    """Email configuration."""
    sender_email: str = ""
    sender_password: str = ""
    recipient_email: str = ""
    smtp_server: str = "smtp.gmail.com"
    smtp_port: int = 587


@dataclass
class StorageConfig:
    """Cloud storage configuration."""
    provider: str = "gcs"
    project_id: str = ""
    bucket_name: str = ""
    custom_domain: Optional[str] = None


@dataclass
class DatabaseConfig:
    """Database configuration."""
    url: str = ""
    async_url: str = ""


class SkillConfig:
    """
    Unified configuration for skills.

    Provides access to shared credentials and settings that skills need.

    Usage:
        from ii_skills.shared.config import get_skill_config

        config = get_skill_config()

        # Get API keys
        newsapi_key = config.get_api_key("newsapi")
        whoop_token = config.get_api_key("whoop")

        # Get email settings
        email = config.email
        print(email.sender_email)

        # Get user settings
        user_email = config.get_user_setting("email")
    """

    def __init__(self):
        """Initialize configuration."""
        self._config_loaded = False
        self._api_keys: Dict[str, str] = {}
        self._user_settings: Dict[str, Any] = {}
        self._email: Optional[EmailConfig] = None
        self._storage: Optional[StorageConfig] = None
        self._database: Optional[DatabaseConfig] = None

        self._load_from_environment()
        self._load_from_ii_agent()
        self._load_from_local_configs()

    def _load_from_environment(self):
        """Load configuration from environment variables."""
        # API Keys
        api_key_prefixes = [
            "NEWSAPI", "WHOOP", "OPENAI", "ANTHROPIC", "COINBASE",
            "YAHOO", "ALPHA_VANTAGE", "BRAVE", "GOOGLE"
        ]

        for prefix in api_key_prefixes:
            for suffix in ["_API_KEY", "_KEY", "_TOKEN", "_CLIENT_ID", "_CLIENT_SECRET"]:
                env_var = f"{prefix}{suffix}"
                value = os.environ.get(env_var)
                if value:
                    key_name = f"{prefix.lower()}{suffix.lower().replace('_', '')}"
                    self._api_keys[key_name] = value

        # Email settings
        self._email = EmailConfig(
            sender_email=os.environ.get("GMAIL_ADDRESS", os.environ.get("SENDER_EMAIL", "")),
            sender_password=os.environ.get("GMAIL_APP_PASSWORD", os.environ.get("SENDER_PASSWORD", "")),
            recipient_email=os.environ.get("RECIPIENT_EMAIL", ""),
        )

        # User settings
        self._user_settings["email"] = os.environ.get("USER_EMAIL", "")
        self._user_settings["name"] = os.environ.get("USER_NAME", "")
        self._user_settings["timezone"] = os.environ.get("USER_TIMEZONE", "America/Toronto")

    def _load_from_ii_agent(self):
        """Load configuration from ii-agent config."""
        try:
            from ii_agent.core.config.ii_agent_config import II_AGENT_CONFIG

            # Storage settings
            self._storage = StorageConfig(
                provider="gcs",
                project_id=getattr(II_AGENT_CONFIG, "GCP_PROJECT_ID", ""),
                bucket_name=getattr(II_AGENT_CONFIG, "GCS_BUCKET_NAME", ""),
                custom_domain=getattr(II_AGENT_CONFIG, "GCS_CUSTOM_DOMAIN", None),
            )

            # Database settings
            self._database = DatabaseConfig(
                url=getattr(II_AGENT_CONFIG, "DATABASE_URL", ""),
                async_url=getattr(II_AGENT_CONFIG, "DATABASE_ASYNC_URL", ""),
            )

            self._config_loaded = True
            logger.debug("Loaded configuration from ii-agent")

        except ImportError:
            logger.debug("ii-agent config not available")

    def _load_from_local_configs(self):
        """Load API keys from skill-specific config files."""
        # Try to load from common config locations
        config_locations = [
            Path("Config"),
            Path.home() / ".ii-agent",
            Path.home() / ".config" / "ii-agent",
        ]

        for config_dir in config_locations:
            if config_dir.exists():
                # Look for credential files
                for cred_file in config_dir.glob("*.env"):
                    self._load_env_file(cred_file)
                for cred_file in config_dir.glob("credentials.json"):
                    self._load_json_credentials(cred_file)

    def _load_env_file(self, path: Path):
        """Load credentials from .env file."""
        try:
            with open(path) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, value = line.split("=", 1)
                        key = key.strip().lower().replace("_", "")
                        value = value.strip().strip('"').strip("'")
                        if value:
                            self._api_keys[key] = value
        except Exception as e:
            logger.debug(f"Could not load {path}: {e}")

    def _load_json_credentials(self, path: Path):
        """Load credentials from JSON file."""
        try:
            import json
            with open(path) as f:
                data = json.load(f)
                if isinstance(data, dict):
                    for key, value in data.items():
                        if isinstance(value, str) and value:
                            self._api_keys[key.lower().replace("_", "")] = value
        except Exception as e:
            logger.debug(f"Could not load {path}: {e}")

    def get_api_key(self, service: str, key_type: str = "api_key") -> Optional[str]:
        """
        Get an API key for a service.

        Args:
            service: Service name (e.g., "newsapi", "whoop", "openai")
            key_type: Type of key (e.g., "api_key", "token", "client_id")

        Returns:
            API key or None if not found
        """
        # Normalize service name
        service = service.lower().replace("-", "").replace("_", "")

        # Try different key formats
        key_formats = [
            f"{service}{key_type.replace('_', '')}",
            f"{service}key",
            f"{service}token",
            f"{service}apikey",
            service,
        ]

        for key_format in key_formats:
            if key_format in self._api_keys:
                return self._api_keys[key_format]

        # Check environment directly as fallback
        env_formats = [
            f"{service.upper()}_API_KEY",
            f"{service.upper()}_KEY",
            f"{service.upper()}_TOKEN",
        ]

        for env_var in env_formats:
            value = os.environ.get(env_var)
            if value:
                return value

        return None

    def get_user_setting(self, key: str, default: Any = None) -> Any:
        """Get a user setting."""
        return self._user_settings.get(key, default)

    def set_user_setting(self, key: str, value: Any):
        """Set a user setting (runtime only)."""
        self._user_settings[key] = value

    @property
    def email(self) -> EmailConfig:
        """Get email configuration."""
        return self._email or EmailConfig()

    @property
    def storage(self) -> StorageConfig:
        """Get storage configuration."""
        return self._storage or StorageConfig()

    @property
    def database(self) -> DatabaseConfig:
        """Get database configuration."""
        return self._database or DatabaseConfig()

    @property
    def is_configured(self) -> bool:
        """Check if config is properly loaded from ii-agent."""
        return self._config_loaded

    def get_all_api_keys(self) -> Dict[str, str]:
        """Get all loaded API keys (masked for security)."""
        return {k: f"{v[:4]}...{v[-4:]}" if len(v) > 8 else "***" for k, v in self._api_keys.items()}


# Global config instance
_config_instance: Optional[SkillConfig] = None


def get_skill_config() -> SkillConfig:
    """Get or create the global SkillConfig instance."""
    global _config_instance
    if _config_instance is None:
        _config_instance = SkillConfig()
    return _config_instance
