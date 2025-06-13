import asyncio
import logging
import uuid
from typing import Dict, Any
from fastapi import WebSocket

from ii_agent.core.storage.files import FileStore
from ii_agent.llm.base import LLMClient
from ii_agent.llm.message_history import MessageHistory
from ii_agent.utils import WorkspaceManager
from ii_agent.agents.function_call import FunctionCallAgent
from ii_agent.agents.reviewer import ReviewerAgent
from ii_agent.llm.context_manager.llm_summarizing import LLMSummarizingContextManager
from ii_agent.llm.token_counter import TokenCounter
from ii_agent.db.manager import Sessions
from ii_agent.tools import get_system_tools
from ii_agent.prompts.system_prompt import (
    SYSTEM_PROMPT,
    SYSTEM_PROMPT_WITH_SEQ_THINKING,
)
from ii_agent.prompts.reviewer_system_prompt import REVIEWER_SYSTEM_PROMPT
from ii_agent.utils.constants import TOKEN_BUDGET

# Constants
MAX_OUTPUT_TOKENS_PER_TURN = 32000
MAX_TURNS = 200


class AgentConfig:
    """Configuration for agent creation."""

    def __init__(
        self,
        logs_path: str,
        minimize_stdout_logs: bool = False,
        docker_container_id: str = None,
        needs_permission: bool = True,
        max_output_tokens_per_turn: int = MAX_OUTPUT_TOKENS_PER_TURN,
        max_turns: int = MAX_TURNS,
        token_budget: int = TOKEN_BUDGET,
    ):
        self.logs_path = logs_path
        self.minimize_stdout_logs = minimize_stdout_logs
        self.docker_container_id = docker_container_id
        self.needs_permission = needs_permission
        self.max_output_tokens_per_turn = max_output_tokens_per_turn
        self.max_turns = max_turns
        self.token_budget = token_budget


class AgentFactory:
    """Factory for creating configured agent instances."""

    def __init__(self, config: AgentConfig):
        """Initialize the agent factory with configuration.

        Args:
            config: Agent configuration
        """
        self.config = config

    def create_agent(
        self,
        client: LLMClient,
        session_id: uuid.UUID,
        workspace_manager: WorkspaceManager,
        websocket: WebSocket,
        tool_args: Dict[str, Any],
        file_store: FileStore,
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
        logger_for_agent_logs = self._setup_logger(websocket)

        # Create database session
        self._create_db_session(
            device_id, session_id, workspace_manager, logger_for_agent_logs
        )

        # Create context manager
        context_manager = self._create_context_manager(client, logger_for_agent_logs)

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
        )

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

    def _create_db_session(
        self,
        device_id: str,
        session_id: uuid.UUID,
        workspace_manager: WorkspaceManager,
        logger: logging.Logger,
    ):
        """Create a new database session or load existing one if it exists."""
        # Check if session already exists
        existing_session = Sessions.get_session_by_id(session_id)

        if existing_session:
            logger.info(
                f"Found existing session {session_id} with workspace at {existing_session.workspace_dir}"
            )
            return

        # Create new session if it doesn't exist
        Sessions.create_session(
            device_id=device_id,
            session_uuid=session_id,
            workspace_path=workspace_manager.root,
        )
        logger.info(
            f"Created new session {session_id} with workspace at {workspace_manager.root}"
        )

    def _create_context_manager(self, client: LLMClient, logger: logging.Logger):
        """Create context manager based on configuration."""
        token_counter = TokenCounter()

        return LLMSummarizingContextManager(
            client=client,
            token_counter=token_counter,
            logger=logger,
            token_budget=self.config.token_budget,
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
    ):
        """Create the actual agent instance."""
        # Initialize agent queue and tools
        queue = asyncio.Queue()
        tools = get_system_tools(
            client=client,
            workspace_manager=workspace_manager,
            message_queue=queue,
            container_id=self.config.docker_container_id,
            ask_user_permission=self.config.needs_permission,
            tool_args=tool_args,
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

    def create_reviewer_agent(
        self,
        client: LLMClient,
        session_id: uuid.UUID,
        workspace_manager: WorkspaceManager,
        websocket: WebSocket,
        tool_args: Dict[str, Any],
        file_store: FileStore,
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
            ask_user_permission=self.config.needs_permission,
            tool_args=tool_args,
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
