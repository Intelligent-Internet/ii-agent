"""Base command handler and CommandType enum for realtime handlers."""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from typing import Any, Callable, ClassVar, Coroutine, Generic, TypeVar

from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio.session import AsyncSession

from ii_agent.agents.runs.agent import (
    ModelTurnMetricsEvent,
    RunCancelledEvent,
    RunCompletedEvent,
    RunErrorEvent,
    RunOutput,
    RunPausedEvent,
    ToolCallCompletedEvent,
)
from ii_agent.settings.llm.schemas import ModelConfig
from ii_agent.core.container import ApplicationContainer
from ii_agent.core.db import get_db_session_local
from ii_agent.core.logger import logger
from ii_agent.core.storage.client import get_storage
from ii_agent.realtime.events.app_events import (
    AgentStreamCompleteEvent,
    BaseEvent,
    ERROR_MESSAGES,
    ErrorCode,
    MetricsUpdatedEvent,
    ModelUsageEvent,
    SystemErrorEvent,
    ToolUsageEvent,
    UserMessageEvent,
)
from ii_agent.realtime.events.converter import convert_agent_event_to_realtime
from ii_agent.realtime.pubsub.asyncio_pubsub import AsyncIOPubSub
from ii_agent.realtime.schemas import CommandType, EmptyContent, BaseCommandQuery
from ii_agent.sessions.schemas import SessionInfo
from ii_agent.tasks.schemas import RunTaskResponse
from ii_agent.tasks.types import RunStatus, TaskType

Publish = Callable[[BaseEvent], Coroutine[Any, Any, None]]

TContent = TypeVar("TContent", bound=BaseModel)


class BaseCommandHandler(ABC, Generic[TContent]):
    """Base class for command handlers.

    Each handler declares its expected content type via the ``_content_type``
    class variable.  The manager calls :meth:`dispatch` which validates the
    raw ``dict`` into ``TContent`` (returning a Pydantic validation error to
    the client on failure) and then delegates to :meth:`handle`.

    Subclasses that need no payload should set ``_content_type = EmptyContent``.
    """

    _content_type: ClassVar[type[BaseModel]] = EmptyContent

    def __init__(self, pubsub: AsyncIOPubSub, container: ApplicationContainer) -> None:
        self._pubsub = pubsub
        self._container = container

    @abstractmethod
    def get_command_type(self) -> CommandType:
        """Return the command type this handler processes."""

    async def dispatch(
        self, raw_content: dict[str, Any] | BaseModel, session_info: SessionInfo
    ) -> None:
        """Entry point for tests and internal callers.

        If *raw_content* is already a Pydantic model (e.g. from
        ``ChatMessageRequest``), it's passed through.  Otherwise the raw
        dict is validated into ``_content_type``.
        """
        if isinstance(raw_content, BaseModel):
            await self.handle(raw_content, session_info)
            return
        try:
            content = self._content_type.model_validate(raw_content)
        except ValidationError as exc:
            logger.warning(
                "Validation error for %s: %s",
                self.get_command_type().value,
                exc.errors(),
            )
            await self._send_error_event(
                session_info.id,
                error_code=ErrorCode.VALIDATION_ERROR,
                message=f"Invalid payload for {self.get_command_type().value}: {exc.errors()}",
            )
            return
        await self.handle(content, session_info)

    @abstractmethod
    async def handle(self, content: TContent, session_info: SessionInfo) -> None:
        """Handle the command with validated content."""

    async def send_event(self, event: BaseEvent) -> None:
        await self._pubsub.publish(event)

    def _create_skill_creator(self, user_id: uuid.UUID | str):
        """Build the per-user skill loader used by realtime agents."""
        from ii_agent.agents.skills.db_creator import DbSkillCreator

        return DbSkillCreator(user_id=user_id, storage=get_storage())

    async def _send_error_event(
        self,
        session_id: uuid.UUID,
        error_code: ErrorCode,
        message: str | None = None,
        run_id: uuid.UUID | None = None,
        user_id: uuid.UUID | None = None,
        **kwargs: Any,
    ) -> None:
        """Send a system error event to the session.

        If *message* is not provided, the default from :data:`ERROR_MESSAGES`
        is used based on *error_code*.
        """
        detail = message or ERROR_MESSAGES.get(error_code, "An error occurred, please try again!")
        content: dict[str, Any] = {
            "message": detail,
            "error_code": str(error_code),
        }
        content.update(kwargs)
        await self.send_event(
            SystemErrorEvent(
                session_id=session_id,
                content=content,
                error_code=error_code,
                detail=detail,
                transient=True,
                run_id=run_id,
                user_id=user_id,
            )
        )

    async def validate_and_update_session(
        self,
        session_info: SessionInfo,
        query_command: BaseCommandQuery,
    ) -> tuple[bool, SessionInfo | None, ModelConfig | None]:
        """Validate session exists, user has credits, update session name.

        Delegates to ``SessionService.validate_and_prepare_for_run()`` and
        translates error codes into Socket.IO error events.
        """
        container = self._container

        async with get_db_session_local() as db:
            result = await container.session_service.validate_and_prepare_for_run(
                db,
                session_id=session_info.id,
                user_id=session_info.user_id,
                source=query_command.source,
                model_id=query_command.model_id,
                text=query_command.text,
                agent_type=query_command.agent_type,
                credit_service=container.credit_service,
                model_setting_service=container.model_setting_service,
            )
            await db.commit()

        if not result.is_valid:
            error_map = {
                "session_not_found": ErrorCode.SESSION_NOT_FOUND,
                "insufficient_credits": ErrorCode.INSUFFICIENT_CREDITS,
            }
            await self._send_error_event(
                session_info.id,
                error_code=error_map.get(result.error_code, ErrorCode.INTERNAL_ERROR),
            )
            return False, result.session_info, None

        return True, result.session_info, result.llm_config

    async def create_user_message_event(
        self,
        session_info: SessionInfo,
        query_command: BaseCommandQuery,
        db: AsyncSession,
        build_mode: str | None = None,
        run_id: uuid.UUID | None = None,
    ) -> tuple[UserMessageEvent, Any]:
        """Create and save user message event."""
        container = self._container
        file_svc = container.file_service

        files_metadata = []
        if query_command.files:
            for file_id in query_command.files:
                try:
                    file_data = await file_svc.get_file_by_id(db, file_id)
                    files_metadata.append(
                        {
                            "id": file_id,
                            "file_name": file_data.name,
                            "file_size": file_data.size,
                            "content_type": file_data.content_type,
                        }
                    )
                except Exception as e:
                    logger.warning(f"Failed to get file metadata for {file_id}: {e}")

        content = {
            "text": query_command.text,
            "files": query_command.files,
            "files_metadata": files_metadata,
        }
        if build_mode:
            content["build_mode"] = build_mode

        event = UserMessageEvent(
            session_id=session_info.id,
            run_id=run_id,
            message=query_command.text or "",
            content=content,
        )

        saved_event = await container.event_service.save_event(
            db, session_id=session_info.id, event=event
        )

        return event, saved_event

    async def check_and_claim_task(
        self,
        session_info: SessionInfo,
        db: AsyncSession,
        task_type: TaskType = TaskType.AGENT_RUN,
    ) -> RunTaskResponse | None:
        """Check for running task and claim a new one if none exists.

        Returns the claimed task, or None if another task is already active
        or the claim was a duplicate.
        """
        from ii_agent.tasks.exceptions import TaskConflictException

        svc = self._container.run_task_service
        running_task = await svc.find_active_by_session(db, session_info.id)

        if running_task:
            logger.info(
                f"Already running task for session {session_info.id}, task: {running_task.id}"
            )
            await self._send_error_event(
                session_info.id,
                error_code=ErrorCode.CONCURRENT_OPERATION,
            )
            return None

        try:
            return await svc.claim_task(
                db,
                session_id=session_info.id,
                task_type=task_type,
            )
        except TaskConflictException:
            logger.warning(
                "Duplicate task claim for session %s",
                session_info.id,
            )
            await self._send_error_event(
                session_info.id,
                error_code=ErrorCode.DUPLICATE_TASK,
            )
            return None

    async def process_agent_event_stream(
        self,
        event_stream: Any,
        session_info: SessionInfo,
        run_id: uuid.UUID,
        is_user_key: bool = False,
        llm_config: ModelConfig | None = None,
    ) -> RunStatus:
        """Process an agent event stream, emitting realtime events and handling run status.

        This is the canonical template method for consuming agent streams.
        All handlers (query, plan, continue_run) should use this instead of
        duplicating the event-loop logic.

        Publishes ``ModelUsageEvent`` (per model turn) and ``ToolUsageEvent``
        (per tool call with cost) so that ``CreditUsageHandler`` can deduct
        credits without any callback injection in the Model layer.

        Returns the final :class:`RunStatus` so the caller can act on it
        (e.g. update milestones, emit extra events).
        """
        run_service = self._container.run_task_service
        final_status: RunStatus | None = None

        async for event in event_stream:
            realtime_event = convert_agent_event_to_realtime(
                event=event,
                run_id=run_id,
                session_id=session_info.id,
            )
            if realtime_event:
                await self.send_event(realtime_event)

            # --- Billing events (per-turn LLM usage) ---
            if isinstance(event, ModelTurnMetricsEvent) and event.metrics and llm_config:
                _metrics = event.metrics
                await self.send_event(
                    ModelUsageEvent(
                        session_id=session_info.id,
                        user_id=session_info.user_id,
                        run_id=run_id,
                        setting_id=llm_config.id,
                        model_id=event.model_id,
                        provider=llm_config.provider,
                        pricing=llm_config.pricing,
                        input_tokens=_metrics.input_tokens,
                        output_tokens=_metrics.output_tokens,
                        cache_read_tokens=_metrics.cache_read_tokens,
                        cache_write_tokens=_metrics.cache_write_tokens,
                        reasoning_tokens=_metrics.reasoning_tokens,
                        is_user_key=is_user_key,
                        billing_backend=_metrics.billing_backend,
                        provider_reported_cost=_metrics.cost,
                        premium_requests=_metrics.premium_requests,
                        content={
                            "model_id": event.model_id,
                            "input_tokens": _metrics.input_tokens,
                            "output_tokens": _metrics.output_tokens,
                            "cache_read_tokens": _metrics.cache_read_tokens,
                            "cache_write_tokens": _metrics.cache_write_tokens,
                            "reasoning_tokens": _metrics.reasoning_tokens,
                            "is_user_key": is_user_key,
                            "billing_backend": _metrics.billing_backend,
                        },
                    )
                )

            # --- Billing events (per-tool-call cost) ---
            if isinstance(event, ToolCallCompletedEvent) and event.tool:
                tool_cost = self._extract_tool_cost(event)
                if tool_cost > 0:
                    tool_name = event.tool.tool_name or ""
                    await self.send_event(
                        ToolUsageEvent(
                            session_id=session_info.id,
                            user_id=session_info.user_id,
                            run_id=run_id,
                            tool_name=tool_name,
                            cost_usd=tool_cost,
                            content={
                                "tool_name": tool_name,
                                "cost_usd": tool_cost,
                            },
                        )
                    )

            if isinstance(event, RunCompletedEvent):
                final_status = RunStatus.COMPLETED
                metrics_content: dict[str, Any] = {
                    "api_version": session_info.api_version,
                }
                if event.metrics:
                    metrics_content["metrics"] = event.metrics.to_dict()
                    metrics_content["model_id"] = event.model
                await self.send_event(
                    MetricsUpdatedEvent(
                        session_id=session_info.id,
                        content=metrics_content,
                    )
                )

            if isinstance(event, RunPausedEvent):
                final_status = RunStatus.PAUSED

            if isinstance(event, RunCancelledEvent):
                final_status = RunStatus.CANCELLED

            if isinstance(event, RunErrorEvent):
                final_status = RunStatus.FAILED

            if isinstance(event, RunOutput):
                # Determine final status from the agent's run output
                if event.status == RunStatus.PAUSED:
                    final_status = RunStatus.PAUSED
                elif event.status == RunStatus.CANCELLED:
                    final_status = RunStatus.CANCELLED
                elif event.status == RunStatus.FAILED:
                    final_status = RunStatus.FAILED
                else:
                    final_status = RunStatus.COMPLETED

                await self.send_event(
                    AgentStreamCompleteEvent(
                        session_id=session_info.id,
                        content={
                            "message": "Agent run completed",
                            "run_id": event.run_id,
                            "api_version": session_info.api_version,
                        },
                    )
                )

        # If no explicit terminal/pause status was observed, treat the stream end as success.
        if final_status is None:
            final_status = RunStatus.COMPLETED

        if final_status in [*RunStatus.terminal_states(), RunStatus.PAUSED]:
            async with get_db_session_local() as db:
                await run_service.transition_status(
                    db,
                    task_id=run_id,
                    to_status=final_status,
                )
                await db.commit()

        return final_status

    @staticmethod
    def _extract_tool_cost(event: ToolCallCompletedEvent) -> float:
        """Extract USD cost from a ToolCallCompletedEvent, if any."""
        from ii_agent.agents.tools.base import ToolResult as BaseToolResult

        if event.tool and isinstance(event.tool.result, BaseToolResult):
            return event.tool.result.cost
        return 0.0
