from __future__ import annotations

from typing import Any, Dict, List, Optional

from ii_agent.agents.agent import IIAgent
from ii_agent.agents.connector.base import BaseConnectorTool
from ii_agent.agents.factory.agent import AgentFactory, agent_factory as default_agent_factory
from ii_agent.agents.factory.tool_manager import AgentToolManager
from ii_agent.agents.models.utils import get_model
from ii_agent.agents.sessions.base import SessionStore
from ii_agent.agents.skills.base import SkillCreator
from ii_agent.agents.types import AgentType
from ii_agent.clients.cowork.config import (
    COWORK_DEFAULT_CONNECTORS,
    COWORK_DEFAULT_CORE_SKILLS,
    COWORK_DEFAULT_CORE_TOOLS,
    CLIENT_SKILL_HEADING,
    DEFAULT_SYSTEM_PROMPT,
    LOG_PREFIX,
)
from ii_agent.clients.proxy_capabilities import (
    RequestedCapabilities,
    build_client_skill_prompt,
    build_client_tools,
    dedupe_tools,
    include_connector_tools,
    include_core_skills,
    include_core_tools,
)
from ii_agent.core.config.llm_config import LLMConfig
from ii_agent.core.logger import logger
from ii_server.core.workspace import WorkspaceManager


class CoworkAgentFactory:
    """Build a runtime-configured ``IIAgent`` for the cowork mode."""

    def __init__(self, factory: AgentFactory):
        self._factory = factory

    async def create_agent(
        self,
        user_id: str,
        session_id: str,
        llm_config: LLMConfig,
        agent_type: AgentType = AgentType.COWORK,
        workspace_manager: Optional[WorkspaceManager] = None,
        session_store: Optional[SessionStore] = None,
        tool_args: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        system_prompt: Optional[str] = None,
        skill_creator: Optional[SkillCreator] = None,
        connector_tool: Optional[BaseConnectorTool] = None,
        requested_capabilities: Optional[Any] = None,
    ) -> IIAgent:
        logger.info(
            "Creating cowork %s agent for session %s",
            agent_type,
            session_id,
        )

        capabilities = RequestedCapabilities.parse(requested_capabilities)
        agent_tools: List[Any] = []

        # Client-defined
        client_tools = build_client_tools(
            capabilities.client_tools, log_prefix=LOG_PREFIX
        )
        if client_tools:
            agent_tools.extend(client_tools)
            logger.info(
                "[cowork] Added %d client-defined tools",
                len(client_tools),
            )
        client_skill_prompt = build_client_skill_prompt(
            capabilities.client_skills, heading=CLIENT_SKILL_HEADING
        )

        # Core tools — user's request wins; default kicks in if request is empty.
        core_tools = include_core_tools(
            capabilities.core_tools,
            default_core_tools=COWORK_DEFAULT_CORE_TOOLS,
            log_prefix=LOG_PREFIX,
        )
        if core_tools:
            agent_tools.extend(core_tools)
            logger.info(
                "[cowork] Added %d core tools", len(core_tools)
            )

        skill_tool, core_skill_prompt = await include_core_skills(
            capabilities.core_skills,
            skill_creator=skill_creator,
            default_core_skills=COWORK_DEFAULT_CORE_SKILLS,
            log_prefix=LOG_PREFIX,
        )
        if skill_tool is not None:
            agent_tools.append(skill_tool)
            logger.info(
                "[cowork] Added SkillTool with %d skills",
                len(skill_tool._skills_registry),
            )

        # Connector — user's choice unless missing, then first default.
        connector_tools = await include_connector_tools(
            capabilities.connector,
            connector_tool=connector_tool,
            workspace_manager=workspace_manager,
            default_connectors=COWORK_DEFAULT_CONNECTORS,
            log_prefix=LOG_PREFIX,
        )
        if connector_tools:
            agent_tools.extend(connector_tools)

        # Final assembly
        agent_tools = dedupe_tools(agent_tools)
        AgentToolManager.log_tool_summary(
            agent_tools, f"cowork agent {agent_type.value}"
        )

        model = get_model(llm_config.provider, llm_config=llm_config)

        if not system_prompt:
            system_prompt = DEFAULT_SYSTEM_PROMPT
        for prompt_section in (client_skill_prompt, core_skill_prompt):
            if prompt_section:
                system_prompt = f"{system_prompt}\n\n{prompt_section}"

        agent = IIAgent(
            user_id=user_id,
            session_id=session_id,
            model=model,
            name=f"{agent_type.value}_agent",
            tools=agent_tools,
            system_message=system_prompt,
            session_store=session_store,
            metadata=metadata,
            sub_agents=[],
            retries=0,
            stream=True,
            stream_events=True,
            store_events=True,
        )
        agent.set_id()

        logger.info(
            "[cowork] Created %s agent with %d tools",
            agent_type.value,
            len(agent_tools),
        )
        return agent


cowork_agent_factory = CoworkAgentFactory(default_agent_factory)
