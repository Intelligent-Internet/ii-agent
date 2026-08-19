"""Browser-extension specific agent factory.

Builds an :class:`IIAgent` for one ii-browser request. Nothing from the
core ii-agent tool/skill catalog is loaded by default — the agent starts
empty and only gains the capabilities the request explicitly asks for via
``requested_capabilities``, gated by the allow-lists in
:mod:`~ii_agent.clients.browser_extension.config`.
"""

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
from ii_agent.clients.browser_extension.config import (
    BROWSER_EXTENSION_DEFAULT_CONNECTORS,
    BROWSER_EXTENSION_DEFAULT_CORE_SKILLS,
    BROWSER_EXTENSION_DEFAULT_CORE_TOOLS,
    CLIENT_SKILL_HEADING,
    DEFAULT_SYSTEM_PROMPT,
    LOG_PREFIX,
    CLIENT_PROMPT_MODE_KEY,
    CLIENT_PROMPT_HEADING,
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


class BrowserExtensionAgentFactory:
    """Build a runtime-configured ``IIAgent`` for the ii-browser extension.

    Capability sources, in the order the factory composes them:

    1. **Client-defined tools** (``requested_capabilities.client_tools``) —
       external Functions whose execution happens entirely inside the
       extension; ii-agent pauses on each call until the extension returns
       ``external_tool_results``.
    2. **Client-defined skills** (``requested_capabilities.client_skills``)
       — appended to the system prompt as an advisory catalog.
    3. **Core tools** (``requested_capabilities.core_tools``) — taken from
       the request as-is. Falls back to
       :data:`BROWSER_EXTENSION_DEFAULT_CORE_TOOLS` when the request is
       silent.
    4. **Core skills** (``requested_capabilities.core_skills``) — taken
       from the request as-is, pulled from the user's persisted
       ``SkillTool`` registry. Falls back to
       :data:`BROWSER_EXTENSION_DEFAULT_CORE_SKILLS` when silent.
    5. **Connector tools** (``requested_capabilities.connector``) — taken
       from the request when a ``connector_tool`` is wired through. Falls
       back to a value from :data:`BROWSER_EXTENSION_DEFAULT_CONNECTORS`
       when silent.
    """

    def __init__(self, factory: AgentFactory):
        self._factory = factory

    async def create_agent(
        self,
        user_id: str,
        session_id: str,
        llm_config: LLMConfig,
        agent_type: AgentType = AgentType.BROWSER_EXTENSION,
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
            "Creating browser_extension %s agent for session %s",
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
                "[browser_extension] Added %d client-defined tools",
                len(client_tools),
            )
        # Client skills — lazy-loaded. The system prompt gets a compact
        # catalog (id + name + description + triggers); bodies are
        # resolved on demand by the client-side `load_client_skill`
        # tool (shipped via `requested_capabilities.client_tools`) so
        # skill content never bloats every turn's context.
        client_skill_prompt = build_client_skill_prompt(
            capabilities.client_skills,
            heading=CLIENT_SKILL_HEADING,
            loader_tool_name="load_client_skill",
        )

        # Core tools — user's request wins; default kicks in if request is empty.
        core_tools = include_core_tools(
            capabilities.core_tools,
            default_core_tools=BROWSER_EXTENSION_DEFAULT_CORE_TOOLS,
            log_prefix=LOG_PREFIX,
        )
        if core_tools:
            agent_tools.extend(core_tools)
            logger.info(
                "[browser_extension] Added %d core tools", len(core_tools)
            )

        skill_tool, core_skill_prompt = await include_core_skills(
            capabilities.core_skills,
            skill_creator=skill_creator,
            default_core_skills=BROWSER_EXTENSION_DEFAULT_CORE_SKILLS,
            log_prefix=LOG_PREFIX,
        )
        if skill_tool is not None:
            agent_tools.append(skill_tool)
            logger.info(
                "[browser_extension] Added SkillTool with %d skills",
                len(skill_tool._skills_registry),
            )

        # Connector — user's choice unless missing, then first default.
        connector_tools = await include_connector_tools(
            capabilities.connector,
            connector_tool=connector_tool,
            workspace_manager=workspace_manager,
            default_connectors=BROWSER_EXTENSION_DEFAULT_CONNECTORS,
            log_prefix=LOG_PREFIX,
        )
        if connector_tools:
            agent_tools.extend(connector_tools)

        # Final assembly
        agent_tools = dedupe_tools(agent_tools)
        AgentToolManager.log_tool_summary(
            agent_tools, f"browser_extension agent {agent_type.value}"
        )

        model = get_model(llm_config.provider, llm_config=llm_config)

        if not system_prompt:
            system_prompt = DEFAULT_SYSTEM_PROMPT
        # Mode fragment goes first so the model reads "what can I do this
        # turn" before the skill catalogs that depend on those capabilities.
        # Unknown keys inside ``client_prompt`` are ignored (the proxy layer
        # ships the dict through verbatim — see proxy_capabilities.py).
        client_mode_prompt = _build_client_mode_prompt(capabilities.client_prompt)
        if client_mode_prompt:
            logger.info(
                "[browser_extension] Folded client_prompt.%s into system prompt",
                CLIENT_PROMPT_MODE_KEY,
            )
        for prompt_section in (
            client_mode_prompt,
            client_skill_prompt,
            core_skill_prompt,
        ):
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
            "[browser_extension] Created %s agent with %d tools",
            agent_type.value,
            len(agent_tools),
        )
        return agent


browser_extension_agent_factory = BrowserExtensionAgentFactory(default_agent_factory)


def _build_client_mode_prompt(client_prompt: dict[str, Any]) -> Optional[str]:
    """Render the ``client_prompt.mode`` fragment for the system prompt.

    The ii-browser extension ships a short turn-scoped instruction here
    so the LLM knows whether this turn has the full agent toolset or only
    the read-only chat subset (and, in chat mode, that it should suggest
    a mode switch when the user asks for an action that's been filtered
    out of ``client_tools``). See ``services/chat/chatMode.ts`` in the
    browser extension for the canonical wording.

    Returns ``None`` when no usable fragment is present so the caller can
    skip the section without sprinkling ``if`` checks at every join site.
    """
    if not client_prompt:
        return None
    mode = client_prompt.get(CLIENT_PROMPT_MODE_KEY)
    if not isinstance(mode, str):
        return None
    mode = mode.strip()
    if not mode:
        return None
    return f"{CLIENT_PROMPT_HEADING}\n\n{mode}"
