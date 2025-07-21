from datetime import datetime, timezone

from ii_agent.prompts.researcher_system_prompt import get_config
from ii_agent.controller.agent import Agent
from ii_agent.llm.base import (
    LLMClient,
    AssistantContentBlock,
    ThinkingBlock,
    ToolCall,
    ToolParam,
    ToolResult,
)
from ii_agent.controller.state import State
from ii_agent.core.config.agent_config import AgentConfig
from ii_agent.tools.web_search_tool import WebSearchTool
from ii_agent.tools.visit_webpage_tool import VisitWebpageTool
from ii_agent.core.config.llm_config import LLMConfig
from ii_agent.prompts.researcher_system_prompt import ConfigConstants


class ResearcherAgent(Agent):
    def __init__(self, llm: LLMClient, config: AgentConfig, tools: list[ToolParam]):
        """Initialize the agent.

        Args:
            llm: The LLM client to use
            config: The configuration for the agent
        """
        super().__init__(llm, config, tools)

    @property
    def system_prompt(self):
        if self.config.system_prompt is not None:
            return self.config.system_prompt.format(
                current_date=datetime.now(timezone.utc).isoformat(),
                available_tools="\n".join(
                    [
                        f"- {tool.name}: {tool.description} with input schema: {tool.input_schema}"
                        for tool in self.tools
                    ]
                ),
            )
        return None

    def step(self, state: State) -> list[AssistantContentBlock]:
        model_responses, _ = self.llm.generate(
            messages=state.get_messages_for_llm(),
            max_tokens=self.config.max_tokens_per_turn,
            system_prompt=self.system_prompt,
            tools=self.tools,
            temperature=self.config.temperature,
        )
        return model_responses

    async def step_async(self, state: State) -> list[AssistantContentBlock]:
        model_responses = await self.llm.generate_stream(
            messages=state.get_messages_for_llm(),
            max_tokens=self.config.max_tokens_per_turn,
            system_prompt=self.system_prompt,
            tools=self.tools,
            temperature=self.config.temperature,
        )
        return model_responses


if __name__ == "__main__":
    import asyncio
    from ii_agent.llm.r1 import R1DirectClient
    from ii_agent.core.config.llm_config import LLMConfig
    from pydantic import SecretStr

    async def main():
        # Initialize LLM config and client
        llm_config = LLMConfig(
            model="r1",
            base_url="http://localhost:4000",
            api_key=SecretStr("sk-123"),
            stop_sequence=ConfigConstants.DEFAULT_STOP_SEQUENCE,
        )
        r1_client = R1DirectClient(llm_config)

        # Initialize agent config
        system_prompt = get_config().system_prompt

        # Initialize ResearcherAgent with R1Client, empty tools list, and config
        researcher_agent = ResearcherAgent(
            llm=r1_client,
            config=AgentConfig(
                system_prompt=system_prompt,
            ),
            tools=[
                WebSearchTool().get_tool_param(),
                VisitWebpageTool().get_tool_param(),
            ],
        )
        state = State()
        state.add_user_prompt("Who is the best footballer in history")
        state.add_assistant_turn(
            [
                ThinkingBlock(
                    signature="",
                    thinking="Let me think, I believe it's either Lionel Messi or Cristiano Ronaldo, Pele, Maradona",
                )
            ]
        )
        state.add_assistant_turn(
            [
                ToolCall(
                    tool_call_id="dummy",
                    tool_name="web_search",
                    tool_input={
                        "query": [
                            "Best Footballer in the world Messi or Ronaldo or Pele or Maradona"
                        ]
                    },
                )
            ]
        )
        state.add_assistant_turn(
            [
                ToolResult(
                    tool_call_id="dummy",
                    tool_name="web_search",
                    tool_output="The best is Lionel Messi. It is widely accepted that Lionel Messi is the best footballer in history.",
                )
            ]
        )
        state.add_assistant_turn(
            [
                ThinkingBlock(
                    signature="",
                    thinking="I am ready to answer, let's end the thinking process here and answer the question. Wait, I need to check if there is any other tool that I can use to answer the question. I already called a tool, let's answer this since enough information is available.",
                )
            ]
        )

        out = researcher_agent.step(state)
        print(out)
        """
        async for chunk in researcher_agent.step_stream(state):
            if isinstance(chunk, TextResult):
                print(chunk.text, end="", flush=True)
        
        print("ResearcherAgent initialized successfully!")
        """

    asyncio.run(main())
