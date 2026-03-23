"""Handler for sandbox_status command."""

import logging
from typing import Dict, Any

from ii_agent.core.event import EventType, RealtimeEvent
from ii_agent.core.event_stream import EventStream
from ii_agent.server.models.sessions import SessionInfo
from ii_agent.server.shared import sandbox_service, config
from ii_agent.server.socket.command.command_handler import (
    CommandHandler,
    UserCommandType,
)

logger = logging.getLogger(__name__)


class SandboxStatusHandler(CommandHandler):
    """Handler for sandbox status command."""

    def __init__(self, event_stream: EventStream) -> None:
        """Initialize the sandbox status handler with required dependencies.

        Args:
            event_stream: Event stream for publishing events
        """
        super().__init__(event_stream=event_stream)

    def get_command_type(self) -> UserCommandType:
        return UserCommandType.SANDBOX_STATUS

    async def handle(self, content: Dict[str, Any], session_info: SessionInfo) -> None:
        """Handle get sandbox status request."""
        sandbox = await sandbox_service.get_sandbox_by_session_id(session_info.id)
        status = "not initialized"
        vscode_url = None
        if sandbox:
            status = await sandbox.status
            if status == "running":
                try:
                    vscode_url = await sandbox.expose_port(config.vscode_port, external=True)
                except Exception as e:
                    logger.warning(f"Failed to expose port for session {session_info.id}: {e}")
            del sandbox
        await self.send_event(
            RealtimeEvent(
                type=EventType.SANDBOX_STATUS,
                session_id=session_info.id,
                content={
                    "status": status,
                    "vscode_url": vscode_url
                },
            )
        )
