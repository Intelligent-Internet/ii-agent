import asyncio
from copy import deepcopy
from typing import Any, Optional, Dict, List

from tools.bash_tool import create_bash_tool, create_docker_bash_tool
from utils.common import (
    DialogMessages,
    LLMTool,
    ToolImplOutput,
)
from utils.llm_client import LLMClient, TextResult
from utils.workspace_manager import WorkspaceManager
from utils.file_manager import FileManager
from tools.complete_tool import CompleteTool
from prompts.system_prompt import SYSTEM_PROMPT
from tools.str_replace_tool import StrReplaceEditorTool
from tools.sequential_thinking_tool import SequentialThinkingTool
from tools.tavily_web_search import TavilySearchTool
from tools.tavily_visit_webpage import TavilyVisitWebpageTool
from tools.planner_agent import PlannerAgent
from tools.writing_agent import WritingAgent
from tools.file_write_tool import FileWriteTool
from tools.browser_use import BrowserUse
from termcolor import colored
from rich.console import Console
import logging
from fastapi import WebSocket
from pydantic import BaseModel
from typing import Literal
from asyncer import syncify

class RealtimeEvent(BaseModel):
    type: Literal["make_response", "tool_call", "tool_result"]
    raw_message: dict[str, Any]

class Agent(LLMTool):
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
        console: Console,
        logger_for_agent_logs: logging.Logger,
        max_output_tokens_per_turn: int = 8192,
        max_turns: int = 10,
        use_prompt_budgeting: bool = True,
        ask_user_permission: bool = False,
        docker_container_id: Optional[str] = None,
        websocket: Optional[WebSocket] = None,
    ):
        """Initialize the agent.

        Args:
            client: The LLM client to use
            max_output_tokens_per_turn: Maximum tokens per turn
            max_turns: Maximum number of turns
            workspace_manager: Optional workspace manager for taking snapshots
        """
        super().__init__()
        self.client = client
        self.console = console
        self.logger_for_agent_logs = logger_for_agent_logs
        self.max_output_tokens = max_output_tokens_per_turn
        self.max_turns = max_turns
        self.workspace_manager = workspace_manager
        self.interrupted = False
        self.dialog = DialogMessages(
            logger_for_agent_logs=logger_for_agent_logs,
            use_prompt_budgeting=use_prompt_budgeting,
        )

        # Initialize file manager for persistent file tracking
        self.file_manager = FileManager(workspace_manager.root)

        # Create and store the complete tool
        self.complete_tool = CompleteTool()
        
        # Create writing agent
        self.writing_agent = WritingAgent(
            client=client,
            workspace_manager=workspace_manager,
            parent_agent=self,
            logger_for_agent_logs=logger_for_agent_logs,
            max_output_tokens=max_output_tokens_per_turn,
        )

        # Create planner agent
        self.planner_agent = PlannerAgent(
            client=client,
            workspace_manager=workspace_manager,
            parent_agent=self,
            logger_for_agent_logs=logger_for_agent_logs,
            max_output_tokens=max_output_tokens_per_turn,
        )

        if docker_container_id is not None:
            print(
                colored(
                    f"Enabling docker bash tool with container {docker_container_id}",
                    "blue",
                )
            )
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
        self.tools = [
            # self.planner_agent,
            self.writing_agent,
            bash_tool,
            StrReplaceEditorTool(workspace_manager=workspace_manager),
            SequentialThinkingTool(),
            TavilySearchTool(),
            TavilyVisitWebpageTool(),
            BrowserUse(message_queue=self.message_queue),
            self.complete_tool,
            FileWriteTool(),
        ]
        self.websocket = websocket


        
    async def _process_messages(self):
        while True:
            try:
                message = await self.message_queue.get()

                await self.websocket.send_json({
                    "type": message.type,
                    "content": message.content
                })

                self.message_queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger_for_agent_logs.error(f"Error processing WebSocket message: {str(e)}")

    async def start_message_processing(self):
        """Start processing the message queue."""
        # self.message_processing_task = anyio.create_task_group().start_soon(self._process_messages)
        self.message_processing_task = asyncio.create_task(self._process_messages())

    def run_impl(
        self,
        tool_input: dict[str, Any],
        dialog_messages: Optional[DialogMessages] = None,
    ) -> ToolImplOutput:
        instruction = tool_input["instruction"]

        user_input_delimiter = "-" * 45 + " USER INPUT " + "-" * 45 + "\n" + instruction
        self.logger_for_agent_logs.info(f"\n{user_input_delimiter}\n")

        # print("Agent starting with instruction:", instruction)

        # Add instruction to dialog before getting mode
        self.dialog.add_user_prompt(instruction)
        self.interrupted = False

        remaining_turns = self.max_turns
        while remaining_turns > 0:
            remaining_turns -= 1

            delimiter = "-" * 45 + " NEW TURN " + "-" * 45
            self.logger_for_agent_logs.info(f"\n{delimiter}\n")

            if self.dialog.use_prompt_budgeting:
                current_tok_count = self.dialog.count_tokens()
                self.logger_for_agent_logs.info(
                    f"(Current token count: {current_tok_count})\n"
                )

            # Get tool parameters for available tools
            tool_params = [tool.get_tool_param() for tool in self.tools]

            # Check for duplicate tool names
            tool_names = [param.name for param in tool_params]
            sorted_names = sorted(tool_names)
            for i in range(len(sorted_names) - 1):
                if sorted_names[i] == sorted_names[i + 1]:
                    raise ValueError(f"Tool {sorted_names[i]} is duplicated")

            try:
                model_response, metadata = self.client.generate(
                    messages=self.dialog.get_messages_for_llm_client(),
                    max_tokens=self.max_output_tokens,
                    tools=tool_params,
                    system_prompt=self._get_system_prompt(),
                )
                self.dialog.add_model_response(model_response)

                # Handle tool calls
                pending_tool_calls = self.dialog.get_pending_tool_calls()

                if len(pending_tool_calls) == 0:
                    # No tools were called, so assume the task is complete
                    self.logger_for_agent_logs.info("[no tools were called]")
                    return ToolImplOutput(
                        tool_output=self.dialog.get_last_model_text_response(),
                        tool_result_message="Task completed",
                    )

                if len(pending_tool_calls) > 1:
                    raise ValueError("Only one tool call per turn is supported")

                assert len(pending_tool_calls) == 1

                # ToolCallParameters(tool_call_id='toolu_vrtx_01YV2bk3haVVECPECN4AWCTz', tool_name='bash', tool_input={'command': 'ls -la /home/pvduy/phu/ii-agent/workspace'})
                tool_call = pending_tool_calls[0]

                self.message_queue.put_nowait(RealtimeEvent(
                    type="tool_call",
                    raw_message={
                        "tool_call_id": tool_call.tool_call_id,
                        "tool_name": tool_call.tool_name,
                        "tool_input": tool_call.tool_input,
                    }
                ))

                text_results = [
                    item for item in model_response if isinstance(item, TextResult)
                ]
                if len(text_results) > 0:
                    text_result = text_results[0]
                    self.logger_for_agent_logs.info(
                        f"Top-level agent planning next step: {text_result.text}\n",
                    )

                try:
                    tool = next(t for t in self.tools if t.name == tool_call.tool_name)
                except StopIteration as exc:
                    raise ValueError(
                        f"Tool with name {tool_call.tool_name} not found"
                    ) from exc

                try:
                    result = tool.run(tool_call.tool_input, deepcopy(self.dialog))

                    tool_input_str = "\n".join(
                        [f" - {k}: {v}" for k, v in tool_call.tool_input.items()]
                    )


                    log_message = f"Calling tool {tool_call.tool_name} with input:\n{tool_input_str}"
                    log_message += f"\nTool output: \n{result}\n\n"
                    self.logger_for_agent_logs.info(log_message)

                    # Handle both ToolResult objects and tuples
                    if isinstance(result, tuple):
                        tool_result, _ = result
                    else:
                        tool_result = result

                    self.dialog.add_tool_call_result(tool_call, tool_result)

                    self.message_queue.put_nowait(RealtimeEvent(
                        type="tool_result",
                        raw_message={
                            "tool_call_id": tool_call.tool_call_id,
                            # "tool_result": tool_result,
                            "tool_name": tool_call.tool_name,
                            "result": tool_result,
                        }
                    ))
                    if self.complete_tool.should_stop:
                        # Add a fake model response, so the next turn is the user's
                        # turn in case they want to resume
                        self.dialog.add_model_response(
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
                    self.dialog.add_tool_call_result(tool_call, interrupt_message)
                    self.dialog.add_model_response(
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
                self.dialog.add_model_response(
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
        self.complete_tool.reset()
        if resume:
            assert self.dialog.is_user_turn()
        else:
            self.dialog.clear()
            self.interrupted = False

        tool_input = {
            "instruction": instruction,
        }
        if orientation_instruction:
            tool_input["orientation_instruction"] = orientation_instruction
        return self.run(tool_input, self.dialog)

    def clear(self):
        """Clear the dialog and reset interruption state.
        Note: This does NOT clear the file manager, preserving file context.
        """
        self.dialog.clear()
        self.interrupted = False

    def write_content(self, file_path: str, instruction: str, content_id: Optional[str] = None) -> str:
        """Hand off to the writing agent to generate content and write to a file.
        
        The writing agent will use this agent's dialog history and context to create
        a comprehensive report based on the provided instructions.
        
        Args:
            file_path: The path where the content should be written.
            instruction: Instructions for generating the writeup.
            content_id: Optional identifier for the content, used for tracking.
            
        Returns:
            The generated content.
        """
        # Generate a content ID if none is provided
        if content_id is None:
            import uuid
            content_id = f"content_{uuid.uuid4().hex[:8]}"
        
        # Register the content with the file manager
        registered_path = self.file_manager.register_content(content_id, file_path)
        
        # Set as active content
        self.file_manager.set_active_content(content_id)
        
        # Use the registered path for the content
        result = self.writing_agent.write_content(registered_path, instruction)
        
        # Update the metadata
        metadata = {
            "last_instruction": instruction,
        }
        self.file_manager.update_content_metadata(metadata, content_id)
        
        return result
    
    def plan_task(self, instruction: str, plan_file_path: str, action: str = "create", plan_id: Optional[str] = None) -> Dict:
        """Hand off to the planner agent to create, update, or get a plan.
        
        The planner agent will use this agent's dialog history and context to create
        or manage a structured plan based on the provided instructions.
        
        Args:
            instruction: Instructions for the planning task.
            plan_file_path: Path where the plan should be stored.
            action: Action to perform: 'create', 'update', or 'get'.
            plan_id: Optional identifier for the plan, used for tracking.
            
        Returns:
            The plan as a dictionary.
        """
        # Generate a plan ID if none is provided
        if plan_id is None:
            import uuid
            plan_id = f"plan_{uuid.uuid4().hex[:8]}"
        
        # Register the plan with the file manager
        registered_path = self.file_manager.register_plan(plan_id, plan_file_path)
        
        # Set as active plan
        self.file_manager.set_active_plan(plan_id)
        
        # Use the registered path for the plan
        result = self.planner_agent.plan(instruction, registered_path, action)
        
        # If successful and this is a create/update, update the metadata
        if action in ["create", "update"] and isinstance(result, dict):
            metadata = {
                "last_action": action,
                "last_instruction": instruction,
            }
            self.file_manager.update_plan_metadata(metadata, plan_id)
        
        return result
    
    def get_active_plan_path(self) -> Optional[str]:
        """Get the path of the currently active plan.
        
        Returns:
            The path to the active plan file, or None if no active plan exists
        """
        return self.file_manager.get_plan_path()
    
    def get_active_content_path(self) -> Optional[str]:
        """Get the path of the currently active content.
        
        Returns:
            The path to the active content file, or None if no active content exists
        """
        return self.file_manager.get_content_path()
    
    def list_plans(self) -> List[Dict]:
        """List all registered plans.
        
        Returns:
            A list of plans with their IDs, paths, and metadata
        """
        return self.file_manager.list_plans()
    
    def list_content(self) -> List[Dict]:
        """List all registered content.
        
        Returns:
            A list of content items with their IDs, paths, and metadata
        """
        return self.file_manager.list_content()
