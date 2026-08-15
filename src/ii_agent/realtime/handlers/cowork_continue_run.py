"""Handler for cowork_continue_run command."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from ii_agent.agents.sessions import AgentSessionStore
from ii_agent.agents.types import AgentType
from ii_agent.clients.cowork.factory import cowork_agent_factory
from ii_agent.core.db import get_db_session_local, get_session_factory
from ii_agent.core.logger import logger
from ii_agent.realtime.events.app_events import (
    AgentContinueEvent,
    AgentProcessingEvent,
    ErrorCode,
)
from ii_agent.realtime.handlers.base import CommandType
from ii_agent.realtime.handlers.continue_run import ContinueRunHandler
from ii_agent.realtime.schemas import CoworkContinueRunContent
from ii_agent.sessions.schemas import SessionInfo


class CoworkContinueRunHandler(ContinueRunHandler):
    """Handle ``cowork_continue_run`` commands."""

    _content_type = CoworkContinueRunContent

    def get_command_type(self) -> CommandType:
        return CommandType.COWORK_CONTINUE_RUN

    async def handle(
        self,
        content: CoworkContinueRunContent,
        session_info: SessionInfo,
    ) -> None:
        if session_info.api_version != "v1":
            await self._send_error_event(
                session_info.id,
                error_code=ErrorCode.UNSUPPORTED_API_VERSION,
                message="continue_run is only supported for v1 API version",
            )
            return

        run_id = content.run_id
        confirmed = content.confirmed
        user_input = content.user_input
        external_tool_results = content.external_tool_results or []

        await self.send_event(
            AgentContinueEvent(
                session_id=UUID(str(session_info.id)),
                content={
                    "message": "Agent continuing...",
                    "confirmed": confirmed,
                    "run_id": run_id,
                },
            )
        )

        try:
            session_store = AgentSessionStore(session_maker=get_session_factory())
            run_response = await session_store.get_by_run_id(
                run_id=run_id, session_id=str(session_info.id)
            )
            if not run_response:
                await self._send_error_event(
                    session_info.id,
                    error_code=ErrorCode.RUN_NOT_FOUND,
                    message=f"Run {run_id} not found",
                )
                return

            run_task_data = await self._load_run_task_data(run_id)

            for tool in run_response.tools_requiring_confirmation:
                tool.confirmed = bool(confirmed)
                logger.info(
                    "[cowork] continue confirmation run=%s tool_call_id=%s confirmed=%s",
                    run_id,
                    tool.tool_call_id,
                    confirmed,
                )

            for tool in run_response.tools_requiring_user_input:
                if confirmed and user_input:
                    self._apply_user_input_to_tool(tool, user_input, run_id)
                    tool.answered = True
                else:
                    tool.answered = False

            self._apply_external_tool_results(
                run_response.tools, external_tool_results, run_id
            )

            llm_config = None
            if session_info.model_setting_id:
                try:
                    async with get_db_session_local() as db:
                        llm_config = (
                            await self._container.model_setting_service.resolve_config_by_setting_id(
                                db, setting_id=session_info.model_setting_id
                            )
                        )
                except Exception as exc:
                    logger.warning(
                        "[cowork] continue_run model resolution failed: %s",
                        exc,
                    )

            agent = await cowork_agent_factory.create_agent(
                user_id=str(session_info.user_id),
                session_id=str(session_info.id),
                llm_config=llm_config,
                agent_type=AgentType(session_info.agent_type)
                if session_info.agent_type
                else AgentType.COWORK,
                session_store=session_store,
                metadata=run_task_data.get("metadata"),
                system_prompt=run_task_data.get("system_prompt"),
                requested_capabilities=run_task_data.get("requested_capabilities"),
                skill_creator=self._create_skill_creator(session_info.user_id),
            )

            await self.send_event(
                AgentProcessingEvent(
                    session_id=UUID(str(session_info.id)),
                    message="Resuming agent execution...",
                    content={
                        "message": "Resuming agent execution...",
                        "run_id": run_id,
                    },
                )
            )

            event_stream = agent.acontinue_run(
                run_id=run_response.run_id,
                updated_tools=run_response.tools,
                stream=True,
                stream_events=True,
            )

            await self.process_agent_event_stream(
                event_stream,
                session_info,
                run_id=UUID(run_response.run_id),
                is_user_key=llm_config.is_user_model() if llm_config else False,
                llm_config=llm_config,
            )

        except ValueError as exc:
            logger.error("[cowork] continue_run ValueError: %s", exc)
            await self._send_error_event(
                session_info.id,
                error_code=ErrorCode.VALIDATION_ERROR,
                message=str(exc),
            )
        except Exception as exc:
            logger.error(
                "[cowork] continue_run failed: %s", exc, exc_info=True
            )
            await self._send_error_event(
                session_info.id,
                error_code=ErrorCode.EXECUTION_ERROR,
                message=f"Failed to continue run: {exc}",
            )

    async def _load_run_task_data(self, run_id: str) -> dict[str, Any]:
        """Reload the original ``RunTask.data`` so overrides survive resume."""
        try:
            run_task_id = UUID(str(run_id))
        except ValueError:
            return {}

        async with get_db_session_local() as db:
            run_task = await self._container.run_task_service.get_task_by_id(
                db, task_id=run_task_id
            )

        if not run_task or not isinstance(run_task.data, dict):
            return {}
        return run_task.data

    @staticmethod
    def _apply_external_tool_results(
        tools: list[Any],
        external_tool_results: list[dict[str, Any]],
        run_id: str,
    ) -> None:
        """Inject extension-side tool execution results back into paused tools."""
        if not external_tool_results:
            return

        by_id = {
            str(item.get("tool_call_id")): item
            for item in external_tool_results
            if isinstance(item, dict) and item.get("tool_call_id")
        }

        for tool in tools:
            tool_call_id = getattr(tool, "tool_call_id", None)
            if not tool_call_id:
                continue
            external = by_id.get(str(tool_call_id))
            if not external:
                continue

            llm_content = external.get("llm_content")
            user_display_content = external.get("user_display_content")
            tool.result = (
                llm_content if llm_content is not None else user_display_content
            )
            tool.tool_call_error = bool(external.get("is_error"))

            tool_input = external.get("tool_input")
            if isinstance(tool_input, dict):
                tool.tool_args = tool_input

            tool_name = external.get("tool_name")
            if isinstance(tool_name, str) and tool_name.strip():
                tool.tool_name = tool_name

            logger.info(
                "[cowork] applied external tool result run=%s tool_call_id=%s error=%s",
                run_id,
                tool_call_id,
                tool.tool_call_error,
            )
