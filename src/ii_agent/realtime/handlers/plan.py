"""Handler for plan mode commands."""

from __future__ import annotations

import uuid

from ii_agent.agents.factory.agent import agent_factory
from ii_agent.agents.sessions import AgentSessionStore
from ii_agent.agents.prompts.plan_mode_prompt import (
    get_plan_mode_prompt,
    get_plan_modification_execute_prompt,
    get_plan_modification_suggestions_prompt,
)
from ii_agent.agents.sandboxes import upload_media_to_sandbox
from ii_agent.agents.tools.plan import MilestoneTool, PlanModificationSuggestionsTool
from ii_agent.core.container import ApplicationContainer
from ii_agent.core.db import get_db_session_local, get_session_factory
from ii_agent.core.logger import logger
from ii_agent.files.media import File as UrlFile, Image
from ii_agent.realtime.events.app_events import (
    AgentProcessingEvent,
    PlanGeneratedEvent,
    PlanModificationOptionsEvent,
    UserMessageEvent,
)
from ii_agent.realtime.handlers.base import (
    BaseCommandHandler,
    CommandType,
)
from ii_agent.realtime.pubsub import AsyncIOPubSub
from ii_agent.realtime.schemas import PlanCommandContent
from ii_agent.sessions.schemas import SessionInfo
from ii_agent.settings.llm.schemas import ModelConfig
from ii_agent.tasks.exceptions import TaskConflictException
from ii_agent.tasks.schemas import RunTaskResponse
from ii_agent.tasks.types import RunStatus, TaskType


class PlanHandler(BaseCommandHandler[PlanCommandContent]):
    """Handler for plan mode commands.

    Uses the same agent infrastructure as query_handler but with:
    - MilestoneTool for structured plan output
    - Plan-specific system prompt
    - Shared conversation history via State
    """

    _content_type = PlanCommandContent

    def __init__(self, pubsub: AsyncIOPubSub, container: ApplicationContainer) -> None:
        super().__init__(pubsub=pubsub, container=container)

    def _run_task_svc(self):
        return self._container.run_task_service

    def get_command_type(self) -> CommandType:
        return CommandType.PLAN

    async def handle(self, content: PlanCommandContent, existing_session: SessionInfo) -> None:
        """Handle plan mode processing."""
        query_command = content

        # Use shared validation from base class
        is_valid, session_info, llm_config = await self.validate_and_update_session(
            existing_session, query_command
        )

        if not is_valid or not session_info or not llm_config:
            return

        await self._handle_plan(query_command, session_info, llm_config)

    async def _handle_plan(
        self,
        query_command: PlanCommandContent,
        session_info: SessionInfo,
        llm_config: ModelConfig,
    ) -> None:
        """Handle plan mode processing."""
        # Claim task
        running_task = await self._claim_task(session_info, query_command)
        if not running_task:
            return

        try:
            # Route to appropriate handler
            if query_command.build_mode == "plan":
                if await self._has_existing_plan(session_info.id):
                    await self._handle_plan_modification(
                        query_command, session_info, llm_config, running_task
                    )
                else:
                    await self._handle_plan_generation(
                        query_command, session_info, llm_config, running_task
                    )
            elif query_command.build_mode == "modify_plan_suggestions":
                await self._handle_plan_modification_suggestions(
                    query_command, session_info, llm_config, running_task
                )
            elif query_command.build_mode == "modify_plan":
                await self._handle_plan_modification(
                    query_command, session_info, llm_config, running_task
                )
            else:
                await self._send_error_event(
                    str(session_info.id),
                    message="Invalid plan mode.",
                    error_type="invalid_mode_error",
                )

        except Exception as e:
            logger.error(f"Error in plan handler: {e}", exc_info=True)
            raise

    async def _has_existing_plan(self, session_id: uuid.UUID) -> bool:
        """Return True if the session has a non-empty stored plan."""
        try:
            container = self._container
            async with get_db_session_local() as db:
                session = await container.session_service.get_session_by_id(db, session_id)
                if not session or not session.session_metadata:
                    return False
                plan = session.session_metadata.get("plan")
                if not isinstance(plan, dict):
                    return False
                milestones = plan.get("milestones")
                return isinstance(milestones, list) and len(milestones) > 0
        except Exception:
            return False

    async def _claim_task(
        self,
        session_info: SessionInfo,
        query_command: PlanCommandContent,
    ) -> RunTaskResponse | None:
        """Create user message event and claim a run task."""
        container = self._container
        svc = container.run_task_service

        async with get_db_session_local() as db:
            existing_task = await svc.find_active_by_session(db, session_info.id)
            if existing_task:
                logger.info(
                    f"Already running task for session {session_info.id}, task: {existing_task.id}"
                )
                return None

            event = UserMessageEvent(
                session_id=session_info.id,
                message="",
                content={
                    "text": query_command.text,
                    "files": query_command.files,
                    "build_mode": query_command.build_mode,
                },
            )
            user_event = await container.event_service.save_event(
                db, session_id=session_info.id, event=event
            )
            await self.send_event(event)

            try:
                running_task = await svc.claim_task(
                    db,
                    session_id=session_info.id,
                    task_type=TaskType.AGENT_RUN,
                )
            except TaskConflictException:
                logger.warning(f"Duplicate task claim in plan for session {session_info.id}")
                await self._send_error_event(
                    session_info.id,
                    message="This operation has already been submitted.",
                    error_type="duplicate_task",
                )
                return None

            user_event.run_id = running_task.id
            await db.commit()

        await self.send_event(
            AgentProcessingEvent(
                session_id=session_info.id,
                message="Processing...",
                content={"message": "Processing your message..."},
            )
        )

        return running_task

    async def _handle_plan_generation(
        self,
        query_command: PlanCommandContent,
        session_info: SessionInfo,
        llm_config: ModelConfig,
        running_task: RunTaskResponse,
    ) -> None:
        """Handle plan generation using IIAgent with MilestoneTool."""
        logger.info(f"Handling plan mode for session {session_info.id}")

        try:
            await self.send_event(
                AgentProcessingEvent(
                    session_id=session_info.id,
                    message="Processing...",
                    content={"message": "Generating project plan..."},
                )
            )

            # Create MilestoneTool with event_stream for direct save/emit
            milestone_tool = MilestoneTool(
                session_id=session_info.id,
                event_stream=self._pubsub,
                session_info=session_info,
            )

            # Create plan agent via factory
            session_store = AgentSessionStore(session_maker=get_session_factory())
            agent = await agent_factory.create_agent(
                user_id=str(session_info.user_id),
                session_id=str(session_info.id),
                llm_config=llm_config,
                session_store=session_store,
                tool_args=query_command.tool_args,
                metadata=query_command.metadata,
                system_prompt=get_plan_mode_prompt(),
                skill_creator=self._create_skill_creator(session_info.user_id),
            )

            # Add plan-specific tools
            agent.add_tool(milestone_tool)

            # Process files
            images, files = await self._handle_file_upload(query_command, session_info)

            # Pre-upload media to sandbox so the agent gets sandbox paths
            if images or files:
                container = self._container
                sandbox_svc = container.sandbox_service
                async with get_db_session_local() as db:
                    sandbox = await sandbox_svc.init_sandbox(
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

            # Run the agent
            event_stream = await agent.arun(
                query_command.text,
                stream=True,
                stream_events=True,
                run_id=str(running_task.id),
                images=images or None,
                files=files or None,
            )

            await self.process_agent_event_stream(
                event_stream,
                session_info,
                run_id=running_task.id,
                is_user_key=llm_config.is_user_model(),
                llm_config=llm_config,
            )

        except Exception as e:
            logger.error(f"Error in plan generation: {e}", exc_info=True)
            async with get_db_session_local() as db:
                await self._run_task_svc().transition_status(
                    db, task_id=running_task.id, to_status=RunStatus.FAILED
                )
                await db.commit()
            await self._send_error_event(
                str(session_info.id),
                message=str(e),
                error_type="plan_error",
            )

    async def _handle_plan_modification_suggestions(
        self,
        query_command: PlanCommandContent,
        session_info: SessionInfo,
        llm_config: ModelConfig,
        running_task: RunTaskResponse,
    ) -> None:
        """Generate plan modification suggestions using IIAgent."""
        logger.info(f"Generating plan modification suggestions for session {session_info.id}")

        try:
            container = self._container
            session_svc = container.session_service

            # Get current plan from session
            async with get_db_session_local() as db:
                session = await session_svc.get_session_by_id(db, session_info.id)
                if not session or not session.session_metadata:
                    await self._run_task_svc().transition_status(
                        db, task_id=running_task.id, to_status=RunStatus.FAILED
                    )
                    await db.commit()
                    await self._send_error_event(
                        str(session_info.id),
                        message="No plan found to modify.",
                        error_type="no_plan_error",
                    )
                    return

                plan_data = session.session_metadata.get("plan", {})
                if not plan_data:
                    await self._run_task_svc().transition_status(
                        db, task_id=running_task.id, to_status=RunStatus.FAILED
                    )
                    await db.commit()
                    await self._send_error_event(
                        str(session_info.id),
                        message="No plan found to modify.",
                        error_type="no_plan_error",
                    )
                    return

            await self.send_event(
                AgentProcessingEvent(
                    session_id=session_info.id,
                    message="Processing...",
                    content={"message": "Generating modification suggestions..."},
                )
            )

            # Get the suggestions prompt
            suggestions_prompt = get_plan_modification_suggestions_prompt(
                plan_summary=plan_data.get("summary", ""),
                milestones=plan_data.get("milestones", []),
            )

            # Create PlanModificationSuggestionsTool
            suggestions_tool = PlanModificationSuggestionsTool(
                session_id=session_info.id,
                run_id=running_task.id,
                event_stream=self._pubsub,
                session_info=session_info,
            )

            # Create plan suggestions agent via factory
            session_store = AgentSessionStore(session_maker=get_session_factory())
            agent = await agent_factory.create_agent(
                user_id=str(session_info.user_id),
                session_id=str(session_info.id),
                llm_config=llm_config,
                session_store=session_store,
                tool_args=query_command.tool_args,
                metadata=query_command.metadata,
                system_prompt=suggestions_prompt,
                skill_creator=self._create_skill_creator(session_info.user_id),
            )
            agent.add_tool(suggestions_tool)

            # Run agent to generate suggestions
            event_stream = await agent.arun(
                "Generate modification suggestions for the current plan.",
                stream=True,
                stream_events=True,
                run_id=str(running_task.id),
            )

            await self.process_agent_event_stream(
                event_stream,
                session_info,
                run_id=running_task.id,
                is_user_key=llm_config.is_user_model(),
                llm_config=llm_config,
            )

        except Exception as e:
            logger.error(f"Error generating modification suggestions: {e}", exc_info=True)
            async with get_db_session_local() as db:
                await self._run_task_svc().transition_status(
                    db, task_id=running_task.id, to_status=RunStatus.FAILED
                )
                await db.commit()
            await self._send_error_event(
                str(session_info.id),
                message=str(e),
                error_type="plan_error",
            )

    async def _handle_plan_modification(
        self,
        query_command: PlanCommandContent,
        session_info: SessionInfo,
        llm_config: ModelConfig,
        running_task: RunTaskResponse,
    ) -> None:
        """Handle plan modification using IIAgent."""
        logger.info(f"Handling modify plan for session {session_info.id}")

        # If user hasn't provided modification text, show suggestions
        if not query_command.text or query_command.text.strip() == "":
            await self._handle_plan_modification_suggestions(
                query_command, session_info, llm_config, running_task
            )
            return

        try:
            container = self._container
            session_svc = container.session_service

            # Get current plan from session
            async with get_db_session_local() as db:
                session = await session_svc.get_session_by_id(db, session_info.id)
                if not session or not session.session_metadata:
                    await self._run_task_svc().transition_status(
                        db, task_id=running_task.id, to_status=RunStatus.FAILED
                    )
                    await db.commit()
                    await self._send_error_event(
                        str(session_info.id),
                        message="No plan found to modify.",
                        error_type="no_plan_error",
                    )
                    return

                plan_data = session.session_metadata.get("plan", {})
                if not plan_data:
                    await self._run_task_svc().transition_status(
                        db, task_id=running_task.id, to_status=RunStatus.FAILED
                    )
                    await db.commit()
                    await self._send_error_event(
                        str(session_info.id),
                        message="No plan found to modify.",
                        error_type="no_plan_error",
                    )
                    return

            await self.send_event(
                AgentProcessingEvent(
                    session_id=session_info.id,
                    message="Processing...",
                    content={"message": "Modifying plan..."},
                )
            )

            # Create modification prompt with current plan context
            modification_prompt = get_plan_modification_execute_prompt(
                plan_summary=plan_data.get("summary", ""),
                milestones=plan_data.get("milestones", []),
                modification_request=query_command.text,
            )

            # Create MilestoneTool with event_stream for direct save/emit
            milestone_tool = MilestoneTool(
                session_id=session_info.id,
                event_stream=self._pubsub,
                session_info=session_info,
            )

            # Create plan agent with modification prompt via factory
            session_store = AgentSessionStore(session_maker=get_session_factory())
            agent = await agent_factory.create_agent(
                user_id=str(session_info.user_id),
                session_id=str(session_info.id),
                llm_config=llm_config,
                session_store=session_store,
                tool_args=query_command.tool_args,
                metadata=query_command.metadata,
                system_prompt=modification_prompt,
                skill_creator=self._create_skill_creator(session_info.user_id),
            )
            agent.add_tool(milestone_tool)

            # Process files
            images, files = await self._handle_file_upload(query_command, session_info)

            # Pre-upload media to sandbox so the agent gets sandbox paths
            if images or files:
                sandbox_svc = container.sandbox_service
                async with get_db_session_local() as db:
                    sandbox = await sandbox_svc.init_sandbox(
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

            # Run agent with the modification request
            event_stream = await agent.arun(
                query_command.text,
                stream=True,
                stream_events=True,
                run_id=str(running_task.id),
                images=images or None,
                files=files or None,
            )

            await self.process_agent_event_stream(
                event_stream,
                session_info,
                run_id=running_task.id,
                is_user_key=llm_config.is_user_model(),
                llm_config=llm_config,
            )

        except Exception as e:
            logger.error(f"Error in plan modification: {e}", exc_info=True)
            async with get_db_session_local() as db:
                await self._run_task_svc().transition_status(
                    db, task_id=running_task.id, to_status=RunStatus.FAILED
                )
                await db.commit()
            await self._send_error_event(
                str(session_info.id),
                message=str(e),
                error_type="modify_plan_error",
            )

    async def _save_and_emit_plan(
        self,
        session_info: SessionInfo,
        plan_data: dict,
    ) -> None:
        """Save plan to session metadata and emit plan generated event."""
        container = self._container
        session_svc = container.session_service

        async with get_db_session_local() as db:
            session = await session_svc.get_session_by_id(db, session_info.id)
            if session:
                updated_metadata = {
                    **(session.session_metadata or {}),
                    "plan": plan_data,
                }
                await session_svc.update_session_fields(
                    db, session_info.id, session_metadata=updated_metadata
                )

                plan_event = PlanGeneratedEvent(
                    session_id=session_info.id,
                    content={
                        "summary": plan_data.get("summary", ""),
                        "milestones": plan_data.get("milestones", []),
                    },
                )

                await container.event_service.save_event(
                    db, session_id=session_info.id, event=plan_event
                )
                await db.commit()

        await self.send_event(
            PlanGeneratedEvent(
                session_id=session_info.id,
                content={
                    "summary": plan_data.get("summary", ""),
                    "milestones": plan_data.get("milestones", []),
                },
            )
        )

        logger.info(f"Plan submitted successfully for session {session_info.id}")

    async def _emit_plan_modification_suggestions(
        self,
        session_info: SessionInfo,
        run_id: uuid.UUID,
        message: str,
        suggestions: list,
    ) -> None:
        """Emit plan modification suggestions event."""
        await self.send_event(
            PlanModificationOptionsEvent(
                session_id=session_info.id,
                content={
                    "message": message,
                    "suggestions": suggestions,
                },
            )
        )
        logger.info(f"Plan modification suggestions emitted for session {session_info.id}")

    async def _handle_file_upload(
        self,
        query_command: PlanCommandContent,
        session_info: SessionInfo,
    ) -> tuple[list[Image], list[UrlFile]]:
        """Handle file uploads for agent with signed URLs."""
        if not query_command.files:
            return [], []

        file_svc = self._container.file_service

        async with get_db_session_local() as db:
            images, files = await file_svc.prepare_agent_files(
                db,
                file_ids=query_command.files,
                user_id=session_info.user_id,
                session_id=session_info.id,
            )

        return images, files
