"""Agent service for managing agent lifecycle."""

import logging
import uuid
from typing import Dict, Any, Optional

from ii_agent.agents.function_call import FunctionCallAgent
from ii_agent.controller.agent_controller import AgentController
from ii_agent.controller.state import State
from ii_agent.core.config.agent_config import AgentConfig
from ii_agent.core.config.ii_agent_config import IIAgentConfig
from ii_agent.core.event_stream import AsyncEventStream
from ii_agent.core.storage.files import FileStore
from ii_agent.core.storage.settings.file_settings_store import FileSettingsStore
from ii_agent.llm import get_client
from ii_agent.llm.context_manager import LLMCompact
from ii_agent.llm.token_counter import TokenCounter
from ii_agent.prompts import get_system_prompt
from ii_agent.utils.workspace_manager import WorkspaceManager
from ii_agent.controller.tool_manager import AgentToolManager
from ii_agent.llm.base import ToolParam
from ii_tool.utils import load_tools_from_mcp
from ii_tool.tools.manager import get_default_tools

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
        event_stream: AsyncEventStream,
        tool_args: Dict[str, Any],
        system_prompt: Optional[str] = None,
    ) -> AgentController:
        """Create a new agent instance following CLI patterns.

        Args:
            model_name: Name of the LLM model to use
            session_id: Session UUID
            workspace_manager: Workspace manager instance
            event_stream: AsyncEventStream for event handling
            tool_args: Tool configuration arguments
            system_prompt: Optional custom system prompt

        Returns:
            AgentController: The controller for the created agent
        """
        # Get settings
        user_id = None  # TODO: Support user id
        settings_store = await FileSettingsStore.get_instance(self.config, user_id)
        settings = await settings_store.load()

        if not settings:
            raise ValueError("Settings not found. Ensure the configuration is correct.")

        # Get LLM configuration
        llm_config = settings.llm_configs.get(model_name)
        if not llm_config:
            raise ValueError(f"LLM config not found for model: {model_name}")

        # Create LLM client
        llm_client = get_client(llm_config)

        # Determine system prompt
        if system_prompt is None:
            system_prompt = get_system_prompt(
                workspace_manager.root.absolute().as_posix()
            )

        # Create agent config
        agent_config = AgentConfig(
            max_tokens_per_turn=self.config.max_output_tokens_per_turn,
            system_prompt=system_prompt,
            temperature=getattr(self.config, "temperature", 0.7),
        )

        # Create tool manager and register tools
        tool_manager = AgentToolManager()

        # Get core tools
        tool_manager.register_tools(
            get_default_tools(
                chat_session_id=str(session_id),
                workspace_path="",
                web_search_config=self.config.web_search_config,
                web_visit_config=self.config.web_visit_config,
                fullstack_dev_config=self.config.fullstack_dev_config,
                image_search_config=self.config.image_search_config,
                video_generate_config=self.config.video_generate_config,
                image_generate_config=self.config.image_generate_config,
            )
        )

        # Load MCP tools if configured
        if self.config.mcp_config:
            mcp_tools = await load_tools_from_mcp(self.config.mcp_config)
            tool_manager.register_tools(mcp_tools)

        # Create agent with proper tools
        agent = FunctionCallAgent(
            llm=llm_client,
            config=agent_config,
            tools=[
                ToolParam(
                    name=tool.name,
                    description=tool.description,
                    input_schema=tool.input_schema,
                )
                for tool in tool_manager.get_tools()
            ],
        )

        # Create context manager
        token_counter = TokenCounter()
        context_manager = LLMCompact(
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

        return AgentController(
            agent=agent,
            tool_manager=tool_manager,
            init_history=state,
            event_stream=event_stream,
            context_manager=context_manager,
            interactive_mode=True,
            config=self.config,
        )

    async def create_reviewer_agent(
        self,
        model_name: str,
        session_id: uuid.UUID,
        workspace_manager: WorkspaceManager,
        event_stream: AsyncEventStream,
        tool_args: Dict[str, Any],
    ) -> AgentController:
        """Create a reviewer agent using FunctionCallAgent with reviewer prompt.

        Args:
            model_name: Name of the LLM model to use
            session_id: Session UUID
            workspace_manager: Workspace manager instance
            event_stream: AsyncEventStream for event handling
            tool_args: Tool configuration arguments

        Returns:
            AgentController: The controller for the reviewer agent
        """
        reviewer_prompt = self.get_reviewer_system_prompt()

        return await self.create_agent(
            model_name=model_name,
            session_id=session_id,
            workspace_manager=workspace_manager,
            event_stream=event_stream,
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
