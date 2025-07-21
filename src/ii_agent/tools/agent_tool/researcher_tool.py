import asyncio
from typing import Any, Optional

from pathlib import Path
from pydantic import SecretStr
from ii_agent.controller.state import State
from ii_agent.core.config.llm_config import LLMConfig
from ii_agent.core.event_stream import AsyncEventStream
from ii_agent.llm.context_manager.llm_summarizing import LLMSummarizingContextManager
from ii_agent.llm.r1 import R1DirectClient
from ii_agent.llm.token_counter import TokenCounter
from ii_agent.prompts.researcher_system_prompt import ConfigConstants
from ii_agent.tools.base import LLMTool, ToolImplOutput
from ii_agent.llm.base import LLMClient
from ii_agent.core.config.agent_config import AgentConfig
from ii_agent.agents.researcher import ResearcherAgent
from ii_agent.tools.tool_manager import AgentToolManager
from ii_agent.tools.visit_webpage_tool import VisitWebpageTool
from ii_agent.tools.web_search_tool import WebSearchTool
from ii_agent.utils.constants import TOKEN_BUDGET
from ii_agent.utils.workspace_manager import WorkspaceManager
from ii_agent.llm.context_manager.base import ContextManager


class ResearcherTool(LLMTool):
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
        client: LLMClient,
        r1_client: LLMClient,
        agent_config: AgentConfig,
        workspace_manager: WorkspaceManager,
        event_stream: AsyncEventStream,
        context_manager: ContextManager,
    ):
        from ii_agent.controller.agent_controller import AgentController

        self.client = client
        self.agent_config = agent_config
        tools = [WebSearchTool(), VisitWebpageTool()]
        tool_manager = AgentToolManager(
            tools=tools,
        )
        researcher_agent = ResearcherAgent(
            r1_client, agent_config, tools=[tool.get_tool_param() for tool in tools]
        )
        self.agent_controller = AgentController(
            agent=researcher_agent,
            tool_manager=tool_manager,
            init_history=State(),
            workspace_manager=workspace_manager,
            event_stream=event_stream,
            context_manager=context_manager,
            interactive_mode=True,
        )

    async def run_impl(
        self, tool_input: dict[str, Any], state: Optional[State] = None
    ) -> ToolImplOutput:
        instruction = tool_input["instruction"]
        output = await self.agent_controller.run_agent_async(instruction)
        return ToolImplOutput(
            tool_output=output.agent_output, tool_result_message="Research finished."
        )


async def main():
    from ii_agent.prompts.researcher_system_prompt import get_config

    llm_config = LLMConfig(
        model="r1",
        base_url="http://localhost:4000",
        api_key=SecretStr("sk-123"),
        stop_sequence=ConfigConstants.DEFAULT_STOP_SEQUENCE,
    )
    r1_client = R1DirectClient(llm_config)

    # Initialize agent config
    system_prompt = get_config().system_prompt

    researcher_tool = ResearcherTool(
        client=r1_client,
        r1_client=r1_client,
        agent_config=AgentConfig(
            system_prompt=system_prompt,
        ),
        workspace_manager=WorkspaceManager(Path("./workspace")),
        event_stream=AsyncEventStream(),
        context_manager=LLMSummarizingContextManager(
            client=r1_client,
            token_counter=TokenCounter(),
            token_budget=TOKEN_BUDGET,
        ),
    )
    await researcher_tool.run_impl({"instruction": "What is the capital of France?"})


if __name__ == "__main__":
    asyncio.run(main())
