"""
Base connector adapter — abstract interface for all external service connectors.

Each adapter maps to a *category* (chat, email, calendar, …), not a specific
product.  The ConnectorRegistry resolves a category to the user's configured
provider at runtime, so workflow code stays product-agnostic.
"""

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class BaseConnectorAdapter(ABC):
    """Abstract base for all connector adapters."""

    category: str = ""          # "chat", "email", "calendar", …
    provider: str = ""          # "slack", "gmail", "google_calendar", …

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self._connected = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    @abstractmethod
    async def connect(self) -> bool:
        """Establish connection to the external service.

        Returns True on success.
        """

    @abstractmethod
    async def disconnect(self) -> None:
        """Gracefully close the connection."""

    @abstractmethod
    async def health_check(self) -> Dict[str, Any]:
        """Return health status.

        Expected keys: ``{"healthy": bool, "message": str}``
        """

    @property
    def is_connected(self) -> bool:
        return self._connected

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _require_connection(self) -> None:
        """Raise if the adapter hasn't connected yet."""
        if not self._connected:
            raise RuntimeError(
                f"{self.category}/{self.provider} adapter is not connected. "
                "Call connect() first."
            )


# ======================================================================
# Category-specific abstract bases
# ======================================================================


class ChatAdapter(BaseConnectorAdapter):
    """Abstract adapter for chat services (Slack, Teams, Discord)."""

    category = "chat"

    @abstractmethod
    async def send_message(self, channel: str, message: str) -> Dict[str, Any]:
        """Send a message to a channel."""

    @abstractmethod
    async def read_messages(self, channel: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Read recent messages from a channel."""

    @abstractmethod
    async def search_messages(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Search message history."""

    @abstractmethod
    async def list_channels(self) -> List[Dict[str, Any]]:
        """List available channels."""


class EmailAdapter(BaseConnectorAdapter):
    """Abstract adapter for email services (Gmail, M365)."""

    category = "email"

    @abstractmethod
    async def send_email(self, to: str, subject: str, body: str) -> Dict[str, Any]:
        """Send an email."""

    @abstractmethod
    async def read_inbox(self, limit: int = 20, unread_only: bool = False) -> List[Dict[str, Any]]:
        """Read inbox messages."""

    @abstractmethod
    async def search_email(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Search emails."""

    @abstractmethod
    async def get_email(self, message_id: str) -> Dict[str, Any]:
        """Get a single email by ID."""


class CalendarAdapter(BaseConnectorAdapter):
    """Abstract adapter for calendar services (Google Calendar, M365)."""

    category = "calendar"

    @abstractmethod
    async def get_events(self, start: str, end: str) -> List[Dict[str, Any]]:
        """Get events in a date range (ISO-8601 strings)."""

    @abstractmethod
    async def create_event(self, title: str, start: str, end: str, **kwargs) -> Dict[str, Any]:
        """Create a calendar event."""

    @abstractmethod
    async def get_today(self) -> List[Dict[str, Any]]:
        """Get today's events."""

    @abstractmethod
    async def get_next_event(self) -> Optional[Dict[str, Any]]:
        """Get the next upcoming event."""


class KnowledgeBaseAdapter(BaseConnectorAdapter):
    """Abstract adapter for knowledge bases (Notion, Confluence, Coda)."""

    category = "knowledge_base"

    @abstractmethod
    async def search(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Search the knowledge base."""

    @abstractmethod
    async def get_page(self, page_id: str) -> Dict[str, Any]:
        """Get a single page by ID."""

    @abstractmethod
    async def create_page(self, title: str, content: str, parent_id: Optional[str] = None) -> Dict[str, Any]:
        """Create a new page."""


class ProjectTrackerAdapter(BaseConnectorAdapter):
    """Abstract adapter for project trackers (Asana, Linear, Jira)."""

    category = "project_tracker"

    @abstractmethod
    async def get_my_tasks(self, status: str = "open") -> List[Dict[str, Any]]:
        """Get tasks assigned to the current user."""

    @abstractmethod
    async def create_task(self, title: str, **kwargs) -> Dict[str, Any]:
        """Create a new task."""

    @abstractmethod
    async def update_task(self, task_id: str, **kwargs) -> Dict[str, Any]:
        """Update an existing task."""

    @abstractmethod
    async def sync_to_local(self) -> List[Dict[str, Any]]:
        """Pull remote tasks into local TASKS.md format."""

    @abstractmethod
    async def sync_from_local(self) -> List[Dict[str, Any]]:
        """Push local TASKS.md changes to the remote tracker."""
