import asyncio
import json
import logging
import time
from typing import Any, List, Optional, Tuple
from functools import partial
import uuid
from datetime import datetime

from fastapi import WebSocket
from ii_agent.agents.base import BaseAgent
from ii_agent.core.event import EventType, RealtimeEvent
from ii_agent.llm.base import LLMClient, TextResult, ToolCallParameters
from ii_agent.llm.context_manager.base import ContextManager
from ii_agent.llm.message_history import MessageHistory
from ii_agent.tools.base import ToolImplOutput, LLMTool
from ii_agent.tools import AgentToolManager
from ii_agent.utils.workspace_manager import WorkspaceManager
from ii_agent.db.manager import Events


class ReviewerAgent(BaseAgent):
    name = "reviewer_agent"
    description = """\
A comprehensive reviewer agent that evaluates and reviews the results/websites/slides created by general agent, 
then provides detailed feedback and improvement suggestions with special focus on functionality testing.

This agent conducts thorough reviews with emphasis on:
- Testing ALL interactive elements (buttons, forms, navigation, etc.)
- Verifying website functionality and user experience
- Providing detailed, natural language feedback without format restrictions
- Identifying specific issues and areas for improvement
"""
    input_schema = {
        "type": "object",
        "properties": {
            "task": {
                "type": "string",
                "description": "The task that the general agent is trying to solve"
            },
            "workspace_dir": {
                "type": "string",
                "description": "The workspace directory of the general agent execution to review"
            },
        },
        "required": ["task", "workspace_dir"]
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
        max_turns: int = 200,
        websocket: Optional[WebSocket] = None,
        session_id: Optional[uuid.UUID] = None,
        interactive_mode: bool = True,
    ):
        """Initialize the reviewer agent."""
        super().__init__()
        self.workspace_manager = workspace_manager
        self.system_prompt = system_prompt
        self.client = client
        self.tool_manager = AgentToolManager(
            tools=tools,
            logger_for_agent_logs=logger_for_agent_logs,
            interactive_mode=interactive_mode,
            reviewer_mode=True,
        )

        self.logger_for_agent_logs = logger_for_agent_logs
        self.max_output_tokens = max_output_tokens_per_turn
        self.max_turns = max_turns

        self.interrupted = False
        self.history = MessageHistory(context_manager)
        self.context_manager = context_manager
        self.session_id = session_id

        self.message_queue = message_queue
        self.websocket = websocket
        
        # Cache for tool parameters to avoid repeated validation
        self._cached_tool_params = None

    async def _process_messages(self):
        pass
    
    async def _generate_llm_response(
        self, 
        messages: List[Any], 
        tools: List[ToolCallParameters]
    ) -> Tuple[List[Any], Any]:
        """Centralized LLM response generation with timing metrics."""
        start_time = time.time()
        
        # Use asyncio.to_thread for cleaner async execution
        model_response, metadata = await asyncio.to_thread(
            self.client.generate,
            messages=messages,
            max_tokens=self.max_output_tokens,
            tools=tools,
            system_prompt=self.system_prompt,
        )
        
        elapsed = time.time() - start_time
        self.logger_for_agent_logs.debug(f"LLM generation took {elapsed:.2f}s")
        
        return model_response, metadata

    def _validate_tool_parameters(self):
        """Validate tool parameters and check for duplicates with caching."""
        if self._cached_tool_params is not None:
            return self._cached_tool_params
            
        tool_params = [tool.get_tool_param() for tool in self.tool_manager.get_tools()]
        tool_names = [param.name for param in tool_params]
        sorted_names = sorted(tool_names)
        for i in range(len(sorted_names) - 1):
            if sorted_names[i] == sorted_names[i + 1]:
                raise ValueError(f"Tool {sorted_names[i]} is duplicated")
        
        self._cached_tool_params = tool_params
        return tool_params

    def start_message_processing(self):
        """Start processing the message queue."""
        return asyncio.create_task(self._process_messages())

    async def run_impl(
        self,
        tool_input: dict[str, Any],
        message_history: Optional[MessageHistory] = None,
    ) -> ToolImplOutput:
        task = tool_input["task"]
        workspace_dir = tool_input["workspace_dir"]
        result = tool_input["result"]
        user_input_delimiter = "-" * 45 + " REVIEWER INPUT " + "-" * 45
        self.logger_for_agent_logs.info(f"\n{user_input_delimiter}\nReviewing agent logs and output...\n")

        # Construct the review instruction
        review_instruction = f"""You are a reviewer agent tasked with evaluating the work done by an general agent. 
You have access to all the same tools that the general agent has.

Here is the task that the general agent is trying to solve:
{task}

Here is the result of the general agent's execution:
{result}

Here is the workspace directory of the general agent's execution:
{workspace_dir}

Now your turn to review the general agent's work.
"""
        self.history.add_user_prompt(review_instruction)
        self.interrupted = False

        remaining_turns = self.max_turns
        while remaining_turns > 0:
            remaining_turns -= 1

            delimiter = "-" * 45 + " REVIEWER TURN " + "-" * 45
            self.logger_for_agent_logs.info(f"\n{delimiter}\n")

            # Get tool parameters for available tools
            all_tool_params = self._validate_tool_parameters()

            if self.interrupted:
                return ToolImplOutput(
                    tool_output="Reviewer interrupted",
                    tool_result_message="Reviewer interrupted by user"
                )

            current_messages = self.history.get_messages_for_llm()
            current_tok_count = self.context_manager.count_tokens(current_messages)
            self.logger_for_agent_logs.info(
                f"(Current token count: {current_tok_count})\n"
            )
            
            # Add early token limit warning
            max_context = getattr(self.context_manager, 'max_context_length', float('inf'))
            if max_context != float('inf') and current_tok_count > max_context * 0.9:
                self.logger_for_agent_logs.warning(
                    f"Approaching token limit: {current_tok_count}/{max_context}"
                )

            truncated_messages_for_llm = (
                self.context_manager.apply_truncation_if_needed(current_messages)
            )

            self.history.set_message_list(truncated_messages_for_llm)

            model_response, _ = await self._generate_llm_response(
                truncated_messages_for_llm, 
                all_tool_params
            )

            if len(model_response) == 0:
                model_response = [TextResult(text="No response from model")]

            # Add the raw response to the canonical history
            self.history.add_assistant_turn(model_response)

            # Handle tool calls
            pending_tool_calls = self.history.get_pending_tool_calls()

            if len(pending_tool_calls) > 1:
                raise ValueError("Only one tool call per turn is supported")

            if len(pending_tool_calls) == 1:
                tool_call = pending_tool_calls[0]

                text_results = [
                    item for item in model_response if isinstance(item, TextResult)
                ]
                if len(text_results) > 0:
                    text_result = text_results[0]
                    self.logger_for_agent_logs.info(
                        f"Reviewer planning next step: {text_result.text}\n",
                    )

                # Handle tool call by the reviewer
                if self.interrupted:
                    self.add_tool_call_result(tool_call, "Tool execution interrupted")
                    return ToolImplOutput(
                        tool_output="Reviewer interrupted",
                        tool_result_message="Reviewer interrupted during tool execution"
                    )
                
                tool_result = await self.tool_manager.run_tool(tool_call, self.history)
                self.add_tool_call_result(tool_call, tool_result)
                if tool_call.tool_name == "return_control_to_general_agent":
                    summarize_review = "Now based on your review, please rewrite detailed feedback to the general agent."
                    self.history.add_user_prompt(summarize_review)
                    current_messages = self.history.get_messages_for_llm()
                    truncated_messages_for_llm = (
                        self.context_manager.apply_truncation_if_needed(current_messages)
                    )
                    self.history.set_message_list(truncated_messages_for_llm)
                    
                    # Use centralized LLM generation
                    model_response, _ = await self._generate_llm_response(
                        truncated_messages_for_llm,
                        all_tool_params
                    )
                    
                    # Extract text output with proper validation
                    tool_output = None
                    for message in model_response:
                        if isinstance(message, TextResult):
                            tool_output = message.text
                            break
                    
                    if tool_output:
                        return ToolImplOutput(
                            tool_output=tool_output,
                            tool_result_message="Reviewer completed comprehensive review"
                        )
                    else:
                        self.logger_for_agent_logs.error("No text output in model response for review summary")
                        return ToolImplOutput(
                            tool_output="ERROR: Reviewer did not provide text feedback",
                            tool_result_message="Review incomplete - no text response"
                        )

        # If we exhausted all turns without completing review
        return ToolImplOutput(
            tool_output="ERROR: Reviewer did not complete review within maximum turns. The review process was interrupted or took too long to complete.",
            tool_result_message="Review incomplete - maximum turns reached"
        )

    def get_tool_start_message(self, tool_input: dict[str, Any]) -> str:
        return f"Reviewer started to analyze agent logs"

    def add_tool_call_result(self, tool_call: ToolCallParameters, tool_result: str):
        """Add a tool call result to the history and send it to the message queue."""
        self.history.add_tool_call_result(tool_call, tool_result)

    def cancel(self):
        """Cancel the reviewer execution."""
        self.interrupted = True
        self.logger_for_agent_logs.info("Reviewer cancellation requested")

    async def run_agent_async(
        self,
        task: str,
        result: str,
        workspace_dir: str,
        resume: bool = False,
    ) -> str:
        """Start a new reviewer run asynchronously.

        Args:
            task: The task that was executed.
            result: The result of the task execution.
            workspace_dir: The workspace directory to review.
            resume: Whether to resume the reviewer from the previous state,
                continuing the dialog.

        Returns:
            The review result string.
        """
        self.tool_manager.reset()
        if resume:
            assert self.history.is_next_turn_user()
        else:
            self.history.clear()
            self.interrupted = False

        tool_input = {
            "task": task,
            "workspace_dir": workspace_dir,
            "result": result,
        }
        return await self.run_async(tool_input, self.history)

    def run_agent(
        self,
        task: str,
        result: str,
        workspace_dir: str,
        resume: bool = False,
    ) -> str:
        """Start a new reviewer run synchronously.

        Args:
            task: The task that was executed.
            result: The result of the task execution.
            workspace_dir: The workspace directory to review.
            resume: Whether to resume the reviewer from the previous state,
                continuing the dialog.

        Returns:
            The review result string.
        """
        try:
            # Check if there's already an event loop running
            loop = asyncio.get_running_loop()
            # If we're here, there's a loop, so create a task
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(
                    asyncio.run,
                    self.run_agent_async(task, result, workspace_dir, resume)
                )
                return future.result()
        except RuntimeError:
            # No event loop running, safe to use asyncio.run
            return asyncio.run(
                self.run_agent_async(task, result, workspace_dir, resume)
            )

    def clear(self):
        """Clear the dialog and reset interruption state."""
        self.history.clear()
        self.interrupted = False
        self._cached_tool_params = None  # Clear cached tool parameters