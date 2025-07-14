import logging
import uuid
from typing import Optional

from ii_agent.core.event import RealtimeEvent
from ii_agent.db.manager import Events


class DatabaseSubscriber:
    """Subscriber that handles database storage for events."""

    def __init__(self, session_id: Optional[uuid.UUID], logger: logging.Logger = None):
        self.session_id = session_id
        self._logger = logger or logging.getLogger(__name__)

    def handle_event(self, event: RealtimeEvent) -> None:
        """Handle an event by saving it to the database."""
        # Save all events to database if we have a session
        if self.session_id is not None:
            Events.save_event(self.session_id, event)
        else:
            self._logger.info(f"No session ID, skipping event: {event}")

    def update_session_id(self, session_id: Optional[uuid.UUID]) -> None:
        """Update the session ID."""
        self.session_id = session_id