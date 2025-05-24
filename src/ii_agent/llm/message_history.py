import json
from typing import Optional, cast, Any
from ii_agent.llm.base import (
    AssistantContentBlock,
    GeneralContentBlock,
    LLMMessages,
    TextPrompt,
    TextResult,
    ToolCall,
    ToolCallParameters,
    ToolFormattedResult,
    ImageBlock,
)


class MessageHistory:
    """Stores the sequence of messages in a dialog."""

    def __init__(self):
        self._message_lists: list[list[GeneralContentBlock]] = []
        self._last_user_prompt_index: int | None = None  # Track the last user prompt index

    def add_user_prompt(
        self, prompt: str, image_blocks: list[dict[str, Any]] | None = None
    ):
        """Adds a user prompt."""
        user_turn = []
        if image_blocks is not None:
            for img_block in image_blocks:
                user_turn.append(ImageBlock(type="image", source=img_block["source"]))

        user_turn.append(TextPrompt(prompt))
        self.add_user_turn(user_turn)
        # Mark this as the last user prompt position
        self._last_user_prompt_index = len(self._message_lists) - 1

    def add_user_turn(self, messages: list[GeneralContentBlock]):
        """Adds a user turn (prompts and/or tool results)."""
        if not self.is_next_turn_user():
            raise ValueError("Cannot add user turn, expected assistant turn next.")
        # Ensure all messages are valid user-side types
        for msg in messages:
            if not isinstance(msg, (TextPrompt, ToolFormattedResult, ImageBlock)):
                raise TypeError(f"Invalid message type for user turn: {type(msg)}")
        self._message_lists.append(messages)

    def add_assistant_turn(self, messages: list[AssistantContentBlock]):
        """Adds an assistant turn (text response and/or tool calls)."""
        if not self.is_next_turn_assistant():
            raise ValueError("Cannot add assistant turn, expected user turn next.")
        self._message_lists.append(cast(list[GeneralContentBlock], messages))

    def get_messages_for_llm(self) -> LLMMessages:  # TODO: change name to get_messages
        """Returns messages formatted for the LLM client."""
        # Return a copy to prevent modification
        return list(self._message_lists)

    def get_pending_tool_calls(self) -> list[ToolCallParameters]:
        """Returns tool calls from the last assistant turn, if any."""
        if self.is_next_turn_assistant() or not self._message_lists:
            return []  # No pending calls if it's user turn or history is empty

        last_turn = self._message_lists[-1]
        tool_calls = []
        for message in last_turn:
            if isinstance(message, ToolCall):
                tool_calls.append(
                    ToolCallParameters(
                        tool_call_id=message.tool_call_id,
                        tool_name=message.tool_name,
                        tool_input=message.tool_input,
                    )
                )
        return tool_calls

    def add_tool_call_result(self, parameters: ToolCallParameters, result: str):
        """Add the result of a tool call to the dialog."""
        self.add_tool_call_results([parameters], [result])

    def add_tool_call_results(
        self, parameters: list[ToolCallParameters], results: list[str]
    ):
        """Add the result of a tool call to the dialog."""
        assert self.is_next_turn_user(), (
            "Cannot add tool call results, expected user turn next."
        )
        self._message_lists.append(
            [
                ToolFormattedResult(
                    tool_call_id=params.tool_call_id,
                    tool_name=params.tool_name,
                    tool_output=result,
                )
                for params, result in zip(parameters, results)
            ]
        )

    def get_last_assistant_text_response(self) -> Optional[str]:  # TODO:: remove get
        """Returns the text part of the last assistant response, if any."""
        if self.is_next_turn_assistant() or not self._message_lists:
            return None  # No assistant response yet or not the last turn

        last_turn = self._message_lists[-1]
        for message in reversed(last_turn):  # Check from end
            if isinstance(message, TextResult):
                return message.text
        return None

    def clear(self):
        """Removes all messages."""
        self._message_lists = []
        self._last_user_prompt_index = None

    def clear_from_last_to_user_message(self):
        """Clears messages from the last turn backwards to the last user prompt (inclusive).
        This preserves the conversation history before the last user prompt.
        """
        if not self._message_lists or self._last_user_prompt_index is None:
            return

        # Keep messages up to and excluding the last user prompt
        self._message_lists = self._message_lists[:self._last_user_prompt_index]
        # Reset the last user prompt index since we've cleared after it
        self._last_user_prompt_index = None

    def is_next_turn_user(self) -> bool:
        """Checks if the next turn should be from the user."""
        # User turn is 0, 2, 4... (even indices in a 0-indexed list)
        return len(self._message_lists) % 2 == 0

    def is_next_turn_assistant(self) -> bool:
        """Checks if the next turn should be from the assistant."""
        return not self.is_next_turn_user()

    def __len__(self) -> int:
        """Returns the number of turns."""
        return len(self._message_lists)

    def __str__(self) -> str:
        """JSON representation of the history."""
        try:
            json_serializable = [
                [message.to_dict() for message in message_list]
                for message_list in self._message_lists
            ]
            return json.dumps(json_serializable, indent=2)
        except Exception as e:
            return f"[Error serializing history: {e}]"

    def get_summary(self, max_str_len: int = 100) -> str:
        """Returns a summarized JSON representation."""

        def truncate_strings(obj):
            if isinstance(obj, str):
                return obj[:max_str_len] + "..." if len(obj) > max_str_len else obj
            elif isinstance(obj, dict):
                return {k: truncate_strings(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [truncate_strings(item) for item in obj]
            return obj

        try:
            json_serializable = truncate_strings(
                [
                    [message.to_dict() for message in message_list]
                    for message_list in self._message_lists
                ]
            )
            return json.dumps(json_serializable, indent=2)
        except Exception as e:
            return f"[Error serializing summary: {e}]"

    def set_message_list(self, message_list: list[list[GeneralContentBlock]]):
        """Sets the message list."""
        self._message_lists = message_list
