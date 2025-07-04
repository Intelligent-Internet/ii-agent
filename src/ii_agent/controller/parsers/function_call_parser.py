"""Function call response parser for tool call responses."""

import json
from typing import Any, Dict, List

from ii_agent.controller.action_parser import ResponseParser, ActionParseError
from ii_agent.events.action import (
    Action, MessageAction, CompleteAction,
    FileReadAction, FileWriteAction, FileEditAction,
    CmdRunAction, IPythonRunCellAction,
    BrowseURLAction, BrowseInteractiveAction
)
from ii_agent.events.action.mcp import MCPAction
from ii_agent.events.tool import ToolCallMetadata
from ii_agent.events.event import EventSource


class FunctionCallResponseParser(ResponseParser):
    """Parser for LLM responses containing function/tool calls.
    
    Handles responses from LLMs that support function calling (like OpenAI GPT models)
    and converts them into appropriate Action objects.
    """

    def __init__(self):
        super().__init__()
        # Map function names to action classes
        self.function_to_action = {
            "file_read": FileReadAction,
            "file_write": FileWriteAction, 
            "file_edit": FileEditAction,
            "cmd_run": CmdRunAction,
            "ipython_run_cell": IPythonRunCellAction,
            "browse_url": BrowseURLAction,
            "browse_interactive": BrowseInteractiveAction,
        }

    def parse(self, response: Any) -> Action:
        """Parse LLM response with function calls into an Action.

        Args:
            response: LLM response object (typically from OpenAI/Anthropic)

        Returns:
            Action: Parsed action object

        Raises:
            ActionParseError: If parsing fails
        """
        try:
            # Handle different response formats
            if hasattr(response, 'choices') and response.choices:
                # OpenAI format
                choice = response.choices[0]
                message = choice.message
                
                # Check for tool calls
                if hasattr(message, 'tool_calls') and message.tool_calls:
                    return self._parse_tool_calls(message.tool_calls, response)
                
                # Check for regular content
                if hasattr(message, 'content') and message.content:
                    return self._parse_text_content(message.content)
                    
            elif isinstance(response, dict):
                # Dictionary format
                if 'tool_calls' in response:
                    return self._parse_tool_calls(response['tool_calls'], response)
                elif 'content' in response:
                    return self._parse_text_content(response['content'])
                    
            else:
                # Try to parse as string
                return self._parse_text_content(str(response))
                
        except Exception as e:
            raise ActionParseError(f"Failed to parse function call response: {e}")
        
        raise ActionParseError("No parseable content found in response")

    def parse_response(self, response: Any) -> str:
        """Extract action string from response (for text-based parsing)."""
        if hasattr(response, 'choices') and response.choices:
            message = response.choices[0].message
            return getattr(message, 'content', '') or ''
        elif isinstance(response, dict):
            return response.get('content', '')
        else:
            return str(response)

    def parse_action(self, action_str: str) -> Action:
        """Parse action string into Action (for text-based workflows)."""
        # For function call parser, this is typically not used
        # as we parse directly from tool calls
        action = MessageAction(content=action_str)
        action.source = EventSource.AGENT
        return action

    def _parse_tool_calls(self, tool_calls: List[Any], full_response: Any) -> Action:
        """Parse tool calls into appropriate actions.

        Args:
            tool_calls: List of tool call objects
            full_response: Full LLM response for metadata

        Returns:
            Action: Appropriate action based on tool call
        """
        if not tool_calls:
            raise ActionParseError("Empty tool calls list")
        
        # Take the first tool call (could be enhanced to handle multiple)
        tool_call = tool_calls[0]
        
        # Extract tool call details
        tool_call_id = getattr(tool_call, 'id', None) or ''
        function_name = ''
        function_args = {}
        
        if hasattr(tool_call, 'function'):
            function = tool_call.function
            function_name = getattr(function, 'name', '')
            
            # Parse arguments
            args_str = getattr(function, 'arguments', '{}')
            try:
                function_args = json.loads(args_str) if args_str else {}
            except json.JSONDecodeError:
                raise ActionParseError(f"Invalid JSON in function arguments: {args_str}")
        
        # Create tool call metadata
        metadata = ToolCallMetadata(
            function_name=function_name,
            tool_call_id=tool_call_id,
            model_response=full_response,
            total_calls_in_response=len(tool_calls)
        )
        
        # Map to specific action type
        action_class = self.function_to_action.get(function_name)
        if action_class:
            try:
                # Create specific action with arguments
                action = action_class(**function_args)
                action.tool_call_metadata = metadata
                
                # Set tool_call_id if the action supports it
                if hasattr(action, 'tool_call_id'):
                    action.tool_call_id = tool_call_id
                    
                return action
            except TypeError as e:
                raise ActionParseError(f"Invalid arguments for {function_name}: {e}")
        else:
            # Fall back to generic tool call action
            action = MCPAction(
                name=function_name,
                arguments=function_args
            )
            action.source = EventSource.AGENT
            action.tool_call_metadata = metadata
            return action

    def _parse_text_content(self, content: str) -> Action:
        """Parse text content when no tool calls are present.

        Args:
            content: Text content from LLM

        Returns:
            Action: Message or Complete action
        """
        if not content or not content.strip():
            action = CompleteAction(final_answer="")
            action.source = EventSource.AGENT
            return action
        
        # Check for completion indicators
        completion_indicators = [
            "task completed",
            "finished",
            "done",
            "complete",
            "no further action needed"
        ]
        
        content_lower = content.lower()
        if any(indicator in content_lower for indicator in completion_indicators):
            action = CompleteAction(final_answer=content)
            action.source = EventSource.AGENT
            return action
        
        # Return as message action
        action = MessageAction(content=content)
        action.source = EventSource.AGENT
        return action