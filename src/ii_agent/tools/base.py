from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

import jsonschema
from anthropic import BadRequestError
from typing_extensions import final

from ii_agent.llm.base import (
    ToolParam,
)
from ii_agent.llm.message_history import MessageHistory

ToolInputSchema = dict[str, Any]


@dataclass
class ToolImplOutput:
    """Output from an LLM tool implementation.

    Attributes:
        tool_output: The main output string or list of dicts that will be shown to the model.
        tool_result_message: A description of what the tool did, for logging purposes.
        auxiliary_data: Additional data that the tool wants to pass along for logging only.
    """

    tool_output: list[dict[str, Any]] | str
    tool_result_message: str
    auxiliary_data: dict[str, Any] = field(default_factory=dict)


class LLMTool(ABC):
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
        message_history: Optional[MessageHistory] = None,
    ) -> str | list[dict[str, Any]]:
        """Run the tool.

        Args:
            tool_input: The input to the tool.
            message_history: The dialog messages so far, if available. The tool
                is allowed to modify this object, so the caller should make a copy
                if that's not desired. The dialog messages should not contain
                pending tool calls. They should end where it's the user's turn.
        """
        if message_history:
            assert message_history.is_next_turn_user()

        try:
            self._validate_tool_input(tool_input)
            result = self.run_impl(tool_input, message_history)
            tool_output = result.tool_output
        except jsonschema.ValidationError as exc:
            tool_output = "Invalid tool input: " + exc.message
        except BadRequestError as exc:
            raise RuntimeError("Bad request: " + exc.message)

        return tool_output

    def get_tool_start_message(self, tool_input: ToolInputSchema) -> str:
        """Return a user-friendly message to be shown to the model when the tool is called."""
        return f"Calling tool '{self.name}'"

    @abstractmethod
    def run_impl(
        self,
        tool_input: dict[str, Any],
        message_history: Optional[MessageHistory] = None,
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
