import asyncio
import logging
from typing import Any, Optional
from functools import partial

from typing import List
from fastapi import WebSocket
from ii_agent.agents.base import BaseAgent
from ii_agent.core.event import EventType, RealtimeEvent
from ii_agent.llm.base import (
    LLMClient,
    TextResult,
    ToolCallParameters,
    AnthropicThinkingBlock,
)
from ii_agent.llm.message_history import MessageHistory
from ii_agent.prompts.system_prompt import SystemPromptBuilder
from ii_agent.tools.base import ToolImplOutput, LLMTool
from ii_agent.tools.utils import encode_image
from ii_agent.db.manager import Events
from ii_agent.tools import AgentToolManager
from ii_agent.utils.constants import COMPLETE_MESSAGE
from ii_agent.utils.workspace_manager import WorkspaceManager

TOOL_RESULT_INTERRUPT_MESSAGE = "Tool execution interrupted by user."
AGENT_INTERRUPT_MESSAGE = "Agent interrupted by user."
TOOL_CALL_INTERRUPT_FAKE_MODEL_RSP = (
    "Tool execution interrupted by user. You can resume by providing a new instruction."
)
AGENT_INTERRUPT_FAKE_MODEL_RSP = (
    "Agent interrupted by user. You can resume by providing a new instruction."
)


class FunctionCallAgent(BaseAgent):
    name = "general_agent"
    description = """\
A general agent that can accomplish tasks and answer questions.

If you are faced with a task that involves more than a few steps, or if the task is complex, or if the instructions are very long,
try breaking down the task into smaller steps. After call this tool to update or create a plan, use write_file or str_replace_tool to update the plan to todo.md
"""
    input_schema = {
        "type": "object",
        "properties": {
            "instruction": {
                "type": "string",
                "description": "The instruction to the agent.",
            },
        },
        "required": ["instruction"],
    }
    websocket: Optional[WebSocket]

    def __init__(
        self,
        system_prompt_builder: SystemPromptBuilder,
        client: LLMClient,
        tools: List[LLMTool],
        init_history: MessageHistory,
        workspace_manager: WorkspaceManager,
        message_queue: asyncio.Queue,
        logger_for_agent_logs: logging.Logger,
        max_output_tokens_per_turn: int = 8192,
        max_turns: int = 200,
        websocket: Optional[WebSocket] = None,
        interactive_mode: bool = True,
    ):
        """Initialize the agent.

        Args:
            system_prompt_builder: The system prompt builder to use
            client: The LLM client to use
            tools: List of tools to use
            message_queue: Message queue for real-time communication
            logger_for_agent_logs: Logger for agent logs
            max_output_tokens_per_turn: Maximum tokens per turn
            max_turns: Maximum number of turns
            websocket: Optional WebSocket for real-time communication
            session_id: UUID of the session this agent belongs to
            interactive_mode: Whether to use interactive mode
            init_history: Optional initial history to use
        """
        super().__init__()
        self.workspace_manager = workspace_manager
        self.system_prompt_builder = system_prompt_builder
        self.client = client
        self.tool_manager = AgentToolManager(
            tools=tools,
            logger_for_agent_logs=logger_for_agent_logs,
            interactive_mode=interactive_mode,
        )

        self.logger_for_agent_logs = logger_for_agent_logs
        self.max_output_tokens = max_output_tokens_per_turn
        self.max_turns = max_turns

        self.interrupted = False
        self.history = init_history
        self.session_id = workspace_manager.session_id

        # Initialize database manager
        self.message_queue = message_queue
        self.websocket = websocket

    async def _process_messages(self):
        try:
            while True:
                try:
                    message: RealtimeEvent = await self.message_queue.get()

                    # Save all events to database if we have a session
                    if self.session_id is not None:
                        Events.save_event(self.session_id, message)
                    else:
                        self.logger_for_agent_logs.info(
                            f"No session ID, skipping event: {message}"
                        )

                    # Only send to websocket if this is not an event from the client and websocket exists
                    if (
                        message.type != EventType.USER_MESSAGE
                        and self.websocket is not None
                    ):
                        try:
                            await self.websocket.send_json(message.model_dump())
                        except Exception as e:
                            # If websocket send fails, just log it and continue processing
                            self.logger_for_agent_logs.warning(
                                f"Failed to send message to websocket: {str(e)}"
                            )
                            # Set websocket to None to prevent further attempts
                            self.websocket = None

                    self.message_queue.task_done()
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    self.logger_for_agent_logs.error(
                        f"Error processing WebSocket message: {str(e)}"
                    )
        except asyncio.CancelledError:
            self.logger_for_agent_logs.info("Message processor stopped")
        except Exception as e:
            self.logger_for_agent_logs.error(f"Error in message processor: {str(e)}")

    def _validate_tool_parameters(self):
        """Validate tool parameters and check for duplicates."""
        tool_params = [tool.get_tool_param() for tool in self.tool_manager.get_tools()]
        tool_names = [param.name for param in tool_params]
        sorted_names = sorted(tool_names)
        for i in range(len(sorted_names) - 1):
            if sorted_names[i] == sorted_names[i + 1]:
                raise ValueError(f"Tool {sorted_names[i]} is duplicated")
        return tool_params

    def start_message_processing(self):
        """Start processing the message queue."""
        return asyncio.create_task(self._process_messages())

    async def run_impl(
        self,
        tool_input: dict[str, Any],
        message_history: Optional[MessageHistory] = None,
    ) -> ToolImplOutput:
        instruction = tool_input["instruction"]
        files = tool_input["files"]

        user_input_delimiter = "-" * 45 + " USER INPUT " + "-" * 45 + "\n" + instruction
        self.logger_for_agent_logs.info(f"\n{user_input_delimiter}\n")

        # Add instruction to dialog before getting model response
        image_blocks = []
        if files:
            # First, list all attached files
            instruction = f"""{instruction}\n\nAttached files:\n"""
            for file in files:
                relative_path = self.workspace_manager.relative_path(file)
                instruction += f" - {relative_path}\n"
                self.logger_for_agent_logs.info(f"Attached file: {relative_path}")

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

            delimiter = "-" * 45 + " NEW TURN " + "-" * 45
            self.logger_for_agent_logs.info(f"\n{delimiter}\n")

            # Get tool parameters for available tools
            all_tool_params = self._validate_tool_parameters()

            if self.interrupted:
                # Handle interruption during model generation or other operations
                self.add_fake_assistant_turn(AGENT_INTERRUPT_FAKE_MODEL_RSP)
                return ToolImplOutput(
                    tool_output=AGENT_INTERRUPT_MESSAGE,
                    tool_result_message=AGENT_INTERRUPT_MESSAGE,
                )

            self.logger_for_agent_logs.info(
                f"(Current token count: {self.history.count_tokens()})\n"
            )
            loop = asyncio.get_event_loop()
            model_response, _ = await loop.run_in_executor(
                None,
                partial(
                    self.client.generate,
                    messages=self.history.get_messages_for_llm(),
                    max_tokens=self.max_output_tokens,
                    tools=all_tool_params,
                    system_prompt=self.system_prompt_builder.get_system_prompt(),
                ),
            )

            if len(model_response) == 0:
                model_response = [TextResult(text=COMPLETE_MESSAGE)]

            # Add the raw response to the canonical history
            self.history.add_assistant_turn(model_response)

            # Handle tool calls
            pending_tool_calls = self.history.get_pending_tool_calls()

            text_results = [
                item
                for item in model_response
                if isinstance(item, TextResult)
                or isinstance(item, AnthropicThinkingBlock)
            ]
            for i in range(len(text_results)):
                text_result = text_results[i]
                if isinstance(text_result, AnthropicThinkingBlock):
                    wrapped_thinking = ""
                    words = text_result.thinking.split()
                    for i in range(0, len(words), 8):
                        wrapped_thinking += " ".join(words[i:i+8]) + "\n"
                    text = f"```Thinking:\n{wrapped_thinking.strip()}\n```"
                else:
                    text = text_result.text
                self.logger_for_agent_logs.info(
                    f"Top-level agent planning next step: {text}\n",
                )
                self.message_queue.put_nowait(
                    RealtimeEvent(
                        type=EventType.AGENT_THINKING,
                        content={"text": text},
                    )
                )

            if len(pending_tool_calls) == 0:
                # No tools were called, so assume the task is complete
                self.logger_for_agent_logs.info("[no tools were called]")
                self.message_queue.put_nowait(
                    RealtimeEvent(
                        type=EventType.AGENT_RESPONSE,
                        content={"text": "Task completed"},
                    )
                )
                return ToolImplOutput(
                    tool_output="",
                    tool_result_message="Task completed",
                )


            if len(pending_tool_calls) > 1:
                raise ValueError("Only one tool call per turn is supported")

            assert len(pending_tool_calls) == 1

            tool_call = pending_tool_calls[0]

            self.message_queue.put_nowait(
                RealtimeEvent(
                    type=EventType.TOOL_CALL,
                    content={
                        "tool_call_id": tool_call.tool_call_id,
                        "tool_name": tool_call.tool_name,
                        "tool_input": tool_call.tool_input,
                    },
                )
            )

            # Handle tool call by the agent
            if self.interrupted:
                # Handle interruption during tool execution
                self.add_tool_call_result(tool_call, TOOL_RESULT_INTERRUPT_MESSAGE)
                self.add_fake_assistant_turn(TOOL_CALL_INTERRUPT_FAKE_MODEL_RSP)
                return ToolImplOutput(
                    tool_output=TOOL_RESULT_INTERRUPT_MESSAGE,
                    tool_result_message=TOOL_RESULT_INTERRUPT_MESSAGE,
                )
            tool_result = await self.tool_manager.run_tool(tool_call, self.history)

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
        self.message_queue.put_nowait(
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
        return await self.run_async(tool_input, self.history)

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
        self.logger_for_agent_logs.info("Agent cancellation requested")

    def add_tool_call_result(self, tool_call: ToolCallParameters, tool_result: str):
        """Add a tool call result to the history and send it to the message queue."""
        self.history.add_tool_call_result(tool_call, tool_result)

        self.message_queue.put_nowait(
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

        self.message_queue.put_nowait(
            RealtimeEvent(
                type=rsp_type,
                content={"text": text},
            )
        )
