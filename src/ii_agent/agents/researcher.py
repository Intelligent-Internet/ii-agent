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
    
    def step_stream(self, state: State):
        import asyncio
        return asyncio.run(self.step_async(state))

    async def step_async(self, state: State) -> list[AssistantContentBlock]:
        model_responses = await self.llm.generate_stream(
            messages=state.get_messages_for_llm(),
            max_tokens=self.config.max_tokens_per_turn,
            system_prompt=self.system_prompt,
            tools=self.tools,
            temperature=self.config.temperature,
        )
        return model_responses

