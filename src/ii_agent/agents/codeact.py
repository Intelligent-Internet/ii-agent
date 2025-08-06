from datetime import datetime, timezone
from typing import Any

from ii_agent.controller.agent import Agent
from ii_agent.llm.base import (
    LLMClient,
    AssistantContentBlock,
    LLMMessages,
    TextPrompt,
    TextResult,
    ThinkingBlock,
    ToolCall,
    ToolFormattedResult,
    ToolParam,
    ToolResult,
)
from ii_agent.controller.state import State
from ii_agent.core.config.agent_config import AgentConfig
from ii_agent.prompts.researcher_system_prompt import ConfigConstants
from ii_tool.tools.agent.parser.codeact_parser import evaluate_block, format_tool_call, format_tool_result, parse_code_blobs


class CodeActAgent(Agent):
    def __init__(self, llm: LLMClient, config: AgentConfig, tools: list[ToolParam]):
        """Initialize the agent.

        Args:
            llm: The LLM client to use
            config: The configuration for the agent
        """
        self.tools = tools
        super().__init__(llm, config)

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
    
    def _transform_messages_pre_llm(
        self,
        messages: LLMMessages,
    ) -> LLMMessages:
        """Prepare messages for OpenAI API format.

        Args:
            messages: Internal message format

        Returns:
            List of messages in OpenAI format
        """
        openai_messages = []
        openai_messages.extend(
            self._compress_adjacent_assistant_messages(messages, self.tools)
        )

        return openai_messages

    def _compress_adjacent_assistant_messages(
        self, temp_messages: LLMMessages, tools: list[ToolParam] | None
    ) -> list[dict]:
        """Compress adjacent assistant messages and return final message list."""
        openai_messages = []
        i = 0
        prev_user_msg = None
        while i < len(temp_messages):
            current_msg = temp_messages[i]

            if isinstance(current_msg[0], TextPrompt):
                prev_user_msg = current_msg[0].text
                openai_messages.append(current_msg)
                i += 1

            elif isinstance(current_msg[0], AssistantContentBlock):
                # Collect adjacent assistant messages
                adjacent_assistant_msgs = [current_msg]
                j = i + 1
                while (
                    j < len(temp_messages) and not isinstance(temp_messages[j][0], TextPrompt)
                ):
                    adjacent_assistant_msgs.append(temp_messages[j])
                    j += 1

                # Compress if we have multiple adjacent assistant messages
                if len(adjacent_assistant_msgs) >= 1:
                    compressed_msg = self._compress(
                        prev_user_msg=prev_user_msg,
                        assistant_messages=adjacent_assistant_msgs,
                        tools=tools or [],
                    )
                    openai_messages.append(compressed_msg)
                else:
                    openai_messages.append(current_msg)

                i = j  # Skip the compressed messages
            else:
                openai_messages.append(current_msg)
                i += 1

        return openai_messages

    def _compress(
        self,
        prev_user_msg: str,
        assistant_messages: LLMMessages,
        tools: list[ToolParam],
    ) -> AssistantContentBlock:
        """Compress a list of adjacent assistant messages into a single message."""
        combined_text = []

        for msg in assistant_messages:
            for content_item in msg:
                if isinstance(content_item, ThinkingBlock):
                    combined_text.append(content_item.thinking)
                elif isinstance(content_item, TextResult):
                    combined_text.append(content_item.text)
                elif isinstance(content_item, ToolCall):
                    combined_text.append(format_tool_call(content_item))
                elif isinstance(content_item, ToolResult) or isinstance(
                    content_item, ToolFormattedResult
                ):
                    combined_text.append(format_tool_result(content_item))
                else:
                    raise ValueError(
                        f"Unsupported content type: {type(content_item)}"
                    )

        instruction = AgentConfig().instructions.format(
            current_date=datetime.now(timezone.utc).isoformat(),
            available_tools="\n".join(
                [
                    f"- {tool.name}: {tool.description} with input schema: {tool.input_schema}"
                    for tool in tools
                ]
            ),
        )


        if combined_text:
            content = (
                f"{ConfigConstants.THINK_TAG_OPEN} So, the user's question is: '{prev_user_msg}' "
                + "\n".join(combined_text)
                + f"\n{instruction if instruction else ''}"
            )
            if isinstance(assistant_messages[-1], ThinkingBlock) and (
                not content.strip().endswith(ConfigConstants.THINK_TAG_CLOSE)
            ):
                content += ConfigConstants.THINK_TAG_CLOSE
        else:
            content = (
                f"{ConfigConstants.THINK_TAG_OPEN} {instruction if instruction else ''} \nSo, the user's question is: '{prev_user_msg}' \n"
                + "\n".join(combined_text)
            )
        
        return TextResult(text=content)



    def parse_model_response(self, messages: list[AssistantContentBlock]) -> list[AssistantContentBlock]:
        """Parse the model response."""
        result = []
        for message in messages:
            if isinstance(message, TextResult):
                raw = message.text
                _, action_string = parse_code_blobs(raw)
            else:
                result.append(message)
                continue

            if action_string:
                try:
                    action = evaluate_block(action_string)
                    result.append(
                        ThinkingBlock(
                            signature="",
                            thinking=raw.replace(ConfigConstants.THINK_TAG_CLOSE, ""),
                        )
                    )
                    result.append(action)
                except ValueError:
                    result.append(TextResult(text=action_string))
            else:
                if ConfigConstants.THINK_TAG_CLOSE in raw:
                    split_result = raw.rsplit(ConfigConstants.THINK_TAG_CLOSE, 1)
                    thoughts, text_result = split_result[0], split_result[1]
                    result.append(ThinkingBlock(signature="", thinking=thoughts))
                    result.append(TextResult(text=text_result))

        return result
    
    def _transform_messages_post_llm(self, messages: list[AssistantContentBlock]) -> list[AssistantContentBlock]:
        return messages

    def step(self, state: State) -> list[AssistantContentBlock]:
        message = self._transform_messages_pre_llm(state.get_messages_for_llm())
        model_responses, _ = self.llm.generate(
            messages=message,
            max_tokens=self.config.max_tokens_per_turn,
            system_prompt=self.system_prompt,
            tools=self.tools,
            temperature=self.config.temperature,
        )
        model_response = self._transform_messages_post_llm(model_responses)
        return model_response
    