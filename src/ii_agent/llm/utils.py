from ii_agent.llm.base import (
    GeneralContentBlock,
    LLMMessages,
    TextPrompt,
    TextResult,
    ToolCall,
    ToolFormattedResult,
)
from anthropic.types import (
    ThinkingBlock as AnthropicThinkingBlock,
    RedactedThinkingBlock as AnthropicRedactedThinkingBlock,
)


def convert_message_to_json(message: GeneralContentBlock) -> dict:
    if str(type(message)) == str(TextPrompt) or str(type(message)) == str(TextResult):
        message_json = {
            "type": "text",
            "text": message.text,
        }
    elif str(type(message)) == str(ToolCall):
        message_json = {
            "type": "tool_call",
            "tool_call_id": message.tool_call_id,
            "tool_name": message.tool_name,
            "tool_input": message.tool_input,
        }
    elif str(type(message)) == str(ToolFormattedResult):
        message_json = {
            "type": "tool_result",
            "tool_call_id": message.tool_call_id,
            "tool_name": message.tool_name,
            "tool_output": message.tool_output,
        }
    elif str(type(message)) == str(AnthropicRedactedThinkingBlock):
        message_json = {
            "type": "redacted_thinking",
            "content": message.data,
        }
    elif str(type(message)) == str(AnthropicThinkingBlock):
        message_json = {
            "type": "thinking",
            "thinking": message.thinking,
            "signature": message.signature,
        }
    else:
        print(
            f"Unknown message type: {type(message)}, expected one of {str(TextPrompt)}, {str(TextResult)}, {str(ToolCall)}, {str(ToolFormattedResult)}"
        )
        raise ValueError(
            f"Unknown message type: {type(message)}, expected one of {str(TextPrompt)}, {str(TextResult)}, {str(ToolCall)}, {str(ToolFormattedResult)}"
        )
    return message_json


def convert_message_history_to_json(messages: LLMMessages) -> list[list[dict]]:
    messages_json = []
    for idx, message_list in enumerate(messages):
        role = "user" if idx % 2 == 0 else "assistant"
        message_content_list = [convert_message_to_json(message) for message in message_list]
        messages_json.append({
            "role": role,
            "content": message_content_list,
        })
    return messages_json