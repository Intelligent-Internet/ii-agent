from datetime import datetime, timezone
from typing import Any, List

from openai import OpenAI
from pydantic import SecretStr

from ii_agent.agents.codeact import CodeActAgent
from ii_agent.core.config.agent_config import AgentConfig
from ii_agent.core.config.llm_config import LLMConfig
from ii_agent.core.event_stream import EventStream
from ii_agent.llm.openai import OpenAIDirectClient
from ii_agent.prompts.researcher_system_prompt import ConfigConstants, ResearcherConfig
from ii_tool.core.config import WebSearchConfig, WebVisitConfig
from ii_tool.tools.base import BaseTool, ToolResult
from ii_agent.llm.context_manager.base import ContextManager
from ii_tool.core.workspace import WorkspaceManager
from ii_tool.tools.agent.base import BaseAgentTool
from ii_tool.tools.web.web_visit_tool import WebVisitTool
from ii_tool.tools.web.web_search_tool import WebSearchTool


class ResearcherAgent(BaseAgentTool):
    name: str = "researcher"
    display_name: str = "Researcher Agent"
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
    read_only = True

    def __init__(
        self,
        context_manager: ContextManager,
        event_stream: EventStream,
        workspace_manager: WorkspaceManager,
        max_turns: int = 200,
    ):
        llm_config = LLMConfig(model = "r1", api_key = SecretStr("dummy"), base_url = "http://localhost:4000/v1", stop_sequence=[ConfigConstants.THINK_TAG_CLOSE])
        tools = [
            WebVisitTool(settings=WebVisitConfig()),
            WebSearchTool(settings=WebSearchConfig()),
        ]
        agent_config = AgentConfig(
            system_prompt=ResearcherConfig().system_prompt,
        )
        researcher_agent = CodeActAgent(
            llm=OpenAIDirectClient(llm_config = llm_config),
            config=agent_config,
            tools=tools,
        )
        super().__init__(
            agent=researcher_agent,
            tools=tools,
            context_manager=context_manager,
            event_stream=event_stream,
            workspace_manager=workspace_manager,
            max_turns=max_turns,
        )
    

    async def execute(self, tool_input: dict[str, Any]) -> ToolResult:
        agent_controller = self._setup_agent_controller()
        
        agent_output = await agent_controller.run_impl(
            tool_input={
                "instruction": tool_input["instruction"],
                "report_type": tool_input["report_type"],
            }
        )
        return ToolResult(
            llm_content=agent_output.llm_content,
            user_display_content=agent_output.user_display_content
        )

    async def execute_mcp_wrapper(
        self,
        description: str,
        prompt: str,
    ):
        return await self._mcp_wrapper(
            tool_input={
                "instruction": prompt,
                "report_type": description,
            }
        )
    