import asyncio
from typing import Any, Optional

from pathlib import Path
from pydantic import SecretStr
from ii_agent.controller.state import State
from ii_agent.core.config.llm_config import LLMConfig
from ii_agent.llm.base import ToolParam
from ii_agent.llm.context_manager.llm_summarizing import LLMSummarizingContextManager
from ii_agent.llm.r1 import R1DirectClient
from ii_agent.llm.token_counter import TokenCounter
from ii_agent.prompts.researcher_system_prompt import ConfigConstants
from ii_agent.agents.researcher import ResearcherAgent
from ii_agent.tools.tool_manager import AgentToolManager
from ii_tool.core.config import WebSearchConfig, WebVisitConfig
from ii_tool.mcp.server import create_mcp
from ii_tool.tools.base import BaseTool, ToolResult
from ii_tool.tools.web import WebSearchTool, WebVisitTool
from ii_agent.utils.constants import TOKEN_BUDGET

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from ii_agent.core.config.agent_config import AgentConfig
    from ii_agent.llm.base import LLMClient
    from ii_agent.llm.context_manager.base import ContextManager
    from ii_agent.utils.workspace_manager import WorkspaceManager
    from ii_agent.core.event_stream import AsyncEventStream
    from fastmcp.client import Client

class ResearcherTool(BaseTool):
    name: str = "researcher"
    description: str = "Researcher tool"
    input_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "instruction": {
                "type": "string",
                "description": "The instruction to perform deep research for",
            },
            "report_type": {
                "type": "string",
                "description": "The type of report to generate. Pick between 'basic' and 'advanced'",
            },
        },
        "required": ["instruction"],
    }

    def __init__(
        self,
        client: "LLMClient",
        r1_client: "LLMClient",
        mcp_client: "Client",
        agent_config: "AgentConfig",
        workspace_manager: "WorkspaceManager",
        event_stream: "AsyncEventStream",
        context_manager: "ContextManager",
    ):

        self.client = client
        self.agent_config = agent_config
        self.r1_client = r1_client
        self.mcp_client = mcp_client
        self.workspace_manager = workspace_manager
        self.event_stream = event_stream
        self.context_manager = context_manager
        self.agent_controller = None

    
    async def init_agent(self):
        from ii_agent.controller.agent_controller import AgentController
        web_search_config = WebSearchConfig()
        web_visit_config = WebVisitConfig()
        tools = [WebSearchTool(web_search_config), WebVisitTool(web_visit_config)]
        tool_manager = AgentToolManager()
        await tool_manager.register_mcp_tools(self.mcp_client, tools, trust=True)
        researcher_agent = ResearcherAgent(
            self.r1_client, self.agent_config, tools=[ToolParam(name=tool.name, description=tool.description, input_schema=tool.input_schema) for tool in tool_manager.get_tools()]
        )
        self.agent_controller = AgentController(
            agent=researcher_agent,
            tool_manager=tool_manager,
            init_history=State(),
            workspace_manager=self.workspace_manager,
            event_stream=self.event_stream,
            context_manager=self.context_manager,
            interactive_mode=True,
        )

    async def execute(
        self, tool_input: dict[str, Any], state: Optional[State] = None
    ) -> ToolResult:
        if not self.agent_controller:
            await self.init_agent()
        instruction = tool_input["instruction"]
        output = await self.agent_controller.run_agent_async(instruction) # type: ignore
        return ToolResult(
            llm_content=output.agent_output,
            user_display_content=output.agent_output,
            is_error=False,
        )
