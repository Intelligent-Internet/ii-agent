"""Tool definitions and utilities."""

import copy
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional, cast
import subprocess

import jsonschema
from anthropic import BadRequestError
from termcolor import colored
from typing_extensions import final

from utils.token_counter import (
    ClaudeTokenCounter,
)
from utils.llm_client import (
    AnthropicRedactedThinkingBlock,
    AnthropicThinkingBlock,
    ToolCall,
    ToolFormattedResult,
)
from utils.llm_client import (
    AssistantContentBlock,
    GeneralContentBlock,
    LLMMessages,
    TextPrompt,
    TextResult,
    ToolParam,
)

ToolInputSchema = dict[str, Any]
"""A JSON schema describing the input to a tool."""


RIGHT = ""  # "▶"
LEFT = ""  # "◀"


@dataclass
class ToolCallParameters:
    tool_call_id: str
    tool_name: str
    tool_input: Any


@dataclass
class ToolImplOutput:
    """Output from an LLM tool implementation.

    Attributes:
        tool_output: The main output string that will be shown to the model.
        tool_result_message: A description of what the tool did, for logging purposes.
        auxiliary_data: Additional data that the tool wants to pass along for logging only.
    """

    tool_output: str
    tool_result_message: str
    auxiliary_data: dict[str, Any] = field(default_factory=dict)


class DialogMessages:
    """Keeps track of messages that compose a dialog.

    A dialog alternates between user and assistant turns. Each turn consists
    of one or more messages, represented by GeneralContentBlock.

    A user turn consists of one or more prompts and tool results.
    An assistant turn consists of a model answer and tool calls.
    """

    def __init__(
        self,
        logger_for_agent_logs: logging.Logger,
        use_prompt_budgeting: bool = False,
    ):
        self.logger_for_agent_logs = logger_for_agent_logs
        self._message_lists: list[list[GeneralContentBlock]] = []
        self.token_counter = ClaudeTokenCounter()
        self.use_prompt_budgeting = use_prompt_budgeting
        self.truncation_history_token_cts: list[int] = []
        self.token_budget_to_trigger_truncation = 120_000
        self.truncate_all_but_N = 3

    def add_user_prompt(
        self, message: str, allow_append_to_tool_call_results: bool = False
    ):
        """Add a user prompt to the dialog.

        Args:
            message: The message to add.
            allow_append_to_tool_call_results: If True, and if the last message
                is a tool call result, then the message will be appended to that
                turn.
        """
        if self.is_user_turn():
            self._message_lists.append([TextPrompt(message)])
        else:
            if allow_append_to_tool_call_results:
                user_messages = self._message_lists[-1]
                for user_message in user_messages:
                    if isinstance(user_message, TextPrompt):
                        raise ValueError(
                            f"Last user turn already contains a text prompt: {user_message}"
                        )
                user_messages.append(TextPrompt(message))
            else:
                self._assert_user_turn()

    def add_tool_call_result(self, parameters: ToolCallParameters, result: str):
        """Add the result of a tool call to the dialog."""
        self.add_tool_call_results([parameters], [result])

    def add_tool_call_results(
        self, parameters: list[ToolCallParameters], results: list[str]
    ):
        """Add the result of a tool call to the dialog."""
        self._assert_user_turn()
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

    def add_model_response(self, response: list[AssistantContentBlock]):
        """Add the result of a model call to the dialog."""
        self._assert_assistant_turn()
        self._message_lists.append(cast(list[GeneralContentBlock], response))

    def count_tokens(self) -> int:
        """Count the total number of tokens in the dialog."""
        total_tokens = 0
        for i, message_list in enumerate(self._message_lists):
            is_last_message_list = i == len(self._message_lists) - 1
            for message in message_list:
                if isinstance(message, (TextPrompt, TextResult)):
                    total_tokens += self.token_counter.count_tokens(message.text)
                elif isinstance(message, ToolFormattedResult):
                    total_tokens += self.token_counter.count_tokens(message.tool_output)
                elif isinstance(message, ToolCall):
                    total_tokens += self.token_counter.count_tokens(
                        json.dumps(message.tool_input)
                    )
                elif isinstance(message, AnthropicRedactedThinkingBlock):
                    total_tokens += 0
                elif isinstance(message, AnthropicThinkingBlock):
                    total_tokens += (
                        self.token_counter.count_tokens(message.thinking)
                        if is_last_message_list
                        else 0
                    )
                else:
                    raise ValueError(f"Unknown message type: {type(message)}")
        return total_tokens

    def run_truncation_strategy(self) -> None:
        """Truncate all the tool results apart from the last N turns."""

        print(
            colored(
                f"Truncating all but the last {self.truncate_all_but_N} turns as we hit the token budget {self.token_budget_to_trigger_truncation}.",
                "yellow",
            )
        )
        self.logger_for_agent_logs.info(
            f"Truncating all but the last {self.truncate_all_but_N} turns as we hit the token budget {self.token_budget_to_trigger_truncation}."
        )

        old_token_ct = self.count_tokens()

        new_message_lists: list[list[GeneralContentBlock]] = copy.deepcopy(
            self._message_lists
        )

        for message_list in new_message_lists[: -self.truncate_all_but_N]:
            for message in message_list:
                if isinstance(message, ToolFormattedResult):
                    message.tool_output = (
                        "[Truncated...re-run tool if you need to see output again.]"
                    )
                elif isinstance(message, ToolCall):
                    if message.tool_name == "sequential_thinking":
                        message.tool_input["thought"] = (
                            "[Truncated...re-run tool if you need to see input/output again.]"
                        )
                    elif message.tool_name == "str_replace_editor":
                        if "file_text" in message.tool_input:
                            message.tool_input["file_text"] = (
                                "[Truncated...re-run tool if you need to see input/output again.]"
                            )
                        if "old_str" in message.tool_input:
                            message.tool_input["old_str"] = (
                                "[Truncated...re-run tool if you need to see input/output again.]"
                            )
                        if "new_str" in message.tool_input:
                            message.tool_input["new_str"] = (
                                "[Truncated...re-run tool if you need to see input/output again.]"
                            )

        self._message_lists = new_message_lists

        new_token_ct = self.count_tokens()
        print(
            colored(
                f" [dialog_messages] Token count after truncation: {new_token_ct}",
                "yellow",
            )
        )

        self.truncation_history_token_cts.append(old_token_ct - new_token_ct)

    def get_messages_for_llm_client(self) -> LLMMessages:
        """Returns messages in the format the LM client expects."""

        if (
            self.use_prompt_budgeting
            and self.count_tokens() > self.token_budget_to_trigger_truncation
        ):
            self.run_truncation_strategy()

        return list(self._message_lists)

    def drop_final_assistant_turn(self):
        """Remove the final assistant turn.

        This allows dialog messages to be passed to tools as they are called,
        without containing the final tool call.
        """
        if self.is_user_turn():
            self._message_lists.pop()

    def drop_tool_calls_from_final_turn(self):
        """Remove tool calls from the final assistant turn.

        This allows dialog messages to be passed to tools as they are called,
        without containing the final tool call.
        """
        if self.is_user_turn():
            new_turn_messages = [
                message
                for message in self._message_lists[-1]
                if not isinstance(message, ToolCall)
            ]
            self._message_lists[-1] = cast(list[GeneralContentBlock], new_turn_messages)

    def get_pending_tool_calls(self) -> list[ToolCallParameters]:
        """Returns the tool calls from the last assistant turn.

        Returns an empty list of no tool calls are pending.
        """
        self._assert_user_turn()
        if len(self._message_lists) == 0:
            return []
        tool_calls = []
        for message in self._message_lists[-1]:
            if isinstance(message, ToolCall):
                tool_calls.append(
                    ToolCallParameters(
                        tool_call_id=message.tool_call_id,
                        tool_name=message.tool_name,
                        tool_input=message.tool_input,
                    )
                )
        return tool_calls

    def get_last_model_text_response(self):
        """Returns the last model response as a string."""
        self._assert_user_turn()
        for message in self._message_lists[-1]:
            if isinstance(message, TextResult):
                return message.text
        raise ValueError("No text response found in last model response")

    def get_last_user_prompt(self) -> str:
        """Returns the last user prompt."""
        self._assert_assistant_turn()
        for message in self._message_lists[-1]:
            if isinstance(message, TextPrompt):
                return message.text
        raise ValueError("No text prompt found in last user prompt")

    def replace_last_user_prompt(self, new_prompt: str):
        """Replace the last user prompt with a new one."""
        self._assert_assistant_turn()
        for i, message in enumerate(self._message_lists[-1]):
            if isinstance(message, TextPrompt):
                self._message_lists[-1][i] = TextPrompt(new_prompt)
                return
        raise ValueError("No text prompt found in last user prompt")

    def clear(self):
        """Delete all messages."""
        self._message_lists = []

    def is_user_turn(self):
        return len(self._message_lists) % 2 == 0

    def is_assistant_turn(self):
        return len(self._message_lists) % 2 == 1

    def __str__(self) -> str:
        json_serializable = [
            [message.to_dict() for message in message_list]
            for message_list in self._message_lists
        ]
        return json.dumps(json_serializable, indent=2)

    def get_summary(self, max_str_len: int = 100) -> str:
        """Returns a summary of the dialog."""

        def truncate_strings(obj):
            # Truncate all leaf strings to 100 characters
            if isinstance(obj, str):
                if len(obj) > max_str_len:
                    return obj[:max_str_len] + "..."
            elif isinstance(obj, dict):
                return {k: truncate_strings(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [truncate_strings(item) for item in obj]
            return obj

        json_serializable = truncate_strings(
            [
                [message.to_dict() for message in message_list]
                for message_list in self._message_lists
            ]
        )
        return json.dumps(json_serializable, indent=2)

    def _assert_user_turn(self):
        assert self.is_user_turn(), "Can only add user prompts on user's turn"

    def _assert_assistant_turn(self):
        assert self.is_assistant_turn(), (
            "Can only get/replace last user prompt on assistant's turn"
        )


class Tool:
    """A tool that can be called by an LLM.

    A general tool may require additional parameters that the model does not
    provide. It may also return arbitrary structured output. Therefore, a
    general tool does not have a well-defined interface for calling it.
    """

    name: str
    description: str
    input_schema: ToolInputSchema


class LLMTool:
    """A tool that fits into the standard LLM tool-calling paradigm.

    An LLM tool can be called by supplying the parameters specified in its
    input_schema, and returns a string that is then shown to the model.
    """

    name: str
    description: str
    input_schema: ToolInputSchema

    @property
    def should_stop(self) -> bool:
        """Whether the tool wants to stop the current agentic run."""
        return False

    # Final is here to indicate that subclasses should override run_impl(), not
    # run(). There may be a reason in the future to override run() itself, and
    # if such a reason comes up, this @final decorator can be removed.
    @final
    def run(
        self,
        tool_input: dict[str, Any],
        dialog_messages: Optional[DialogMessages] = None,
    ) -> str:
        """Run the tool.

        Args:
            tool_input: The input to the tool.
            dialog_messages: The dialog messages so far, if available. The tool
                is allowed to modify this object, so the caller should make a copy
                if that's not desired. The dialog messages should not contain
                pending tool calls. They should end where it's the user's turn.
        """
        if dialog_messages:
            assert dialog_messages.is_user_turn()

        try:
            self._validate_tool_input(tool_input)
            result = self.run_impl(tool_input, dialog_messages)
            tool_output = result.tool_output
        except jsonschema.ValidationError as exc:
            tool_output = "Invalid tool input: " + exc.message
        except BadRequestError as exc:
            raise RuntimeError("Bad request: " + exc.message)

        return tool_output

    def get_tool_start_message(self, tool_input: ToolInputSchema) -> str:
        """Return a user-friendly message to be shown to the model when the tool is called."""
        return f"Calling tool '{self.name}'"

    def run_impl(
        self,
        tool_input: dict[str, Any],
        dialog_messages: Optional[DialogMessages] = None,
    ) -> ToolImplOutput:
        """Subclasses should implement this.

        Returns:
            A ToolImplOutput containing the output string, description, and any auxiliary data.
        """
        raise NotImplementedError()

    def get_tool_param(self) -> ToolParam:
        return ToolParam(
            name=self.name,
            description=self.description,
            input_schema=self.input_schema,
        )

    def _validate_tool_input(self, tool_input: dict[str, Any]):
        """Validates the tool input.

        Raises:
            jsonschema.ValidationError: If the tool input is invalid.
        """
        jsonschema.validate(instance=tool_input, schema=self.input_schema)


def call_tools(
    tools: list[LLMTool],
    calls_to_make: list[ToolCallParameters],
    dialog_messages: Optional[DialogMessages] = None,
) -> list[str]:
    """Call the requested tools and return their outputs.

    Args:
        tools: The tools to call.
        calls_to_make: The calls to make.
        dialog_messages: If supplied, the tool call results will be recorded here.
    """
    tool_outputs = []
    for call in calls_to_make:
        tool = next(t for t in tools if t.name == call.tool_name)
        tool_outputs.append(tool.run(call.tool_input))

    if dialog_messages:
        dialog_messages.add_tool_call_results(calls_to_make, tool_outputs)

    return tool_outputs


def generate_patch(git_repo, reverse=False):
    """Generate the patch for the prediction."""
    logging.info(f"Generating patch in {git_repo}")
    cmd = [
        "git",
        "--no-pager",
        "diff",
        "-U5",  # Include 5 lines of context
        "--no-color",  # Don't include color codes in the output
        "HEAD",  # Compare against the current commit
    ]
    if reverse:
        cmd.append("-R")
    max_retries = 3
    for attempt in range(max_retries):
        try:
            diff = subprocess.check_output(
                cmd,
                cwd=git_repo,
                text=True,
                errors="backslashreplace",
            )
            return diff
        except Exception as e:
            if attempt < max_retries - 1:
                logging.warning(
                    f"Error {e} occurred. Retrying... (Attempt {attempt + 1}/{max_retries})"
                )
                time.sleep(5)  # Add a small delay before retrying
            else:
                logging.error(
                    f"Failed to decode git diff output after {max_retries} attempts."
                )
                raise
