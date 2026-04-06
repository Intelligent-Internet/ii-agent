"""Handler for cowork_query command with agent overrides.

Adapted from the legacy ``server.socket.command.cowork_query``
to use the new ``BaseCommandHandler`` / pubsub / container pattern.
"""

from __future__ import annotations

from ii_agent.agents.factory.agent import agent_factory
from ii_agent.agents.types import AgentType
from ii_agent.core.db import get_db_session_local
from ii_agent.core.logger import logger
from ii_agent.realtime.events.app_events import ErrorCode
from ii_agent.realtime.handlers.base import CommandType
from ii_agent.realtime.handlers.query import UserQueryHandler
from ii_agent.realtime.schemas import QueryCommandContent
from ii_agent.sessions.schemas import SessionInfo
from ii_agent.sessions.types import AppKind
from ii_agent.settings.llm.schemas import ModelConfig
from ii_agent.tasks.types import RunStatus, TaskType


class CoworkQueryHandler(UserQueryHandler):
    """Handler for cowork-specific query command with agent overrides."""

    COWORK_SESSION_AGENT_TYPE = "cowork"

    def get_command_type(self) -> CommandType:
        return CommandType.COWORK_QUERY

    async def handle(self, content: QueryCommandContent, existing_session: SessionInfo) -> None:
        query_command = content

        # Stamp the session as a cowork app_kind so it is excluded from the
        # standard Project sidebar listing. Cowork sessions are managed by
        # the desktop runtime and must never appear there.
        await self._ensure_cowork_app_kind(existing_session.id)

        is_valid, session_info, llm_config = await self.validate_and_update_session(
            existing_session, query_command
        )

        # For cowork mode, fall back to hardcoded model if resolution fails
        if not is_valid or not llm_config:
            if not session_info:
                return

        await self._handle_cowork_query(query_command, session_info, llm_config)

    async def _handle_cowork_query(
        self,
        query_command: QueryCommandContent,
        session_info: SessionInfo,
        llm_config: ModelConfig,
    ) -> None:
        """Handle cowork query by delegating to the cowork agent factory."""
        plan_service = self._container.plan_service
        run_service = self._container.run_task_service

        milestone_context = None
        if query_command.milestone_ids and query_command.plan_context:
            milestone_context = plan_service.get_milestone_context(
                plan_context=query_command.plan_context,
                milestone_ids=query_command.milestone_ids,
            )

        run_task = None
        try:
            async with get_db_session_local() as db:
                run_task = await run_service.claim_task(
                    db,
                    session_id=session_info.id,
                    task_type=TaskType.AGENT_RUN,
                    data=query_command.model_dump(),
                )
                user_event, _ = await self.create_user_message_event(
                    session_info, query_command, db, run_id=run_task.id
                )
                await db.commit()

            await self.send_event(user_event)
        except Exception as e:
            logger.error(f"Failed to claim task: {e}", exc_info=True)
            await self._send_error_event(
                session_id=session_info.id,
                error_code=ErrorCode.INTERNAL_ERROR,
                message=str(e),
                user_id=session_info.user_id,
            )
            return

        final_status = RunStatus.FAILED
        try:
            agent = await agent_factory.create_cowork_agent(
                session_info=session_info,
                llm_config=llm_config,
                workspace_manager=None,
                agent_type=AgentType(session_info.agent_type)
                if session_info.agent_type
                else AgentType.GENERAL,
                tool_args=query_command.tool_args,
                metadata=query_command.metadata,
                system_prompt=getattr(query_command, "system_prompt", None),
                tool_names=getattr(query_command, "tool_names", None),
                skill_names=getattr(query_command, "skill_names", None),
                desktop_capabilities=getattr(query_command, "desktop_capabilities", None),
                agent_config=getattr(query_command, "agent_config", None),
            )

            instruction_text = query_command.text
            if milestone_context:
                instruction_text = f"{milestone_context}\n\nUser instruction: {query_command.text}"

            event_stream = await agent.arun(
                instruction_text,
                stream=True,
                stream_events=True,
                run_id=str(run_task.id),
                yield_run_output=False,
            )

            final_status = await self.process_agent_event_stream(
                event_stream,
                session_info,
                run_id=run_task.id,
                is_user_key=llm_config.is_user_model(),
                llm_config=llm_config,
            )

            async with get_db_session_local() as db:
                await plan_service.update_milestones_after_run(
                    db,
                    session_id=session_info.id,
                    milestone_ids=query_command.milestone_ids,
                    status=final_status,
                )

        except Exception as e:
            logger.opt(exception=True).error("Error processing cowork query: {}", str(e))
            async with get_db_session_local() as db:
                await run_service.transition_status(
                    db, task_id=run_task.id, to_status=RunStatus.FAILED
                )
                await db.commit()
            if query_command.milestone_ids:
                async with get_db_session_local() as db:
                    await plan_service.reset_milestones_to_pending(
                        db,
                        session_id=session_info.id,
                        milestone_ids=query_command.milestone_ids,
                    )
            raise
    
    async def _ensure_cowork_app_kind(self, session_id) -> None:
        """Persist ``app_kind = cowork`` on the session row if not already set.

        Cowork sessions must be invisible to the standard Project sidebar
        listing. Stamping ``app_kind`` here is the canonical discriminator
        used by ``SessionRepository.get_user_sessions``.
        """
        try:
            async with get_db_session_local() as db:
                session = await self._container.session_service._session_repo.get_by_id(
                    db, session_id
                )
                if session is None:
                    return
                if session.app_kind != AppKind.COWORK:
                    session.app_kind = AppKind.COWORK
                    await db.commit()
        except Exception as exc:
            logger.warning(
                "Failed to stamp cowork app_kind on session %s: %s", session_id, exc
            )
