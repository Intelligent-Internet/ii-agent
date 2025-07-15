import asyncio
import logging
from typing import Any, Optional, AsyncGenerator
import uuid
from functools import partial

from typing import List
from ii_agent.controller.agent import Agent
from ii_agent.core.event import EventType, RealtimeEvent
from ii_agent.core.event_stream import EventStream
from ii_agent.llm.base import LLMClient, TextResult, ToolCallParameters
from ii_agent.llm.message_history import MessageHistory
from ii_agent.tools.base import ToolImplOutput, LLMTool
from ii_agent.tools.utils import encode_image
from ii_agent.tools import AgentToolManager
from ii_agent.utils.constants import COMPLETE_MESSAGE
from ii_agent.utils.workspace_manager import WorkspaceManager
from ii_agent.utils.concurrent_execution import should_run_concurrently, run_tools_concurrently, run_tools_serially
from ii_agent.core.logger import logger

TOOL_RESULT_INTERRUPT_MESSAGE = "Tool execution interrupted by user."
AGENT_INTERRUPT_MESSAGE = "Agent interrupted by user."
TOOL_CALL_INTERRUPT_FAKE_MODEL_RSP = (
    "Tool execution interrupted by user. You can resume by providing a new instruction."
)
AGENT_INTERRUPT_FAKE_MODEL_RSP = (
    "Agent interrupted by user. You can resume by providing a new instruction."
)


class AgentController:
    def __init__(
        self,
        agent: Agent,
        tools: List[LLMTool],
        init_history: MessageHistory,
        workspace_manager: WorkspaceManager,
        event_stream: EventStream,
        max_turns: int = 200,
        interactive_mode: bool = True,
    ):
        """Initialize the agent.

        Args:
            agent: The agent to use
            tools: List of tools to use
            init_history: Initial history to use
            workspace_manager: Workspace manager for file operations
            event_stream: Event stream for publishing events
            max_turns: Maximum number of turns
            interactive_mode: Whether to use interactive mode
        """
        super().__init__()
        self.workspace_manager = workspace_manager
        self.agent = agent
        self.tool_manager = AgentToolManager(
            tools=tools,
            logger_for_agent_logs=logger,
            interactive_mode=interactive_mode,
        )

        self.max_turns = max_turns

        self.interrupted = False
        self.history = init_history
        self.event_stream = event_stream


    def _validate_tool_parameters(self):
        """Validate tool parameters and check for duplicates."""
        tool_params = [tool.get_tool_param() for tool in self.tool_manager.get_tools()]
        tool_names = [param.name for param in tool_params]
        sorted_names = sorted(tool_names)
        for i in range(len(sorted_names) - 1):
            if sorted_names[i] == sorted_names[i + 1]:
                raise ValueError(f"Tool {sorted_names[i]} is duplicated")
        return tool_params


    async def run_impl(
        self,
        tool_input: dict[str, Any],
        message_history: Optional[MessageHistory] = None,
    ) -> ToolImplOutput:
        instruction = tool_input["instruction"]
        files = tool_input["files"]

        # Add instruction to dialog before getting model response
        image_blocks = []
        if files:
            # First, list all attached files
            instruction = f"""{instruction}\n\nAttached files:\n"""
            for file in files:
                relative_path = self.workspace_manager.relative_path(file)
                instruction += f" - {relative_path}\n"
                logger.info(f"Attached file: {relative_path}")

            # Then process images for image blocks
            for file in files:
                ext = file.split(".")[-1]
                if ext == "jpg":
                    ext = "jpeg"
                if ext in ["png", "gif", "jpeg", "webp"]:
                    base64_image = encode_image(
                        str(self.workspace_manager.workspace_path(file))
                    )
                    image_blocks.append(
                        {
                            "source": {
                                "type": "base64",
                                "media_type": f"image/{ext}",
                                "data": base64_image,
                            }
                        }
                    )

        self.history.add_user_prompt(instruction, image_blocks)
        self.interrupted = False

        remaining_turns = self.max_turns
        while remaining_turns > 0:
            self.history.truncate()
            remaining_turns -= 1


            # Get tool parameters for available tools
            all_tool_params = self._validate_tool_parameters()

            if self.interrupted:
                # Handle interruption during model generation or other operations
                self.add_fake_assistant_turn(AGENT_INTERRUPT_FAKE_MODEL_RSP)
                return ToolImplOutput(
                    tool_output=AGENT_INTERRUPT_MESSAGE,
                    tool_result_message=AGENT_INTERRUPT_MESSAGE,
                )

            logger.info(
                f"(Current token count: {self.history.count_tokens()})\n"
            )
            loop = asyncio.get_event_loop()
            model_response = await loop.run_in_executor(
                None,
                partial(
                    self.agent.step,
                    self.history,
                ),
            )

            if len(model_response) == 0:
                model_response = [TextResult(text=COMPLETE_MESSAGE)]

            # Add the raw response to the canonical history
            self.history.add_assistant_turn(model_response)

            # Handle tool calls
            pending_tool_calls = self.history.get_pending_tool_calls()

            if len(pending_tool_calls) == 0:
                # No tools were called, so assume the task is complete
                logger.info("[no tools were called]")
                self.event_stream.add_event(
                    RealtimeEvent(
                        type=EventType.AGENT_RESPONSE,
                        content={"text": "Task completed"},
                    )
                )
                return ToolImplOutput(
                    tool_output=self.history.get_last_assistant_text_response(),
                    tool_result_message="Task completed",
                )

            # Handle tool calls - single or multiple

            text_results = [
                item for item in model_response if isinstance(item, TextResult)
            ]
            if len(text_results) > 0:
                text_result = text_results[0]
                logger.info(
                    f"Top-level agent planning next step: {text_result.text}\n",
                )

            # Check for interruption before tool execution
            if self.interrupted:
                # Handle interruption during tool execution
                for tool_call in pending_tool_calls:
                    self.add_tool_call_result(tool_call, TOOL_RESULT_INTERRUPT_MESSAGE)
                self.add_fake_assistant_turn(TOOL_CALL_INTERRUPT_FAKE_MODEL_RSP)
                return ToolImplOutput(
                    tool_output=TOOL_RESULT_INTERRUPT_MESSAGE,
                    tool_result_message=TOOL_RESULT_INTERRUPT_MESSAGE,
                )
            
            # Execute tools - either concurrently or serially based on read-only status
            if len(pending_tool_calls) == 1:
                # Single tool call - execute normally
                tool_call = pending_tool_calls[0]
                
                self.event_stream.add_event(
                    RealtimeEvent(
                        type=EventType.TOOL_CALL,
                        content={
                            "tool_call_id": tool_call.tool_call_id,
                            "tool_name": tool_call.tool_name,
                            "tool_input": tool_call.tool_input,
                        },
                    )
                )
                
                tool_result = await self.tool_manager.run_tool(tool_call, self.history)
                self.add_tool_call_result(tool_call, tool_result)
            else:
                # Multiple tool calls - execute based on read-only status
                logger.info(f"Executing {len(pending_tool_calls)} tools")
                
                # Send events for all tool calls
                for tool_call in pending_tool_calls:
                    self.event_stream.add_event(
                        RealtimeEvent(
                            type=EventType.TOOL_CALL,
                            content={
                                "tool_call_id": tool_call.tool_call_id,
                                "tool_name": tool_call.tool_name,
                                "tool_input": tool_call.tool_input,
                            },
                        )
                    )
                
                # Execute tools in batch
                tool_results = await self.tool_manager.run_tools_batch(pending_tool_calls, self.history)
                
                # Add all results to history in order
                for tool_call, tool_result in zip(pending_tool_calls, tool_results):
                    self.add_tool_call_result(tool_call, tool_result)
            if self.tool_manager.should_stop():
                # Add a fake model response, so the next turn is the user's
                # turn in case they want to resume
                self.add_fake_assistant_turn(self.tool_manager.get_final_answer())
                return ToolImplOutput(
                    tool_output=self.tool_manager.get_final_answer(),
                    tool_result_message="Task completed",
                )

        agent_answer = "Agent did not complete after max turns"
        self.event_stream.add_event(
            RealtimeEvent(type=EventType.AGENT_RESPONSE, content={"text": agent_answer})
        )
        return ToolImplOutput(
            tool_output=agent_answer, tool_result_message=agent_answer
        )

    def get_tool_start_message(self, tool_input: dict[str, Any]) -> str:
        return f"Agent started with instruction: {tool_input['instruction']}"

    async def run_agent_async(
        self,
        instruction: str,
        files: list[str] | None = None,
        resume: bool = False,
        orientation_instruction: str | None = None,
    ) -> str:
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
        self.tool_manager.reset()
        if not resume:
            self.history.clear()
            self.interrupted = False

        tool_input = {
            "instruction": instruction,
            "files": files,
        }
        if orientation_instruction:
            tool_input["orientation_instruction"] = orientation_instruction
        return await self.run_impl(tool_input, self.history)

    def run_agent(
        self,
        instruction: str,
        files: list[str] | None = None,
        resume: bool = False,
        orientation_instruction: str | None = None,
    ) -> str:
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
            self.run_agent_async(instruction, files, resume, orientation_instruction)
        )

    def clear(self):
        """Clear the dialog and reset interruption state.
        Note: This does NOT clear the file manager, preserving file context.
        """
        self.history.clear()
        self.interrupted = False

    def cancel(self):
        """Cancel the agent execution."""
        self.interrupted = True
        logger.info("Agent cancellation requested")

    def add_tool_call_result(self, tool_call: ToolCallParameters, tool_result: str):
        """Add a tool call result to the history and send it to the message queue."""
        self.history.add_tool_call_result(tool_call, tool_result)

        self.event_stream.add_event(
            RealtimeEvent(
                type=EventType.TOOL_RESULT,
                content={
                    "tool_call_id": tool_call.tool_call_id,
                    "tool_name": tool_call.tool_name,
                    "result": tool_result,
                },
            )
        )

    def add_fake_assistant_turn(self, text: str):
        """Add a fake assistant turn to the history and send it to the message queue."""
        self.history.add_assistant_turn([TextResult(text=text)])
        if self.interrupted:
            rsp_type = EventType.AGENT_RESPONSE_INTERRUPTED
        else:
            rsp_type = EventType.AGENT_RESPONSE

        self.event_stream.add_event(
            RealtimeEvent(
                type=rsp_type,
                content={"text": text},
            )
        )
