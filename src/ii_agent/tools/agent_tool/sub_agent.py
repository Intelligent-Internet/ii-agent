from typing import ContextManager, List

from fastmcp.client import Client
from pydantic import SecretStr
from ii_agent.core.config.agent_config import AgentConfig
from ii_agent.core.event_stream import AsyncEventStream
from ii_agent.llm.context_manager.base import ContextManager
from ii_agent.llm.base import LLMClient
from ii_agent.llm.r1 import R1DirectClient
from ii_agent.prompts.researcher_system_prompt import CONFIG, ConfigConstants
from ii_agent.core.config.llm_config import LLMConfig
from ii_agent.tools.agent_tool.researcher_tool import ResearcherTool
from ii_agent.utils.workspace_manager import WorkspaceManager
from ii_tool.tools.base import BaseTool


def get_sub_agents(client: LLMClient,mcp_client: Client,workspace_manager: WorkspaceManager, event_stream: AsyncEventStream, context_manager: ContextManager) -> List[BaseTool]:
    agent_config = AgentConfig(system_prompt=CONFIG.system_prompt)
    llm_config = LLMConfig(
        model="r1",
        base_url="http://localhost:4000",
        api_key=SecretStr("sk-123"),
        stop_sequence=ConfigConstants.DEFAULT_STOP_SEQUENCE,
    )
    r1_client = R1DirectClient(llm_config)
    return [
        ResearcherTool(
            client=r1_client,
            r1_client=r1_client,
            mcp_client=mcp_client,
            agent_config=agent_config,
            workspace_manager=workspace_manager,
            event_stream=event_stream,
            context_manager=context_manager,
        )
    ]

