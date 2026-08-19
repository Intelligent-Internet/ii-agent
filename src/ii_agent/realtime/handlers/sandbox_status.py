"""Handler for sandbox_status command.

Extracted from ``server.socket.command.sandbox_status_handler``.
"""

from ii_agent.core.logger import logger
from ii_agent.realtime.pubsub import AsyncIOPubSub
from ii_agent.realtime.events.app_events import SandboxStatusChangedEvent
from ii_agent.core.container import ApplicationContainer
from ii_agent.core.db import get_db_session_local
from ii_agent.sessions.schemas import SessionInfo
from ii_agent.realtime.handlers.base import (
    BaseCommandHandler,
    CommandType,
)
from ii_agent.realtime.schemas import SandboxStatusContent
from ii_agent.agents.sandboxes import SandboxStatus


class SandboxStatusHandler(BaseCommandHandler[SandboxStatusContent]):
    """Handler for sandbox status command."""

    _content_type = SandboxStatusContent

    def __init__(self, pubsub: AsyncIOPubSub, container: ApplicationContainer) -> None:
        super().__init__(pubsub=pubsub, container=container)

    def get_command_type(self) -> CommandType:
        return CommandType.SANDBOX_STATUS

    async def handle(self, content: SandboxStatusContent, session_info: SessionInfo) -> None:
        """Handle get sandbox status request."""
        status = SandboxStatus.NOT_INITIALIZED.value
        vscode_url = None
        vnc_url = None
        sandbox_service = self._container.sandbox_service

        async with get_db_session_local() as db:
            try:
                sandbox = await sandbox_service.get_sandbox_for_session(db, session_info.id)
                if sandbox:
                    sandbox_info = await sandbox.get_info()
                    status = sandbox_info.status.value
                    vscode_url = sandbox_info.vscode_url
                    vnc_url = sandbox_info.vnc_url
            except Exception as e:
                logger.error(f"Failed to get sandbox status for session {session_info.id}: {e}")
                status = SandboxStatus.ERROR.value

        # Normalise status to the Literal expected by the event model
        valid_statuses = {"starting", "ready", "paused", "terminated", "error"}
        event_status = status if status in valid_statuses else "starting"

        await self.send_event(
            SandboxStatusChangedEvent(
                session_id=session_info.id,
                content={"status": status, "vscode_url": vscode_url, "vnc_url": vnc_url},
                status=event_status,
                vscode_url=vscode_url,
                vnc_url=vnc_url,
            )
        )
