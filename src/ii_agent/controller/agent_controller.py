import asyncio
from dataclasses import dataclass
import time
import base64

import httpx

from typing import Any, Optional, cast
from uuid import UUID

from ii_agent.controller.agent import Agent
from ii_agent.controller.tool_manager import AgentToolManager, ToolCallParameters
from ii_agent.controller.state import State
from ii_agent.db.manager import get_db_session_local
from ii_agent.core.config.ii_agent_config import IIAgentConfig
from ii_agent.core.event import AgentStatus, EventType, RealtimeEvent
from ii_agent.core.event_stream import EventStream
from ii_agent.core.logger import logger
from ii_agent.db.agent import RunStatus
from ii_agent.llm.base import (
    TextResult,
    AssistantContentBlock,
    ThinkingBlock,
    TextPrompt,
)
from ii_agent.llm.context_manager.base import ContextManager
from ii_agent.server.services.agent_run_service import AgentRunService
from ii_agent.utils.constants import COMPLETE_MESSAGE
from ii_tool.tools.base import (
    ImageContent,
    TextContent,
    ToolResult,
)

TOOL_RESULT_INTERRUPT_MESSAGE = "[Request interrupted by user for tool use]"
AGENT_INTERRUPT_MESSAGE = "Agent interrupted by user."
TOOL_CALL_INTERRUPT_FAKE_MODEL_RSP = "[Request interrupted by user for tool use]"
AGENT_INTERRUPT_FAKE_MODEL_RSP = (
    "Agent interrupted by user. You can resume by providing a new instruction."
)


@dataclass
class AgentController:
    """Agent controller for managing agent execution and tool interactions."""

    # Core components
    agent: Agent
    tool_manager: AgentToolManager
    history: State
    event_stream: EventStream
    context_manager: ContextManager
    session_id: UUID
    run_id: UUID
    config: Optional[IIAgentConfig] = None

    _interruption_lock: asyncio.Lock = asyncio.Lock()
    # Configuration
    max_turns: int = 500
    interactive_mode: bool = True
    is_sub_agent: bool = False

    # Tool confirmation tracking
    _pending_confirmations: Optional[dict[str, dict]] = None
    _confirmation_responses: Optional[dict[str, dict]] = None

    def __post_init__(self):
        """Initialize runtime state after dataclass initialization."""
        if self._pending_confirmations is None:
            self._pending_confirmations = {}
        if self._confirmation_responses is None:
            self._confirmation_responses = {}

    async def is_interrupted(self) -> bool:
        """Safely check if the agent is interrupted."""
        async with self._interruption_lock as _:  # type: ignore
            async with get_db_session_local() as db, db.begin():  # type: ignore
                task_response = await AgentRunService.get_task_by_id(
                    db=db, task_id=self.run_id
                )

        if not (task_response):
            raise ValueError("Agent run task not found")

        return task_response.status == RunStatus.ABORTED

    @property
    def state(self) -> State:
        """Return the current conversation state/history."""
        return self.history

    async def run_impl(
        self,
        tool_input: dict[str, Any],
    ) -> ToolResult:
        instruction = tool_input.get("instruction")
        files = tool_input.get("files")
        images_data = tool_input.get("images_data")
        # Add instruction to dialog before getting model response
        image_blocks = []
        if files:
            # Add file paths to user message
            instruction = f"""{instruction}\n\nAttached files:\n"""
            for file in files:
                instruction += f" - {file}\n"
                logger.debug(f"Attached file: {file}")

        # Then process images for image data
        if images_data:
            async with httpx.AsyncClient(timeout=30.0) as client:
                for image_data in images_data:
                    response = await client.get(image_data["url"])
                    response.raise_for_status()
                    base64_image = base64.b64encode(response.content).decode("utf-8")
                    image_blocks.append(
                        {
                            "source": {
                                "type": "base64",
                                "media_type": image_data["content_type"],
                                "data": base64_image,
                            }
                        }
                    )

        self.history.add_user_prompt(instruction or "", image_blocks)

        remaining_turns = self.max_turns
        while remaining_turns > 0:
            await self.truncate_history()
            remaining_turns -= 1

            if await self.is_interrupted():
                await self.add_fake_assistant_turn(AGENT_INTERRUPT_FAKE_MODEL_RSP)
                return ToolResult(
                    llm_content=AGENT_INTERRUPT_MESSAGE,
                    user_display_content=AGENT_INTERRUPT_MESSAGE,
                    is_interrupted=True
                )

            # Only show token count in debug mode, not in interactive CLI
            if not self.interactive_mode:
                logger.info(f"(Current token count: {self.count_tokens()})\n")

            agent_response = await self.agent.astep(self.history)

            # Extract content and metrics from AgentResponse
            model_response = agent_response.content
            metrics = agent_response.metrics

            # Emit metrics event if we have metrics data
            if agent_response.has_metrics and metrics:
                await self.event_stream.publish(
                    RealtimeEvent(
                        type=EventType.METRICS_UPDATE,
                        session_id=self.session_id,
                        run_id=self.run_id,
                        content=metrics.model_dump(),
                    )
                )

            if len(model_response) == 0:
                model_response = [TextResult(text=COMPLETE_MESSAGE)]

            # Add the raw response to the canonical history
            self.history.add_assistant_turn(
                cast(list[AssistantContentBlock], model_response)
            )

            # Process all TextResult blocks first
            text_results = [
                item
                for item in model_response
                if isinstance(item, (TextResult, ThinkingBlock))
            ]
            for text_result in text_results:
                # Add thinking block to history if it's a ThinkingBlock
                if isinstance(text_result, ThinkingBlock):
                    await self.event_stream.publish(
                        RealtimeEvent(
                            type=EventType.AGENT_THINKING,
                            session_id=self.session_id,
                            run_id=self.run_id,
                            content={"text": text_result.thinking},
                        )
                    )
                else:
                    # Emit event for each TextResult to be displayed in console
                    await self.event_stream.publish(
                        RealtimeEvent(
                            type=EventType.AGENT_RESPONSE,
                            session_id=self.session_id,
                            run_id=self.run_id,
                            content={"text": text_result.text},
                        )
                    )

            # Handle tool calls
            pending_tool_calls = self.history.get_pending_tool_calls()

            if len(pending_tool_calls) == 0:
                # Check if any text results indicate a retry is needed
                text_prompts = [
                    item for item in model_response if isinstance(item, TextPrompt)
                ]
                if any(
                    getattr(result, "should_retry", False) for result in text_prompts
                ):
                    logger.debug("[retry needed due to should_retry flag]")
                    self.history.message_lists = self.history.message_lists[
                        :-1
                    ]  # remove the last turn
                    continue  # Continue the loop instead of completing

                # No tools were called, so assume the task is complete
                logger.debug("[no tools were called]")

                if not self.is_sub_agent:
                    await self.event_stream.publish(
                        RealtimeEvent(
                            type=EventType.COMPLETE,
                            session_id=self.session_id,
                            run_id=self.run_id,
                            content={"text": "Task completed"},
                        )
                    )
                    await self.event_stream.publish(
                        RealtimeEvent(
                            type=EventType.STATUS_UPDATE,
                            session_id=self.session_id,
                            run_id=self.run_id,
                            content={"status": AgentStatus.READY},
                        )
                    )

                return ToolResult(
                    llm_content=self.history.get_last_assistant_text_response()
                    or "Task completed",
                    user_display_content="Task completed",
                )

            # Check for interruption before tool execution
            if await self.is_interrupted():
                # Handle interruption during tool execution
                for tool_call in pending_tool_calls:
                    await self.add_tool_call_result(
                        tool_call,
                        ToolResult(
                            llm_content=TOOL_RESULT_INTERRUPT_MESSAGE,
                            user_display_content=TOOL_RESULT_INTERRUPT_MESSAGE,
                            is_interrupted=True
                        ),
                    )
                await self.add_fake_assistant_turn(TOOL_CALL_INTERRUPT_FAKE_MODEL_RSP)
                return ToolResult(
                    llm_content=TOOL_RESULT_INTERRUPT_MESSAGE,
                    user_display_content=TOOL_RESULT_INTERRUPT_MESSAGE,
                    is_interrupted=True
                )

            # Execute all tool calls using batch approach
            logger.debug(f"Executing {len(pending_tool_calls)} tool(s)")

            # Handle tool confirmation and execution
            approved_tool_calls = []
            denied_tool_calls = []
            alternative_instructions = []

            for tool_call in pending_tool_calls:
                try:
                    tool = self.tool_manager.get_tool(tool_call.tool_name)
                except ValueError as e:
                    logger.warning(f"Tool lookup failed: {str(e)}")
                    continue

                await self.event_stream.publish(
                    RealtimeEvent(
                        type=EventType.TOOL_CALL,
                        session_id=self.session_id,
                        run_id=self.run_id,
                        content={
                            "tool_call_id": tool_call.tool_call_id,
                            "tool_name": tool_call.tool_name,
                            "tool_input": tool_call.tool_input,
                            "tool_display_name": tool.display_name,
                        },
                    )
                )
                approved_tool_calls.append(tool_call)

            # Handle denied tools
            if denied_tool_calls:
                denial_message = f"Tool execution denied for: {', '.join([tc.tool_name for tc in denied_tool_calls])}"
                if alternative_instructions:
                    denial_message += f"\nAlternative instructions: {'; '.join(alternative_instructions)}"

                # Add denial results to history
                for tool_call in denied_tool_calls:
                    await self.add_tool_call_result(
                        tool_call,
                        ToolResult(
                            llm_content=denial_message,
                            user_display_content=denial_message,
                        ),
                    )

            # Execute approved tools in batch
            if approved_tool_calls:
                tool_results = await self.tool_manager.run_tools_batch(
                    approved_tool_calls
                )

                for tool_call, tool_result in zip(approved_tool_calls, tool_results):
                    await self.add_tool_call_result(tool_call, tool_result)

                    if tool_call.tool_name in {"message", "message_user"}:
                        # If message user tool is result, complete the task
                        tool_input_type = None
                        if isinstance(tool_call.tool_input, dict):
                            tool_input_type = tool_call.tool_input.get("type")

                        if (
                            isinstance(tool_input_type, str)
                            and (tool_input_type.lower() == "result" or tool_input_type.lower() == "ask")
                        ):
                            if not self.is_sub_agent:
                                await self.event_stream.publish(
                                    RealtimeEvent(
                                        type=EventType.COMPLETE,
                                        session_id=self.session_id,
                                        run_id=self.run_id,
                                        content={"text": "Task completed"},
                                    )
                                )
                                await self.event_stream.publish(
                                    RealtimeEvent(
                                        type=EventType.STATUS_UPDATE,
                                        session_id=self.session_id,
                                        run_id=self.run_id,
                                        content={"status": AgentStatus.READY},
                                    )
                                )

                            return ToolResult(
                                llm_content="Task completed",
                                user_display_content="Task completed",
                            )

            # If all tools were denied and we have alternative instructions, add them to history
            if not approved_tool_calls and alternative_instructions:
                alt_instruction_text = (
                    "User provided alternative instructions: "
                    + "; ".join(alternative_instructions)
                )
                self.history.add_user_prompt(alt_instruction_text)

        agent_answer = "Agent did not complete after max turns"
        await self.event_stream.publish(
            RealtimeEvent(
                type=EventType.COMPLETE,
                session_id=self.session_id,
                run_id=self.run_id,
                content={"text": agent_answer},
            )
        )
        return ToolResult(llm_content=agent_answer, user_display_content=agent_answer)

    async def run_agent_async(
        self,
        instruction: str,
        files: list[str] | None = None,
        resume: bool = False,
        images_data: list[dict[str, str]] | None = None,
        orientation_instruction: str | None = None,
    ) -> ToolResult:
        """Start a new agent run asynchronously.

        Args:
            instruction: The instruction to the agent.
            files: Optional list of files to attach
            resume: Whether to resume the agent from the previous state,
                continuing the dialog.
            orientation_instruction: Optional orientation instruction

        Returns:
            The result from the agent execution.
        """
        if not resume:
            self.history.clear()

        tool_input = {
            "instruction": instruction,
            "files": files,
            "images_data": images_data,
        }
        if orientation_instruction:
            tool_input["orientation_instruction"] = orientation_instruction
        return await self.run_impl(tool_input)

    def run_agent(
        self,
        instruction: str,
        files: list[str] | None = None,
        resume: bool = False,
        images_data: list[dict[str, str]] | None = None,
        orientation_instruction: str | None = None,
    ) -> ToolResult:
        """Start a new agent run synchronously.

        Args:
            instruction: The instruction to the agent.
            files: Optional list of files to attach
            resume: Whether to resume the agent from the previous state,
                continuing the dialog.
            orientation_instruction: Optional orientation instruction

        Returns:
            The result from the agent execution.
        """
        return asyncio.run(
            self.run_agent_async(
                instruction, files, resume, images_data, orientation_instruction
            )
        )

    async def clear(self):
        """Clear the dialog and reset interruption state.
        Note: This does NOT clear the file manager, preserving file context.
        """
        self.history.clear()

    async def cancel(self):
        """Cancel the agent execution (local interruption).

        Note: For distributed environments, use cancel_async() instead to publish
        interruption via Redis pub/sub.
        """
        from ii_agent.sub_agent.base import BaseAgentTool

        for tool in self.tool_manager.get_tools():
            if isinstance(tool, BaseAgentTool):
                tool.cancel()
        logger.debug("Agent cancellation requested (local)")

    async def add_tool_call_result(
        self, tool_call: ToolCallParameters, tool_result: ToolResult
    ):
        """Add a tool call result to the history and send it to the message queue."""
        llm_content = tool_result.llm_content
        user_display_content = tool_result.user_display_content
        is_error = tool_result.is_error
        if not user_display_content:
            if isinstance(llm_content, list):
                user_display_content = [item.model_dump() for item in llm_content]
            elif isinstance(llm_content, str):
                user_display_content = llm_content
            else:
                raise ValueError(f"Unknown content type: {type(llm_content)}")

        if isinstance(llm_content, str):
            self.history.add_tool_call_result(tool_call, llm_content)
        # NOTE: the current tool output is maximum 1 text block and 1 image block
        # TODO: handle this better, may be move the logic to each LLM client
        elif isinstance(llm_content, list):
            if len(llm_content) == 1 and isinstance(llm_content[0], TextContent):
                llm_content_text = llm_content[0].text
                self.history.add_tool_call_result(tool_call, llm_content_text)
            else:
                llm_content_fmt: list[dict[str, Any]] = []
                for content in llm_content:
                    if isinstance(content, TextContent):
                        llm_content_fmt.append(
                            {
                                "type": "text",
                                "text": content.text,
                            }
                        )
                    elif isinstance(content, ImageContent):
                        llm_content_fmt.append(
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": str(content.mime_type),
                                    "data": str(content.data),
                                },
                            }
                        )
                    else:
                        raise ValueError(f"Unknown content type: {type(content)}")

                self.history.add_tool_call_result(tool_call, llm_content_fmt)
        else:
            raise ValueError(f"Unknown content type: {type(llm_content)}")

        await self.event_stream.publish(
            RealtimeEvent(
                type=EventType.TOOL_RESULT,
                session_id=self.session_id,
                run_id=self.run_id,
                content={
                    "tool_call_id": tool_call.tool_call_id,
                    "tool_name": tool_call.tool_name,
                    "tool_input": tool_call.tool_input,
                    "result": user_display_content,
                    "is_error": is_error,
                },
            )
        )

    async def add_fake_assistant_turn(self, text: str):
        """Add a fake assistant turn to the history and send it to the message queue."""
        self.history.add_assistant_turn(
            cast(list[AssistantContentBlock], [TextResult(text=text)])
        )
        if await self.is_interrupted():
            rsp_type = EventType.AGENT_RESPONSE_INTERRUPTED
        else:
            rsp_type = EventType.AGENT_RESPONSE

        await self.event_stream.publish(
            RealtimeEvent(
                type=rsp_type,
                session_id=self.session_id,
                run_id=self.run_id,
                content={"text": text},
            )
        )

    def count_tokens(self) -> int:
        """Count the tokens in the current message history."""
        return self.context_manager.count_tokens(self.history.get_messages_for_llm())

    async def truncate_history(self) -> None:
        """Remove oldest messages when context window limit is exceeded."""
        original_messages = self.history.get_messages_for_llm()
        truncated_messages_for_llm = (
            await self.context_manager.apply_truncation_if_needed(original_messages)
        )

        # Check if compaction occurred
        if len(truncated_messages_for_llm) != len(original_messages):
            # Get the summary content (first message after compaction)
            summary_content = ""
            if truncated_messages_for_llm and truncated_messages_for_llm[0]:
                first_msg = truncated_messages_for_llm[0][0]
                if isinstance(first_msg, TextPrompt):
                    summary_content = first_msg.text

            # Emit model compact event
            await self.event_stream.publish(
                RealtimeEvent(
                    type=EventType.MODEL_COMPACT,
                    session_id=self.session_id,
                    run_id=self.run_id,
                    content={"status": "compacted", "summary": summary_content},
                )
            )

        self.history.set_message_list(truncated_messages_for_llm)
