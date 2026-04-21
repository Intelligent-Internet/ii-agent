"""Agent factory for creating configured agent instances."""

from typing import Any, Dict, Optional
from uuid import UUID

from ii_agent.core.config.settings import Settings, get_settings
from ii_agent.core.config.llm_config import LLMConfig
from ii_agent.chat.base import LLMClient
from ii_server.core.workspace import WorkspaceManager
from ii_agent.agents.prompts.agent_prompts import get_system_prompt_for_agent_type
from ii_agent.agents.sandboxes import Sandbox
from ii_agent.agents.agent import IIAgent
from ii_agent.agents.skills.base import SkillCreator
from ii_agent.agents.connector import BaseConnectorTool
from ii_agent.agents.factory.tools import AgentConfigManager, AgentType
from ii_agent.agents.factory.tool_manager import AgentToolManager
from ii_agent.agents.models.utils import get_model
from ii_agent.agents.sessions import SessionStore
from ii_agent.agents.tools.task import SYSTEM_PROMPT, TaskAgentTool, DESCRIPTION
from ii_agent.core.logger import logger


def _append_prompt_section(base_prompt: Optional[str], section: Optional[str]) -> Optional[str]:
    """Append an extra XML/text block to the system prompt when present."""
    if not section:
        return base_prompt
    if not base_prompt:
        return section
    return f"{base_prompt}\n\n{section}"


class AgentFactory:
    """Factory for creating configured agent instances."""

    def __init__(self, config: Settings):
        """Initialize the agent factory.

        Args:
            config: II Agent configuration
        """
        self.config = config

    async def create_agent(
        self,
        user_id: str,
        session_id: str,
        llm_config: LLMConfig,
        agent_type: AgentType = AgentType.GENERAL,
        workspace_manager: Optional[WorkspaceManager] = None,
        session_store: Optional[SessionStore] = None,
        tool_args: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        system_prompt: Optional[str] = None,
        skill_creator: Optional[SkillCreator] = None,
        connector_tool: Optional[BaseConnectorTool] = None,
    ) -> IIAgent:
        """Create a configured agent instance.

        The factory filters the provided tools based on agent type configuration
        and tool_args. The caller is responsible for loading the tools.
        tools_enabled = {
            "deep_research": false,
            "design_document": false,
            "pdf": true,
            "media_generation": false,
            "audio_generation": false,
            "browser": true,
            "enable_reviewer": false,
            "codex_tools": false,
            "claude_code": false
        }

        Args:
            user_id: User ID
            session_id: Session ID
            llm_config: LLM configuration
            agent_type: Type of agent to create
            workspace_manager: Workspace manager instance
            session_store: Session store for persistence
            tool_args: Tool configuration arguments (media_generation, browser, etc.)
            metadata: Additional metadata
            system_prompt: Optional custom system prompt
            skill_creator: Optional skill creator for loading user-specific skills
            connector_tool: Optional connector tool for loading user-specific connectors

        Returns:
            Configured IIAgent instance
        """
        logger.info(f"Creating {agent_type} agent for session {session_id}")

        # Parse tool_args
        tool_args = tool_args or {}
        has_media = tool_args.get("media_generation", False)
        has_task_agent = tool_args.get("task_agent", False)
        has_researcher = tool_args.get("deep_research", False)
        has_design_doc = tool_args.get("design_document", False)

        # Get LLM client and model
        provider = llm_config.provider
        # Resolve model
        model = get_model(provider, llm_config=llm_config)

        # Resolve required tool names based on agent type, model, and tool_args
        agent_tools = AgentToolManager.resolve_tools(
            agent_type=agent_type,
            model_name=model.id,
            tool_args=tool_args,
        )

        # Add SkillTool if skill creator is available
        skill_prompt_section: Optional[str] = None
        if skill_creator is not None:
            skill_tool = await skill_creator.create_skill_tool()
            if skill_tool:
                agent_tools.append(skill_tool)
                skill_prompt_section = skill_tool.description
                logger.info(f"Added SkillTool with {len(skill_tool._skills_registry)} skills")

        # Add connector tools if available
        if connector_tool is not None:
            try:
                connector_tools = await connector_tool.create_connector_tools(
                    workspace_manager=workspace_manager,
                )
                if connector_tools:
                    logger.info(
                        f"[V1 Factory] Received {len(connector_tools)} connector tools from loader"
                    )
                    logger.debug(
                        f"[V1 Factory] Connector tool names: {[t.name for t in connector_tools]}"
                    )
                    agent_tools.extend(connector_tools)
                    logger.info(
                        f"[V1 Factory] Successfully added {len(connector_tools)} connector tools to agent"
                    )

            except Exception as e:
                logger.error(f"[V1 Factory] Failed to load connector tools: {e}", exc_info=True)

        AgentToolManager.log_tool_summary(agent_tools, f"Agent {agent_type.value}")

        # Generate system prompt if not provided
        if system_prompt is None:
            workspace_path = (
                workspace_manager.workspace_path.as_posix() if workspace_manager else "/workspace"
            )

            # Check if A2A agents are available (from metadata or config)
            has_a2a = False  # This would be determined by A2AManager in production

            system_prompt = await get_system_prompt_for_agent_type(
                agent_type=agent_type,
                workspace_path=workspace_path,
                design_document=has_design_doc,
                researcher=has_researcher,
                media=has_media,
                a2a_agents=has_a2a,
                task_agent=has_task_agent,
                metadata=metadata,
                provider=llm_config.provider if llm_config else None,
            )

        system_prompt = _append_prompt_section(system_prompt, skill_prompt_section)

        sub_agents = []
        if has_task_agent:
            task_agent = await self.create_task_agent_tool(
                user_id=user_id,
                session_id=session_id,
                llm_config=llm_config,
                tool_args=tool_args,
            )
            sub_agents.append(task_agent)

        # Create the agent
        agent = IIAgent(
            user_id=user_id,
            session_id=session_id,
            model=model,
            name=f"{agent_type.value}_agent",
            tools=agent_tools,
            system_message=system_prompt,
            session_store=session_store,
            metadata=metadata,
            sub_agents=sub_agents,
            retries=0,
            stream=True,
            stream_events=True,
            store_events=True,
        )

        # Set agent ID
        agent.set_id()

        logger.info(f"Created {agent_type.value} agent with {len(agent_tools)} tools")

        return agent

    async def create_general_agent(
        self,
        user_id: str,
        session_id: str,
        llm_config: LLMConfig,
        workspace_manager: Optional[WorkspaceManager] = None,
        session_store: Optional[SessionStore] = None,
        tool_args: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        system_prompt: Optional[str] = None,
        skill_creator: Optional[SkillCreator] = None,
        connector_tool: Optional[BaseConnectorTool] = None,
    ) -> IIAgent:
        """Create a general purpose agent.

        This is a convenience method for creating general agents.
        """
        return await self.create_agent(
            user_id=user_id,
            session_id=session_id,
            llm_config=llm_config,
            agent_type=AgentType.GENERAL,
            workspace_manager=workspace_manager,
            session_store=session_store,
            tool_args=tool_args,
            metadata=metadata,
            system_prompt=system_prompt,
            skill_creator=skill_creator,
            connector_tool=connector_tool,
        )

    def get_agent_config(self, agent_type: AgentType):
        """Get configuration for an agent type.

        Args:
            agent_type: The agent type

        Returns:
            AgentConfig for the type
        """
        return AgentConfigManager.get_config(agent_type)

    # ==================== Sub-Agent Creation Methods ====================

    async def create_task_agent_tool(
        self,
        user_id: str,
        session_id: str,
        llm_config: LLMConfig,
        tool_args: Optional[Dict[str, Any]] = None,
        run_id: Optional[UUID] = None,
    ):
        """Create a task agent as a tool for delegation.

        Args:
            llm_client: LLM client instance
            tools: List of loaded tool instances (will be filtered)
            context_manager: Context manager for the agent
            event_stream: Event stream for communication
            max_turns: Maximum conversation turns
            tool_args: Tool configuration arguments
            session_id: Session ID
            run_id: Run ID

        Returns:
            Task agent wrapped as a BaseAgentTool
        """

        logger.info("Creating task agent sub-agent tool")

        provider = llm_config.provider
        # Resolve model
        model = get_model(provider, llm_config=llm_config)
        # Resolve required tool names
        agent_tools = AgentToolManager.resolve_tools(
            agent_type=AgentType.TASK_AGENT,
            model_name=model.id,
            tool_args=tool_args,
        )

        task_agent = IIAgent(
            user_id=user_id,
            session_id=session_id,
            model=model,
            tools=agent_tools,
            name=TaskAgentTool.name,
            system_message=SYSTEM_PROMPT,
            description=DESCRIPTION,
            stream=True,
            stream_events=True,
            store_events=False,
        )

        # # Wrap in task agent tool
        # task_agent = TaskAgentTool(
        #     agent=task_agent,
        #     session_id=session_id,
        #     run_id=run_id,
        # )

        logger.info(f"Created task agent tool with {len(agent_tools)} tools")
        return task_agent

    async def create_researcher_agent_tool(
        self,
        context_manager,  # ContextManager type
        event_stream,  # EventStream type
        max_turns: int = 200,
        user_client: Optional[LLMClient] = None,
        session_id: Optional[UUID] = None,
        run_id: Optional[UUID] = None,
    ):
        """Create a researcher agent as a tool for delegation.

        Args:
            sandbox: Sandbox instance
            all_tools: All available tools to filter from
            context_manager: Context manager for the agent
            event_stream: Event stream for communication
            max_turns: Maximum conversation turns
            user_client: Optional user LLM client
            session_id: Session ID
            run_id: Run ID

        Returns:
            Researcher agent wrapped as a BaseAgentTool
        """
        from ii_agent.sub_agent.researcher_agent_tool import ResearcherAgent

        logger.info("Creating researcher agent sub-agent tool")

        # Get model name
        model_name = user_client.model_name if user_client else None

        # Resolve required tool names
        researcher_tools = AgentToolManager.resolve_tools(
            agent_type=AgentType.RESEARCHER,
            model_name=model_name,
            tool_args=None,
        )

        AgentToolManager.log_tool_summary(researcher_tools, "Researcher Agent")

        # Create researcher agent
        researcher_agent = ResearcherAgent(
            tools=researcher_tools,
            context_manager=context_manager,
            event_stream=event_stream,
            max_turns=max_turns,
            config=self.config,
            user_client=user_client,
            session_id=session_id,
            run_id=run_id,
        )

        logger.info(f"Created researcher agent tool with {len(researcher_tools)} tools")
        return researcher_agent

    async def create_design_document_agent_tool(
        self,
        llm_client: LLMClient,
        context_manager,  # ContextManager type
        event_stream,  # EventStream type
        max_turns: int = 200,
        tool_args: Optional[Dict[str, Any]] = None,
        session_id: Optional[UUID] = None,
        run_id: Optional[UUID] = None,
    ):
        """Create a design document agent as a tool for delegation.

        Args:
            llm_client: LLM client instance
            all_tools: All available tools to filter from
            context_manager: Context manager for the agent
            event_stream: Event stream for communication
            max_turns: Maximum conversation turns
            tool_args: Tool configuration arguments
            session_id: Session ID
            run_id: Run ID

        Returns:
            Design document agent wrapped as a BaseAgentTool
        """
        from ii_agent.sub_agent.design_document_agent import (
            DesignDocumentAgent,
            SYSTEM_PROMPT as DESIGN_DOC_PROMPT,
        )
        from ii_agent.agents.function_call import FunctionCallAgent
        from ii_agent.core.config.agent_config import AgentConfig
        from ii_agent.agents.tools.base import ToolParam

        logger.info("Creating design document agent sub-agent tool")

        # Parse tool args
        tool_args = tool_args or {}

        # Get model name
        model_name = llm_client.model_name if llm_client else None

        # Resolve required tool names
        design_document_tools = AgentToolManager.resolve_tools(
            agent_type=AgentType.DESIGN_DOCUMENT,
            model_name=model_name,
            tool_args=tool_args,
            include_mcp=True,
            include_connectors=True,
        )

        AgentToolManager.log_tool_summary(design_document_tools, "Design Document Agent")

        # Create agent config
        design_agent_config = AgentConfig(
            max_tokens_per_turn=self.config.agent.max_output_tokens_per_turn,
            system_prompt=DESIGN_DOC_PROMPT,
        )

        # Create the function call agent
        sub_agent = FunctionCallAgent(
            llm=llm_client,
            config=design_agent_config,
            tools=[
                ToolParam(
                    name=tool.name,
                    description=tool.description,
                    input_schema=tool.input_schema,
                )
                for tool in design_document_tools
            ],
        )

        # Wrap in design document agent tool
        design_doc_agent = DesignDocumentAgent(
            agent=sub_agent,
            tools=design_document_tools,
            context_manager=context_manager,
            event_stream=event_stream,
            max_turns=max_turns,
            config=self.config,
            session_id=session_id,
            run_id=run_id,
        )

        logger.info(f"Created design document agent tool with {len(design_document_tools)} tools")
        return design_doc_agent

    async def create_codex_agent_tool(
        self,
        sandbox: Sandbox,
        event_stream,  # EventStream type
        session_id: UUID,
        run_id: UUID,
    ):
        """Create a codex agent as a tool for delegation.

        Args:
            sandbox: Sandbox instance
            event_stream: Event stream for communication
            session_id: Session ID
            run_id: Run ID

        Returns:
            Codex agent wrapped as a BaseAgentTool, or None if not available
        """
        import httpx
        from ii_agent.sub_agent.codex import CodexAgent

        logger.info("Attempting to create codex agent sub-agent tool")

        # Check if codex server is available
        try:
            codex_url = await sandbox.expose_port(self.config.codex_port)
            codex_health_url = f"{codex_url}/health"

            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(codex_health_url)
                if response.status_code == 200:
                    logger.info("Codex server is available, registering Codex tool")

                    codex_agent = CodexAgent(
                        event_stream=event_stream,
                        codex_url=f"{codex_url}/messages",
                        session_id=session_id,
                        run_id=run_id,
                    )

                    logger.info("Created codex agent tool")
                    return codex_agent
                else:
                    logger.warning(f"Codex health check failed with status {response.status_code}")
                    return None
        except Exception as e:
            logger.warning(f"Failed to connect to codex server: {e}")
            return None


agent_factory = AgentFactory(config=get_settings())
