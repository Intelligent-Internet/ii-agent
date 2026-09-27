"""Handler for awake_sandbox command.

Extracted from ``server.socket.command.awake_sandbox_handler``.
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
from ii_agent.realtime.schemas import AwakeSandboxContent
from ii_agent.agents.sandboxes import SandboxStatus


class AwakeSandboxHandler(BaseCommandHandler[AwakeSandboxContent]):
    """Handler for awake sandbox command."""

    _content_type = AwakeSandboxContent

    def __init__(self, pubsub: AsyncIOPubSub, container: ApplicationContainer) -> None:
        super().__init__(pubsub=pubsub, container=container)

    def get_command_type(self) -> CommandType:
        return CommandType.AWAKE_SANDBOX

    async def handle(self, content: AwakeSandboxContent, session_info: SessionInfo) -> None:
        """Handle awake sandbox request.

        Uses SandboxService.get_sandbox_for_session() which delegates to the
        correct provider (E2B or Docker).  DockerSandbox.connect() will
        automatically restart stopped/exited containers.
        """
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
                logger.error(f"Failed to awake sandbox for session {session_info.id}: {e}")
                status = SandboxStatus.ERROR.value

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
