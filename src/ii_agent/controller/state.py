import json
from pathlib import Path

from typing import Optional, cast, Any

from pydantic import BaseModel, Field
from ii_agent.core.storage.files import FileStore
from ii_agent.core.storage.locations import get_conversation_agent_history_filename
from ii_agent.llm.base import (
    AssistantContentBlock,
    GeneralContentBlock,
    LLMMessages,
    TextPrompt,
    TextResult,
    ToolCall,
    ToolFormattedResult,
    ImageBlock,
)
from ii_agent.tools import ToolCallParameters


class State(BaseModel):
    """Represents the current state of an agent."""

    message_lists: list[list[GeneralContentBlock]] = Field(default_factory=list)
    last_user_prompt_index: int | None = None

    @classmethod
    def _ensure_tool_call_integrity(
        cls, message_turns: list[list[GeneralContentBlock]]
    ) -> list[list[GeneralContentBlock]]:
        """
         Ensures that ToolCall blocks have matching ToolFormattedResult blocks and vice-versa.
        Removes any unmatched tool calls or results.
        """
        # First pass: collect all tool call IDs
        assistant_turn_tool_calls: dict[int, list[str]] = {}
        all_present_tool_call_ids_from_assistants = set()

        for idx, turn in enumerate(message_turns):
            ids_in_turn = [
                block.tool_call_id
                for block in turn
                if isinstance(block, ToolCall) and block.tool_call_id is not None
            ]
            if ids_in_turn:
                assistant_turn_tool_calls[idx] = ids_in_turn
                all_present_tool_call_ids_from_assistants.update(ids_in_turn)

        # Second pass: collect all tool result IDs
        all_present_tool_result_ids = set()
        for turn in message_turns:
            for block in turn:
                if (
                    isinstance(block, ToolFormattedResult)
                    and block.tool_call_id is not None
                ):
                    all_present_tool_result_ids.add(block.tool_call_id)

        # Get valid tool interaction IDs (those that have both call and result)
        valid_tool_interaction_ids = (
            all_present_tool_call_ids_from_assistants.intersection(
                all_present_tool_result_ids
            )
        )

        # Third pass: filter turns based on valid tool interactions
        cleaned_turns = []
        for idx, turn in enumerate(message_turns):
            new_turn_blocks = []
            is_assistant_turn_with_calls = idx in assistant_turn_tool_calls
            contains_tool_results = any(
                isinstance(block, ToolFormattedResult) for block in turn
            )

            if is_assistant_turn_with_calls:
                has_non_tool_call_content = False
                has_valid_tool_call = False
                for block in turn:
                    if isinstance(block, ToolCall):
                        if block.tool_call_id in valid_tool_interaction_ids:
                            new_turn_blocks.append(block)
                            has_valid_tool_call = True
                    else:  # e.g., TextResult
                        new_turn_blocks.append(block)
                        has_non_tool_call_content = True

                if has_non_tool_call_content or has_valid_tool_call:
                    cleaned_turns.append(new_turn_blocks)

            elif contains_tool_results:
                for block in turn:
                    if isinstance(block, ToolFormattedResult):
                        if block.tool_call_id in valid_tool_interaction_ids:
                            new_turn_blocks.append(block)
                if new_turn_blocks:
                    cleaned_turns.append(new_turn_blocks)

            else:  # User prompt, system message, or assistant reply without any tool calls
                cleaned_turns.append(turn)

        return cleaned_turns

    def restore_from_session(self, session_id: str, file_store: FileStore):
        """Restores the message history from the file store."""
        try:
            filename = get_conversation_agent_history_filename(session_id)
            json_data = file_store.read(filename)
            state_dict = json.loads(json_data)
            
            # Use Pydantic's model_validate to restore the entire state
            restored_state = State.model_validate(state_dict)
            self.message_lists = restored_state.message_lists
            self.last_user_prompt_index = restored_state.last_user_prompt_index
        except FileNotFoundError:
            raise FileNotFoundError(
                f"Could not restore history from file for session id: {session_id}"
            )

    def save_to_session(self, session_id: str, file_store: FileStore):
        """Save only core state as JSON"""
        filename = get_conversation_agent_history_filename(session_id)
        
        try:
            # Use Pydantic's model_dump to serialize the entire state
            json_data = json.dumps(self.model_dump(), indent=2, ensure_ascii=False)
            file_store.write(filename, json_data)
        except Exception as e:
            raise Exception(f"Error saving message history to session: {e}")

    def add_user_prompt(
        self, prompt: str, image_blocks: list[dict[str, Any]] | None = None
    ):
        """Adds a user prompt."""
        user_turn = []
        if image_blocks is not None:
            for img_block in image_blocks:
                user_turn.append(ImageBlock(type="image", source=img_block["source"]))

        user_turn.append(TextPrompt(text=prompt))
        self.add_user_turn(user_turn)
        # Mark this as the last user prompt position
        self.last_user_prompt_index = len(self.message_lists) - 1

    def add_user_turn(self, messages: list[GeneralContentBlock]):
        """Adds a user turn (prompts and/or tool results)."""
        # Ensure all messages are valid user-side types
        for msg in messages:
            if not isinstance(msg, (TextPrompt, ToolFormattedResult, ImageBlock)):
                raise TypeError(f"Invalid message type for user turn: {type(msg)}")
        self.message_lists.append(messages)

    def add_assistant_turn(self, messages: list[AssistantContentBlock]):
        """Adds an assistant turn (text response and/or tool calls)."""
        # Allow multiple tool calls per turn for parallel execution
        self.message_lists.append(
            cast(list[GeneralContentBlock], messages)
        )

    def get_messages_for_llm(self) -> LLMMessages:  # TODO: change name to get_messages
        """Returns messages formatted for the LLM client."""
        # Return a copy to prevent modification
        return list(self.message_lists)

    def get_pending_tool_calls(self) -> list[ToolCallParameters]:
        """Returns tool calls from the last assistant turn, if any."""
        last_turn = self.message_lists[-1]
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
        self.message_lists.append(
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
        if not self.message_lists:
            return None  # No assistant response yet or not the last turn

        last_turn = self.message_lists[-1]
        for message in reversed(last_turn):  # Check from end
            if isinstance(message, TextResult):
                return message.text
        return None

    def clear(self):
        """Removes all messages."""
        self.message_lists = []
        self.last_user_prompt_index = None

    def clear_from_last_to_user_message(self):
        """Clears messages from the last turn backwards to the last user prompt (inclusive).
        This preserves the conversation history before the last user prompt.
        """
        if not self.message_lists or self.last_user_prompt_index is None:
            return

        # Keep messages up to and excluding the last user prompt
        self.message_lists = self.message_lists[: self.last_user_prompt_index]
        # Reset the last user prompt index since we've cleared after it
        self.last_user_prompt_index = None

    def __len__(self) -> int:
        """Returns the number of turns."""
        return len(self.message_lists)

    def __str__(self) -> str:
        """JSON representation of the history."""
        try:
            return json.dumps(self.model_dump(), indent=2, ensure_ascii=False)
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
            # Use model_dump to serialize then truncate
            serialized_data = self.model_dump()
            truncated_data = truncate_strings(serialized_data)
            return json.dumps(truncated_data, indent=2, ensure_ascii=False)
        except Exception as e:
            return f"[Error serializing summary: {e}]"

    def set_message_list(self, message_list: list[list[GeneralContentBlock]]):
        """Sets the message list and ensures tool call integrity."""
        self.message_lists = State._ensure_tool_call_integrity(message_list)

