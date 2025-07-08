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
from ii_agent.events.event import EventType, Event
from ii_agent.llm.base import LLMClient, TextResult, ToolCallParameters
from ii_agent.llm.context_manager.base import ContextManager
from ii_agent.tools.base import ToolImplOutput, LLMTool
from ii_agent.tools import AgentToolManager
from ii_agent.utils.workspace_manager import WorkspaceManager
from ii_agent.db.manager import Events
from ii_agent.controller.state import State, AgentState
from ii_agent.events.action import Action, MessageAction, CompleteAction
from ii_agent.events.action.mcp import MCPAction
from ii_agent.events.event import EventSource
from ii_agent.core.logger import logger


class ReviewerAgent(BaseAgent):
    """Thin ReviewerAgent that only converts state to review actions.
    
    This agent focuses purely on decision-making for review tasks,
    converting review state to appropriate actions. The actual tool
    execution is handled by ReviewerController.
    """
    name = "reviewer_agent"
    description = """\
A thin reviewer agent that converts review state to appropriate actions.
Focuses on analyzing agent work and determining next review steps.
"""

    def __init__(
        self,
        system_prompt: str,
        client: LLMClient,
        workspace_manager: WorkspaceManager,
        message_queue: asyncio.Queue,
        context_manager: ContextManager,
        max_output_tokens_per_turn: int = 8192,
        max_turns: int = 200,
        websocket: Optional[WebSocket] = None,
        session_id: Optional[uuid.UUID] = None,
    ):
        """Initialize the thin reviewer agent (state->action conversion only)."""
        super().__init__()
        self.workspace_manager = workspace_manager
        self.system_prompt = system_prompt
        self.client = client
        self.max_output_tokens = max_output_tokens_per_turn
        self.max_turns = max_turns
        self.history = []  # Simple list to store conversation history
        self.context_manager = context_manager
        self.session_id = session_id
        self.message_queue = message_queue
        self.websocket = websocket

    async def _process_messages(self):
        """Process messages from queue (no-op for thin agent)."""
        pass
    
    async def step(self, state: State) -> Action:
        """Convert current review state to the next action to take.
        
        This is the core method for the thin agent - it analyzes the
        review state and determines what action should be taken next.
        
        Args:
            state: Current state containing review history and context
            
        Returns:
            Action: The next action to take in the review process
        """
        # Get current messages for LLM context (simplified for reviewer)
        current_messages = self.history
        
        # Apply truncation if needed for context limits
        truncated_messages = self.context_manager.apply_truncation_if_needed(current_messages)
        
        try:
            # Generate LLM response to determine next action
            model_response, metadata = await asyncio.to_thread(
                self.client.generate,
                messages=truncated_messages,
                max_tokens=self.max_output_tokens,
                tools=[],  # Thin agent doesn't define tools
                system_prompt=self.system_prompt,
            )
            
            if not model_response:
                return MessageAction(content="No response from model")
            
            # Parse the model response into appropriate action
            return self._parse_response_to_action(model_response)
            
        except Exception as e:
            logger.error(f"Error in reviewer step: {e}")
            return MessageAction(content=f"Error determining next action: {e}")
    
    def _parse_response_to_action(self, model_response: List[Any]) -> Action:
        """Parse LLM response into appropriate Action object.
        
        Args:
            model_response: Raw response from LLM
            
        Returns:
            Action: Parsed action to execute
        """
        # Extract text and tool calls from response
        text_content = ""
        tool_calls = []
        
        for item in model_response:
            if isinstance(item, TextResult):
                text_content += item.text
            elif hasattr(item, 'tool_name'):  # Tool call
                tool_calls.append(item)
        
        # If we have tool calls, create MCPAction
        if tool_calls:
            tool_call = tool_calls[0]  # Take first tool call
            action = MCPAction(
                name=tool_call.tool_name,
                arguments=tool_call.tool_input,
                source=EventSource.AGENT
            )
            return action
        
        # Check if this looks like a completion
        if any(word in text_content.lower() for word in ['complete', 'finished', 'done', 'return control']):
            action = CompleteAction(final_answer=text_content)
            action.source = EventSource.AGENT
            return action
        
        # Default to message action
        action = MessageAction(content=text_content)
        action.source = EventSource.AGENT
        return action
    
    def start_message_processing(self):
        """Start processing the message queue."""
        return asyncio.create_task(self._process_messages())

    def cancel(self):
        """Cancel the reviewer execution."""
        logger.info("Reviewer cancellation requested")

    def clear(self):
        """Clear the dialog history."""
        self.history.clear()


class ReviewerController:
    """Controller for managing reviewer execution using the thin ReviewerAgent.
    
    This controller orchestrates the review process by:
    1. Taking review requests 
    2. Using ReviewerAgent to convert state to actions
    3. Executing actions via tool manager
    4. Managing the overall review workflow
    """
    
    def __init__(
        self,
        reviewer_agent: ReviewerAgent,
        tool_manager: AgentToolManager,
        workspace_manager: WorkspaceManager,
        message_queue: asyncio.Queue,
        max_turns: int = 200,
        websocket: Optional[WebSocket] = None,
        session_id: Optional[uuid.UUID] = None,
    ):
        """Initialize the reviewer controller."""
        self.reviewer_agent = reviewer_agent
        self.tool_manager = tool_manager
        self.workspace_manager = workspace_manager
        self.message_queue = message_queue
        self.max_turns = max_turns
        self.websocket = websocket
        self.session_id = session_id
        self.interrupted = False

    async def run_review_async(
        self,
        task: str,
        result: str,
        workspace_dir: str,
        resume: bool = False,
    ) -> str:
        """Run a comprehensive review asynchronously.
        
        Args:
            task: The task that was executed
            result: The result of the task execution  
            workspace_dir: The workspace directory to review
            resume: Whether to resume from previous state
            
        Returns:
            Review feedback string
        """
        # Reset state for new review
        if not resume:
            self.reviewer_agent.clear()
            self.interrupted = False

        # Set up initial review context
        review_instruction = f"""You are a reviewer agent tasked with evaluating the work done by a general agent. 
You have access to all the same tools that the general agent has.

Here is the task that the general agent was trying to solve:
{task}

Here is the result of the general agent's execution:
{result}

Here is the workspace directory of the general agent's execution:
{workspace_dir}

Please conduct a thorough review of the general agent's work and provide detailed feedback.
"""
        
        # Add user prompt to simple history (simplified for reviewer)
        self.reviewer_agent.history.append({"role": "user", "content": review_instruction})
        
        # Create state for the review process
        state = State(
            session_id=str(self.session_id) if self.session_id else "",
            agent_state=AgentState.RUNNING,
            history=[],  # Will be populated as we go
            outputs={"task": task, "result": result, "workspace_dir": workspace_dir}
        )

        # Main review loop
        remaining_turns = self.max_turns
        while remaining_turns > 0 and not self.interrupted:
            remaining_turns -= 1
            
            delimiter = "-" * 45 + " REVIEWER TURN " + "-" * 45
            logger.info(f"\n{delimiter}\n")

            try:
                # Get next action from thin reviewer agent
                action = await self.reviewer_agent.step(state)
                
                # Handle different action types
                if isinstance(action, CompleteAction):
                    # Review is complete
                    logger.info("Review completed")
                    return action.final_answer
                
                elif isinstance(action, MCPAction):
                    # Execute tool call
                    tool_result = await self._execute_tool_action(action)
                    
                    # Check for special completion tool
                    if action.name == "return_control_to_general_agent":
                        # Request final summary
                        summary_instruction = "Based on your review, please provide detailed feedback to the general agent."
                        self.reviewer_agent.history.append({"role": "user", "content": summary_instruction})
                        
                        # Get final summary action
                        final_action = await self.reviewer_agent.step(state)
                        if isinstance(final_action, (MessageAction, CompleteAction)):
                            return getattr(final_action, 'content', '') or getattr(final_action, 'final_answer', '')
                
                elif isinstance(action, MessageAction):
                    # Log the reviewer's thoughts
                    logger.info(f"Reviewer analysis: {action.content}")
                    
            except Exception as e:
                logger.error(f"Error in review turn: {e}")
                return f"Review failed due to error: {e}"

        # Review did not complete within turn limit
        return "ERROR: Review did not complete within maximum turns. The review process took too long to complete."

    async def _execute_tool_action(self, action: MCPAction) -> str:
        """Execute a tool call action and add result to history."""
        try:
            # Create tool call object for execution
            tool_call = ToolCallParameters(
                tool_name=action.name,
                tool_input=action.arguments,
                tool_call_id=action.id
            )
            
            # Execute the tool
            tool_result = await self.tool_manager.run_tool(tool_call)
            
            # Add result to simple history
            self.reviewer_agent.history.append({"role": "assistant", "content": tool_result})
            
            return tool_result
            
        except Exception as e:
            error_msg = f"Tool execution failed: {e}"
            logger.error(error_msg)
            return error_msg

    def run_agent(
        self,
        task: str,
        result: str,
        workspace_dir: str,
        resume: bool = False,
    ) -> str:
        """Run review synchronously (for compatibility)."""
        try:
            # Check if there's already an event loop running
            loop = asyncio.get_running_loop()
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(
                    asyncio.run,
                    self.run_review_async(task, result, workspace_dir, resume)
                )
                return future.result()
        except RuntimeError:
            # No event loop running, safe to use asyncio.run
            return asyncio.run(
                self.run_review_async(task, result, workspace_dir, resume)
            )

    def start_message_processing(self):
        """Start processing the message queue."""
        return self.reviewer_agent.start_message_processing()

    def cancel(self):
        """Cancel the review execution."""
        self.interrupted = True
        self.reviewer_agent.cancel()
        logger.info("Review cancellation requested")

    @property
    def agent(self):
        """Access to underlying agent for compatibility."""
        return self.reviewer_agent

    @property
    def websocket(self):
        """Access to websocket for compatibility."""
        return self.reviewer_agent.websocket
        
    @websocket.setter  
    def websocket(self, value):
        """Set websocket for compatibility."""
        self.reviewer_agent.websocket = value