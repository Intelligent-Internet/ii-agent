import asyncio
import logging
from typing import Any, Optional
import uuid

from typing import List
from fastapi import WebSocket
from ii_agent.agents.base import BaseAgent
from ii_agent.core.event import EventType, RealtimeEvent
from ii_agent.llm.base import LLMClient, TextResult, ToolCallParameters
from ii_agent.llm.context_manager.base import ContextManager
from ii_agent.llm.message_history import MessageHistory
from ii_agent.tools.base import ToolImplOutput, LLMTool
from ii_agent.tools.utils import encode_image
from ii_agent.db.manager import DatabaseManager
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


class AnthropicFC(BaseAgent):
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
        system_prompt: str,
        client: LLMClient,
        tools: List[LLMTool],
        workspace_manager: WorkspaceManager,
        message_queue: asyncio.Queue,
        logger_for_agent_logs: logging.Logger,
        context_manager: ContextManager,
        max_output_tokens_per_turn: int = 8192,
        max_turns: int = 10,
        websocket: Optional[WebSocket] = None,
        session_id: Optional[uuid.UUID] = None,
        interactive_mode: bool = True,
    ):
        """Initialize the agent.

        Args:
            system_prompt: The system prompt to use
            client: The LLM client to use
            tools: List of tools to use
            message_queue: Message queue for real-time communication
            logger_for_agent_logs: Logger for agent logs
            context_manager: Context manager for managing conversation context
            max_output_tokens_per_turn: Maximum tokens per turn
            max_turns: Maximum number of turns
            websocket: Optional WebSocket for real-time communication
            session_id: UUID of the session this agent belongs to
        """
        super().__init__()
        self.workspace_manager = workspace_manager
        self.system_prompt = system_prompt
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
        self.history = MessageHistory(context_manager)
        self.session_id = session_id

        # Initialize database manager
        self.db_manager = DatabaseManager()

        self.message_queue = message_queue
        self.websocket = websocket

    async def _process_messages(self):
        try:
            while True:
                try:
                    message: RealtimeEvent = await self.message_queue.get()

                    # Save all events to database if we have a session
                    if self.session_id is not None:
                        self.db_manager.save_event(self.session_id, message)
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

    def run_impl(
        self,
        tool_input: dict[str, Any],
        message_history: Optional[MessageHistory] = None,
    ) -> ToolImplOutput:
        # Add comprehensive None and type checks for tool_input
        if tool_input is None:
            self.logger_for_agent_logs.error("tool_input is None")
            raise ValueError("tool_input cannot be None")
        
        if not isinstance(tool_input, dict):
            self.logger_for_agent_logs.error(f"tool_input is not a dict, got type: {type(tool_input)}, value: {tool_input}")
            raise ValueError(f"tool_input must be a dictionary, got {type(tool_input)}")
        
        # Check if instruction key exists
        if "instruction" not in tool_input:
            self.logger_for_agent_logs.error(f"'instruction' key missing from tool_input: {tool_input}")
            raise ValueError("tool_input must contain an 'instruction' key")
        
        instruction = tool_input["instruction"]
        
        # Add None check for instruction
        if instruction is None:
            self.logger_for_agent_logs.error("instruction is None")
            raise ValueError("instruction cannot be None")
        
        files = tool_input.get("files")  # Use .get() to handle missing key gracefully

        user_input_delimiter = "-" * 45 + " USER INPUT " + "-" * 45 + "\n" + str(instruction)
        self.logger_for_agent_logs.info(f"\n{user_input_delimiter}\n")

        # Add instruction to dialog before getting model response
        image_blocks = []
        if files:
            # First, list all attached files
            instruction = f"""{instruction}\n\nAttached files:\n"""
            for file in files:
                # Add None check for file
                if file is None:
                    self.logger_for_agent_logs.warning("Skipping None file in files list")
                    continue
                    
                relative_path = self.workspace_manager.relative_path(file)
                instruction += f" - {relative_path}\n"
                self.logger_for_agent_logs.info(f"Attached file: {relative_path}")

            # Then process images for image blocks
            for file in files:
                # Add None check for file
                if file is None:
                    continue
                    
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
            model_response, _ = self.client.generate(
                messages=self.history.get_messages_for_llm(),
                max_tokens=self.max_output_tokens,
                tools=all_tool_params,
                system_prompt=self.system_prompt,
            )

            # Validate model response
            if model_response is None or len(model_response) == 0:
                error_msg = "LLM client returned empty or None response"
                self.logger_for_agent_logs.error(error_msg)
                model_response = [TextResult(text=COMPLETE_MESSAGE)]

            # Add the raw response to the canonical history
            self.history.add_assistant_turn(model_response)

            # Handle tool calls
            pending_tool_calls = self.history.get_pending_tool_calls()

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
                    tool_output=self.history.get_last_assistant_text_response(),
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

            text_results = [
                item for item in model_response if isinstance(item, TextResult)
            ]
            if len(text_results) > 0:
                text_result = text_results[0]
                self.logger_for_agent_logs.info(
                    f"Top-level agent planning next step: {text_result.text}\n",
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
            
            try:
                tool_result = self.tool_manager.run_tool(tool_call, self.history)

                # Add safety check for tool_result
                if tool_result is None:
                    self.logger_for_agent_logs.warning(f"Tool {tool_call.tool_name} returned None result, using empty string")
                    tool_result = ""

                self.add_tool_call_result(tool_call, tool_result)
            except Exception as e:
                self.logger_for_agent_logs.error(f"Error executing tool {tool_call.tool_name}: {str(e)}")
                # Re-raise with more context
                raise RuntimeError(f"Tool execution failed for {tool_call.tool_name}: {str(e)}") from e

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
        # Add safety checks before accessing tool_input
        if tool_input is None:
            return "Agent started with undefined instruction (tool_input is None)"
        
        if not isinstance(tool_input, dict):
            return f"Agent started with invalid tool_input type: {type(tool_input)}"
        
        if "instruction" not in tool_input:
            return f"Agent started with missing instruction key in tool_input: {tool_input}"
        
        instruction = tool_input.get("instruction", "undefined instruction")
        if instruction is None:
            instruction = "None instruction"
        
        return f"Agent started with instruction: {instruction}"

    def run_agent(
        self,
        instruction: str,
        files: list[str] | None = None,
        resume: bool = False,
        orientation_instruction: str | None = None,
    ) -> str:
        """Start a new agent run.

        Args:
            instruction: The instruction to the agent.
            resume: Whether to resume the agent from the previous state,
                continuing the dialog.
            orientation_instruction: Optional orientation instruction

        Returns:
            A tuple of (result, message).
        """
        # Add safety check for instruction parameter
        if instruction is None:
            self.logger_for_agent_logs.error("instruction parameter is None in run_agent")
            raise ValueError("instruction cannot be None")
        
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
        return self.run(tool_input, self.history)

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
