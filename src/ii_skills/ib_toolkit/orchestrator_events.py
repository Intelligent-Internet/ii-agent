"""
Event System for Deal Orchestrator

Provides real-time progress updates via ii-agent's event stream
for Socket.IO broadcasting to connected clients.

Usage:
    from ii_skills.ib_toolkit.orchestrator_events import (
        EventStreamProgressCallback,
        create_orchestrator_with_events,
    )

    # With ii-agent event stream
    callback = EventStreamProgressCallback(event_stream, session_id)
    orchestrator = DealOrchestrator(user_id, progress_callback=callback)

    # Or use convenience function
    orchestrator = create_orchestrator_with_events(user_id, session_id, event_stream)
"""

import logging
from typing import Optional, Dict, Any
from datetime import datetime
from uuid import UUID, uuid4

logger = logging.getLogger(__name__)


# Event types for deal orchestration
class DealEventType:
    """Event types specific to deal orchestration."""
    DEAL_STARTED = "deal_started"
    PHASE_STARTED = "phase_started"
    PHASE_COMPLETED = "phase_completed"
    TASK_STARTED = "task_started"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"
    DEAL_COMPLETED = "deal_completed"
    DEAL_ERROR = "deal_error"
    CHECKPOINT_SAVED = "checkpoint_saved"


class EventStreamProgressCallback:
    """
    Progress callback that publishes to ii-agent event stream.

    Events are automatically broadcast to connected Socket.IO clients.
    """

    def __init__(
        self,
        event_stream=None,
        session_id: Optional[str] = None,
        run_id: Optional[str] = None,
    ):
        """
        Initialize the event stream callback.

        Args:
            event_stream: ii-agent AsyncEventStream instance
            session_id: Session ID for event routing
            run_id: Run ID for tracking
        """
        self._event_stream = event_stream
        self._session_id = UUID(session_id) if session_id else uuid4()
        self._run_id = UUID(run_id) if run_id else uuid4()
        self._deal_id: Optional[str] = None

    async def _publish(self, event_type: str, content: Dict[str, Any]):
        """Publish event to stream."""
        if self._event_stream is None:
            logger.debug(f"Event (no stream): {event_type} - {content}")
            return

        try:
            # Try to use ii-agent event types
            from ii_agent.core.event import RealtimeEvent, EventType

            # Map to closest ii-agent event type
            type_map = {
                DealEventType.DEAL_STARTED: EventType.AGENT_THINKING,
                DealEventType.PHASE_STARTED: EventType.STATUS_UPDATE,
                DealEventType.PHASE_COMPLETED: EventType.AGENT_RESPONSE,
                DealEventType.TASK_STARTED: EventType.TOOL_CALL,
                DealEventType.TASK_COMPLETED: EventType.TOOL_RESULT,
                DealEventType.TASK_FAILED: EventType.ERROR,
                DealEventType.DEAL_COMPLETED: EventType.COMPLETE,
                DealEventType.DEAL_ERROR: EventType.ERROR,
            }

            ii_event_type = type_map.get(event_type, EventType.STATUS_UPDATE)

            event = RealtimeEvent(
                type=ii_event_type,
                session_id=self._session_id,
                run_id=self._run_id,
                content={
                    "deal_event_type": event_type,
                    "deal_id": self._deal_id,
                    **content,
                },
            )

            await self._event_stream.publish(event)

        except ImportError:
            logger.debug(f"ii-agent events not available: {event_type}")
        except Exception as e:
            logger.warning(f"Failed to publish event: {e}")

    async def on_deal_start(self, deal_id: str, company_name: str, deal_type: str):
        """Called when deal analysis starts."""
        self._deal_id = deal_id
        await self._publish(DealEventType.DEAL_STARTED, {
            "company_name": company_name,
            "deal_type": deal_type,
            "message": f"Starting {deal_type.upper()} analysis for {company_name}",
        })

    async def on_phase_start(self, phase, tasks):
        """Called when a phase starts."""
        await self._publish(DealEventType.PHASE_STARTED, {
            "phase": phase.value,
            "tasks": tasks,
            "task_count": len(tasks),
            "message": f"Starting phase: {phase.value}",
        })

    async def on_task_start(self, task):
        """Called when a task starts."""
        await self._publish(DealEventType.TASK_STARTED, {
            "task_id": task.id,
            "task_name": task.name,
            "phase": task.phase.value,
            "message": f"Running: {task.name}",
        })

    async def on_task_complete(self, task):
        """Called when a task completes."""
        await self._publish(DealEventType.TASK_COMPLETED, {
            "task_id": task.id,
            "task_name": task.name,
            "phase": task.phase.value,
            "duration_ms": task.duration_ms,
            "message": f"Completed: {task.name}",
        })

    async def on_task_error(self, task, error: str):
        """Called when a task fails."""
        await self._publish(DealEventType.TASK_FAILED, {
            "task_id": task.id,
            "task_name": task.name,
            "error": error,
            "message": f"Failed: {task.name} - {error}",
        })

    async def on_phase_complete(self, phase, results):
        """Called when a phase completes."""
        await self._publish(DealEventType.PHASE_COMPLETED, {
            "phase": phase.value,
            "tasks_completed": len(results),
            "message": f"Completed phase: {phase.value}",
        })

    async def on_deal_complete(self, state):
        """Called when deal analysis completes."""
        await self._publish(DealEventType.DEAL_COMPLETED, {
            "company_name": state.company_name,
            "outputs": list(state.outputs.keys()),
            "phases_completed": len(state.completed_phases),
            "message": f"Analysis complete for {state.company_name}",
        })

    async def on_checkpoint(self, deal_id: str, phase: str):
        """Called when checkpoint is saved."""
        await self._publish(DealEventType.CHECKPOINT_SAVED, {
            "phase": phase,
            "message": f"Checkpoint saved after {phase}",
        })


class WebhookProgressCallback:
    """
    Progress callback that sends updates to a webhook URL.

    Useful for external integrations and notifications.
    """

    def __init__(
        self,
        webhook_url: str,
        auth_header: Optional[str] = None,
    ):
        """
        Initialize webhook callback.

        Args:
            webhook_url: URL to POST updates to
            auth_header: Optional Authorization header value
        """
        self._webhook_url = webhook_url
        self._auth_header = auth_header
        self._deal_id: Optional[str] = None

    async def _send(self, event_type: str, data: Dict):
        """Send webhook request."""
        try:
            import aiohttp

            headers = {"Content-Type": "application/json"}
            if self._auth_header:
                headers["Authorization"] = self._auth_header

            payload = {
                "event": event_type,
                "deal_id": self._deal_id,
                "timestamp": datetime.now().isoformat(),
                "data": data,
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self._webhook_url,
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as response:
                    if response.status >= 400:
                        logger.warning(f"Webhook failed: {response.status}")

        except ImportError:
            logger.warning("aiohttp not available for webhooks")
        except Exception as e:
            logger.warning(f"Webhook send failed: {e}")

    async def on_phase_start(self, phase, tasks):
        await self._send("phase_start", {"phase": phase.value, "tasks": tasks})

    async def on_task_start(self, task):
        await self._send("task_start", {"task_id": task.id, "name": task.name})

    async def on_task_complete(self, task):
        await self._send("task_complete", {"task_id": task.id, "duration_ms": task.duration_ms})

    async def on_task_error(self, task, error):
        await self._send("task_error", {"task_id": task.id, "error": error})

    async def on_phase_complete(self, phase, results):
        await self._send("phase_complete", {"phase": phase.value, "results": len(results)})

    async def on_deal_complete(self, state):
        await self._send("deal_complete", {"outputs": list(state.outputs.keys())})


class CompositeProgressCallback:
    """
    Combines multiple progress callbacks.

    Useful when you want both console output and event streaming.
    """

    def __init__(self, *callbacks):
        """Initialize with multiple callbacks."""
        self._callbacks = callbacks

    async def on_phase_start(self, phase, tasks):
        for cb in self._callbacks:
            await cb.on_phase_start(phase, tasks)

    async def on_task_start(self, task):
        for cb in self._callbacks:
            await cb.on_task_start(task)

    async def on_task_complete(self, task):
        for cb in self._callbacks:
            await cb.on_task_complete(task)

    async def on_task_error(self, task, error):
        for cb in self._callbacks:
            await cb.on_task_error(task, error)

    async def on_phase_complete(self, phase, results):
        for cb in self._callbacks:
            await cb.on_phase_complete(phase, results)

    async def on_deal_complete(self, state):
        for cb in self._callbacks:
            await cb.on_deal_complete(state)


def create_orchestrator_with_events(
    user_id: str,
    session_id: Optional[str] = None,
    event_stream=None,
    include_console: bool = True,
):
    """
    Create a DealOrchestrator with event stream integration.

    Args:
        user_id: User ID
        session_id: Session ID for event routing
        event_stream: ii-agent AsyncEventStream
        include_console: Also print to console

    Returns:
        Configured DealOrchestrator
    """
    from ii_skills.ib_toolkit.deal_orchestrator import (
        DealOrchestrator,
        ConsoleProgressCallback,
    )

    callbacks = []

    if event_stream:
        callbacks.append(EventStreamProgressCallback(event_stream, session_id))

    if include_console:
        callbacks.append(ConsoleProgressCallback())

    if len(callbacks) == 1:
        progress = callbacks[0]
    elif len(callbacks) > 1:
        progress = CompositeProgressCallback(*callbacks)
    else:
        progress = ConsoleProgressCallback()

    return DealOrchestrator(
        user_id=user_id,
        session_id=session_id,
        progress_callback=progress,
    )
