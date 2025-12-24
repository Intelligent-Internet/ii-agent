"""Agent service for managing agent lifecycle."""

import logging
import uuid
from typing import Dict, Any, List, Optional
from uuid import UUID
import httpx

from ii_agent.agents.function_call import FunctionCallAgent
from ii_agent.controller.agent_controller import AgentController
from ii_agent.controller.state import State
from ii_agent.core.config.agent_config import AgentConfig
from ii_agent.core.config.ii_agent_config import IIAgentConfig
from ii_agent.core.config.llm_config import LLMConfig
from ii_agent.core.event_stream import EventStream
from ii_agent.core.pubsub import RedisPubSub
from ii_agent.db.agent import AgentRunTask
from ii_agent.llm import get_client
from ii_agent.llm.context_manager.base import ContextManager
from ii_agent.sandbox import IISandbox
from ii_agent.storage.base import BaseStorage
from ii_agent.llm.context_manager import LLMCompact
from ii_agent.llm.token_counter import TokenCounter
from ii_agent.prompts.agent_prompts import get_system_prompt_for_agent_type
from ii_agent.config.agent_types import AgentType, AgentTypeConfig
from ii_agent.sub_agent.base import BaseAgentTool
from ii_agent.sub_agent.researcher_agent_tool import ResearcherAgent
from ii_agent.sub_agent.task_agent_tool import TaskAgentTool
from ii_agent.sub_agent.design_document_agent import DesignDocumentAgent
from ii_agent.utils.workspace_manager import WorkspaceManager
from ii_agent.controller.tool_manager import AgentToolManager
from ii_agent.llm.base import LLMClient, ToolParam
from ii_agent.adapters.sandbox_adapter import IISandboxToSandboxInterfaceAdapter

# Removed unused import that conflicts with local variable
from ii_tool.tools.base import BaseTool
from ii_tool.utils import load_tools_from_mcp
from ii_tool.tools.manager import get_common_tools
from ii_agent.sub_agent.codex import CodexAgent


logger = logging.getLogger(__name__)


class AgentService:
    """Service for managing agent lifecycle and creation."""

    def __init__(self, config: IIAgentConfig, file_store: BaseStorage):
        self.config = config
        self.file_store = file_store

    async def create_task_agent(
        self,
        llm_client: LLMClient,
        tools: List[BaseTool],
        context_manager: ContextManager,
        event_stream: EventStream,
        max_turns: int = 200,
        tool_args: dict[str, Any] | None = None,
        session_id: Optional[UUID] = None,
        run_id: Optional[UUID] = None,
    ) -> BaseAgentTool:
        from ii_agent.sub_agent.task_agent_tool import (
            SYSTEM_PROMPT as TASK_AGENT_PROMPT,
        )

        model_name = llm_client.model_name if llm_client else None
        task_agent_tool = AgentTypeConfig.get_allowed_toolset(
            AgentType.TASK_AGENT, model_name
        )
        if tool_args is not None and tool_args.get("media_generation"):
            task_agent_tool.extend(
                AgentTypeConfig.get_allowed_toolset(AgentType.MEDIA, model_name)
            )
        if tool_args is not None and tool_args.get("browser"):
            task_agent_tool.extend(
                AgentTypeConfig.get_allowed_toolset(AgentType.BROWSER)
            )
        tools = [tool for tool in tools if tool.name in set(task_agent_tool)]
        system_prompt = TASK_AGENT_PROMPT
        task_agent_config = AgentConfig(
            max_tokens_per_turn=self.config.max_output_tokens_per_turn,
            system_prompt=system_prompt,
        )
        sub_agent = FunctionCallAgent(
            llm=llm_client,
            config=task_agent_config,
            tools=[tool.get_tool_params() for tool in tools],
        )
        task_agent = TaskAgentTool(
            agent=sub_agent,
            tools=tools,
            context_manager=context_manager,
            event_stream=event_stream,
            max_turns=max_turns,
            config=self.config,
            session_id=session_id,
            run_id=run_id,
        )
        return task_agent

    async def create_researcher_agent(
        self,
        sandbox: IISandbox,
        tools: List[BaseTool],
        context_manager: ContextManager,
        event_stream: EventStream,
        max_turns: int = 200,
        user_client: LLMClient | None = None,
        session_id: Optional[UUID] = None,
        run_id: Optional[UUID] = None,
    ) -> BaseAgentTool:
        researcher_tool = [
            tool
            for tool in tools
            if tool.name
            in AgentTypeConfig.get_allowed_toolset(
                AgentType.RESEARCHER, user_client.model_name if user_client else None
            )
        ]
        researcher_subagent = ResearcherAgent(
            sandbox=sandbox,
            tools=researcher_tool,
            context_manager=context_manager,
            event_stream=event_stream,
            max_turns=max_turns,
            config=self.config,
            user_client=user_client,
            session_id=session_id,
            run_id=run_id,
        )
        return researcher_subagent

    async def create_design_document_agent(
        self,
        llm_client: LLMClient,
        tools: List[BaseTool],
        context_manager: ContextManager,
        event_stream: EventStream,
        max_turns: int = 200,
        tool_args: dict[str, Any] | None = None,
        session_id: Optional[UUID] = None,
        run_id: Optional[UUID] = None,
    ) -> BaseAgentTool:
        from ii_agent.sub_agent.design_document_agent import (
            SYSTEM_PROMPT as DESIGN_DOC_PROMPT,
        )

        design_document_tools = AgentTypeConfig.get_allowed_toolset(
            AgentType.DESIGN_DOCUMENT
        )
        if tool_args is not None and tool_args.get("media_generation"):
            design_document_tools.extend(
                AgentTypeConfig.get_allowed_toolset(AgentType.MEDIA)
            )
        if tool_args is not None and tool_args.get("browser"):
            design_document_tools.extend(
                AgentTypeConfig.get_allowed_toolset(AgentType.BROWSER)
            )

        model_name = llm_client.model_name if llm_client else None
        design_document_tools = AgentTypeConfig.get_allowed_toolset(
            AgentType.DESIGN_DOCUMENT, model_name
        )
        if tool_args is not None and tool_args.get("media_generation"):
            design_document_tools.extend(
                AgentTypeConfig.get_allowed_toolset(AgentType.MEDIA, model_name)
            )

        tools = [tool for tool in tools if tool.name in set(design_document_tools)]
        system_prompt = DESIGN_DOC_PROMPT
        design_agent_config = AgentConfig(
            max_tokens_per_turn=self.config.max_output_tokens_per_turn,
            system_prompt=system_prompt,
        )
        sub_agent = FunctionCallAgent(
            llm=llm_client,
            config=design_agent_config,
            tools=[
                ToolParam(
                    name=tool.name,
                    description=tool.description,
                    input_schema=tool.input_schema,
                )
                for tool in tools
            ],
        )
        design_document_agent = DesignDocumentAgent(
            agent=sub_agent,
            tools=tools,
            context_manager=context_manager,
            event_stream=event_stream,
            max_turns=max_turns,
            config=self.config,
            session_id=session_id,
            run_id=run_id,
        )
        return design_document_agent

    async def create_agent(
        self,
        llm_config: LLMConfig,
        sandbox: IISandbox,
        workspace_manager: WorkspaceManager,
        event_stream: EventStream,
        agent_task: AgentRunTask,
        system_prompt: Optional[str] = None,
        agent_type: AgentType = AgentType.GENERAL,
        tool_args: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> AgentController:
        """Create a new agent instance following CLI patterns.

        Args:
            llm_config: LLM client instance
            session_id: Session UUID
            sandbox_public_port_url_generator: Generator for sandbox public port URL
            workspace_manager: Workspace manager instance
            event_stream: AsyncEventStream for event handling
            tool_args: Tool configuration arguments
            system_prompt: Optional custom system prompt

        Returns:
            AgentController: The controller for the created agent
        """

        llm_client: LLMClient = get_client(llm_config)
        # Create context manager
        token_counter = TokenCounter()
        context_manager = LLMCompact(
            client=llm_client,
            token_counter=token_counter,
            token_budget=self.config.token_budget,
        )
        mcp_sandbox_url = await sandbox.expose_port(self.config.mcp_port) + "/mcp/"

        # Determine system prompt
        if system_prompt is None:
            # Extract flags from tool_args
            design_document = (
                tool_args.get("design_document", False) if tool_args else False
            )
            researcher = tool_args.get("deep_research", False) if tool_args else False
            media = tool_args.get("media_generation", False) if tool_args else False
            browser = tool_args.get("browser", False) if tool_args else False

            system_prompt = await get_system_prompt_for_agent_type(
                agent_type,
                workspace_manager.root.absolute().as_posix(),
                design_document=design_document,
                researcher=researcher,
                media=media,
                browser=browser,
                metadata=metadata,
            )

        model_name = llm_client.model_name if llm_client else None

        # Create agent config
        agent_config = AgentConfig(
            max_tokens_per_turn=self.config.max_output_tokens_per_turn,
            system_prompt=system_prompt,
            temperature=getattr(self.config, "temperature", 0.7),
        )

        # Create tool manager and register tools
        tool_manager = AgentToolManager()

        # First, get core sandbox tools to see what's already available
        all_sandbox_tools = await load_tools_from_mcp(
            mcp_sandbox_url,
            timeout=self.config.mcp_timeout,
            sandbox_client=sandbox.client,
            sandbox_id=sandbox.sandbox_id,
        )
        # ==============================================================
        ### Sub Agents Tool Registration
        # ==============================================================
        # Task Sub Agent
        task_subagent = await self.create_task_agent(
            llm_client=llm_client,
            tools=all_sandbox_tools,
            context_manager=context_manager,
            event_stream=event_stream,
            tool_args=tool_args,
            session_id=uuid.UUID(agent_task.session_id),
            run_id=agent_task.id,  # type: ignore
        )
        tool_manager.register_tools([task_subagent])

        # Register Deep Research agent if enabled
        if tool_args is not None and tool_args.get("deep_research"):
            researcher_subagent = await self.create_researcher_agent(
                sandbox=sandbox,
                tools=all_sandbox_tools,  # type: ignore
                context_manager=context_manager,
                event_stream=event_stream,
                user_client=llm_client if llm_config.is_user_model() else None,
                session_id=uuid.UUID(agent_task.session_id),
                run_id=agent_task.id,  # type: ignore
            )
            tool_manager.register_tools([researcher_subagent])

        # Register design document agent if enabled
        if tool_args is not None and tool_args.get("design_document"):
            design_doc_agent = await self.create_design_document_agent(
                llm_client=llm_client,
                tools=all_sandbox_tools, # type: ignore
                context_manager=context_manager,
                event_stream=event_stream,
                tool_args=tool_args,
                session_id=uuid.UUID(agent_task.session_id), # type: ignore
                run_id=agent_task.id,  # type: ignore
            )
            tool_manager.register_tools([design_doc_agent])

        # Register Codex agent if enabled and codex port is set
        if tool_args is not None and tool_args.get("codex_tools"):
            # register codex port and check for available
            url = await sandbox.expose_port(self.config.codex_port)
            # health check url/codex/health by httpx
            codex_health_url = f"{url}/health"
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(codex_health_url)
                if response.status_code == 200:
                    logger.info("Codex server is available, registering Codex tool.")

                    codex_tool = CodexAgent(
                        event_stream=event_stream,
                        codex_url=f"{url}/messages",
                        session_id=uuid.UUID(str(agent_task.session_id)),  # type: ignore
                        run_id=agent_task.id,  # type: ignore
                    )
                    tool_manager.register_tools([codex_tool])
                else:
                    logger.warning(
                        f"Codex health check failed with status {response.status_code}"
                    )

        # ==============================================================
        ### Register All Other Sandbox And MCP Tools
        # ==============================================================
        all_common_tools = get_common_tools(
            sandbox=IISandboxToSandboxInterfaceAdapter(sandbox)
        )
        # Log loaded MCP tools count
        tool_names = [tool.name for tool in all_sandbox_tools]
        logger.info(f"Loaded {len(all_sandbox_tools)} MCP tools: {tool_names}")

        # Get allowed tools for this agent type
        # Pass model_name to customize toolset (e.g., use ApplyPatchTool for GPT-5)
        model_name = llm_client.model_name if llm_client else None
        allowed_tool_names = AgentTypeConfig.get_allowed_toolset(agent_type, model_name)
        # Add Media tool to allowed tool set if available
        if tool_args is not None and tool_args.get("media_generation"):
            allowed_tool_names.extend(
                AgentTypeConfig.get_allowed_toolset(AgentType.MEDIA, model_name)
            )
        if tool_args is not None and tool_args.get("browser"):
            allowed_tool_names.extend(
                AgentTypeConfig.get_allowed_toolset(AgentType.BROWSER)
            )

        tool_manager.register_tools(
            [
                tool
                for tool in [
                    *all_common_tools,
                    *all_sandbox_tools,
                ]
                if (tool.name in allowed_tool_names or (tool.name.startswith("mcp_")))
            ]
        )

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

        # Create or restore state
        state = State()
        try:
            state.restore_from_session(agent_task.session_id, self.file_store)  # type: ignore
            logger.info(f"Restored state from session {agent_task.session_id}")
        except FileNotFoundError:
            logger.info(f"No history found for session {agent_task.session_id}")

        controller = AgentController(
            agent=agent,
            tool_manager=tool_manager,
            history=state,
            event_stream=event_stream,
            context_manager=context_manager,
            interactive_mode=True,
            config=self.config,
            session_id=uuid.UUID(agent_task.session_id),  # type: ignore
            run_id=agent_task.id,  # type: ignore
        )

        return controller
