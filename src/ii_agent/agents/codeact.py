from ii_agent.agents.parser.base import MessageParser
from ii_agent.controller.agent import Agent
from ii_agent.controller.agent_response import AgentResponse
from ii_agent.llm.base import (
    LLMClient,
)
from ii_agent.controller.state import State
from ii_agent.core.config.agent_config import AgentConfig


class CodeActAgent(Agent):
    def __init__(
        self,
        llm: LLMClient,
        config: AgentConfig,
        parser: MessageParser,
        is_completion: bool = False,
    ):
        """Initialize the agent.

        Args:
            llm: The LLM client to use
            config: The configuration for the agent
        """
        self.parser = parser
        self.is_completion = is_completion

        super().__init__(llm, config)

    def step(self, state: State) -> AgentResponse:
        message = self.parser.pre_llm_parse(state.get_messages_for_llm())
        model_responses, raw_metrics = self.llm.generate(
            messages=message,
            max_tokens=self.config.max_tokens_per_turn,
            system_prompt=self.config.system_prompt,
            tools=self.config.tools if self.config.tools is not None else [],
            temperature=self.config.temperature,
            stop_sequence=self.config.stop_sequence,
        )
        model_response = self.parser.post_llm_parse(model_responses)
        model_name = self.llm.application_model_name
        return AgentResponse.from_content_and_raw_metrics(
            content=model_response, raw_metrics=raw_metrics, model_name=model_name
        )

    async def astep(self, state: State) -> AgentResponse:
        message = self.parser.pre_llm_parse(state.get_messages_for_llm())
        if self.is_completion:
            model_responses, raw_metrics = await self.llm.acompletion(
                messages=message,
                max_tokens=self.config.max_tokens_per_turn,
                system_prompt=self.config.system_prompt,
                temperature=self.config.temperature,
                stop_sequence=self.config.stop_sequence,
                presence_penalty=self.config.presence_penalty,
                top_p=self.config.top_p,
            )
        else:
            # When prefix=True, we use text-based thinking simulation (e.g., <THINK> tags)
            # rather than Anthropic's native extended thinking. Disable native thinking
            # to avoid conflicts with the message parser's text-based approach.
            model_responses, raw_metrics = await self.llm.agenerate(
                messages=message,
                max_tokens=self.config.max_tokens_per_turn,
                system_prompt=self.config.system_prompt,
                tools=[],
                temperature=self.config.temperature,
                stop_sequence=self.config.stop_sequence,
                prefix=True,
                thinking_tokens=0,  # Disable native thinking when using prefix mode
            )
        model_response = self.parser.post_llm_parse(model_responses)
        model_name = self.llm.application_model_name
        return AgentResponse.from_content_and_raw_metrics(
            content=model_response, raw_metrics=raw_metrics, model_name=model_name
        )
