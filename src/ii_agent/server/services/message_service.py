"""Message service for processing WebSocket messages."""

import asyncio
import logging
from typing import Dict, Any, TYPE_CHECKING

from pydantic import ValidationError

from ii_agent.core.config.ii_agent_config import IIAgentConfig
from ii_agent.core.event import EventType, RealtimeEvent
from ii_agent.core.storage.models.settings import Settings
from ii_agent.core.storage.settings.file_settings_store import FileSettingsStore
from ii_agent.db.manager import Sessions, Events
from ii_agent.llm import get_client
from ii_agent.llm.base import ToolCall
from ii_agent.server.models.messages import (
    InitAgentContent,
    QueryContent,
    EditQueryContent,
    EnhancePromptContent,
    ReviewResultContent,
)
from ii_agent.server.services.agent_service import AgentService
from ii_agent.utils.prompt_generator import enhance_user_prompt

if TYPE_CHECKING:
    from ii_agent.server.websocket.chat_session import ChatSession

logger = logging.getLogger(__name__)


class MessageService:
    """Service for processing different types of WebSocket messages."""

    def __init__(
        self,
        agent_service: AgentService,
        config: IIAgentConfig,
    ):
        self.agent_service = agent_service
        self.config = config

    async def process_message(
        self,
        message_type: str,
        content: Dict[str, Any],
        session: "ChatSession",
    ) -> None:
        """Process a WebSocket message and route to appropriate handler.
        
        Args:
            message_type: Type of message to process
            content: Message content dictionary
            session: Chat session instance
        """
        handlers = {
            "init_agent": self._handle_init_agent,
            "query": self._handle_query,
            "workspace_info": self._handle_workspace_info,
            "ping": self._handle_ping,
            "cancel": self._handle_cancel,
            "edit_query": self._handle_edit_query,
            "enhance_prompt": self._handle_enhance_prompt,
            "review_result": self._handle_review_result,
        }

        handler = handlers.get(message_type)
        if handler:
            await handler(content, session)
        else:
            await session.send_event(
                RealtimeEvent(
                    type=EventType.ERROR,
                    content={"message": f"Unknown message type: {message_type}"},
                )
            )

    async def _handle_init_agent(self, content: dict, session: "ChatSession") -> None:
        """Handle agent initialization."""
        try:
            init_content = InitAgentContent(**content)

            # Create main agent
            agent, controller = await self.agent_service.create_agent(
                model_name=init_content.model_name,
                session_id=session.session_uuid,
                workspace_manager=session.workspace_manager,
                websocket=session.websocket,
                tool_args=init_content.tool_args,
            )

            # Set thinking tokens if provided
            if init_content.thinking_tokens:
                # Update the LLM config with thinking tokens
                user_id = None
                settings_store = await FileSettingsStore.get_instance(self.config, user_id)
                settings = await settings_store.load()
                llm_config = settings.llm_configs.get(init_content.model_name)
                if llm_config:
                    llm_config.thinking_tokens = init_content.thinking_tokens

            # Store agent and controller in session
            session.agent = agent
            session.agent_controller = controller

            # Check if reviewer is enabled
            session.enable_reviewer = init_content.tool_args.get("enable_reviewer", False)
            if session.enable_reviewer:
                # Create reviewer agent
                reviewer_agent, reviewer_controller = await self.agent_service.create_reviewer_agent(
                    model_name=init_content.model_name,
                    session_id=session.session_uuid,
                    workspace_manager=session.workspace_manager,
                    websocket=session.websocket,
                    tool_args=init_content.tool_args,
                )
                
                session.reviewer_agent = reviewer_agent
                session.reviewer_controller = reviewer_controller

            await session.send_event(
                RealtimeEvent(
                    type=EventType.AGENT_INITIALIZED,
                    content={
                        "message": "Agent initialized"
                        + (" with reviewer" if session.enable_reviewer else "")
                    },
                )
            )

        except ValidationError as e:
            await session.send_event(
                RealtimeEvent(
                    type=EventType.ERROR,
                    content={"message": f"Invalid init_agent content: {str(e)}"},
                )
            )
        except Exception as e:
            logger.error(f"Error initializing agent: {str(e)}")
            await session.send_event(
                RealtimeEvent(
                    type=EventType.ERROR,
                    content={"message": f"Error initializing agent: {str(e)}"},
                )
            )

    async def _handle_query(self, content: dict, session: "ChatSession") -> None:
        """Handle query processing."""
        try:
            query_content = QueryContent(**content)

            # Set session name from first message
            if session.first_message and query_content.text.strip():
                session_name = query_content.text.strip()[:100]
                Sessions.update_session_name(session.session_uuid, session_name)
                session.first_message = False

            # Check if there's an active task
            if session.has_active_task():
                await session.send_event(
                    RealtimeEvent(
                        type=EventType.ERROR,
                        content={"message": "A query is already being processed"},
                    )
                )
                return

            # Send processing acknowledgment
            await session.send_event(
                RealtimeEvent(
                    type=EventType.PROCESSING,
                    content={"message": "Processing your request..."},
                )
            )

            # Run the agent with the query
            session.active_task = asyncio.create_task(
                self._run_agent_async(query_content, session)
            )

        except ValidationError as e:
            await session.send_event(
                RealtimeEvent(
                    type=EventType.ERROR,
                    content={"message": f"Invalid query content: {str(e)}"},
                )
            )

    async def _handle_workspace_info(self, content: dict, session: "ChatSession") -> None:
        """Handle workspace info request."""
        await session.send_event(
            RealtimeEvent(
                type=EventType.WORKSPACE_INFO,
                content={"path": str(session.workspace_manager.root)},
            )
        )

    async def _handle_ping(self, content: dict, session: "ChatSession") -> None:
        """Handle ping message."""
        await session.send_event(RealtimeEvent(type=EventType.PONG, content={}))

    async def _handle_cancel(self, content: dict, session: "ChatSession") -> None:
        """Handle query cancellation."""
        if not session.agent_controller:
            await session.send_event(
                RealtimeEvent(
                    type=EventType.ERROR,
                    content={"message": "No active agent for this session"},
                )
            )
            return

        session.agent_controller.cancel()

        await session.send_event(
            RealtimeEvent(
                type=EventType.SYSTEM,
                content={"message": "Query cancelled"},
            )
        )

    async def _handle_edit_query(self, content: dict, session: "ChatSession") -> None:
        """Handle query editing."""
        try:
            edit_content = EditQueryContent(**content)

            if not session.agent_controller:
                await session.send_event(
                    RealtimeEvent(
                        type=EventType.ERROR,
                        content={"message": "No active agent for this session"},
                    )
                )
                return

            # Cancel current execution and clear history
            session.agent_controller.cancel()
            session.agent_controller.state.clear_from_last_to_user_message()

            # Delete events from database
            if hasattr(session.agent_controller, "session_id"):
                try:
                    Events.delete_events_from_last_to_user_message(
                        session.agent_controller.session_id
                    )
                    await session.send_event(
                        RealtimeEvent(
                            type=EventType.SYSTEM,
                            content={
                                "message": "Session history cleared from last event to last user message"
                            },
                        )
                    )
                except Exception as e:
                    logger.error(f"Error deleting session events: {str(e)}")

            # Check if there's an active task
            if session.has_active_task():
                await session.send_event(
                    RealtimeEvent(
                        type=EventType.ERROR,
                        content={"message": "A query is already being processed"},
                    )
                )
                return

            # Send processing acknowledgment
            await session.send_event(
                RealtimeEvent(
                    type=EventType.PROCESSING,
                    content={"message": "Processing your request..."},
                )
            )

            # Run the agent with the edited query
            session.active_task = asyncio.create_task(
                self._run_agent_async(edit_content, session)
            )

        except ValidationError as e:
            await session.send_event(
                RealtimeEvent(
                    type=EventType.ERROR,
                    content={"message": f"Invalid edit_query content: {str(e)}"},
                )
            )

    async def _handle_enhance_prompt(self, content: dict, session: "ChatSession") -> None:
        """Handle prompt enhancement request."""
        try:
            enhance_content = EnhancePromptContent(**content)
            
            # Create LLM client
            user_id = None
            settings_store = await FileSettingsStore.get_instance(self.config, user_id)
            settings = await settings_store.load()

            llm_config = settings.llm_configs.get(enhance_content.model_name)
            if not llm_config:
                raise ValueError(f"LLM config not found for model: {enhance_content.model_name}")
            
            client = get_client(llm_config)

            # Enhance the prompt
            success, message, enhanced_prompt = await enhance_user_prompt(
                client=client,
                user_input=enhance_content.text,
                files=enhance_content.files,
            )

            if success and enhanced_prompt:
                await session.send_event(
                    RealtimeEvent(
                        type=EventType.PROMPT_GENERATED,
                        content={
                            "result": enhanced_prompt,
                            "original_request": enhance_content.text,
                        },
                    )
                )
            else:
                await session.send_event(
                    RealtimeEvent(
                        type=EventType.ERROR,
                        content={"message": message},
                    )
                )

        except ValidationError as e:
            await session.send_event(
                RealtimeEvent(
                    type=EventType.ERROR,
                    content={"message": f"Invalid enhance_prompt content: {str(e)}"},
                )
            )

    async def _handle_review_result(self, content: dict, session: "ChatSession") -> None:
        """Handle reviewer's feedback."""
        try:
            if not session.agent_controller:
                await session.send_event(
                    RealtimeEvent(
                        type=EventType.ERROR,
                        content={"message": "No active agent for this session"},
                    )
                )
                return

            review_content = ReviewResultContent(**content)
            user_input = review_content.user_input

            if not user_input:
                await session.send_event(
                    RealtimeEvent(
                        type=EventType.ERROR,
                        content={"message": "No user query found to review"},
                    )
                )
                return

            await self._run_reviewer_async(user_input, session)

        except Exception as e:
            logger.error(f"Error handling review request: {str(e)}")
            await session.send_event(
                RealtimeEvent(
                    type=EventType.ERROR,
                    content={"message": f"Error handling review request: {str(e)}"},
                )
            )

    async def _run_agent_async(self, query_content, session: "ChatSession") -> None:
        """Run the agent asynchronously."""
        if not session.agent_controller:
            await session.send_event(
                RealtimeEvent(
                    type=EventType.ERROR,
                    content={"message": "Agent not initialized for this session"},
                )
            )
            return

        try:
            # Add user message and run agent
            await session.agent_controller.run_agent_async(
                instruction=query_content.text,
                files=getattr(query_content, "files", []),
                resume=getattr(query_content, "resume", False),
            )

        except Exception as e:
            logger.error(f"Error running agent: {str(e)}")
            await session.send_event(
                RealtimeEvent(
                    type=EventType.ERROR,
                    content={"message": f"Error running agent: {str(e)}"},
                )
            )
        finally:
            # Clean up task reference
            session.active_task = None

    async def _run_reviewer_async(self, user_input: str, session: "ChatSession") -> None:
        """Run the reviewer agent to analyze the main agent's output."""
        if not session.reviewer_controller:
            await session.send_event(
                RealtimeEvent(
                    type=EventType.ERROR,
                    content={"message": "Reviewer not initialized for this session"},
                )
            )
            return

        try:
            # Extract final result from main agent's history
            final_result = ""
            found = False
            
            for message in session.agent_controller.state._message_lists[::-1]:
                for sub_message in message:
                    if (
                        hasattr(sub_message, "tool_name")
                        and sub_message.tool_name == "message_user"
                        and isinstance(sub_message, ToolCall)
                    ):
                        found = True
                        final_result = sub_message.tool_input["text"]
                        break
                if found:
                    break
            
            if not found:
                logger.warning("No final result found from agent to review")
                return

            # Send notification that reviewer is starting
            await session.send_event(
                RealtimeEvent(
                    type=EventType.SYSTEM,
                    content={
                        "type": "reviewer_agent",
                        "message": "Reviewer agent is analyzing the output...",
                    },
                )
            )

            # Create review instruction with the template format
            review_instruction = f"""You are a reviewer agent tasked with evaluating the work done by a general agent. 
You have access to all the same tools that the general agent has.

Here is the task that the general agent is trying to solve:
{user_input}

Here is the result of the general agent's execution:
{final_result}

Here is the workspace directory of the general agent's execution:
{str(session.workspace_manager.root)}

Now your turn to review the general agent's work.
"""

            # Run reviewer agent
            reviewer_feedback = await session.reviewer_controller.run_agent_async(
                instruction=review_instruction,
                files=[],
                resume=False,
            )

            if reviewer_feedback and reviewer_feedback.strip():
                # Send feedback to main agent for improvement
                await session.send_event(
                    RealtimeEvent(
                        type=EventType.SYSTEM,
                        content={
                            "type": "reviewer_agent",
                            "message": "Applying reviewer feedback...",
                        },
                    )
                )

                feedback_prompt = f"""Based on the reviewer's analysis, here is the feedback for improvement:

{reviewer_feedback}

Please review this feedback and implement the suggested improvements to better complete the original task: "{user_input}"
"""

                # Run main agent with reviewer feedback
                await session.agent_controller.run_agent_async(
                    instruction=feedback_prompt,
                    files=[],
                    resume=True,
                )

        except Exception as e:
            logger.error(f"Error running reviewer: {str(e)}")
            await session.send_event(
                RealtimeEvent(
                    type=EventType.ERROR,
                    content={"message": f"Error running reviewer: {str(e)}"},
                )
            )