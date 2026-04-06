"""Handler for query command that processes user queries and runs agents.

Extracted from ``server.socket.command.query_handler``.
"""

from __future__ import annotations

from ii_agent.agents.factory.agent import agent_factory
from ii_agent.agents.sandboxes import upload_media_to_sandbox
from ii_agent.agents.sessions import AgentSessionStore
from ii_agent.agents.types import AgentType
from ii_agent.core.container import ApplicationContainer
from ii_agent.core.db import get_db_session_local, get_session_factory
from ii_agent.core.logger import logger
from ii_agent.files.media import File as UrlFile, Image
from ii_agent.realtime.events.app_events import ErrorCode
from ii_agent.realtime.handlers.base import BaseCommandHandler, CommandType
from ii_agent.realtime.pubsub import AsyncIOPubSub
from ii_agent.realtime.schemas import QueryCommandContent
from ii_agent.sessions.schemas import SessionInfo
from ii_agent.settings.llm.schemas import ModelConfig
from ii_agent.tasks.types import RunStatus, TaskType


class UserQueryHandler(BaseCommandHandler[QueryCommandContent]):
    """Handler for query command that processes user queries and runs agents."""

    _content_type = QueryCommandContent

    def __init__(self, pubsub: AsyncIOPubSub, container: ApplicationContainer) -> None:
        super().__init__(pubsub=pubsub, container=container)

    def get_command_type(self) -> CommandType:
        return CommandType.QUERY

    async def handle(self, content: QueryCommandContent, existing_session: SessionInfo) -> None:
        """Handle query processing by creating ChatSessionContext and running the agent."""
        query_command = content

        is_valid, session_info, llm_config = await self.validate_and_update_session(
            existing_session, query_command
        )
        if not is_valid or not session_info or not llm_config:
            return

        await self._handle_query(query_command, session_info, llm_config)

    async def _handle_query(
        self, query_command: QueryCommandContent, session_info: SessionInfo, llm_config: ModelConfig
    ) -> None:
        """Handle query processing for v1 API."""
        plan_service = self._container.plan_service
        file_service = self._container.file_service

        milestone_context = None
        if query_command.milestone_ids and query_command.plan_context:
            milestone_context = plan_service.get_milestone_context(
                plan_context=query_command.plan_context,
                milestone_ids=query_command.milestone_ids,
            )

        run_service = self._container.run_task_service
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
            session_store = AgentSessionStore(session_maker=get_session_factory())

            # Merge DB-backed user preferences as base, with request tool_args as override
            from ii_agent.memory.service import MemoryService
            tool_args = query_command.tool_args or {}
            try:
                memory_service: MemoryService = self._container.memory_service
                async with get_db_session_local() as prefs_db:
                    user_prefs = await memory_service.load_user_memory_preferences(
                        prefs_db, session_info.user_id
                    )
                tool_args = {**user_prefs, **tool_args}
            except Exception as e:
                logger.warning(f"Failed to load user memory preferences: {e}")

            agent = await agent_factory.create_agent(
                user_id=str(session_info.user_id),
                session_id=str(session_info.id),
                llm_config=llm_config,
                agent_type=AgentType(session_info.agent_type)
                if session_info.agent_type
                else AgentType.GENERAL,
                session_store=session_store,
                tool_args=tool_args,
                metadata=query_command.metadata,
                skill_creator=self._create_skill_creator(session_info.user_id),
            )

            # Prepare files via FileService
            images: list[Image] = []
            files: list[UrlFile] = []
            if query_command.files:
                async with get_db_session_local() as db:
                    images, files = await file_service.prepare_agent_files(
                        db,
                        file_ids=query_command.files,
                        user_id=session_info.user_id,
                        session_id=session_info.id,
                    )

            # Pre-upload media to sandbox so the agent gets sandbox paths
            if images or files:
                sandbox_service = self._container.sandbox_service
                async with get_db_session_local() as db:
                    sandbox = await sandbox_service.init_sandbox(
                        db,
                        session_id=session_info.id,
                        user_id=session_info.user_id,
                    )
                agent.sandbox = sandbox
                await sandbox.create_directory(sandbox.upload_path, exist_ok=True)
                sandbox_files, sandbox_images = await upload_media_to_sandbox(
                    sandbox=sandbox,
                    files=files or [],
                    images=images or [],
                    upload_path=sandbox.upload_path,
                )
                if sandbox_files:
                    files = sandbox_files
                if sandbox_images:
                    images = sandbox_images

            # Build instruction text with milestone context if available
            instruction_text = query_command.text
            if milestone_context:
                instruction_text = f"{milestone_context}\n\nUser instruction: {query_command.text}"

            event_stream = await agent.arun(
                instruction_text,
                stream=True,
                stream_events=True,
                run_id=str(run_task.id),
                images=images or None,
                files=files or None,
                yield_run_output=False,
            )

            final_status = await self.process_agent_event_stream(
                event_stream,
                session_info,
                run_id=run_task.id,
                is_user_key=llm_config.is_user_model(),
                llm_config=llm_config,
            )

            # Update milestones after successful run
            async with get_db_session_local() as db:
                await plan_service.update_milestones_after_run(
                    db,
                    session_id=session_info.id,
                    milestone_ids=query_command.milestone_ids,
                    status=final_status,
                )

        except Exception as e:
            logger.opt(exception=True).error("Error processing v1 query: {}", str(e))
            # Transition RunTask to FAILED so it doesn't stay stuck in RUNNING
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
