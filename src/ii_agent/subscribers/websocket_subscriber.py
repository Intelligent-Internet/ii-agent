import logging
from typing import Optional
from fastapi import WebSocket

from ii_agent.core.event import RealtimeEvent, EventType


class WebSocketSubscriber:
    """Subscriber that handles WebSocket communication for events."""

    def __init__(self, websocket: Optional[WebSocket], logger: logging.Logger = None):
        self.websocket = websocket
        self._logger = logger or logging.getLogger(__name__)

    async def handle_event(self, event: RealtimeEvent) -> None:
        """Handle an event by sending it to the WebSocket if appropriate."""
        # Only send to websocket if this is not an event from the client and websocket exists
        if event.type != EventType.USER_MESSAGE and self.websocket is not None:
            try:
                await self.websocket.send_json(event.model_dump())
            except Exception as e:
                # If websocket send fails, just log it and continue processing
                self._logger.warning(
                    f"Failed to send message to websocket: {str(e)}"
                )
                # Set websocket to None to prevent further attempts
                self.websocket = None

    def update_websocket(self, websocket: Optional[WebSocket]) -> None:
        """Update the websocket connection."""
        self.websocket = websocket