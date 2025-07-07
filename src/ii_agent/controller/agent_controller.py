from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Optional, List, Any
from functools import partial

from fastapi import WebSocket
from ii_agent.agents.base import BaseAgent
from ii_agent.core.event import EventType, RealtimeEvent
from ii_agent.tools.base import ToolImplOutput
from ii_agent.tools import AgentToolManager
from ii_agent.utils.workspace_manager import WorkspaceManager
from ii_agent.utils.constants import COMPLETE_MESSAGE
from ii_agent.db.manager import Events
from ii_agent.core.logger import logger

from .state import State, AgentState
from ..events.action import Action, MessageAction, CompleteAction
from ..events.action.mcp import MCPAction
from ..events.observation import Observation, SystemObservation
from ..events.event import EventSource


TOOL_RESULT_INTERRUPT_MESSAGE = "Tool execution interrupted by user."
AGENT_INTERRUPT_MESSAGE = "Agent interrupted by user."
TOOL_CALL_INTERRUPT_FAKE_MODEL_RSP = (
    "Tool execution interrupted by user. You can resume by providing a new instruction."
)
AGENT_INTERRUPT_FAKE_MODEL_RSP = (
    "Agent interrupted by user. You can resume by providing a new instruction."
)


class AgentController:
    """Controls the execution of agents using the State-Action-Observation pattern."""
    
    def __init__(
        self,
        agent: BaseAgent,
        tool_manager: AgentToolManager,
        workspace_manager: WorkspaceManager,
        message_queue: asyncio.Queue,
        max_turns: int = 200,
        websocket: Optional[WebSocket] = None,
        session_id: Optional[uuid.UUID] = None,
        interactive_mode: bool = True,
        initial_state: Optional[State] = None,
    ):
        """Initialize the agent controller.
        
        Args:
            agent: The agent to control
            tool_manager: Tool manager for executing actions
            workspace_manager: Workspace manager
            message_queue: Message queue for real-time communication
            max_turns: Maximum number of turns
            websocket: Optional WebSocket for real-time communication
            session_id: UUID of the session this controller belongs to
            interactive_mode: Whether to use interactive mode
            initial_state: Optional initial state to restore from previous session
        """
        self.agent = agent
        self.tool_manager = tool_manager
        self.workspace_manager = workspace_manager
        self.max_turns = max_turns
        self.message_queue = message_queue
        self.websocket = websocket
        self.session_id = session_id
        self.interactive_mode = interactive_mode
        
        self.interrupted = False
        # Use provided initial state or create a new one
        if initial_state is not None:
            self.state = initial_state
        else:
            self.state = State(session_id=str(session_id) if session_id else "")

    async def _process_messages(self):
        """Process messages from the queue."""
        try:
            while True:
                try:
                    message: RealtimeEvent = await self.message_queue.get()

                    # Save all events to database if we have a session
                    if self.session_id is not None:
                        Events.save_event(self.session_id, message)
                    else:
                        logger.info(
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
                            logger.warning(
                                f"Failed to send message to websocket: {str(e)}"
                            )
                            self.websocket = None

                    self.message_queue.task_done()
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(
                        f"Error processing WebSocket message: {str(e)}"
                    )
        except asyncio.CancelledError:
            logger.info("Message processor stopped")
        except Exception as e:
            logger.error(f"Error in message processor: {str(e)}")

    def start_message_processing(self):
        """Start processing the message queue."""
        return asyncio.create_task(self._process_messages())

    async def run_async(self, instruction: str, files: list[str] | None = None) -> ToolImplOutput:
        """Run the agent controller asynchronously.
        
        Args:
            instruction: The instruction to execute
            files: Optional list of files to attach
            
        Returns:
            ToolImplOutput: The result of the execution
        """
        user_input_delimiter = "-" * 45 + " USER INPUT " + "-" * 45 + "\n" + instruction
        logger.info(f"\n{user_input_delimiter}\n")

        # Add initial user message as action
        event = MessageAction(
            content=instruction,
            files=files or [],
            source=EventSource.USER
        )
        self.state.add_event(event)
        self.state.agent_state = AgentState.THINKING

        remaining_turns = self.max_turns
        while remaining_turns > 0:
            remaining_turns -= 1

            delimiter = "-" * 45 + " NEW TURN " + "-" * 45
            logger.info(f"\n{delimiter}\n")

            if self.interrupted:
                # Handle interruption
                system_obs = SystemObservation(
                    event_type="interruption",
                    content=AGENT_INTERRUPT_MESSAGE
                )
                self.state.add_event(system_obs)
                return ToolImplOutput(
                    tool_output=AGENT_INTERRUPT_MESSAGE,
                    tool_result_message=AGENT_INTERRUPT_MESSAGE,
                )

            # Agent step: State -> Action
            self.state.agent_state = AgentState.THINKING
            try:
                action = self.agent.step(self.state)
                self.state.add_event(action)
            except Exception as e:
                logger.error(f"Agent step failed: {e}")
                self.state.agent_state = AgentState.ERROR
                return ToolImplOutput(
                    tool_output=f"Agent error: {e}",
                    tool_result_message=f"Agent error: {e}"
                )

            # Handle different action types
            if isinstance(action, CompleteAction):
                self.state.agent_state = AgentState.COMPLETED
                self.message_queue.put_nowait(
                    RealtimeEvent(
                        type=EventType.AGENT_RESPONSE,
                        content={"text": action.final_answer or "Task completed"},
                    )
                )
                return ToolImplOutput(
                    tool_output=action.final_answer or "Task completed",
                    tool_result_message="Task completed",
                )

            elif isinstance(action, MessageAction):
                # Handle message action - mostly for communication
                self.message_queue.put_nowait(
                    RealtimeEvent(
                        type=EventType.AGENT_RESPONSE,
                        content={"text": action.content},
                    )
                )
                return ToolImplOutput(
                    tool_output=action.content,
                    tool_result_message=action.content,
                )

            elif isinstance(action, MCPAction):
                # Handle tool call action
                self.state.agent_state = AgentState.ACTING
                
                self.message_queue.put_nowait(
                    RealtimeEvent(
                        type=EventType.TOOL_CALL,
                        content={
                            "tool_call_id": getattr(action.tool_call_metadata, 'tool_call_id', '') if hasattr(action, 'tool_call_metadata') and action.tool_call_metadata else getattr(action, 'id', ''),
                            "tool_name": action.name,
                            "tool_input": action.arguments,
                        },
                    )
                )

                if self.interrupted:
                    # Handle interruption during tool execution
                    tool_obs = SystemObservation(
                        content=TOOL_RESULT_INTERRUPT_MESSAGE,
                        event_type="tool_interrupted",
                        cause=action.id
                    )
                    # Transfer tool_call_metadata from action to observation (following OpenHands pattern)
                    if hasattr(action, 'tool_call_metadata') and action.tool_call_metadata:
                        tool_obs.tool_call_metadata = action.tool_call_metadata
                    self.state.add_event(tool_obs)
                    return ToolImplOutput(
                        tool_output=TOOL_RESULT_INTERRUPT_MESSAGE,
                        tool_result_message=TOOL_RESULT_INTERRUPT_MESSAGE,
                    )
                # Execute tool via tool manager: Action -> Observation
                try:
                    observation = await self.tool_manager.handle_action(action)
                    self.state.add_event(observation)
                    
                    # Send tool result to message queue for real-time updates
                    self.message_queue.put_nowait(
                        RealtimeEvent(
                            type=EventType.TOOL_RESULT,
                            content={
                                "tool_call_id": getattr(action.tool_call_metadata, 'tool_call_id', '') if hasattr(action, 'tool_call_metadata') and action.tool_call_metadata else getattr(action, 'id', ''),
                                "tool_name": action.name,
                                "result": observation.content,
                                "observation_id": observation.id,
                            },
                        )
                    )
                    
                        
                except Exception as e:
                    logger.error(f"Tool execution failed: {e}")
                    error_obs = SystemObservation(
                        content=f"Tool execution error: {e}",
                        event_type="tool_error",
                        cause=action.id
                    )
                    self.state.add_event(error_obs)
                    
                    # Send tool error to message queue for real-time updates
                    self.message_queue.put_nowait(
                        RealtimeEvent(
                            type=EventType.ERROR,
                            content={
                                "tool_call_id": getattr(action.tool_call_metadata, 'tool_call_id', '') if hasattr(action, 'tool_call_metadata') and action.tool_call_metadata else getattr(action, 'id', ''),
                                "tool_name": action.name,
                                "error": str(e),
                                "observation_id": error_obs.id,
                            },
                        )
                    )

        # Max turns exceeded
        agent_answer = "Agent did not complete after max turns"
        self.state.agent_state = AgentState.ERROR
        self.message_queue.put_nowait(
            RealtimeEvent(type=EventType.AGENT_RESPONSE, content={"text": agent_answer})
        )
        return ToolImplOutput(
            tool_output=agent_answer, tool_result_message=agent_answer
        )

    def cancel(self):
        """Cancel the agent execution."""
        self.interrupted = True
        logger.info("Agent cancellation requested")

    def handle_edit_query(self):
        """Handle edit query by canceling execution and clearing history from last user message."""
        # Cancel the agent execution
        self.cancel()
        # Clear history from last user message
        self.agent.history.clear_from_last_to_user_message()
        logger.info("Agent edit query handled: cancelled and cleared history")

    def clear(self):
        """Clear the state and reset interruption state."""
        self.state.clear()
        self.interrupted = False

    def get_tool_start_message(self, instruction: str) -> str:
        return f"Agent started with instruction: {instruction}"