"""
Connector Skill

Tool-agnostic connector layer for external services. Skills reference
connectors by *category* (chat, email, calendar, knowledge_base,
project_tracker), not by product name.

The ConnectorRegistry resolves categories to the user's configured MCP
servers via ``.mcp.json``. Unconfigured connectors degrade gracefully —
they return an error dict instead of crashing.

Fork safety: Entirely new directory, no modifications to existing files.
"""

import asyncio
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from ii_skills import BaseSkill, register_skill

logger = logging.getLogger(__name__)

__version__ = "1.0.0"
__author__ = "II-Agent System"


@register_skill
class ConnectorSkill(BaseSkill):
    """Tool-agnostic connectors for chat, email, calendar, knowledge base, project trackers."""

    name = "connectors"
    version = __version__
    description = "Tool-agnostic connectors for chat, email, calendar, knowledge base, project trackers"

    SKILL_DIR = Path(__file__).parent

    def __init__(self, config: Optional[Dict] = None):
        super().__init__(config)
        self._registry = None

    def initialize(self) -> bool:
        """Initialize the connector registry."""
        from ii_skills.connectors.registry import ConnectorRegistry

        workspace_root = self.config.get("workspace_root", str(Path.cwd()))
        config_path = Path(workspace_root) / ".mcp.json"
        self._registry = ConnectorRegistry(config_path=str(config_path))
        self._initialized = True
        return True

    def validate_config(self) -> List[str]:
        """No required config — connectors are optional."""
        return []

    def get_capabilities(self) -> List[str]:
        """Return list of actions this skill provides."""
        return [
            # Discovery
            "list_connectors",
            "check_health",
            # Chat
            "send_message",
            "read_messages",
            "search_messages",
            # Email
            "send_email",
            "read_inbox",
            "search_email",
            # Calendar
            "get_calendar",
            "get_today_schedule",
            "create_event",
            # Knowledge Base
            "search_kb",
            "get_kb_page",
            # Project Tracker
            "get_tracker_tasks",
            "sync_tasks",
            # Configuration
            "get_config_template",
        ]

    def execute(self, action: str, **kwargs) -> Dict:
        """Execute a connector action."""
        loop = None
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            pass

        if loop and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, self._execute_async(action, **kwargs))
                return future.result()
        return asyncio.run(self._execute_async(action, **kwargs))

    async def _execute_async(self, action: str, **kwargs) -> Dict:
        """Async action router."""
        actions = {
            # Discovery
            "list_connectors": self._list_connectors,
            "check_health": self._check_health,
            # Chat
            "send_message": self._send_message,
            "read_messages": self._read_messages,
            "search_messages": self._search_messages,
            # Email
            "send_email": self._send_email,
            "read_inbox": self._read_inbox,
            "search_email": self._search_email,
            # Calendar
            "get_calendar": self._get_calendar,
            "get_today_schedule": self._get_today_schedule,
            "create_event": self._create_event,
            # Knowledge Base
            "search_kb": self._search_kb,
            "get_kb_page": self._get_kb_page,
            # Project Tracker
            "get_tracker_tasks": self._get_tracker_tasks,
            "sync_tasks": self._sync_tasks,
            # Configuration
            "get_config_template": self._get_config_template,
        }

        handler = actions.get(action)
        if not handler:
            raise NotImplementedError(f"Action '{action}' not implemented")
        return await handler(**kwargs)

    # ------------------------------------------------------------------
    # Ensure registry is initialized
    # ------------------------------------------------------------------

    def _ensure_registry(self) -> None:
        """Lazily initialize registry if needed."""
        if self._registry is None:
            self.initialize()

    def _get_adapter(self, category: str) -> Optional[Any]:
        """Get adapter for a category, or return None."""
        self._ensure_registry()
        return self._registry.get_connector(category)

    def _not_configured(self, category: str) -> Dict:
        """Standard error response for unconfigured connectors."""
        return {
            "error": f"No connector configured for category '{category}'",
            "available": False,
            "hint": "Add configuration to .mcp.json — see 'get_config_template' action",
        }

    # ------------------------------------------------------------------
    # Discovery Actions
    # ------------------------------------------------------------------

    async def _list_connectors(self, **kwargs) -> Dict:
        """Show all known categories and which are configured."""
        self._ensure_registry()
        from ii_skills.connectors.registry import CONNECTOR_CATEGORIES

        configured = self._registry.list_configured()
        categories = {}
        for cat, providers in CONNECTOR_CATEGORIES.items():
            categories[cat] = {
                "configured": cat in configured,
                "provider": configured.get(cat, None),
                "available_providers": providers,
            }

        return {
            "categories": categories,
            "configured": configured,
            "configured_count": len(configured),
            "total_categories": len(CONNECTOR_CATEGORIES),
        }

    async def _check_health(self, **kwargs) -> Dict:
        """Health check all configured connectors."""
        self._ensure_registry()
        health = self._registry.health_check()
        all_healthy = all(v.get("healthy", False) for v in health.values()) if health else True
        return {
            "overall": "healthy" if all_healthy else "degraded",
            "connectors": health,
        }

    # ------------------------------------------------------------------
    # Chat Actions
    # ------------------------------------------------------------------

    async def _send_message(self, channel: str, message: str, **kwargs) -> Dict:
        """Send a message via the configured chat connector."""
        adapter = self._get_adapter("chat")
        if not adapter:
            return self._not_configured("chat")
        return await adapter.send_message(channel, message)

    async def _read_messages(self, channel: str, limit: int = 20, **kwargs) -> Dict:
        """Read messages from a chat channel."""
        adapter = self._get_adapter("chat")
        if not adapter:
            return self._not_configured("chat")
        messages = await adapter.read_messages(channel, limit=limit)
        return {"messages": messages, "count": len(messages)}

    async def _search_messages(self, query: str, limit: int = 10, **kwargs) -> Dict:
        """Search chat message history."""
        adapter = self._get_adapter("chat")
        if not adapter:
            return self._not_configured("chat")
        results = await adapter.search_messages(query, limit=limit)
        return {"results": results, "count": len(results)}

    # ------------------------------------------------------------------
    # Email Actions
    # ------------------------------------------------------------------

    async def _send_email(self, to: str, subject: str, body: str, **kwargs) -> Dict:
        """Send an email via the configured email connector."""
        adapter = self._get_adapter("email")
        if not adapter:
            return self._not_configured("email")
        return await adapter.send_email(to, subject, body)

    async def _read_inbox(self, limit: int = 20, unread_only: bool = False, **kwargs) -> Dict:
        """Read inbox messages."""
        adapter = self._get_adapter("email")
        if not adapter:
            return self._not_configured("email")
        messages = await adapter.read_inbox(limit=limit, unread_only=unread_only)
        return {"messages": messages, "count": len(messages)}

    async def _search_email(self, query: str, limit: int = 10, **kwargs) -> Dict:
        """Search emails."""
        adapter = self._get_adapter("email")
        if not adapter:
            return self._not_configured("email")
        results = await adapter.search_email(query, limit=limit)
        return {"results": results, "count": len(results)}

    # ------------------------------------------------------------------
    # Calendar Actions
    # ------------------------------------------------------------------

    async def _get_calendar(self, start: str, end: str, **kwargs) -> Dict:
        """Get calendar events in a date range."""
        adapter = self._get_adapter("calendar")
        if not adapter:
            return self._not_configured("calendar")
        events = await adapter.get_events(start, end)
        return {"events": events, "count": len(events)}

    async def _get_today_schedule(self, **kwargs) -> Dict:
        """Get today's calendar events."""
        adapter = self._get_adapter("calendar")
        if not adapter:
            return self._not_configured("calendar")
        events = await adapter.get_today()
        return {"events": events, "count": len(events)}

    async def _create_event(self, title: str, start: str, end: str, **kwargs) -> Dict:
        """Create a calendar event."""
        adapter = self._get_adapter("calendar")
        if not adapter:
            return self._not_configured("calendar")
        return await adapter.create_event(title, start, end, **kwargs)

    # ------------------------------------------------------------------
    # Knowledge Base Actions
    # ------------------------------------------------------------------

    async def _search_kb(self, query: str, limit: int = 10, **kwargs) -> Dict:
        """Search the knowledge base."""
        adapter = self._get_adapter("knowledge_base")
        if not adapter:
            return self._not_configured("knowledge_base")
        results = await adapter.search(query, limit=limit)
        return {"results": results, "count": len(results)}

    async def _get_kb_page(self, page_id: str, **kwargs) -> Dict:
        """Get a knowledge base page by ID."""
        adapter = self._get_adapter("knowledge_base")
        if not adapter:
            return self._not_configured("knowledge_base")
        return await adapter.get_page(page_id)

    # ------------------------------------------------------------------
    # Project Tracker Actions
    # ------------------------------------------------------------------

    async def _get_tracker_tasks(self, status: str = "open", **kwargs) -> Dict:
        """Get tasks from the project tracker."""
        adapter = self._get_adapter("project_tracker")
        if not adapter:
            return self._not_configured("project_tracker")
        tasks = await adapter.get_my_tasks(status=status)
        return {"tasks": tasks, "count": len(tasks)}

    async def _sync_tasks(self, direction: str = "pull", **kwargs) -> Dict:
        """Sync tasks between project tracker and TASKS.md.

        direction: "pull" (remote → local), "push" (local → remote), "both"
        """
        adapter = self._get_adapter("project_tracker")
        if not adapter:
            return self._not_configured("project_tracker")

        results: Dict[str, Any] = {"direction": direction}

        if direction in ("pull", "both"):
            pulled = await adapter.sync_to_local()
            results["pulled"] = pulled
            results["pulled_count"] = len(pulled)

        if direction in ("push", "both"):
            pushed = await adapter.sync_from_local()
            results["pushed"] = pushed
            results["pushed_count"] = len(pushed)

        results["success"] = True
        return results

    # ------------------------------------------------------------------
    # Configuration Actions
    # ------------------------------------------------------------------

    async def _get_config_template(self, **kwargs) -> Dict:
        """Return the example .mcp.json configuration template."""
        template_path = self.SKILL_DIR / "config" / "connectors.example.json"
        if template_path.exists():
            import json
            template = json.loads(template_path.read_text(encoding="utf-8"))
            return {"template": template, "path": str(template_path)}
        return {"error": "Template file not found"}


def get_connector_skill(config: Optional[Dict] = None) -> ConnectorSkill:
    """Get an instance of the Connector skill."""
    skill = ConnectorSkill(config)
    skill.initialize()
    return skill
