import asyncio
from copy import deepcopy
import json
import logging
import os
from typing import Any, Optional
from fastapi import WebSocket
from ii_agent.agents.base import BaseAgent
from ii_agent.core.event import EventType, RealtimeEvent
from ii_agent.llm.base import LLMClient, TextResult
from ii_agent.llm.context_manager.base import ContextManager
from ii_agent.llm.message_history import MessageHistory
from ii_agent.llm.utils import convert_message_history_to_json, convert_message_to_json
from ii_agent.prompts.system_prompt import SYSTEM_PROMPT
from ii_agent.tools import (
    CompleteTool,
    create_bash_tool,
    create_docker_bash_tool,
    StrReplaceEditorTool,
    SequentialThinkingTool,
    TavilySearchTool,
    TavilyVisitWebpageTool,
    StaticDeployTool,
)
from ii_agent.tools.base import ToolImplOutput, LLMTool
from ii_agent.tools.browser_tool import (
    BrowserNavigationTool,
    BrowserRestartTool,
    BrowserScrollDownTool,
    BrowserScrollUpTool,
    BrowserViewTool,
    BrowserWaitTool,
    BrowserSwitchTabTool,
    BrowserOpenNewTabTool,
    BrowserClickTool,
    BrowserEnterTextTool,
    BrowserPressKeyTool,
    BrowserGetSelectOptionsTool,
    BrowserSelectDropdownOptionTool,
)

from ii_agent.tools.advanced_tools.audio_tool import (
    AudioTranscribeTool,
    AudioGenerateTool,
)
from ii_agent.tools.advanced_tools.pdf_tool import PdfTextExtractTool
from ii_agent.tools.text_inspector_tool import TextInspectorTool
from ii_agent.tools.visualizer import DisplayLocalImageTool
from ii_agent.tools.utils import save_base64_image_png
from ii_agent.utils import WorkspaceManager
from ii_agent.browser.browser import Browser


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

    def _get_system_prompt(self):
        """Get the system prompt, including any pending messages.

        Returns:
            The system prompt with messages prepended if any
        """
        return SYSTEM_PROMPT.format(
            workspace_root=self.workspace_manager.root,
        )

    def __init__(
        self,
        client: LLMClient,
        workspace_manager: WorkspaceManager,
        logger_for_agent_logs: logging.Logger,
        context_manager: ContextManager,
        max_output_tokens_per_turn: int = 8192,
        max_turns: int = 10,
        ask_user_permission: bool = False,
        docker_container_id: Optional[str] = None,
        websocket: Optional[WebSocket] = None,
    ):
        """Initialize the agent.

        Args:
            client: The LLM client to use
            workspace_manager: Workspace manager for taking snapshots
            logger_for_agent_logs: Logger for agent logs
            context_manager: Context manager for managing conversation context
            max_output_tokens_per_turn: Maximum tokens per turn
            max_turns: Maximum number of turns
            ask_user_permission: Whether to ask for permission before executing commands
            docker_container_id: Optional Docker container ID to run commands in
            websocket: Optional WebSocket for real-time communication
        """
        super().__init__()
        self.client = client
        self.logger_for_agent_logs = logger_for_agent_logs
        self.max_output_tokens = max_output_tokens_per_turn
        self.max_turns = max_turns
        self.workspace_manager = workspace_manager
        self.interrupted = False
        self.history = MessageHistory()
        self.context_manager = context_manager

        # Create and store the complete tool
        self.complete_tool = CompleteTool()

        if docker_container_id is not None:
            self.logger_for_agent_logs.info(
                f"Enabling docker bash tool with container {docker_container_id}"
            )
            bash_tool = create_docker_bash_tool(
                container=docker_container_id,
                ask_user_permission=ask_user_permission,
            )
        else:
            bash_tool = create_bash_tool(
                ask_user_permission=ask_user_permission,
                cwd=workspace_manager.root,
            )

        self.message_queue = asyncio.Queue()

        self.browser = Browser()

        self.tools = [
            bash_tool,
            StrReplaceEditorTool(workspace_manager=workspace_manager),
            SequentialThinkingTool(),
            TavilySearchTool(),
            TavilyVisitWebpageTool(),
            self.complete_tool,
            StaticDeployTool(workspace_manager=workspace_manager),
            # Browser tools
            BrowserNavigationTool(browser=self.browser),
            BrowserRestartTool(browser=self.browser),
            BrowserScrollDownTool(browser=self.browser),
            BrowserScrollUpTool(browser=self.browser),
            BrowserViewTool(browser=self.browser, message_queue=self.message_queue),
            BrowserWaitTool(browser=self.browser),
            BrowserSwitchTabTool(browser=self.browser),
            BrowserOpenNewTabTool(browser=self.browser),
            BrowserClickTool(browser=self.browser),
            BrowserEnterTextTool(browser=self.browser),
            BrowserPressKeyTool(browser=self.browser),
            BrowserGetSelectOptionsTool(browser=self.browser),
            BrowserSelectDropdownOptionTool(browser=self.browser),
            # audio tools
            AudioTranscribeTool(workspace_manager=workspace_manager),
            AudioGenerateTool(workspace_manager=workspace_manager),
            # pdf tools
            # PdfTextExtractTool(workspace_manager=workspace_manager),
            # text inspector tool
            TextInspectorTool(workspace_manager=workspace_manager),
            # visualizer tool
            DisplayLocalImageTool(workspace_manager=workspace_manager),
        ]
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

    def start_message_processing(self):
        """Start processing the message queue."""
        return asyncio.create_task(self._process_messages())

    def run_impl(
        self,
        tool_input: dict[str, Any],
        message_history: Optional[MessageHistory] = None,
        log_dir: Optional[str] = None,
    ) -> ToolImplOutput:
        instruction = tool_input["instruction"]

        user_input_delimiter = "-" * 45 + " USER INPUT " + "-" * 45 + "\n" + instruction
        self.logger_for_agent_logs.info(f"\n{user_input_delimiter}\n")

        # Add instruction to dialog before getting mode
        self.history.add_user_prompt(instruction)
        self.interrupted = False

        step = 0

        remaining_turns = self.max_turns
        while remaining_turns > 0:
            step_log_dir = f"{log_dir}/step_{step}"
            os.makedirs(step_log_dir, exist_ok=True)

            remaining_turns -= 1
            step += 1

            delimiter = "-" * 45 + " NEW TURN " + "-" * 45
            self.logger_for_agent_logs.info(f"\n{delimiter}\n")

            # Get tool parameters for available tools
            tool_params = [tool.get_tool_param() for tool in self.tools]

            # Check for duplicate tool names
            tool_names = [param.name for param in tool_params]
            sorted_names = sorted(tool_names)
            for i in range(len(sorted_names) - 1):
                if sorted_names[i] == sorted_names[i + 1]:
                    raise ValueError(f"Tool {sorted_names[i]} is duplicated")

            try:
                current_messages = self.history.get_messages_for_llm()
                current_messages_json = convert_message_history_to_json(current_messages)
                current_messages_json_hide_img = convert_message_history_to_json(current_messages, hide_base64_image=True)
                with open(f"{step_log_dir}/current_messages.json", "w") as f:
                    json.dump(current_messages_json, f, indent=4)
                with open(f"{step_log_dir}/current_messages_hide_img.json", "w") as f:
                    json.dump(current_messages_json_hide_img, f, indent=4)

                current_tok_count = self.context_manager.count_tokens(current_messages)
                self.logger_for_agent_logs.info(
                    f"(Current token count: {current_tok_count})\n"
                )

                truncated_messages_for_llm = (
                    self.context_manager.apply_truncation_if_needed(current_messages)
                )
                truncated_messages_for_llm_json = convert_message_history_to_json(truncated_messages_for_llm)
                truncated_messages_for_llm_json_hide_img = convert_message_history_to_json(truncated_messages_for_llm, hide_base64_image=True)
                with open(f"{step_log_dir}/truncated_messages_for_llm.json", "w") as f:
                    json.dump(truncated_messages_for_llm_json, f, indent=4)
                with open(f"{step_log_dir}/truncated_messages_for_llm_hide_img.json", "w") as f:
                    json.dump(truncated_messages_for_llm_json_hide_img, f, indent=4)

                # NOTE:
                # If truncation happened, the `history` object itself was modified.
                # We need to update the message list in the `history` object to use the truncated version.
                self.history.set_message_list(truncated_messages_for_llm)

                model_response, _ = self.client.generate(
                    messages=truncated_messages_for_llm,
                    max_tokens=self.max_output_tokens,
                    tools=tool_params,
                    system_prompt=self._get_system_prompt(),
                )

                model_response_json = [convert_message_to_json(msg) for msg in model_response]
                with open(f"{step_log_dir}/model_response.json", "w") as f:
                    json.dump(model_response_json, f, indent=4)

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

                try:
                    tool: LLMTool = next(
                        t for t in self.tools if t.name == tool_call.tool_name
                    )
                except StopIteration as exc:
                    raise ValueError(
                        f"Tool with name {tool_call.tool_name} not found"
                    ) from exc

                try:
                    result = tool.run(tool_call.tool_input, deepcopy(self.history))

                    tool_call_json = {
                        "type": "tool_call",
                        "tool_call_id": tool_call.tool_call_id,
                        "tool_name": tool_call.tool_name,
                        "tool_input": tool_call.tool_input,
                    }
                    with open(f"{step_log_dir}/tool_call.json", "w") as f:
                        json.dump(tool_call_json, f, indent=4)

                    tool_input_str = "\n".join(
                        [f" - {k}: {v}" for k, v in tool_call.tool_input.items()]
                    )

                    log_message = f"Calling tool {tool_call.tool_name} with input:\n{tool_input_str}"
                    if isinstance(result, str):
                        log_message += f"\nTool output: \n{result}\n\n"
                    else:
                        # Handle image data in tool output more gracefully
                        if isinstance(result, list):
                            output_str = ""
                            for item in result:
                                if isinstance(item, dict):
                                    if item.get("type") == "image":
                                        output_str += "[Image data truncated for logging]\n"
                                    else:
                                        output_str += str(item) + "\n"
                                else:
                                    output_str += str(item) + "\n"
                            log_message += f"\nTool output: \n{output_str}\n\n"
                        else:
                            log_message += f"\nTool output: \n{result[0]}\n\n"
                    self.logger_for_agent_logs.info(log_message)

                    tool_result_json = {
                        "type": "tool_result",
                        "tool_call_id": tool_call.tool_call_id,
                        "tool_name": tool_call.tool_name,
                        "tool_output": result,
                    }
                    with open(f"{step_log_dir}/tool_result.json", "w") as f:
                        json.dump(tool_result_json, f, indent=4)
                    if isinstance(result, list):
                        for item in result:
                            if isinstance(item, dict) and item.get("type") == "image":
                                img_base64 = item.get("source").get("data")
                                if tool_call.tool_name == "browser_view":
                                    save_base64_image_png(img_base64, f"{step_log_dir}/browser_view.png")
                                elif tool_call.tool_name == "display_local_image":
                                    save_base64_image_png(img_base64, f"{step_log_dir}/display_local_image.png")

                    # Handle both ToolResult objects and tuples
                    if isinstance(result, tuple):
                        tool_result, _ = result
                    else:
                        tool_result = result

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
                    if self.complete_tool.should_stop:
                        # Add a fake model response, so the next turn is the user's
                        # turn in case they want to resume
                        self.history.add_assistant_turn(
                            [TextResult(text="Completed the task.")]
                        )
                        return ToolImplOutput(
                            tool_output=self.complete_tool.answer,
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
        log_dir: str | None = None,
    ) -> str:
        """Start a new agent run.

        Args:
            instruction: The instruction to the agent.
            resume: Whether to resume the agent from the previous state,
                continuing the dialog.

        Returns:
            A tuple of (result, message).
        """
        self.complete_tool.reset()
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
        return self.run(tool_input, self.history, log_dir)

    def clear(self):
        """Clear the dialog and reset interruption state.
        Note: This does NOT clear the file manager, preserving file context.
        """
        self.history.clear()
        self.interrupted = False
