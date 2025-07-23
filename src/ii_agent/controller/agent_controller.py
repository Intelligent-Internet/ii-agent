import asyncio
from typing import Any, Optional, List
from functools import partial

from ii_agent.controller.agent import Agent
from ii_agent.core.event import EventType, RealtimeEvent
from ii_agent.core.event_stream import EventStream
from ii_agent.llm.base import TextResult, ToolCallParameters
from ii_agent.controller.state import State
from ii_agent.tools.base import ToolImplOutput, LLMTool
from ii_agent.tools.utils import encode_image
from ii_agent.tools import AgentToolManager
from ii_agent.utils.constants import COMPLETE_MESSAGE
from ii_agent.utils.workspace_manager import WorkspaceManager
from ii_agent.core.logger import logger
from ii_agent.llm.context_manager.base import ContextManager

TOOL_RESULT_INTERRUPT_MESSAGE = "[Request interrupted by user for tool use]"
AGENT_INTERRUPT_MESSAGE = "Agent interrupted by user."
TOOL_CALL_INTERRUPT_FAKE_MODEL_RSP = "[Request interrupted by user for tool use]"
AGENT_INTERRUPT_FAKE_MODEL_RSP = (
    "Agent interrupted by user. You can resume by providing a new instruction."
)


class AgentController:
    def __init__(
        self,
        agent: Agent,
        tools: List[LLMTool],
        init_history: State,
        workspace_manager: WorkspaceManager,
        event_stream: EventStream,
        context_manager: ContextManager,
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
            context_manager: Context manager for token counting and truncation
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
        self.interactive_mode = interactive_mode
        self.interrupted = False
        self.history = init_history
        self.event_stream = event_stream
        self.context_manager = context_manager

    @property
    def state(self) -> State:
        """Return the current conversation state/history."""
        return self.history

    def _validate_tool_parameters(self):
        """Validate tool parameters and check for duplicates."""
        tool_params = [tool.get_tool_param() for tool in self.tool_manager.tools]
        tool_names = [param.name for param in tool_params]
        sorted_names = sorted(tool_names)
        for i in range(len(sorted_names) - 1):
            if sorted_names[i] == sorted_names[i + 1]:
                raise ValueError(f"Tool {sorted_names[i]} is duplicated")
        return tool_params

    async def run_impl(
        self,
        tool_input: dict[str, Any],
        state: Optional[State] = None,
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
                logger.debug(f"Attached file: {relative_path}")

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
            self.truncate_history()
            remaining_turns -= 1

            self._validate_tool_parameters()

            if self.interrupted:
                # Handle interruption during model generation or other operations
                self.add_fake_assistant_turn(AGENT_INTERRUPT_FAKE_MODEL_RSP)
                return ToolImplOutput(
                    tool_output=AGENT_INTERRUPT_MESSAGE,
                    tool_result_message=AGENT_INTERRUPT_MESSAGE,
                )

            # Only show token count in debug mode, not in interactive CLI
            if not self.interactive_mode:
                logger.info(f"(Current token count: {self.count_tokens()})\n")

            # Emit thinking event before model response
            self.event_stream.add_event(
                RealtimeEvent(type=EventType.AGENT_THINKING, content={})
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

            # Process all TextResult blocks first
            text_results = [
                item for item in model_response if isinstance(item, TextResult)
            ]
            for text_result in text_results:
                logger.debug(
                    f"Top-level agent planning next step: {text_result.text}\n",
                )
                # Emit event for each TextResult to be displayed in console
                self.event_stream.add_event(
                    RealtimeEvent(
                        type=EventType.AGENT_RESPONSE,
                        content={"text": text_result.text},
                    )
                )

            # Handle tool calls
            pending_tool_calls = self.history.get_pending_tool_calls()

            if len(pending_tool_calls) == 0:
                # No tools were called, so assume the task is complete
                logger.debug("[no tools were called]")
                # Only emit "Task completed" if there were no text results
                if not text_results:
                    self.event_stream.add_event(
                        RealtimeEvent(
                            type=EventType.AGENT_RESPONSE,
                            content={"text": "Task completed"},
                        )
                    )
                return ToolImplOutput(
                    tool_output=self.history.get_last_assistant_text_response()
                    or "Task completed",
                    tool_result_message="Task completed",
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

            # Execute all tool calls using batch approach
            logger.debug(f"Executing {len(pending_tool_calls)} tool(s)")

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

            # Execute tools in batch (handles both single and multiple tools)
            tool_results = await self.tool_manager.run_tools_batch(
                pending_tool_calls, self.history
            )

            # Add all results to history in order
            for tool_call, tool_result in zip(pending_tool_calls, tool_results):
                self.add_tool_call_result(tool_call, tool_result)

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
    ) -> ToolImplOutput:
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
    ) -> ToolImplOutput:
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
        logger.debug("Agent cancellation requested")

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

    def count_tokens(self) -> int:
        """Count the tokens in the current message history."""
        return self.context_manager.count_tokens(self.history.get_messages_for_llm())

    def truncate_history(self) -> None:
        """Remove oldest messages when context window limit is exceeded."""
        truncated_messages_for_llm = self.context_manager.apply_truncation_if_needed(
            self.history.get_messages_for_llm()
        )
        self.history.set_message_list(truncated_messages_for_llm)

    def compact_context(self) -> dict[str, Any]:
        """Manually compact the conversation context using truncation.

        Returns:
            Dict containing operation status and token information.
        """
        try:
            # Get current token count before compacting
            original_token_count = self.count_tokens()

            # Apply truncation regardless of current token count
            truncated_messages_for_llm = self.context_manager.apply_truncation(
                self.history.get_messages_for_llm()
            )

            # Update history with truncated messages
            self.history.set_message_list(truncated_messages_for_llm)

            # Get new token count after compacting
            new_token_count = self.count_tokens()

            return {
                "success": True,
                "original_tokens": original_token_count,
                "new_tokens": new_token_count,
                "tokens_saved": original_token_count - new_token_count,
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
            }
