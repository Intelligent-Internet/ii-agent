import asyncio
import json
import logging
import uuid
from typing import Optional, Dict, Any
from fastapi import WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from ii_agent.llm.base import ToolCall
from ii_agent.agents.base import BaseAgent
from ii_agent.agents.reviewer import ReviewerAgent
from ii_agent.core.event import RealtimeEvent, EventType
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
from ii_agent.llm.base import LLMClient
from ii_agent.llm.message_history import MessageHistory
from ii_agent.agents.function_call import FunctionCallAgent
from ii_agent.llm.context_manager.llm_summarizing import LLMSummarizingContextManager
from ii_agent.llm.token_counter import TokenCounter
from ii_agent.tools import get_system_tools
from ii_agent.prompts.system_prompt import (
    SYSTEM_PROMPT,
    SYSTEM_PROMPT_WITH_SEQ_THINKING,
)
from ii_agent.prompts.reviewer_system_prompt import REVIEWER_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


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
        self.agent: Optional[BaseAgent] = None
        self.reviewer_agent: Optional[ReviewerAgent] = None
        self.active_task: Optional[asyncio.Task] = None
        self.message_processor: Optional[asyncio.Task] = None
        self.reviewer_message_processor: Optional[asyncio.Task] = None
        self.first_message = True
        self.enable_reviewer = False
        self.config = config

    async def send_event(self, event: RealtimeEvent):
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
                RealtimeEvent(
                    type=EventType.ERROR,
                    content={"message": "Invalid JSON format"},
                )
            )
        except WebSocketDisconnect:
            logger.info("Client disconnected")
            if self.agent:
                self.agent.cancel()  # NOTE: Now we cancel the agent on disconnect, the background implementation will come later

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
        await self.send_event(
            RealtimeEvent(
                type=EventType.CONNECTION_ESTABLISHED,
                content={
                    "message": "Connected to Agent WebSocket Server",
                    "workspace_path": str(self.workspace_manager.root),
                },
            )
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
                    RealtimeEvent(
                        type=EventType.ERROR,
                        content={"message": f"Unknown message type: {msg_type}"},
                    )
                )

        except ValidationError as e:
            await self.send_event(
                RealtimeEvent(
                    type=EventType.ERROR,
                    content={"message": f"Invalid message format: {str(e)}"},
                )
            )
        except Exception as e:
            logger.error(f"Error handling message: {str(e)}")
            await self.send_event(
                RealtimeEvent(
                    type=EventType.ERROR,
                    content={"message": f"Error processing request: {str(e)}"},
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
            self.agent = self._create_agent(
                client,
                self.session_uuid,
                self.workspace_manager,
                self.websocket,
                init_content.tool_args,
                self.file_store,
                settings=settings,
            )

            # Start message processor for this session
            self.message_processor = self.agent.start_message_processing()

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
                RealtimeEvent(
                    type=EventType.AGENT_INITIALIZED,
                    content={
                        "message": "Agent initialized"
                        + (" with reviewer" if self.enable_reviewer else "")
                    },
                )
            )
        except ValidationError as e:
            await self.send_event(
                RealtimeEvent(
                    type=EventType.ERROR,
                    content={"message": f"Invalid init_agent content: {str(e)}"},
                )
            )
        except Exception as e:
            await self.send_event(
                RealtimeEvent(
                    type=EventType.ERROR,
                    content={"message": f"Error initializing agent: {str(e)}"},
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
                    RealtimeEvent(
                        type=EventType.ERROR,
                        content={"message": "A query is already being processed"},
                    )
                )
                return

            # Send acknowledgment
            await self.send_event(
                RealtimeEvent(
                    type=EventType.PROCESSING,
                    content={"message": "Processing your request..."},
                )
            )

            # Run the agent with the query in a separate task
            self.active_task = asyncio.create_task(
                self._run_agent_async(
                    query_content.text, query_content.resume, query_content.files
                )
            )

        except ValidationError as e:
            await self.send_event(
                RealtimeEvent(
                    type=EventType.ERROR,
                    content={"message": f"Invalid query content: {str(e)}"},
                )
            )

    async def _handle_workspace_info(self, content: dict = None):
        """Handle workspace info request."""
        await self.send_event(
            RealtimeEvent(
                type=EventType.WORKSPACE_INFO,
                content={"path": str(self.workspace_manager.root)},
            )
        )

    async def _handle_ping(self, content: dict = None):
        """Handle ping message."""
        await self.send_event(RealtimeEvent(type=EventType.PONG, content={}))

    async def _handle_cancel(self, content: dict = None):
        """Handle query cancellation."""
        if not self.agent:
            await self.send_event(
                RealtimeEvent(
                    type=EventType.ERROR,
                    content={"message": "No active agent for this session"},
                )
            )
            return

        self.agent.cancel()

        # Send acknowledgment that cancellation was received
        await self.send_event(
            RealtimeEvent(
                type=EventType.SYSTEM,
                content={"message": "Query cancelled"},
            )
        )

    async def _handle_edit_query(self, content: dict):
        """Handle query editing."""
        try:
            edit_content = EditQueryContent(**content)

            if not self.agent:
                await self.send_event(
                    RealtimeEvent(
                        type=EventType.ERROR,
                        content={"message": "No active agent for this session"},
                    )
                )
                return

            # Cancel the agent and clear history
            self.agent.cancel()
            self.agent.history.clear_from_last_to_user_message()

            # Delete events from database up to last user message if we have a session ID
            if self.agent.session_id:
                try:
                    Events.delete_events_from_last_to_user_message(
                        self.agent.session_id
                    )
                    await self.send_event(
                        RealtimeEvent(
                            type=EventType.SYSTEM,
                            content={
                                "message": "Session history cleared from last event to last user message"
                            },
                        )
                    )
                except Exception as e:
                    logger.error(f"Error deleting session events: {str(e)}")
                    await self.send_event(
                        RealtimeEvent(
                            type=EventType.ERROR,
                            content={"message": f"Error clearing history: {str(e)}"},
                        )
                    )

            # Send acknowledgment that query editing was received
            await self.send_event(
                RealtimeEvent(
                    type=EventType.SYSTEM,
                    content={"message": "Query editing mode activated"},
                )
            )

            # Check if there's an active task for this session
            if self.has_active_task():
                await self.send_event(
                    RealtimeEvent(
                        type=EventType.ERROR,
                        content={"message": "A query is already being processed"},
                    )
                )
                return

            # Send processing acknowledgment
            await self.send_event(
                RealtimeEvent(
                    type=EventType.PROCESSING,
                    content={"message": "Processing your request..."},
                )
            )

            # Run the agent with the query in a separate task
            self.active_task = asyncio.create_task(
                self._run_agent_async(
                    edit_content.text, edit_content.resume, edit_content.files
                )
            )

        except ValidationError as e:
            await self.send_event(
                RealtimeEvent(
                    type=EventType.ERROR,
                    content={"message": f"Invalid edit_query content: {str(e)}"},
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
                await self.send_event(
                    RealtimeEvent(
                        type=EventType.PROMPT_GENERATED,
                        content={
                            "result": enhanced_prompt,
                            "original_request": enhance_content.text,
                        },
                    )
                )
            else:
                # Send error message
                await self.send_event(
                    RealtimeEvent(
                        type=EventType.ERROR,
                        content={"message": message},
                    )
                )

        except ValidationError as e:
            await self.send_event(
                RealtimeEvent(
                    type=EventType.ERROR,
                    content={"message": f"Invalid enhance_prompt content: {str(e)}"},
                )
            )

    async def _handle_review_result(self, content: dict):
        """Handle reviewer's feedback."""
        try:
            if not self.agent:
                await self.send_event(
                    RealtimeEvent(
                        type=EventType.ERROR,
                        content={"message": "No active agent for this session"},
                    )
                )
                return

            review_content = ReviewResultContent(**content)
            user_input = review_content.user_input

            if not user_input:
                await self.send_event(
                    RealtimeEvent(
                        type=EventType.ERROR,
                        content={"message": "No user query found to review"},
                    )
                )
                return

            await self._run_reviewer_async(user_input)

        except Exception as e:
            logger.error(f"Error handling review request: {str(e)}")
            await self.send_event(
                RealtimeEvent(
                    type=EventType.ERROR,
                    content={"message": f"Error handling review request: {str(e)}"},
                )
            )

    async def _run_agent_async(
        self, user_input: str, resume: bool = False, files: list = []
    ):
        """Run the agent asynchronously and send results back to the websocket."""
        if not self.agent:
            await self.send_event(
                RealtimeEvent(
                    type=EventType.ERROR,
                    content={"message": "Agent not initialized for this session"},
                )
            )
            return

        try:
            # Add user message to the event queue to save to database
            self.agent.message_queue.put_nowait(
                RealtimeEvent(type=EventType.USER_MESSAGE, content={"text": user_input})
            )
            # Run the agent with the query using the new async method
            await self.agent.run_agent_async(user_input, files, resume)

        except Exception as e:
            logger.error(f"Error running agent: {str(e)}")
            import traceback

            traceback.print_exc()
            await self.send_event(
                RealtimeEvent(
                    type=EventType.ERROR,
                    content={"message": f"Error running agent: {str(e)}"},
                )
            )
        finally:
            # Clean up the task reference
            self.active_task = None

    async def _run_reviewer_async(self, user_input: str):
        """Run the reviewer agent to analyze the main agent's output."""
        try:
            # Extract the final result from the agent's history
            final_result = ""
            found = False
            for message in self.agent.history._message_lists[::-1]:
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
            await self.send_event(
                RealtimeEvent(
                    type=EventType.SYSTEM,
                    content={
                        "type": "reviewer_agent",
                        "message": "Reviewer agent is analyzing the output...",
                    },
                )
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

                # Run agent with reviewer feedback
                await self.agent.run_agent_async(feedback_prompt, [], True)

        except Exception as e:
            logger.error(f"Error running reviewer: {str(e)}")
            await self.send_event(
                RealtimeEvent(
                    type=EventType.ERROR,
                    content={"message": f"Error running reviewer: {str(e)}"},
                )
            )

    def has_active_task(self) -> bool:
        """Check if there's an active task for this session."""
        return self.active_task is not None and not self.active_task.done()

    def cleanup(self):
        """Clean up resources associated with this session."""
        # Set websocket to None in the agent but keep the message processor running
        if self.agent:
            self.agent.websocket = (
                None  # This will prevent sending to websocket but keep processing
            )
            if self.agent.history:
                self.agent.history.save_to_session(
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
        self.agent = None
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
        """Create a new agent instance for a websocket connection.

        Args:
            client: LLM client instance
            session_id: Session UUID
            workspace_manager: Workspace manager
            websocket: WebSocket connection
            tool_args: Tool configuration arguments

        Returns:
            Configured agent instance
        """
        device_id = websocket.query_params.get("device_id")

        # Setup logging
        logger_for_agent_logs = logging.getLogger(f"agent_logs_{id(websocket)}")
        logger_for_agent_logs.setLevel(logging.DEBUG)
        logger_for_agent_logs.propagate = False

        # Ensure we don't duplicate handlers
        if not logger_for_agent_logs.handlers:
            logger_for_agent_logs.addHandler(logging.FileHandler(self.config.logs_path))
            if not self.config.minimize_stdout_logs:
                logger_for_agent_logs.addHandler(logging.StreamHandler())

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
            logger=logger,
            token_budget=self.config.token_budget,
        )

        # Create agent
        return self._create_agent_instance(
            client,
            workspace_manager,
            websocket,
            session_id,
            tool_args,
            context_manager,
            logger_for_agent_logs,
            file_store,
            settings,
        )

    def _create_agent_instance(
        self,
        client: LLMClient,
        workspace_manager: WorkspaceManager,
        websocket: WebSocket,
        session_id: uuid.UUID,
        tool_args: Dict[str, Any],
        context_manager,
        logger: logging.Logger,
        file_store: FileStore,
        settings: Settings,
    ):
        """Create the actual agent instance."""
        # Initialize agent queue and tools
        queue = asyncio.Queue()
        tools = get_system_tools(
            client=client,
            workspace_manager=workspace_manager,
            message_queue=queue,
            container_id=self.config.docker_container_id,
            tool_args=tool_args,
            settings=settings,
        )

        # Choose system prompt based on tool args
        system_prompt = (
            SYSTEM_PROMPT_WITH_SEQ_THINKING
            if tool_args.get("sequential_thinking", False)
            else SYSTEM_PROMPT
        )

        # try to get history from file store
        init_history = MessageHistory(context_manager)
        try:
            init_history.restore_from_session(str(session_id), file_store)

        except FileNotFoundError:
            logger.info(f"No history found for session {session_id}")

        agent = FunctionCallAgent(
            system_prompt=system_prompt,
            client=client,
            tools=tools,
            workspace_manager=workspace_manager,
            message_queue=queue,
            logger_for_agent_logs=logger,
            init_history=init_history,
            max_output_tokens_per_turn=self.config.max_output_tokens_per_turn,
            max_turns=self.config.max_turns,
            websocket=websocket,
            session_id=session_id,
        )

        # Store the session ID in the agent for event tracking
        agent.session_id = session_id
        return agent

    def _setup_logger(self, websocket: WebSocket) -> logging.Logger:
        """Setup logger for the agent."""
        logger_for_agent_logs = logging.getLogger(f"agent_logs_{id(websocket)}")
        logger_for_agent_logs.setLevel(logging.DEBUG)
        logger_for_agent_logs.propagate = False

        # Ensure we don't duplicate handlers
        if not logger_for_agent_logs.handlers:
            logger_for_agent_logs.addHandler(logging.FileHandler(self.config.logs_path))
            if not self.config.minimize_stdout_logs:
                logger_for_agent_logs.addHandler(logging.StreamHandler())

        return logger_for_agent_logs

    def _create_context_manager(self, client: LLMClient, logger: logging.Logger):
        """Create context manager based on configuration."""
        token_counter = TokenCounter()

        return LLMSummarizingContextManager(
            client=client,
            token_counter=token_counter,
            logger=logger,
            token_budget=self.config.token_budget,
        )

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
        """Create a new reviewer agent instance for a websocket connection.

        Args:
            client: LLM client instance
            session_id: Session UUID
            workspace_manager: Workspace manager
            websocket: WebSocket connection
            tool_args: Tool configuration arguments
            file_store: File store instance

        Returns:
            Configured reviewer agent instance
        """
        # Setup logging
        logger_for_agent_logs = self._setup_logger(websocket)

        # Create context manager
        context_manager = self._create_context_manager(client, logger_for_agent_logs)

        # Initialize agent queue and tools
        queue = asyncio.Queue()
        tools = get_system_tools(
            client=client,
            workspace_manager=workspace_manager,
            message_queue=queue,
            container_id=self.config.docker_container_id,
            tool_args=tool_args,
            settings=settings,
        )

        reviewer_agent = ReviewerAgent(
            system_prompt=REVIEWER_SYSTEM_PROMPT,
            client=client,
            tools=tools,
            workspace_manager=workspace_manager,
            message_queue=queue,
            logger_for_agent_logs=logger_for_agent_logs,
            context_manager=context_manager,
            max_output_tokens_per_turn=self.config.max_output_tokens_per_turn,
            max_turns=self.config.max_turns,
            websocket=websocket,
            session_id=session_id,
        )

        return reviewer_agent
