"""Handler for cowork_query command with agent overrides."""

from __future__ import annotations

from ii_agent.agents.sandboxes import upload_media_to_sandbox
from ii_agent.agents.sessions import AgentSessionStore
from ii_agent.agents.types import AgentType
from ii_agent.clients.cowork.factory import cowork_agent_factory
from ii_agent.core.db import get_db_session_local, get_session_factory
from ii_agent.core.logger import logger
from ii_agent.files.media import File as UrlFile, Image
from ii_agent.realtime.events.app_events import ErrorCode
from ii_agent.realtime.handlers.base import CommandType
from ii_agent.realtime.handlers.query import UserQueryHandler
from ii_agent.realtime.schemas import CoworkQueryCommandContent
from ii_agent.sessions.schemas import SessionInfo
from ii_agent.sessions.types import AppKind
from ii_agent.settings.llm.schemas import ModelConfig
from ii_agent.tasks.types import RunStatus, TaskType


class CoworkQueryHandler(UserQueryHandler):
    """Handle ``cowork_query`` commands from the cowork mode."""

    _content_type = CoworkQueryCommandContent

    def get_command_type(self) -> CommandType:
        return CommandType.COWORK_QUERY

    async def handle(
        self,
        content: CoworkQueryCommandContent,
        existing_session: SessionInfo,
    ) -> None:
        await self._ensure_cowork_app_kind(existing_session.id)

        is_valid, session_info, llm_config = await self.validate_and_update_session(
            existing_session, content
        )
        if not is_valid or not session_info or not llm_config:
            return

        await self._handle_cowork_query(content, session_info, llm_config)

    async def _handle_cowork_query(
        self,
        query_command: CoworkQueryCommandContent,
        session_info: SessionInfo,
        llm_config: ModelConfig,
    ) -> None:
        run_service = self._container.run_task_service
        file_service = self._container.file_service

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
        except Exception as exc:
            logger.error(
                "[cowork] Failed to claim task: %s", exc, exc_info=True
            )
            await self._send_error_event(
                session_id=session_info.id,
                error_code=ErrorCode.INTERNAL_ERROR,
                message=str(exc),
                user_id=session_info.user_id,
            )
            return

        try:
            session_store = AgentSessionStore(session_maker=get_session_factory())
            agent = await cowork_agent_factory.create_agent(
                user_id=str(session_info.user_id),
                session_id=str(session_info.id),
                llm_config=llm_config,
                agent_type=AgentType(session_info.agent_type)
                if session_info.agent_type
                else AgentType.COWORK,
                session_store=session_store,
                tool_args=query_command.tool_args,
                metadata=query_command.metadata,
                system_prompt=query_command.system_prompt,
                requested_capabilities=query_command.requested_capabilities,
                skill_creator=self._create_skill_creator(session_info.user_id),
            )

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

            event_stream = await agent.arun(
                query_command.text,
                stream=True,
                stream_events=True,
                run_id=str(run_task.id),
                images=images or None,
                files=files or None,
                yield_run_output=False,
            )

            await self.process_agent_event_stream(
                event_stream,
                session_info,
                run_id=run_task.id,
                is_user_key=llm_config.is_user_model(),
                llm_config=llm_config,
            )
        except Exception as exc:
            logger.opt(exception=True).error(
                "[cowork] Error processing query: %s", exc
            )
            async with get_db_session_local() as db:
                await run_service.transition_status(
                    db, task_id=run_task.id, to_status=RunStatus.FAILED
                )
                await db.commit()
            raise

    async def _ensure_cowork_app_kind(self, session_id) -> None:
        """Stamp ``app_kind = cowork`` on the session if not set."""
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
                "[cowork] Failed to stamp app_kind on session %s: %s",
                session_id,
                exc,
            )
