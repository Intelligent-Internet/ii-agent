"""Action parser system for converting LLM responses to actions."""

from abc import ABC, abstractmethod
from typing import Any, List

from ii_agent.events.action import Action


class ActionParseError(Exception):
    """Exception raised when the response from the LLM cannot be parsed into an action."""

    def __init__(self, error: str):
        self.error = error

    def __str__(self) -> str:
        return self.error


class ResponseParser(ABC):
    """Abstract base class for parsing LLM responses into actions.
    
    This provides a standardized interface for converting different types of LLM responses
    into structured Action objects.
    """

    def __init__(self) -> None:
        # Order matters - parsers are tried in sequence
        self.action_parsers: List[ActionParser] = []

    @abstractmethod
    def parse(self, response: Any) -> Action:
        """Parse the response from the LLM into an Action.

        Args:
            response: The response from the LLM (can be string, dict, etc.)

        Returns:
            Action: The parsed action

        Raises:
            ActionParseError: If the response cannot be parsed
        """
        pass

    @abstractmethod
    def parse_response(self, response: Any) -> str:
        """Extract the action string from the LLM response.

        Args:
            response: The response from the LLM

        Returns:
            str: The extracted action string

        Raises:
            ActionParseError: If the response cannot be parsed
        """
        pass

    @abstractmethod
    def parse_action(self, action_str: str) -> Action:
        """Parse the action string into an Action object.

        Args:
            action_str: The action string extracted from LLM response

        Returns:
            Action: The parsed action

        Raises:
            ActionParseError: If the action string cannot be parsed
        """
        pass


class ActionParser(ABC):
    """Abstract base class for parsing specific action types from action strings.
    
    Each concrete implementation handles a specific type of action (e.g., file operations,
    commands, messages) and determines if it can parse a given action string.
    """

    @abstractmethod
    def check_condition(self, action_str: str) -> bool:
        """Check if this parser can handle the given action string.

        Args:
            action_str: The action string to check

        Returns:
            bool: True if this parser can handle the action string
        """
        pass

    @abstractmethod
    def parse(self, action_str: str) -> Action:
        """Parse the action string into an Action object.

        Args:
            action_str: The action string to parse

        Returns:
            Action: The parsed action

        Raises:
            ActionParseError: If parsing fails
        """
        pass