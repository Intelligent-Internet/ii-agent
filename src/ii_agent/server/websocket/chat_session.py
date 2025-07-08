import asyncio
import json
import logging
import uuid
from typing import Optional, Dict, Any
from fastapi import WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from ii_agent.llm.base import ToolCall
from ii_agent.agents.base import BaseAgent
from ii_agent.agents.reviewer import ReviewerAgent, ReviewerController
from ii_agent.events.event import Event, EventType
from ii_agent.events.observation.error import ErrorObservation
from ii_agent.core.storage.files import FileStore
from ii_agent.core.storage.models.settings import Settings
from ii_agent.core.storage.settings.file_settings_store import FileSettingsStore
from ii_agent.db.manager import Sessions, Events
from ii_agent.llm import get_client
from ii_agent.utils.prompt_generator import enhance_user_prompt
from ii_agent.utils.workspace_manager import WorkspaceManager
from ii_agent.server.models.messages import (
    WebSocketMessage,
    QueryContent,
    InitAgentContent,
    EnhancePromptContent,
    EditQueryContent,
    ReviewResultContent,
)
from ii_agent.core.config.ii_agent_config import IIAgentConfig
from ii_agent.core.config.agent_config import AgentConfig
from ii_agent.llm.base import LLMClient
from ii_agent.llm.message_history import MessageHistory
from ii_agent.agents.function_call import FunctionCallAgent
from ii_agent.controller.agent_controller import AgentController
from ii_agent.controller.state import State
from ii_agent.llm.context_manager.llm_summarizing import LLMSummarizingContextManager
from ii_agent.llm.token_counter import TokenCounter
from ii_agent.tools import get_system_tools
from ii_agent.prompts.system_prompt import (
    SYSTEM_PROMPT,
    SYSTEM_PROMPT_WITH_SEQ_THINKING,
)
from ii_agent.prompts.reviewer_system_prompt import REVIEWER_SYSTEM_PROMPT
from ii_agent.core.logger import logger
from ii_agent.tools.tool_manager import AgentToolManager


class ChatSession:
    """Manages a single standalone chat session with its own agent, workspace, and message handling."""

    def __init__(
        self,
        websocket: WebSocket,
        workspace_manager: WorkspaceManager,
        session_uuid: uuid.UUID,
        file_store: FileStore,
        config: IIAgentConfig,
    ):
        self.websocket = websocket
        self.workspace_manager = workspace_manager
        self.session_uuid = session_uuid
        self.file_store = file_store
        # Session state
        self.controller: Optional[AgentController] = None
        self.reviewer_agent: Optional[ReviewerAgent] = None
        self.active_task: Optional[asyncio.Task] = None
        self.message_processor: Optional[asyncio.Task] = None
        self.reviewer_message_processor: Optional[asyncio.Task] = None
        self.first_message = True
        self.enable_reviewer = False
        self.config = config

    async def send_event(self, event: Event):
        """Send an event to the client via WebSocket."""
        if self.websocket:
            try:
                await self.websocket.send_json(event.model_dump())
            except Exception as e:
                logger.error(f"Error sending event to client: {e}")

    async def start_chat_loop(self):
        """Start the chat loop for this session."""
        await self.handshake()
        try:
            while True:
                message_text = await self.websocket.receive_text()
                message_data = json.loads(message_text)
                await self.handle_message(message_data)
        except json.JSONDecodeError:
            await self.send_event(
                ErrorObservation(
                    content="Invalid JSON format",
                    cause=None,
                )
            )
        except WebSocketDisconnect:
            logger.info("Client disconnected")
            if self.controller:
                self.controller.cancel()  # NOTE: Now we cancel the controller on disconnect, the background implementation will come later

            # Wait for active task to complete before cleanup
            if self.active_task and not self.active_task.done():
                try:
                    await self.active_task
                except asyncio.CancelledError:
                    logger.info("Active task was cancelled")
                except Exception as e:
                    logger.error(f"Error waiting for active task completion: {e}")

            self.cleanup()

    async def handshake(self):
        """Handle handshake message."""
        await self.websocket.send_json(
            {
                "type": "connection_established",
                "content": {
                    "message": "Connected to Agent WebSocket Server",
                    "workspace_path": str(self.workspace_manager.root),
                },
            }
        )

    async def handle_message(self, message_data: dict):
        """Handle incoming WebSocket messages for this session."""
        try:
            # Validate message structure
            ws_message = WebSocketMessage(**message_data)
            msg_type = ws_message.type
            content = ws_message.content

            # Route to appropriate handler
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

            handler = handlers.get(msg_type)
            if handler:
                await handler(content)
            else:
                await self.send_event(
                    ErrorObservation(
                        content=f"Unknown message type: {msg_type}",
                        cause=None,
                    )
                )

        except ValidationError as e:
            await self.send_event(
                ErrorObservation(
                    content=f"Invalid message format: {str(e)}",
                    cause=None,
                )
            )
        except Exception as e:
            logger.error(f"Error handling message: {str(e)}")
            await self.send_event(
                ErrorObservation(
                    content=f"Error processing request: {str(e)}",
                    cause=None,
                )
            )

    async def _handle_init_agent(self, content: dict):
        """Handle agent initialization."""
        try:
            init_content = InitAgentContent(**content)

            # Create LLM client using factory
            user_id = None  # TODO: Support user id
            settings_store = await FileSettingsStore.get_instance(self.config, user_id)
            settings = await settings_store.load()
            llm_config = settings.llm_configs.get(init_content.model_name)
            if not llm_config:
                raise ValueError(
                    f"LLM config not found for model: {init_content.model_name}"
                )

            llm_config.thinking_tokens = init_content.thinking_tokens
            client = get_client(llm_config)

            # Create agent using internal methods
            self.controller = self._create_agent(
                client,
                self.session_uuid,
                self.workspace_manager,
                self.websocket,
                init_content.tool_args,
                self.file_store,
                settings=settings,
            )

            # Start message processor for this session
            self.message_processor = self.controller.start_message_processing()

            # Check if reviewer is enabled in tool_args
            self.enable_reviewer = init_content.tool_args.get("enable_reviewer", False)
            if self.enable_reviewer:
                # Create reviewer agent using factory
                self.reviewer_agent = self._create_reviewer_agent(
                    client,
                    self.session_uuid,
                    self.workspace_manager,
                    self.websocket,
                    init_content.tool_args,
                    self.file_store,
                    settings=settings,
                )

                # Start message processor for reviewer
                self.reviewer_message_processor = (
                    self.reviewer_agent.start_message_processing()
                )
                print("Initialized Reviewer")

            await self.send_event(
                Event.create_agent_event(
                    EventType.AGENT_INITIALIZED,
                    {
                        "message": "Agent initialized"
                        + (" with reviewer" if self.enable_reviewer else "")
                    },
                )
            )
        except ValidationError as e:
            await self.send_event(
                ErrorObservation(
                    content=f"Invalid init_agent content: {str(e)}",
                    cause=None,
                )
            )
        except Exception as e:
            await self.send_event(
                ErrorObservation(
                    content=f"Error initializing agent: {str(e)}",
                    cause=None,
                )
            )

    async def _handle_query(self, content: dict):
        """Handle query processing."""
        try:
            query_content = QueryContent(**content)

            # Set session name from first message
            if self.first_message and query_content.text.strip():
                # Extract first few words as session name (max 100 characters)
                session_name = query_content.text.strip()[:100]
                Sessions.update_session_name(self.session_uuid, session_name)
                self.first_message = False

            # Check if there's an active task for this session
            if self.has_active_task():
                await self.send_event(
                    ErrorObservation(
                        content="A query is already being processed",
                        cause=None,
                    )
                )
                return

            # Send acknowledgment
            await self.websocket.send_json(
                {
                    "type": "processing",
                    "content": {"message": "Processing your request..."},
                }
            )

            # Run the agent with the query in a separate task
            self.active_task = asyncio.create_task(
                self._run_agent_async(
                    query_content.text, query_content.resume, query_content.files
                )
            )

        except ValidationError as e:
            await self.send_event(
                ErrorObservation(
                    content=f"Invalid query content: {str(e)}",
                    cause=None,
                )
            )

    async def _handle_workspace_info(self, content: dict = None):
        """Handle workspace info request."""
        await self.send_event(
            {
                "type": "workspace_info",
                "content": {"path": str(self.workspace_manager.root)},
            }
        )

    async def _handle_ping(self, content: dict = None):
        """Handle ping message."""
        await self.websocket.send_json(
            {
                "type": "pong",
                "content": {},
            }
        )

    async def _handle_cancel(self, content: dict = None):
        """Handle query cancellation."""
        if not self.controller:
            await self.send_event(
                ErrorObservation(
                    content="No active controller for this session",
                    cause=None,
                )
            )
            return

        self.controller.cancel()

        # Send acknowledgment that cancellation was received
        await self.websocket.send_json(
            {
                "type": "system",
                "content": {"message": "Query cancelled"},
            }
        )

    async def _handle_edit_query(self, content: dict):
        """Handle query editing."""
        try:
            edit_content = EditQueryContent(**content)

            if not self.controller:
                await self.send_event(
                    ErrorObservation(
                        content="No active controller for this session",
                        cause=None,
                    )
                )
                return

            # Handle edit query using dedicated method
            self.controller.handle_edit_query()

            # Delete events from database up to last user message if we have a session ID
            if self.controller.session_id:
                try:
                    Events.delete_events_from_last_to_user_message(
                        self.controller.session_id
                    )
                    await self.websocket.send_json(
                        {
                            "type": "system",
                            "content": {
                                "message": "Session history cleared from last event to last user message"
                            },
                        }
                    )
                except Exception as e:
                    logger.error(f"Error deleting session events: {str(e)}")
                    await self.send_event(
                        ErrorObservation(
                            content=f"Error clearing history: {str(e)}",
                            cause=None,
                        )
                    )

            # Send acknowledgment that query editing was received
            await self.websocket.send_json(
                {
                    "type": "system",
                    "content": {"message": "Query editing mode activated"},
                }
            )

            # Check if there's an active task for this session
            if self.has_active_task():
                await self.send_event(
                    ErrorObservation(
                        content="A query is already being processed",
                        cause=None,
                    )
                )
                return

            # Send processing acknowledgment
            await self.websocket.send_json(
                {
                    "type": "processing",
                    "content": {"message": "Processing your request..."},
                }
            )

            # Run the agent with the query in a separate task
            self.active_task = asyncio.create_task(
                self._run_agent_async(
                    edit_content.text, edit_content.resume, edit_content.files
                )
            )

        except ValidationError as e:
            await self.send_event(
                ErrorObservation(
                    content=f"Invalid edit_query content: {str(e)}",
                    cause=None,
                )
            )

    async def _handle_enhance_prompt(self, content: dict):
        """Handle prompt enhancement request."""
        try:
            enhance_content = EnhancePromptContent(**content)
            # Create LLM client using factory
            user_id = None  # TODO: Support user id
            settings_store = await FileSettingsStore.get_instance(self.config, user_id)
            settings = await settings_store.load()

            llm_config = settings.llm_configs.get(enhance_content.model_name)
            if not llm_config:
                raise ValueError(
                    f"LLM config not found for model: {enhance_content.model_name}"
                )
            client = get_client(llm_config)

            # Call the enhance_prompt function
            success, message, enhanced_prompt = await enhance_user_prompt(
                client=client,
                user_input=enhance_content.text,
                files=enhance_content.files,
            )

            if success and enhanced_prompt:
                # Send the enhanced prompt back to the client
                await self.websocket.send_json(
                    {
                        "type": "prompt_generated",
                        "content": {
                            "result": enhanced_prompt,
                            "original_request": enhance_content.text,
                        },
                    }
                )
            else:
                # Send error message
                await self.send_event(
                    ErrorObservation(
                        content=message,
                        cause=None,
                    )
                )

        except ValidationError as e:
            await self.send_event(
                ErrorObservation(
                    content=f"Invalid enhance_prompt content: {str(e)}",
                    cause=None,
                )
            )

    async def _handle_review_result(self, content: dict):
        """Handle reviewer's feedback."""
        try:
            if not self.controller:
                await self.send_event(
                    ErrorObservation(
                        content="No active controller for this session",
                        cause=None,
                    )
                )
                return

            review_content = ReviewResultContent(**content)
            user_input = review_content.user_input

            if not user_input:
                await self.send_event(
                    ErrorObservation(
                        content="No user query found to review",
                        cause=None,
                    )
                )
                return

            await self._run_reviewer_async(user_input)

        except Exception as e:
            logger.error(f"Error handling review request: {str(e)}")
            await self.send_event(
                ErrorObservation(
                    content=f"Error handling review request: {str(e)}",
                    cause=None,
                )
            )

    async def _run_agent_async(
        self, user_input: str, resume: bool = False, files: list = []
    ):
        """Run the agent controller asynchronously and send results back to the websocket."""
        if not self.controller:
            await self.send_event(
                ErrorObservation(
                    content="Controller not initialized for this session",
                    cause=None,
                )
            )
            return

        try:
            # Add user message to the event queue to save to database
            self.controller.message_queue.put_nowait(
                MessageAction(
                    content=user_input,
                    source=EventSource.USER,
                )
            )
            # Run the controller with the query using the new async method
            await self.controller.run_async(user_input, files)

        except Exception as e:
            logger.error(f"Error running agent: {str(e)}")
            await self.send_event(
                ErrorObservation(
                    content=f"Error running agent: {str(e)}",
                    cause=None,
                )
            )
        finally:
            # Clean up the task reference
            self.active_task = None

    async def _run_reviewer_async(self, user_input: str):
        """Run the reviewer agent to analyze the main agent's output."""
        try:
            # Extract the final result from the controller's history
            final_result = ""
            found = False
            for message in self.controller.agent.history._message_lists[::-1]:
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
                logger.warning("No final result found from controller to review")
                return
            # Send notification that reviewer is starting
            await self.websocket.send_json(
                {
                    "type": "system",
                    "content": {
                        "type": "reviewer_agent",
                        "message": "Reviewer agent is analyzing the output...",
                    },
                }
            )

            # Run reviewer agent
            reviewer_feedback = await asyncio.to_thread(
                self.reviewer_agent.run_agent,
                task=user_input,
                result=final_result,
                workspace_dir=str(self.workspace_manager.root),
            )
            if reviewer_feedback and reviewer_feedback.strip():
                # Send feedback to agent for improvement
                await self.send_event(
                    {
                        "type": "system",
                        "content": {
                            "type": "reviewer_agent",
                            "message": "Applying reviewer feedback...",
                        },
                    }
                )

                feedback_prompt = f"""Based on the reviewer's analysis, here is the feedback for improvement:

{reviewer_feedback}

Please review this feedback and implement the suggested improvements to better complete the original task: "{user_input}"
"""

                # Run controller with reviewer feedback
                await self.controller.run_async(feedback_prompt, [])

        except Exception as e:
            logger.error(f"Error running reviewer: {str(e)}")
            await self.send_event(
                ErrorObservation(
                    content=f"Error running reviewer: {str(e)}",
                    cause=None,
                )
            )

    def has_active_task(self) -> bool:
        """Check if there's an active task for this session."""
        return self.active_task is not None and not self.active_task.done()

    def cleanup(self):
        """Clean up resources associated with this session."""
        # Set websocket to None in the controller but keep the message processor running
        if self.controller:
            self.controller.websocket = (
                None  # This will prevent sending to websocket but keep processing
            )
            if self.controller.agent.history:
                self.controller.agent.history.save_to_session(
                    str(self.session_uuid), self.file_store
                )

        # Clean up reviewer agent
        if self.reviewer_agent:
            self.reviewer_agent.websocket = None

        # Cancel any running tasks
        if self.active_task and not self.active_task.done():
            self.active_task.cancel()
            self.active_task = None

        # Clean up references
        self.websocket = None
        self.controller = None
        self.reviewer_agent = None
        self.message_processor = None
        self.reviewer_message_processor = None

    def _create_agent(
        self,
        client: LLMClient,
        session_id: uuid.UUID,
        workspace_manager: WorkspaceManager,
        websocket: WebSocket,
        tool_args: Dict[str, Any],
        file_store: FileStore,
        settings: Settings,
    ):
        """Create a new agent controller instance for a websocket connection.

        Args:
            client: LLM client instance
            session_id: Session UUID
            workspace_manager: Workspace manager
            websocket: WebSocket connection
            tool_args: Tool configuration arguments
            file_store: File store instance
            settings: Settings instance

        Returns:
            Configured agent controller instance
        """
        device_id = websocket.query_params.get("device_id")

        # Check and create database session
        existing_session = Sessions.get_session_by_id(session_id)
        if existing_session:
            logger.info(
                f"Found existing session {session_id} with workspace at {existing_session.workspace_dir}"
            )
        else:
            # Create new session if it doesn't exist
            Sessions.create_session(
                device_id=device_id,
                session_uuid=session_id,
                workspace_path=workspace_manager.root,
            )
            logger.info(
                f"Created new session {session_id} with workspace at {workspace_manager.root}"
            )

        # Create context manager
        token_counter = TokenCounter()
        context_manager = LLMSummarizingContextManager(
            client=client,
            token_counter=token_counter,
            token_budget=self.config.token_budget,
        )

        queue = asyncio.Queue()
        tools = get_system_tools(
            client=client,
            workspace_manager=workspace_manager,
            message_queue=queue,
            container_id=self.config.docker_container_id,
            tool_args=tool_args,
            settings=settings,
        )

        tool_manager = AgentToolManager(tools=tools)

        # Choose system prompt based on tool args
        system_prompt = (
            SYSTEM_PROMPT_WITH_SEQ_THINKING
            if tool_args.get("sequential_thinking", False)
            else SYSTEM_PROMPT
        )

        # Restore state from previous session if available
        initial_state = self._maybe_restore_state(session_id, file_store)

        # Get available tool parameters from tool manager so agent knows what actions it can perform
        available_tool_params = [tool.get_tool_param() for tool in tool_manager.get_tools()]

        # Create agent config for the thin agent
        agent_config = AgentConfig(
            max_tokens_per_turn=self.config.max_output_tokens_per_turn,
            system_prompt=system_prompt,
            temperature=0.0,
        )

        # Create agent
        agent = FunctionCallAgent(
            llm=client,
            config=agent_config,
            system_prompt=system_prompt,
            available_tools=available_tool_params,
        )

        controller = AgentController(
            agent=agent,
            tool_manager=tool_manager,
            workspace_manager=workspace_manager,
            message_queue=queue,
            max_turns=self.config.max_turns,
            websocket=websocket,
            session_id=session_id,
            interactive_mode=True,
            initial_state=initial_state,
        )

        return controller

    def _create_reviewer_agent(
        self,
        client: LLMClient,
        session_id: uuid.UUID,
        workspace_manager: WorkspaceManager,
        websocket: WebSocket,
        tool_args: Dict[str, Any],
        file_store: FileStore,
        settings: Settings,
    ):
        """Create a new reviewer controller instance for a websocket connection.

        Args:
            client: LLM client instance
            session_id: Session UUID
            workspace_manager: Workspace manager
            websocket: WebSocket connection
            tool_args: Tool configuration arguments
            file_store: File store instance

        Returns:
            Configured reviewer controller instance
        """
        # Create context manager
        token_counter = TokenCounter()
        context_manager = LLMSummarizingContextManager(
            client=client,
            token_counter=token_counter,
            token_budget=self.config.token_budget,
        )

        # Initialize agent queue and tool manager
        queue = asyncio.Queue()
        tool_manager = get_system_tools(
            client=client,
            workspace_manager=workspace_manager,
            message_queue=queue,
            container_id=self.config.docker_container_id,
            tool_args=tool_args,
            settings=settings,
        )

        # Create thin reviewer agent (only for state->action conversion)
        thin_reviewer = ReviewerAgent(
            system_prompt=REVIEWER_SYSTEM_PROMPT,
            client=client,
            workspace_manager=workspace_manager,
            message_queue=queue,
            context_manager=context_manager,
            max_output_tokens_per_turn=self.config.max_output_tokens_per_turn,
            max_turns=self.config.max_turns,
            websocket=websocket,
            session_id=session_id,
        )

        # Create ReviewerController to orchestrate execution
        reviewer_controller = ReviewerController(
            reviewer_agent=thin_reviewer,
            tool_manager=tool_manager,
            workspace_manager=workspace_manager,
            message_queue=queue,
            max_turns=self.config.max_turns,
            websocket=websocket,
            session_id=session_id,
        )

        return reviewer_controller

    def _maybe_restore_state(self, session_id: uuid.UUID, file_store: FileStore) -> State | None:
        """Helper method to handle state restore logic."""
        restored_state = None

        try:
            restored_state = State.restore_from_session(
                str(session_id), file_store, None  # user_id is None in our case
            )
            logger.info(f'Restored state from session, session_id: {session_id}')
        except Exception as e:
            # For now, we'll just log and continue without restored state
            # In the future, we could check if we have events and should have a state
            logger.debug(f'State could not be restored for session {session_id}: {e}')
        
        return restored_state
