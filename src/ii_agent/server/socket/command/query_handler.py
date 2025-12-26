import logging
import os
from pathlib import Path
from pdb import run
from typing import Dict, Any, Tuple
import uuid

from exceptiongroup import catch
from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.config.agent_types import AgentType
from ii_agent.core import lock
from ii_agent.core.config.llm_config import LLMConfig
from ii_agent.core.event import EventType, RealtimeEvent
from ii_agent.core.event_stream import EventStream
from ii_agent.core.pubsub import RedisPubSub
from ii_agent.db.agent import AgentRunTask, RunStatus
from ii_agent.db.manager import Events, Sessions, SessionsTable, get_db_session_local

from ii_agent.sandbox.ii_sandbox import IISandbox
from ii_agent.server.credits.service import has_sufficient_credits
from ii_agent.server.llm_settings.service import (
    get_model_settings,
    get_user_llm_config,
    get_system_llm_config,
)
from ii_agent.server.models.messages import (
    InitAgentContent,
    QueryContentInternal,
    QueryCommandContent,
)
from ii_agent.server.models.sessions import SessionInfo
from ii_agent.server.services.agent_run_service import (
    AgentRunService,
    AgentRunTaskResponse,
)
from ii_agent.server.shared import (
    agent_service,
    file_service,
    sandbox_service,
    session_service,
    config,
    storage,
)
from ii_agent.server.socket.chat_session import ChatSessionContext
from ii_agent.server.socket.command.command_handler import (
    CommandHandler,
    UserCommandType,
)
from ii_agent.utils.workspace_manager import WorkspaceManager

logger = logging.getLogger(__name__)


class UserQueryHandler(CommandHandler):
    """Handler for query command that processes user queries and runs agents."""

    def __init__(self, event_stream: EventStream) -> None:
        """Initialize the query handler with required dependencies.

        Args:
            event_stream: Event publisher
        """
        super().__init__(event_stream=event_stream)

    async def _send_agent_initialized_event(
        self, session_id: str, vscode_url: str
    ) -> None:
        """Send agent initialized event to the session."""
        await self._send_event(
            session_id=session_id,
            message="Agent initialized",
            event_type=EventType.AGENT_INITIALIZED,
            vscode_url=vscode_url,
        )

    async def update_session_name_and_validation(
        self, session_info: SessionInfo, query_command: QueryCommandContent
    ) -> tuple[bool, SessionInfo | None]:
        """Validate session exists, user has sufficient credits, and update session name.

        Returns:
            Tuple of (is_valid, session_object)
        """
        async with get_db_session_local() as db:
            session = await Sessions.find_session_by_id(
                db=db, session_id=session_info.id
            )

            if not session:
                logger.error(f"Session not found, {session_info.id}")
                await self._send_error_event(
                    str(session_info.id),
                    message="Session not found!",
                    error_type="unexpected_error",
                )
                return False, None

            # Update session name if needed
            if not session_info.name and query_command.text:
                session_name = query_command.text.strip()[:100]
                session.name = session_name
            if session.agent_type is None:
                session.agent_type = query_command.agent_type

            llm_settings = await self._get_llm_settings(
                session=session_info,
                source=query_command.source,
                model_id=query_command.model_id,
            )

            if not session.llm_setting_id:
                session.llm_setting_id = llm_settings.setting_id

            if llm_settings.is_user_model():
                has_credits = True
            else:
                has_credits = await has_sufficient_credits(
                    db_session=db,
                    user_id=str(session.user_id),
                    amount=1.0,  # Minimum credits required to start a query
                )

            db.add(session)
            await db.flush()
            await db.refresh(session)

            await db.commit()

            session_info = SessionInfo(
                id=str(session.id),
                user_id=session.user_id,
                name=session.name,
                status=session.status,
                sandbox_id=session.sandbox_id,
                agent_type=session.agent_type,
                created_at=session.created_at.isoformat(),
                updated_at=session.updated_at.isoformat(),
                workspace_dir=session.get_workspace_dir(),
                is_public=session.is_public,
                token_usage=None,
            )
            if not has_credits:
                await self._send_error_event(
                    str(session_info.id),
                    message="Insufficient credits to process this request. Please check your credit balance.",
                    error_type="insufficient_credits",
                )
                return False, session_info

        return True, session_info

    async def get_running_task(
        self, session_id: uuid.UUID, db: AsyncSession
    ) -> AgentRunTask | None:
        """Check if there's already a running task for this session.

        Returns:
            True if there's a running task (and error event was sent), False otherwise
        """
        running_task = await AgentRunService.get_running_task(
            session_id=session_id, db=db
        )

        if running_task:
            logger.info(
                f"Skipping new task creation since there's already a running task for session {session_id}, task id: {running_task.id}"
            )

        return running_task

    async def _process_query(
        self,
        query_command: QueryCommandContent,
        session_info: SessionInfo,
        running_task: AgentRunTask,
        sandbox: IISandbox,
    ) -> AgentRunTaskResponse:
        """Process the query by handling file uploads, creating chat session, and running agent.

        Returns:
            RunStatus indicating the result
        """
        try:
            # Handle file uploads
            file_upload_paths, images_data = await self._handle_file_upload(
                query_command, sandbox, session_info
            )

            # Create chat session
            chat_session = await self._init_chat_session(
                query_command, session_info, sandbox, agent_task=running_task
            )

            # Create query content with processed file data
            query_content = QueryContentInternal(
                text=query_command.text,
                resume=query_command.resume,
                file_upload_paths=file_upload_paths,
                images_data=images_data,
            )

            # Run the agent
            agent_responses = await chat_session.arun(query_content=query_content)

            if agent_responses.is_interrupted:
                status = RunStatus.ABORTED
            else:
                status = RunStatus.COMPLETED

        except Exception as e:
            logger.error(f"Error processing query: {str(e)}", exc_info=True)
            await self._send_error_event(
                str(session_info.id),
                message="An unexpected error occurred. Please try again.",
                error_type="unexpected_error",
            )
            status = RunStatus.FAILED

        async with get_db_session_local() as db:
            updated_task = await AgentRunService.update_task_status(
                db=db, task_id=running_task.id, status=status
            )
            if not updated_task:
                logger.error(f"Could not find task {running_task.id} to update status")
                raise ValueError(
                    f"Could not find task {running_task.id} to update status={status}"
                )
            await db.commit()

        return updated_task

    def get_command_type(self) -> UserCommandType:
        return UserCommandType.QUERY

    async def handle(
        self, content: Dict[str, Any], existing_session: SessionInfo
    ) -> None:
        """Handle query processing by creating ChatSessionContext and running the agent."""
        # Parse and validate the content using Pydantic model
        query_command = QueryCommandContent(**content)

        # Validate session exists, user has credits, and update session name
        is_valid, session_info = await self.update_session_name_and_validation(
            existing_session, query_command
        )

        if not is_valid:
            return

        lock_instance = lock.LockFactory.get_lock(
            f"session_{session_info.id}", timeout=60, namespace="session"
        )
        try:
            async with lock_instance as _:
                async with get_db_session_local() as db:
                    running_task: AgentRunTask | None = await self.get_running_task(
                        session_info.id, db
                    )
                    # Check for running task
                    if running_task:
                        logger.info(
                            f"There's already a running task for session {session_info.id}, task id: {running_task.id}"
                        )
                        return

                    event = RealtimeEvent(
                        session_id=session_info.id,
                        type=EventType.USER_MESSAGE,
                        content={
                            "text": query_command.text,
                            "files": query_command.files,  # store file ids is enough
                        },
                    )

                    user_event = await Events.save_event_db_session(
                        db=db, session_id=session_info.id, event=event
                    )

                    await self.send_event(event)
                    # Create new task
                    running_task = await AgentRunTask.create(
                        db=db,
                        session_id=session_info.id,
                        user_message_id=user_event.id,
                    )

                    user_event.run_id = running_task.id

                    await db.commit()

                await self.send_event(
                    RealtimeEvent(
                        type=EventType.PROCESSING,
                        session_id=session_info.id,
                        run_id=running_task.id,
                        content={"message": "Processing your message..."},
                    )
                )

                sandbox = await sandbox_service.get_sandbox_by_session(session_info.id)

            # Process the query
            task_response = await self._process_query(
                query_command, session_info, running_task, sandbox
            )
            logger.info(
                f"Agent run id: {task_response.id} finished with status: {task_response.status}"
            )

        except Exception as e:
            logger.error(f"Could not process query due to error: {e}")
            raise

    async def _init_chat_session(
        self,
        query_command: QueryCommandContent,
        session: SessionInfo,
        sandbox: IISandbox,
        agent_task: AgentRunTask,
    ) -> ChatSessionContext:
        """Process query and create ChatSessionContext with all necessary components."""

        # Create workspace for this session
        workspace_path = Path(config.workspace_path).resolve()

        init_content = InitAgentContent(
            model_id=query_command.model_id,
            tool_args=query_command.tool_args,
            source=query_command.source,  # type : ignore
            thinking_tokens=query_command.thinking_tokens,
            agent_type=session.agent_type,
            metadata=query_command.metadata,
        )

        workspace_manager = WorkspaceManager(
            root=workspace_path,
            container_workspace=config.use_container_workspace,
        )

        llm_config = await self._get_llm_settings(
            session=session, source=init_content.source, model_id=init_content.model_id
        )
        # Create agent controller
        agent_controller = await agent_service.create_agent(
            agent_task=agent_task,
            llm_config=llm_config,
            sandbox=sandbox,
            workspace_manager=workspace_manager,
            event_stream=self.event_stream,
            agent_type=session.agent_type or AgentType.GENERAL,
            tool_args=init_content.tool_args,
            metadata=init_content.metadata,
        )

        vscode_url = await sandbox.expose_port(config.vscode_port, external=True)

        # Create ChatSessionContext with file upload data
        chat_session = ChatSessionContext(
            workspace_manager=workspace_manager,
            file_store=storage,
            config=config,
            llm_config=llm_config,
            session_info=session,
            agent_controller=agent_controller,
            sandbox=sandbox,
            vscode_url=vscode_url,
            event_stream=self.event_stream,
        )

        # Send initialization event
        await self._send_agent_initialized_event(session.id, vscode_url)

        return chat_session

    async def _get_llm_settings(
        self, session: SessionInfo, source: str | None, model_id: str | None
    ) -> LLMConfig:
        """Get LLM settings for the session.

        Args:
            session: Session information
            init_content: Initialization content with model details

        Returns:
            Tuple of (llm_config, is_user_model)
        """
        # Check if this is the first time init_agent is called for this session
        async with get_db_session_local() as db_session:
            current_session = await Sessions.find_session_by_id(
                db=db_session, session_id=session.id
            )
            if not current_session:
                raise ValueError("Session not found!")

            if current_session.llm_setting_id is None:
                # Potentially raise error if model is not provided for first time (resume = False)
                # First time init_agent is called - store the LLM setting ID based on source
                if source == "user":
                    # Get user's LLM config and store the setting ID
                    llm_config = await get_user_llm_config(
                        model_id=model_id,
                        user_id=str(session.user_id),
                        db_session=db_session,
                    )
                else:
                    llm_config = get_system_llm_config(
                        model_id=model_id,
                    )
            else:
                # Try to get as user model first
                try:
                    llm_config = await get_user_llm_config(
                        model_id=current_session.llm_setting_id,
                        user_id=str(session.user_id),
                        db_session=db_session,
                    )
                except ValueError:
                    llm_config = get_system_llm_config(
                        model_id=current_session.llm_setting_id,
                    )

        return llm_config

    # TODO: optimize this
    async def _handle_file_upload(
        self,
        query_command: QueryCommandContent,
        sandbox: IISandbox,
        session_info: SessionInfo,
    ):
        file_upload_paths = []
        images_data = []
        if query_command.files:
            upload_path = config.workspace_upload_path
            await sandbox.create_directory(upload_path, exist_ok=True)

            for file_id in query_command.files:
                file_data = await file_service.get_file_by_id(file_id)
                await file_service.update_file_session_id(file_id, str(session_info.id))

                # if file is image
                if file_data.content_type in [
                    "image/png",
                    "image/jpeg",
                    "image/gif",
                    "image/webp",
                ]:
                    images_data.append(
                        {
                            "content_type": file_data.content_type,
                            "url": file_data.url,
                        }
                    )

                # upload file to sandbox from URL
                file_upload_path = os.path.join(upload_path, file_data.name)
                if not await sandbox.upload_file_from_url(
                    file_data.url, file_upload_path
                ):
                    raise Exception(f"Failed to upload file {file_data.name}")

                file_upload_paths.append(file_upload_path)
        return file_upload_paths, images_data
