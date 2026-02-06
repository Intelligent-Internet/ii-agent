"""
ConnectorRegistry: Maps ~~category placeholders to configured MCP servers.

Design principle: Skills reference connectors by category (e.g., "chat"),
not by product (e.g., "slack"). The registry resolves the category to
the user's configured MCP server for that category.

This allows workflows to be portable across different tool stacks:
- Company A uses Slack + Asana + Notion
- Company B uses Teams + Jira + Confluence
- Same skill code works for both

Configuration lives in ``.mcp.json`` at the workspace root (gitignored).
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from ii_skills.connectors.adapters.base import BaseConnectorAdapter

logger = logging.getLogger(__name__)

# Known categories and their supported providers
CONNECTOR_CATEGORIES: Dict[str, List[str]] = {
    "chat": ["slack", "teams", "discord"],
    "email": ["microsoft365", "gmail"],
    "calendar": ["microsoft365", "google_calendar"],
    "knowledge_base": ["notion", "confluence", "coda"],
    "project_tracker": ["asana", "linear", "jira", "monday", "clickup"],
    "office_suite": ["microsoft365", "google_workspace"],
}


class ConnectorRegistry:
    """Resolves connector categories to configured adapter instances."""

    def __init__(self, config_path: str = ".mcp.json"):
        self._config_path = Path(config_path)
        self._config: Dict[str, Any] = {}
        self._adapters: Dict[str, BaseConnectorAdapter] = {}
        self._loaded = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_connector(self, category: str) -> Optional[BaseConnectorAdapter]:
        """Get the configured adapter for a category, or None."""
        self._ensure_loaded()
        return self._adapters.get(category)

    def list_categories(self) -> List[str]:
        """List all known connector categories."""
        return list(CONNECTOR_CATEGORIES.keys())

    def list_configured(self) -> Dict[str, str]:
        """Return mapping of configured categories to their provider names."""
        self._ensure_loaded()
        result: Dict[str, str] = {}
        connectors = self._config.get("connectors", {})
        for category, cfg in connectors.items():
            if isinstance(cfg, dict) and cfg.get("provider"):
                result[category] = cfg["provider"]
        return result

    def is_configured(self, category: str) -> bool:
        """Check if a category has a configured connector."""
        self._ensure_loaded()
        return category in self.list_configured()

    def health_check(self) -> Dict[str, Dict[str, Any]]:
        """Check health of all configured connectors.

        Returns ``{category: {"healthy": bool, "message": str}}``.
        Connectors that aren't instantiated report as not connected.
        """
        self._ensure_loaded()
        results: Dict[str, Dict[str, Any]] = {}
        configured = self.list_configured()

        for category in configured:
            adapter = self._adapters.get(category)
            if adapter and adapter.is_connected:
                results[category] = {"healthy": True, "message": f"{adapter.provider} connected"}
            elif adapter:
                results[category] = {"healthy": False, "message": f"{adapter.provider} not connected"}
            else:
                results[category] = {
                    "healthy": False,
                    "message": f"Configured ({configured[category]}) but adapter not instantiated",
                }

        return results

    def register_adapter(self, category: str, adapter: BaseConnectorAdapter) -> None:
        """Manually register an adapter for a category."""
        self._adapters[category] = adapter
        logger.info(f"Registered adapter for '{category}': {adapter.provider}")

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    def load_config(self) -> Dict[str, Any]:
        """Load configuration from .mcp.json."""
        if not self._config_path.exists():
            logger.debug(f"Config file not found: {self._config_path}")
            self._config = {}
            self._loaded = True
            return self._config

        try:
            self._config = json.loads(self._config_path.read_text(encoding="utf-8"))
            self._loaded = True
            logger.info(f"Loaded connector config from {self._config_path}")
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to load connector config: {e}")
            self._config = {}
            self._loaded = True

        return self._config

    def _ensure_loaded(self) -> None:
        """Lazily load config on first access."""
        if not self._loaded:
            self.load_config()
