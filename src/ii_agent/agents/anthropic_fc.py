import asyncio

import logging
from typing import Any, Optional, List
from fastapi import WebSocket
from ii_agent.agents.base import BaseAgent
from ii_agent.core.event import EventType, RealtimeEvent
from ii_agent.llm.base import LLMClient, TextResult
from ii_agent.llm.context_manager.base import ContextManager
from ii_agent.llm.message_history import MessageHistory
from ii_agent.tools import AgentToolManager
from ii_agent.tools.base import ToolImplOutput
from ii_agent.tools.base import LLMTool


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
        message_queue: asyncio.Queue,
        logger_for_agent_logs: logging.Logger,
        context_manager: ContextManager,
        max_output_tokens_per_turn: int = 8192,
        max_turns: int = 10,
        websocket: Optional[WebSocket] = None,
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
        """
        super().__init__()
        self.system_prompt = system_prompt
        self.client = client
        self.tool_manager = AgentToolManager(
            tools=tools,
            logger_for_agent_logs=logger_for_agent_logs,
        )

        self.logger_for_agent_logs = logger_for_agent_logs
        self.max_output_tokens = max_output_tokens_per_turn
        self.max_turns = max_turns

        self.interrupted = False
        self.history = MessageHistory()
        self.context_manager = context_manager
        self.message_queue = message_queue
        self.websocket = websocket

    async def _process_messages(self):
        if not self.websocket:
            return

        try:
            while True:
                try:
                    message: RealtimeEvent = await self.message_queue.get()

                    await self.websocket.send_json(message.model_dump())

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
        instruction = tool_input["instruction"]

        user_input_delimiter = "-" * 45 + " USER INPUT " + "-" * 45 + "\n" + instruction
        self.logger_for_agent_logs.info(f"\n{user_input_delimiter}\n")

        # Add instruction to dialog before getting mode
        self.history.add_user_prompt(instruction)
        self.interrupted = False

        remaining_turns = self.max_turns
        while remaining_turns > 0:
            remaining_turns -= 1

            delimiter = "-" * 45 + " NEW TURN " + "-" * 45
            self.logger_for_agent_logs.info(f"\n{delimiter}\n")

            # Get tool parameters for available tools
            all_tool_params = self._validate_tool_parameters()

            try:
                current_messages = self.history.get_messages_for_llm()
                current_tok_count = self.context_manager.count_tokens(current_messages)
                self.logger_for_agent_logs.info(
                    f"(Current token count: {current_tok_count})\n"
                )

                truncated_messages_for_llm = (
                    self.context_manager.apply_truncation_if_needed(current_messages)
                )

                # NOTE:
                # If truncation happened, the `history` object itself was modified.
                # We need to update the message list in the `history` object to use the truncated version.
                self.history.set_message_list(truncated_messages_for_llm)

                model_response, _ = self.client.generate(
                    messages=truncated_messages_for_llm,
                    max_tokens=self.max_output_tokens,
                    tools=all_tool_params,
                    system_prompt=self.system_prompt,
                )

                # Add the raw response to the canonical history
                self.history.add_assistant_turn(model_response)

                # Handle tool calls
                pending_tool_calls = self.history.get_pending_tool_calls()

                if len(pending_tool_calls) == 0:
                    # No tools were called, so assume the task is complete
                    self.logger_for_agent_logs.info("[no tools were called]")
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
                try:
                    tool_result = self.tool_manager.run_tool(tool_call, self.history)
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
                    if self.tool_manager.should_stop():
                        # Add a fake model response, so the next turn is the user's
                        # turn in case they want to resume
                        self.history.add_assistant_turn(
                            [TextResult(text="Completed the task.")]
                        )
                        return ToolImplOutput(
                            tool_output=self.tool_manager.get_final_answer(),
                            tool_result_message="Task completed",
                        )
                except KeyboardInterrupt:
                    # Handle interruption during tool execution
                    self.interrupted = True
                    interrupt_message = "Tool execution was interrupted by user."
                    self.history.add_tool_call_result(tool_call, interrupt_message)
                    self.history.add_assistant_turn(
                        [
                            TextResult(
                                text="Tool execution interrupted by user. You can resume by providing a new instruction."
                            )
                        ]
                    )
                    return ToolImplOutput(
                        tool_output=interrupt_message,
                        tool_result_message=interrupt_message,
                    )

            except KeyboardInterrupt:
                # Handle interruption during model generation or other operations
                self.interrupted = True
                self.history.add_assistant_turn(
                    [
                        TextResult(
                            text="Agent interrupted by user. You can resume by providing a new instruction."
                        )
                    ]
                )
                return ToolImplOutput(
                    tool_output="Agent interrupted by user",
                    tool_result_message="Agent interrupted by user",
                )

        agent_answer = "Agent did not complete after max turns"
        return ToolImplOutput(
            tool_output=agent_answer, tool_result_message=agent_answer
        )

    def get_tool_start_message(self, tool_input: dict[str, Any]) -> str:
        return f"Agent started with instruction: {tool_input['instruction']}"

    def run_agent(
        self,
        instruction: str,
        resume: bool = False,
        orientation_instruction: str | None = None,
    ) -> str:
        """Start a new agent run.

        Args:
            instruction: The instruction to the agent.
            resume: Whether to resume the agent from the previous state,
                continuing the dialog.

        Returns:
            A tuple of (result, message).
        """
        self.tool_manager.reset()
        if resume:
            assert self.history.is_next_turn_user()
        else:
            self.history.clear()
            self.interrupted = False

        tool_input = {
            "instruction": instruction,
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
