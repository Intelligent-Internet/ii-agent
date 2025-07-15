from ii_agent.llm.base import (
    GeneralContentBlock,
    LLMMessages,
    TextPrompt,
    TextResult,
    ToolCall,
    ToolFormattedResult,
    ImageBlock,
    ThinkingBlock,
    RedactedThinkingBlock,
)
from copy import deepcopy


def _hide_base64_image_from_tool_output(tool_output: list[dict]) -> list[dict]:
    """Hide the base64 image from the tool output.

    Args:
        tool_output (list[dict]): The tool output to hide the base64 image from.

    Returns:
        list[dict]: The tool output with the base64 image hidden.
    """
    refined_tool_output = []
    for item in tool_output:
        if isinstance(item, dict) and item.get("type") == "image":
            refined_item = {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": "[base64-image-data]",
                },
            }
            refined_tool_output.append(refined_item)
        else:
            refined_tool_output.append(item)
    return refined_tool_output


def convert_message_to_json(
    message: GeneralContentBlock, hide_base64_image: bool = False
) -> dict:
    """Convert a GeneralContentBlock to a JSON object.

    Args:
        message (GeneralContentBlock): The message to convert.
        hide_base64_image (bool, optional): Whether to hide the base64 image if the message is a tool result. Defaults to False.

    Raises:
        ValueError: If the message is not a TextPrompt, TextResult, ToolCall, or AnthropicRedactedThinkingBlock.

    Returns:
        dict: The JSON object.
    """
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
        }
        if isinstance(message.tool_output, list):
            message_json["tool_output"] = (
                _hide_base64_image_from_tool_output(message.tool_output)
                if hide_base64_image
                else message.tool_output
            )
        else:
            message_json["tool_output"] = message.tool_output
    elif str(type(message)) == str(RedactedThinkingBlock):
        message_json = {
            "type": "redacted_thinking",
            "content": message.data,
        }
    elif str(type(message)) == str(ThinkingBlock):
        message_json = {
            "type": "thinking",
            "thinking": message.thinking,
            "signature": message.signature,
        }
    elif str(type(message)) == str(ImageBlock):
        message_json = {
            "type": "image",
            "source": message.source,
        }
        if hide_base64_image:
            message_json["source"]["data"] = "[base64-image-data]"
    else:
        print(
            f"Unknown message type: {type(message)}, expected one of {str(TextPrompt)}, {str(TextResult)}, {str(ToolCall)}, {str(ToolFormattedResult)}"
        )
        raise ValueError(
            f"Unknown message type: {type(message)}, expected one of {str(TextPrompt)}, {str(TextResult)}, {str(ToolCall)}, {str(ToolFormattedResult)}"
        )
    return message_json


def convert_state_to_json(
    messages: LLMMessages, hide_base64_image: bool = False
) -> list[list[dict]]:
    """Convert a LLMMessages object to a JSON object.

    Args:
        messages (LLMMessages): The LLMMessages object to convert.
        hide_base64_image (bool, optional): Whether to hide the base64 image if the message is a tool result. Defaults to False.

    Returns:
        list[list[dict]]: The JSON object.
    """
    messages_cp = deepcopy(messages)
    messages_json = []
    for idx, message_list in enumerate(messages_cp):
        role = "user" if idx % 2 == 0 else "assistant"
        message_content_list = [
            convert_message_to_json(message, hide_base64_image)
            for message in message_list
        ]
        messages_json.append(
            {
                "role": role,
                "content": message_content_list,
            }
        )
    return messages_json
