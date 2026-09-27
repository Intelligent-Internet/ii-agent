"""Handler for cancel command.

Extracted from ``server.socket.command.cancel_handler``.
"""

from ii_agent.core.redis import cancel
from ii_agent.core.container import ApplicationContainer
from ii_agent.realtime.pubsub import AsyncIOPubSub
from ii_agent.tasks.types import RunStatus
from ii_agent.core.db import get_db_session_local
from ii_agent.sessions.schemas import SessionInfo
from ii_agent.core.logger import logger
from ii_agent.realtime.events.app_events import (
    AgentResponseInterruptedEvent,
    ErrorCode,
)
from ii_agent.realtime.handlers.base import (
    BaseCommandHandler,
    CommandType,
)
from ii_agent.realtime.schemas import CancelContent


class CancelHandler(BaseCommandHandler[CancelContent]):
    """Handler for cancel command."""

    _content_type = CancelContent

    def __init__(self, pubsub: AsyncIOPubSub, container: ApplicationContainer) -> None:
        super().__init__(pubsub=pubsub, container=container)

    def get_command_type(self) -> CommandType:
        return CommandType.CANCEL

    async def handle(self, content: CancelContent, session: SessionInfo) -> None:
        """Handle cancel request -- signals the running agent to stop."""
        svc = self._container.run_task_service
        async with get_db_session_local() as db:
            last_task = await svc.get_last_by_session_id(db, session.id)
            if not last_task:
                await self._send_error_event(
                    session.id,
                    error_code=ErrorCode.RUN_NOT_FOUND,
                    message="Task Run not found",
                )
                return

            if last_task.status == RunStatus.ABORTING:
                # Task already aborting — check if the agent is still alive.
                run_id = last_task.id
                active_runs = await cancel.get_active_runs()
                if str(run_id) in active_runs:
                    # Agent is still tracked — re-signal cancellation.
                    await cancel.cancel_run(str(run_id))
                    logger.info(
                        f"Re-signalled cancellation for aborting run {run_id} "
                        f"in session {session.id}"
                    )
                else:
                    # Agent is gone (e.g. server restarted) — force to CANCELLED.
                    await self._force_cancel(db, svc, last_task.id, session)
                return

            if last_task.status not in [RunStatus.RUNNING, RunStatus.PAUSED]:
                logger.info(
                    f"Cancel requested for non-running task {last_task.id} "
                    f"in status {last_task.status}, no action taken."
                )
                return

            await svc.transition_status(db, task_id=last_task.id, to_status=RunStatus.ABORTING)
            await db.commit()

        run_id = last_task.id
        cancelled = await cancel.cancel_run(str(run_id))

        if cancelled:
            logger.info(f"Run {run_id} cancelled for session {session.id}")
        else:
            # Run not registered — agent is likely dead (e.g. server restart).
            # Force-transition to CANCELLED so the session isn't stuck.
            logger.warning(
                f"Run {run_id} not registered in cancellation manager, "
                f"force-cancelling orphaned task"
            )
            async with get_db_session_local() as db:
                await self._force_cancel(db, svc, run_id, session)

    async def _force_cancel(self, db, svc, task_id, session) -> None:
        """Transition an orphaned task to CANCELLED and notify the frontend."""
        await svc.transition_status(
            db,
            task_id=task_id,
            to_status=RunStatus.CANCELLED,
            error_message="Force-cancelled: agent no longer running",
        )
        await db.commit()

        await self.send_event(
            AgentResponseInterruptedEvent(
                session_id=session.id,
                run_id=task_id,
                content={
                    "message": "Run was cancelled",
                    "run_id": str(task_id),
                    "run_status": RunStatus.CANCELLED,
                },
            )
        )
        logger.info(f"Force-cancelled orphaned task {task_id} for session {session.id}")
