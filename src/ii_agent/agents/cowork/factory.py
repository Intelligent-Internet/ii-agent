"""Cowork-specific agent creation helpers."""

from typing import Any, Dict, List, Optional

from ii_agent.core.config.llm_config import LLMConfig
from ii_agent.core.logger import logger
from ii_agent.agents.prompts.agent_prompts import get_system_prompt_for_agent_type
from ii_server.core.workspace import WorkspaceManager
from ii_agent.agents.agent import IIAgent
from ii_agent.agents.connector.base import BaseConnectorTool
from ii_agent.agents.cowork.desktop_proxy_tools import (
    build_desktop_proxy_tools,
    build_desktop_skill_context,
)
from ii_agent.agents.factory.agent import AgentFactory
from ii_agent.agents.factory.tool_manager import AgentToolManager
from ii_agent.agents.factory.tools import AgentType, TOOL_CLASS_MAP
from ii_agent.agents.models.utils import get_model
from ii_agent.agents.sessions.base import SessionStore
from ii_agent.agents.skills.base import SkillCreator
from ii_agent.agents.skills.prompt_db import generate_skill_tool_description
from ii_agent.settings.llm import Provider

class CoworkAgentFactory:
    """Factory for cowork-specific IIAgent creation with runtime overrides."""

    def __init__(self, factory: AgentFactory):
        self.factory = factory

    @staticmethod
    def _normalize_name_list(values: Optional[List[str]]) -> Optional[set[str]]:
        if not values:
            return None
        normalized = {
            value.strip().lower()
            for value in values
            if isinstance(value, str) and value.strip()
        }
        return normalized or None

    def _apply_skill_name_overrides(self, skill_tool, skill_names: Optional[List[str]]):
        requested_skill_names = self._normalize_name_list(skill_names)
        if skill_tool is None or not requested_skill_names:
            return skill_tool

        filtered_registry = {
            name: skill
            for name, skill in skill_tool._skills_registry.items()
            if name.strip().lower() in requested_skill_names
        }
        missing_skill_names = requested_skill_names - {
            name.strip().lower() for name in skill_tool._skills_registry.keys()
        }
        if missing_skill_names:
            logger.warning(
                f"Requested cowork skills were not found: {sorted(missing_skill_names)}"
            )

        if not filtered_registry:
            logger.warning("Cowork skill override removed all available skills")
            return None

        skill_tool._skills_registry = filtered_registry
        skill_tool.description = generate_skill_tool_description(list(filtered_registry.values()))
        return skill_tool

    def _add_requested_tools(
        self,
        agent_tools: List[Any],
        requested_tool_names: Optional[List[str]],
    ) -> List[Any]:
        normalized_requested = self._normalize_name_list(requested_tool_names)
        if not normalized_requested:
            return agent_tools

        existing_names = {
            tool.name.strip().lower() for tool in agent_tools if hasattr(tool, "name")
        }
        missing_tool_names = normalized_requested - existing_names
        for tool_name in missing_tool_names:
            requested_tool = None
            for registered_tool_name in TOOL_CLASS_MAP.keys():
                if registered_tool_name.strip().lower() == tool_name:
                    requested_tool = AgentToolManager.convert_tool(registered_tool_name)
                    break
            if requested_tool is None:
                logger.warning(f"Requested cowork tool `{tool_name}` is not registered")
                continue
            agent_tools.append(requested_tool)

        return agent_tools

    def _filter_tools_by_name(
        self,
        agent_tools: List[Any],
        requested_tool_names: Optional[List[str]],
    ) -> List[Any]:
        normalized_requested = self._normalize_name_list(requested_tool_names)
        if not normalized_requested:
            return agent_tools

        filtered_tools = [
            tool
            for tool in agent_tools
            if getattr(tool, "name", "").strip().lower() in normalized_requested
        ]
        found_tool_names = {
            getattr(tool, "name", "").strip().lower()
            for tool in filtered_tools
            if hasattr(tool, "name")
        }
        missing_tool_names = normalized_requested - found_tool_names
        if missing_tool_names:
            logger.warning(
                f"Requested cowork tools were not created: {sorted(missing_tool_names)}"
            )

        return filtered_tools

    @staticmethod
    def _dedupe_tools_by_name(agent_tools: List[Any]) -> List[Any]:
        unique_tools: List[Any] = []
        seen_names: set[str] = set()
        for tool in agent_tools:
            tool_name = getattr(tool, "name", None)
            if not tool_name:
                unique_tools.append(tool)
                continue
            normalized_name = tool_name.strip().lower()
            if normalized_name in seen_names:
                continue
            seen_names.add(normalized_name)
            unique_tools.append(tool)
        return unique_tools

    @staticmethod
    def _build_agent_runtime_config(
        agent_type: AgentType,
        agent_config: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        config_overrides = agent_config or {}
        return {
            "name": config_overrides.get("name", f"{agent_type.value}_agent"),
            "description": config_overrides.get("description"),
            "additional_context": config_overrides.get("additional_context"),
            "tool_call_limit": config_overrides.get("tool_call_limit"),
            "tool_choice": config_overrides.get("tool_choice"),
            "retries": config_overrides.get("retries", 0),
            "delay_between_retries": config_overrides.get("delay_between_retries", 1),
            "exponential_backoff": config_overrides.get("exponential_backoff", False),
            "stream": config_overrides.get("stream", True),
            "stream_events": config_overrides.get("stream_events", True),
            "store_events": config_overrides.get("store_events", True),
            "delegate_to_all_members": config_overrides.get("delegate_to_all_members", False),
            "stream_member_events": config_overrides.get("stream_member_events", True),
            "store_member_responses": config_overrides.get("store_member_responses", False),
            "role": config_overrides.get("role"),
        }

    @staticmethod
    def _get_cowork_metadata(metadata: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        if not isinstance(metadata, dict):
            return {}
        cowork_metadata = metadata.get("cowork")
        return cowork_metadata if isinstance(cowork_metadata, dict) else {}

    @classmethod
    def _is_desktop_execution_mode(cls, metadata: Optional[Dict[str, Any]]) -> bool:
        cowork_metadata = cls._get_cowork_metadata(metadata)
        return cowork_metadata.get("execution_context") == "desktop"

    @classmethod
    def _uses_desktop_proxy_tools(cls, metadata: Optional[Dict[str, Any]]) -> bool:
        cowork_metadata = cls._get_cowork_metadata(metadata)
        return cls._is_desktop_execution_mode(metadata) and cowork_metadata.get(
            "tool_runtime"
        ) in {
            "desktop_builtin",
            "desktop_proxy",
        }

    @classmethod
    def _uses_desktop_tools_exclusively(cls, metadata: Optional[Dict[str, Any]]) -> bool:
        cowork_metadata = cls._get_cowork_metadata(metadata)
        binding_mode = cowork_metadata.get("tool_binding_mode")
        if binding_mode is None:
            binding_mode = "desktop_only" if cls._uses_desktop_proxy_tools(metadata) else None
        return cls._uses_desktop_proxy_tools(metadata) and binding_mode == "desktop_only"

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
        tool_names: Optional[List[str]] = None,
        skill_names: Optional[List[str]] = None,
        desktop_capabilities: Optional[Dict[str, Any]] = None,
        agent_config: Optional[Dict[str, Any]] = None,
    ) -> IIAgent:
        logger.info(f"Creating cowork {agent_type} agent for session {session_id}")

        tool_args = tool_args or {}
        has_media = tool_args.get("media_generation", False)
        has_task_agent = tool_args.get("task_agent", False)
        has_researcher = tool_args.get("deep_research", False)
        has_design_doc = tool_args.get("design_document", False)

        provider = llm_config.provider
        model = get_model(provider, llm_config=llm_config)

        uses_desktop_proxy_tools = self._uses_desktop_proxy_tools(metadata)
        uses_desktop_tools_exclusively = self._uses_desktop_tools_exclusively(metadata)

        if uses_desktop_tools_exclusively:
            agent_tools = build_desktop_proxy_tools(
                desktop_capabilities=desktop_capabilities,
                requested_tool_names=tool_names,
            )
            logger.info("Cowork desktop tool runtime enabled; using desktop proxy tools only")
        else:
            agent_tools = AgentToolManager.resolve_tools(
                agent_type=agent_type,
                model_name=model.id,
                tool_args=tool_args,
            )
            agent_tools = self._add_requested_tools(agent_tools, tool_names)
            if uses_desktop_proxy_tools:
                agent_tools.extend(
                    build_desktop_proxy_tools(
                        desktop_capabilities=desktop_capabilities,
                        requested_tool_names=tool_names,
                    )
                )
                logger.info("Cowork desktop tool runtime enabled; merging desktop proxy tools")

        if skill_creator is not None and not uses_desktop_tools_exclusively:
            skill_tool = await skill_creator.create_skill_tool()
            skill_tool = self._apply_skill_name_overrides(skill_tool, skill_names)
            if skill_tool:
                agent_tools.append(skill_tool)
                logger.info(f"Added SkillTool with {len(skill_tool._skills_registry)} skills")

        if connector_tool is not None and not uses_desktop_tools_exclusively:
            try:
                connector_tools = await connector_tool.create_connector_tools(
                    workspace_manager=workspace_manager,
                )
                if connector_tools:
                    logger.info(
                        f"[Cowork Factory] Received {len(connector_tools)} connector tools from loader"
                    )
                    logger.debug(
                        f"[Cowork Factory] Connector tool names: {[t.name for t in connector_tools]}"
                    )
                    agent_tools.extend(connector_tools)
            except Exception as e:
                logger.error(
                    f"[Cowork Factory] Failed to load connector tools: {e}", exc_info=True
                )

        agent_tools = self._filter_tools_by_name(agent_tools, tool_names)
        agent_tools = self._dedupe_tools_by_name(agent_tools)
        AgentToolManager.log_tool_summary(agent_tools, f"Cowork agent {agent_type.value}")

        if system_prompt is None:
            workspace_path = (
                workspace_manager.workspace_path.as_posix()
                if workspace_manager
                else "/workspace"
            )
            system_prompt = await get_system_prompt_for_agent_type(
                agent_type=agent_type,
                workspace_path=workspace_path,
                design_document=has_design_doc,
                researcher=has_researcher,
                media=has_media,
                a2a_agents=False,
                task_agent=has_task_agent,
                metadata=metadata,
                provider=llm_config.provider if llm_config else None,
            )

        desktop_skill_context = build_desktop_skill_context(
            desktop_capabilities=desktop_capabilities,
            requested_skill_names=skill_names,
        )
        if desktop_skill_context:
            system_prompt = f"{system_prompt}\n\n{desktop_skill_context}"

        sub_agents = []
        if has_task_agent:
            task_agent = await self.factory.create_task_agent_tool(
                user_id=user_id,
                session_id=session_id,
                llm_config=llm_config,
                tool_args=tool_args,
            )
            sub_agents.append(task_agent)

        runtime_config = self._build_agent_runtime_config(
            agent_type=agent_type,
            agent_config=agent_config,
        )

        agent = IIAgent(
            user_id=user_id,
            session_id=session_id,
            model=model,
            name=runtime_config["name"],
            description=runtime_config["description"],
            additional_context=runtime_config["additional_context"],
            tools=agent_tools,
            tool_call_limit=runtime_config["tool_call_limit"],
            tool_choice=runtime_config["tool_choice"],
            system_message=system_prompt,
            session_store=session_store,
            metadata=metadata,
            sub_agents=sub_agents,
            retries=runtime_config["retries"],
            delay_between_retries=runtime_config["delay_between_retries"],
            exponential_backoff=runtime_config["exponential_backoff"],
            stream=runtime_config["stream"],
            stream_events=runtime_config["stream_events"],
            store_events=runtime_config["store_events"],
            delegate_to_all_members=runtime_config["delegate_to_all_members"],
            stream_member_events=runtime_config["stream_member_events"],
            store_member_responses=runtime_config["store_member_responses"],
            role=runtime_config["role"],
        )
        agent.set_id()

        logger.info(f"Created cowork {agent_type.value} agent with {len(agent_tools)} tools")
        return agent
