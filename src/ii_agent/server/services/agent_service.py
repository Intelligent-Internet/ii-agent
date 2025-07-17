"""Agent service for managing agent lifecycle."""

import asyncio
import logging
import uuid
from typing import Dict, Any, Optional, Tuple

from fastapi import WebSocket

from ii_agent.agents.function_call import FunctionCallAgent
from ii_agent.controller.agent_controller import AgentController
from ii_agent.controller.state import State
from ii_agent.core.config.agent_config import AgentConfig
from ii_agent.core.config.ii_agent_config import IIAgentConfig
from ii_agent.core.event_stream import AsyncEventStream
from ii_agent.core.storage.files import FileStore
from ii_agent.core.storage.models.settings import Settings
from ii_agent.core.storage.settings.file_settings_store import FileSettingsStore
from ii_agent.db.manager import Sessions
from ii_agent.llm import get_client
from ii_agent.llm.base import LLMClient
from ii_agent.llm.context_manager.llm_summarizing import LLMSummarizingContextManager
from ii_agent.llm.token_counter import TokenCounter
from ii_agent.prompts.system_prompt import SYSTEM_PROMPT, SYSTEM_PROMPT_WITH_SEQ_THINKING
from ii_agent.subscribers.websocket_subscriber import WebSocketSubscriber
from ii_agent.tools import get_system_tools
from ii_agent.utils.workspace_manager import WorkspaceManager

logger = logging.getLogger(__name__)


class AgentService:
    """Service for managing agent lifecycle and creation."""

    def __init__(
        self,
        config: IIAgentConfig,
        file_store: FileStore,
    ):
        self.config = config
        self.file_store = file_store

    async def create_agent(
        self,
        model_name: str,
        session_id: uuid.UUID,
        workspace_manager: WorkspaceManager,
        websocket: WebSocket,
        tool_args: Dict[str, Any],
        system_prompt: Optional[str] = None,
    ) -> Tuple[FunctionCallAgent, AgentController]:
        """Create a new agent instance following CLI patterns.
        
        Args:
            model_name: Name of the LLM model to use
            session_id: Session UUID
            workspace_manager: Workspace manager instance
            websocket: WebSocket connection
            tool_args: Tool configuration arguments
            system_prompt: Optional custom system prompt
            
        Returns:
            Tuple of (FunctionCallAgent, AgentController)
        """
        # Get settings
        user_id = None  # TODO: Support user id
        settings_store = await FileSettingsStore.get_instance(self.config, user_id)
        settings = await settings_store.load()
        
        # Get LLM configuration
        llm_config = settings.llm_configs.get(model_name)
        if not llm_config:
            raise ValueError(f"LLM config not found for model: {model_name}")
        
        # Create LLM client
        llm_client = get_client(llm_config)
        
        # Determine system prompt
        if system_prompt is None:
            system_prompt = (
                SYSTEM_PROMPT_WITH_SEQ_THINKING
                if tool_args.get("sequential_thinking", False)
                else SYSTEM_PROMPT
            )
        
        # Create agent config
        agent_config = AgentConfig(
            max_tokens_per_turn=self.config.max_output_tokens_per_turn,
            system_prompt=system_prompt,
            temperature=getattr(self.config, "temperature", 0.7),
        )
        
        # Get tools
        tools = get_system_tools(
            client=llm_client,
            workspace_manager=workspace_manager,
            settings=settings,
            container_id=self.config.docker_container_id,
            tool_args=tool_args,
        )
        
        # Create agent
        agent = FunctionCallAgent(
            llm=llm_client,
            config=agent_config,
            tools=tools,
        )
        
        # Create event stream
        event_stream = AsyncEventStream(logger=logger)
        
        # Add WebSocket subscriber
        websocket_subscriber = WebSocketSubscriber(websocket)
        event_stream.subscribe(websocket_subscriber.handle_event)
        
        # Create context manager
        token_counter = TokenCounter()
        context_manager = LLMSummarizingContextManager(
            client=llm_client,
            token_counter=token_counter,
            token_budget=self.config.token_budget,
        )
        
        # Create or restore state
        state = State()
        try:
            state.restore_from_session(str(session_id), self.file_store)
        except FileNotFoundError:
            logger.info(f"No history found for session {session_id}")
        
        # Create controller
        controller = AgentController(
            agent=agent,
            tools=tools,
            init_history=state,
            workspace_manager=workspace_manager,
            event_stream=event_stream,
            context_manager=context_manager,
            interactive_mode=True,
        )
        
        # Store session ID for tracking
        controller.session_id = session_id
        
        return agent, controller

    async def create_reviewer_agent(
        self,
        model_name: str,
        session_id: uuid.UUID,
        workspace_manager: WorkspaceManager,
        websocket: WebSocket,
        tool_args: Dict[str, Any],
    ) -> Tuple[FunctionCallAgent, AgentController]:
        """Create a reviewer agent using FunctionCallAgent with reviewer prompt.
        
        Args:
            model_name: Name of the LLM model to use
            session_id: Session UUID
            workspace_manager: Workspace manager instance
            websocket: WebSocket connection
            tool_args: Tool configuration arguments
            
        Returns:
            Tuple of (FunctionCallAgent, AgentController) configured for reviewing
        """
        reviewer_prompt = self.get_reviewer_system_prompt()
        
        return await self.create_agent(
            model_name=model_name,
            session_id=session_id,
            workspace_manager=workspace_manager,
            websocket=websocket,
            tool_args=tool_args,
            system_prompt=reviewer_prompt,
        )

    def get_reviewer_system_prompt(self) -> str:
        """Get the system prompt for reviewer functionality."""
        return """You are a reviewer agent tasked with evaluating the work done by a general agent. 
You have access to all the same tools that the general agent has.

Focus on:
- Testing ALL interactive elements (buttons, forms, navigation, etc.)
- Verifying functionality and user experience  
- Providing detailed, natural language feedback
- Identifying specific issues and areas for improvement

The user will provide you with the task, result, and workspace directory to review. Conduct a thorough review with emphasis on functionality testing and user experience evaluation."""

    def _ensure_session_exists(self, session_id: uuid.UUID, workspace_manager: WorkspaceManager, device_id: Optional[str] = None):
        """Ensure a database session exists for the given session ID."""
        existing_session = Sessions.get_session_by_id(session_id)
        if existing_session:
            logger.info(f"Found existing session {session_id} with workspace at {existing_session.workspace_dir}")
        else:
            # Create new session if it doesn't exist
            Sessions.create_session(
                device_id=device_id,
                session_uuid=session_id,
                workspace_path=workspace_manager.root,
            )
            logger.info(f"Created new session {session_id} with workspace at {workspace_manager.root}")