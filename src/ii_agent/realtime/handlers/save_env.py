"""Handler for saving environment variables and resuming agent loop."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TYPE_CHECKING

from ii_agent.agents.types import AgentType
from ii_agent.realtime.pubsub import AsyncIOPubSub
from ii_agent.realtime.events.app_events import AgentStatusUpdateEvent, ErrorCode
from ii_agent.tasks.schemas import RunTaskResponse
from ii_agent.tasks.types import RunStatus, TaskType
from ii_agent.core.db import get_db_session_local
from ii_agent.core.container import ApplicationContainer
from ii_agent.sessions.schemas import SessionInfo
from ii_agent.agents.sandboxes import Sandbox
from ii_agent.realtime.schemas import QueryToolResultInternal
from ii_agent.projects.service import ProjectNotFoundError
from ii_agent.realtime.chat_session import ChatSessionContext
from ii_agent.realtime.handlers.base import (
    BaseCommandHandler,
    CommandType,
)
from ii_agent.realtime.schemas import SaveEnvContent
from ii_agent.settings.llm.schemas import ModelConfig
from ii_agent.core.config.settings import get_settings
from ii_server.core.workspace import WorkspaceManager
from ii_agent.core.logger import logger

if TYPE_CHECKING:
    from ii_agent.tasks.models import RunTask


class SaveEnvHandler(BaseCommandHandler[SaveEnvContent]):
    """Handle env var submission for ask_user_env tool and resume agent loop."""

    _content_type = SaveEnvContent

    def __init__(self, pubsub: AsyncIOPubSub, container: ApplicationContainer) -> None:
        super().__init__(pubsub=pubsub, container=container)

    def get_command_type(self) -> CommandType:
        return CommandType.SAVE_ENV

    async def handle(self, content: SaveEnvContent, session_info: SessionInfo) -> None:
        tool_call_id = content.tool_call_id
        tool_name = content.tool_name
        secrets_payload = content.secrets
        project_directory = content.project_directory
        tool_args = content.tool_args

        secrets = self._normalize_secrets(secrets_payload)
        if not secrets:
            await self._send_error_event(session_info.id, message="No secrets provided to save")
            return

        from ii_agent.tasks.exceptions import TaskConflictException

        svc = self._container.run_task_service
        async with get_db_session_local() as db:
            running_task = await svc.find_active_by_session(db, session_info.id)
            if running_task:
                logger.info(
                    f"save_env skipped: running task {running_task.id} already active for {session_info.id}"
                )
                return

            try:
                run_task = await svc.claim_task(
                    db,
                    session_id=session_info.id,
                    task_type=TaskType.AGENT_RUN,
                )
            except TaskConflictException:
                logger.warning(f"Duplicate task claim in save_env for session {session_info.id}")
                await self._send_error_event(
                    session_info.id,
                    error_code=ErrorCode.DUPLICATE_TASK,
                )
                return
            await db.commit()

        await self.send_event(
            AgentStatusUpdateEvent(
                session_id=session_info.id,
                message="Agent running",
                status="running",
                content={"status": "running", "run_id": str(run_task.id)},
            )
        )

        try:
            container = self._container
            sandbox = await container.sandbox_service.get_sandbox_by_session(session_info.id)
            # Process the secrets
            task_response = await self._process_secrets(
                session_info=session_info,
                running_task=run_task,
                sandbox=sandbox,
                tool_call_id=tool_call_id,
                tool_name=tool_name,
                secrets=secrets,
                project_directory=project_directory,
                tool_args=tool_args,
            )
            logger.info(
                f"Agent run id: {task_response.id} finished with status: {task_response.status}"
            )
        except Exception as exc:
            logger.error(f"Could not process secrets due to error: {exc}")
            raise

    async def _get_model_config(self, session: SessionInfo) -> ModelConfig:
        container = self._container
        async with get_db_session_local() as db_session:
            session_info = await container.session_service.get_session_by_id(db_session, session.id)
            if not session_info or not session_info.model_setting_id:
                raise ValueError("Session model settings not found")

            return await container.model_setting_service.resolve_config_by_setting_id(
                db_session, setting_id=session_info.model_setting_id
            )

    async def _process_secrets(
        self,
        *,
        session_info: SessionInfo,
        running_task: RunTask,
        sandbox: Sandbox,
        tool_call_id: str,
        tool_name: str,
        secrets: dict[str, str],
        project_directory: str | None,
        tool_args: dict[str, Any] | None,
    ) -> RunTaskResponse:
        """Save secrets, continue the agent loop, and update task status."""
        try:
            llm_config = await self._get_model_config(session_info)

            chat_session = await self._init_chat_session(
                session_info=session_info,
                sandbox=sandbox,
                agent_task=running_task,
                tool_args=tool_args,
                llm_config=llm_config,
            )

            save_success = False
            save_error: str | None = None
            try:
                save_success = await self._container.project_service.add_secrets_and_sync(
                    session_id=session_info.id,
                    user_id=str(session_info.user_id),
                    secrets=secrets,
                    project_path=project_directory,
                )
                if not save_success:
                    save_error = "Failed to save environment variables."
            except ProjectNotFoundError:
                save_error = (
                    "Project not found. Please init a project to save environment variables."
                )
            except Exception as exc:
                save_error = str(exc) or "Failed to save environment variables."
                logger.error(f"save_env failed: {exc}", exc_info=True)

            env_tool_result = QueryToolResultInternal(
                tool_call_id=tool_call_id,
                tool_name=tool_name,
                tool_input={
                    "secrets": list(secrets.keys()),
                    "project_directory": project_directory,
                },
                llm_content=self._format_llm_result(secrets, save_success, save_error),
                user_display_content=(
                    "Environment variables saved."
                    if save_success
                    else "Failed to save environment variables."
                ),
                is_error=not save_success,
            )

            agent_result = await chat_session.acontinue(env_tool_result)

            status = RunStatus.CANCELLED if agent_result.is_interrupted else RunStatus.COMPLETED
        except Exception as exc:
            logger.error(f"Error processing save_env: {exc}", exc_info=True)
            await self._send_error_event(
                session_info.id,
                error_code=ErrorCode.UNEXPECTED_ERROR,
            )
            status = RunStatus.FAILED

        svc = self._container.run_task_service
        async with get_db_session_local() as db:
            updated_task = await svc.transition_status(
                db, task_id=running_task.id, to_status=status
            )
            if not updated_task:
                logger.error(f"Could not find task {running_task.id} to update status")
                raise ValueError(f"Could not find task {running_task.id} to update status={status}")
            await db.commit()

        return updated_task

    async def _init_chat_session(
        self,
        session_info: SessionInfo,
        sandbox: Sandbox,
        agent_task: RunTask,
        tool_args: dict[str, Any] | None,
        llm_config: ModelConfig,
    ):
        container = self._container
        cfg = get_settings()
        workspace_manager = WorkspaceManager(
            workspace_path=Path(cfg.workspace_path).resolve(),
        )
        async with get_db_session_local() as db:
            from ii_agent.agents.factory.agent import agent_factory

            agent_controller = await agent_factory.create_agent(
                agent_task=agent_task,
                llm_config=llm_config,
                sandbox=sandbox,
                workspace_manager=workspace_manager,
                event_stream=self._pubsub,
                agent_type=session_info.agent_type or AgentType.GENERAL,
                tool_args=tool_args or {},
                db_session=db,
                user_id=str(session_info.user_id),
            )

        return ChatSessionContext(
            workspace_manager=workspace_manager,
            file_store=container.storage_service,
            config=cfg,
            llm_config=llm_config,
            session_info=session_info,
            agent_controller=agent_controller,
            sandbox=sandbox,
            event_stream=self._pubsub,
        )

    @staticmethod
    def _normalize_secrets(payload: Any) -> dict[str, str]:
        secrets: dict[str, str] = {}
        if isinstance(payload, dict):
            for key, value in payload.items():
                if isinstance(key, str) and key and value is not None:
                    secrets[key] = str(value)
            return secrets

        if isinstance(payload, list):
            for item in payload:
                if not isinstance(item, dict):
                    continue
                key = item.get("key")
                value = item.get("value")
                if isinstance(key, str) and key and value is not None:
                    secrets[key] = str(value)
        return secrets

    @staticmethod
    def _format_llm_result(secrets: dict[str, str], success: bool, error: str | None) -> str:
        payload = {
            "saved_keys": sorted(secrets.keys()),
            "success": success,
        }
        if success:
            payload["message"] = "Environment variables saved."
        else:
            payload["message"] = "Failed to save environment variables."
            if error:
                payload["error"] = error
        return json.dumps(payload)
