"""Conversation memory system for processing events into LLM messages."""

from typing import List, Dict, Optional, Generator

from ii_agent.core.message import Message, TextContent, ImageContent, ToolCall
from ii_agent.events.event import Event, EventSource
from ii_agent.events.action import (
    Action, MessageAction, CompleteAction,
    FileReadAction, FileWriteAction, FileEditAction,
    CmdRunAction, IPythonRunCellAction,
    BrowseURLAction, BrowseInteractiveAction
)
from ii_agent.events.observation import (
    Observation, SystemObservation,
    FileReadObservation, FileWriteObservation, FileEditObservation
)
from ii_agent.events.action.mcp import MCPAction


class ConversationMemory:
    """Processes event history into a coherent conversation for the agent.
    
    Based on OpenHands' ConversationMemory pattern, this class converts
    ii-agent Events (Actions and Observations) into Message objects that
    can be sent to LLMs.
    """

    def __init__(self, max_message_chars: Optional[int] = None):
        """Initialize conversation memory.
        
        Args:
            max_message_chars: Maximum characters per message (for truncation)
        """
        self.max_message_chars = max_message_chars

    def process_events(
        self,
        events: List[Event],
        initial_user_message: Optional[str] = None,
        vision_enabled: bool = False,
    ) -> List[Message]:
        """Process event history into a list of messages for the LLM.

        Args:
            events: List of events to convert
            initial_user_message: Initial user message if not in events
            vision_enabled: Whether to include image content

        Returns:
            List[Message]: Processed messages ready for LLM
        """
        messages = []
        
        # Ensure we start with a system message if needed
        self._ensure_system_message(events, messages)
        
        # Add initial user message if provided and not in events
        if initial_user_message and not self._has_initial_user_message(events):
            messages.append(Message(
                role="user",
                content=[TextContent(text=initial_user_message)]
            ))

        # Track pending tool calls and their responses
        pending_tool_calls: Dict[str, Message] = {}
        tool_responses: Dict[str, Message] = {}

        for event in events:
            if isinstance(event, Action):
                msgs_to_add = self._process_action(
                    event, pending_tool_calls, vision_enabled
                )
            elif isinstance(event, Observation):
                msgs_to_add = self._process_observation(
                    event, tool_responses, vision_enabled
                )
            else:
                # Unknown event type, skip
                continue

            # Check if any pending tool calls are now complete
            completed_calls = []
            for response_id, pending_msg in pending_tool_calls.items():
                if pending_msg.tool_calls and all(
                    tc.id in tool_responses for tc in pending_msg.tool_calls
                ):
                    # All tool calls for this message have responses
                    msgs_to_add.append(pending_msg)
                    # Add all the tool responses
                    for tc in pending_msg.tool_calls:
                        msgs_to_add.append(tool_responses[tc.id])
                        tool_responses.pop(tc.id)
                    completed_calls.append(response_id)

            # Remove completed tool calls
            for response_id in completed_calls:
                pending_tool_calls.pop(response_id)

            messages.extend(msgs_to_add)

        # Filter out unmatched tool calls/responses
        messages = list(self._filter_unmatched_tool_calls(messages))

        # Apply formatting
        messages = self._apply_message_formatting(messages)

        return messages

    def _process_action(
        self,
        action: Action,
        pending_tool_calls: Dict[str, Message],
        vision_enabled: bool = False,
    ) -> List[Message]:
        """Convert an action into message format.

        Args:
            action: Action to convert
            pending_tool_calls: Dict of pending tool call messages
            vision_enabled: Whether vision is enabled

        Returns:
            List[Message]: Messages for this action
        """
        if isinstance(action, MessageAction):
            # Regular message from agent or user
            role = "user" if action.source == EventSource.USER else "assistant"
            content = [TextContent(text=action.content or "")]
            
            # Add image content if available and vision enabled
            if vision_enabled and hasattr(action, 'image_urls') and action.image_urls:
                content.append(ImageContent(image_urls=action.image_urls))
            
            return [Message(role=role, content=content)]

        elif isinstance(action, CompleteAction):
            # Task completion
            role = "user" if action.source == EventSource.USER else "assistant"
            return [Message(
                role=role,
                content=[TextContent(text=action.final_answer or "Task completed")]
            )]

        elif isinstance(action, MCPAction):
            # Tool call from agent
            self._add_tool_call_to_current_assistant_message(
                action, pending_tool_calls
            )

        elif isinstance(action, (
            FileReadAction, FileWriteAction, FileEditAction,
            CmdRunAction, IPythonRunCellAction,
            BrowseURLAction, BrowseInteractiveAction
        )):
            # Specific tool actions
            return self._handle_specific_tool_action(action, pending_tool_calls)

        return []

    def _process_observation(
        self,
        observation: Observation,
        tool_responses: Dict[str, Message],
        vision_enabled: bool = False,
    ) -> List[Message]:
        """Convert an observation into message format.

        Args:
            observation: Observation to convert
            tool_responses: Dict of tool response messages
            vision_enabled: Whether vision is enabled

        Returns:
            List[Message]: Messages for this observation
        """
        # Create content for the observation
        content_text = self._get_observation_content(observation)
        content = [TextContent(text=content_text)]

        # Add images if available and vision enabled
        if vision_enabled and hasattr(observation, 'image_urls'):
            image_urls = getattr(observation, 'image_urls', [])
            if image_urls:
                content.append(ImageContent(image_urls=image_urls))

        # Check if this is a tool response
        if hasattr(observation, 'tool_call_metadata') and observation.tool_call_metadata:
            metadata = observation.tool_call_metadata
            tool_responses[metadata.tool_call_id] = Message(
                role="tool",
                content=content,
                tool_call_id=metadata.tool_call_id,
                name=metadata.function_name
            )
            return []  # Don't add to messages yet
        else:
            # Regular observation (user role)
            return [Message(role="user", content=content)]

    def _add_tool_call_to_current_assistant_message(
        self, action: MCPAction, pending_tool_calls: Dict[str, Message]
    ) -> List[Message]:
        """Handle MCPAction tool calls."""
        # Get tool call ID from metadata if available, fallback to action id
        tool_call_id = action.id
        if hasattr(action, 'tool_call_metadata') and action.tool_call_metadata:
            tool_call_id = action.tool_call_metadata.tool_call_id or str(action.id)
        
        # Create tool call object
        tool_call = ToolCall(
            id=tool_call_id,
            function={
                "name": action.name,
                "arguments": str(action.arguments)
            }
        )

        # Get response ID for grouping - use metadata if available
        response_id = str(action.id)
        if hasattr(action, 'tool_call_metadata') and action.tool_call_metadata:
            metadata = action.tool_call_metadata
            if hasattr(metadata, 'model_response') and metadata.model_response:
                if hasattr(metadata.model_response, 'id'):
                    response_id = metadata.model_response.id
                elif isinstance(metadata.model_response, dict):
                    response_id = metadata.model_response.get('id', str(action.id))
            elif metadata.response_id:
                response_id = metadata.response_id

        # Store pending tool call
        pending_tool_calls[response_id] = Message(
            role="assistant",
            content=[],  # Tool calls typically have no content
            tool_calls=[tool_call]
        )

        return []  # Will be added when responses are ready

    def _handle_specific_tool_action(
        self, action: Action, pending_tool_calls: Dict[str, Message]
    ) -> List[Message]:
        """Handle specific tool actions (file, command, browse)."""
        # Map action to function name
        function_name = self._get_function_name_for_action(action)
        
        if not action.tool_call_metadata:
            # No metadata, treat as regular message
            return [Message(
                role="assistant",
                content=[TextContent(text=action.message)]
            )]

        # Create tool call
        tool_call = ToolCall(
            id=getattr(action, 'tool_call_id', ''),
            function={
                "name": function_name,
                "arguments": self._serialize_action_args(action)
            }
        )

        # Store pending
        response_id = getattr(action.tool_call_metadata, 'model_response', {})
        response_id = getattr(response_id, 'id', tool_call.id)
        
        pending_tool_calls[response_id] = Message(
            role="assistant",
            content=[],
            tool_calls=[tool_call]
        )

        return []

    def _get_observation_content(self, observation: Observation) -> str:
        """Get text content for an observation."""
        if isinstance(observation, SystemObservation):
            return observation.content
        elif isinstance(observation, (
            FileReadObservation, FileWriteObservation, FileEditObservation
        )):
            return str(observation)
        else:
            return getattr(observation, 'content', str(observation))

    def _get_function_name_for_action(self, action: Action) -> str:
        """Get function name for a specific action type."""
        action_to_function = {
            FileReadAction: "file_read",
            FileWriteAction: "file_write", 
            FileEditAction: "file_edit",
            CmdRunAction: "cmd_run",
            IPythonRunCellAction: "ipython_run_cell",
            BrowseURLAction: "browse_url",
            BrowseInteractiveAction: "browse_interactive",
        }
        return action_to_function.get(type(action), "unknown_action")

    def _serialize_action_args(self, action: Action) -> str:
        """Serialize action arguments for tool call."""
        import json
        
        # Extract key fields from action
        args = {}
        for field_name, field in action.__dataclass_fields__.items():
            if not field_name.startswith('_') and field_name not in [
                'source', 'timestamp', 'id', 'hidden', 'tool_call_metadata'
            ]:
                value = getattr(action, field_name, None)
                if value is not None:
                    args[field_name] = value
        
        return json.dumps(args)

    def _ensure_system_message(self, events: List[Event], messages: List[Message]):
        """Ensure there's a system message at the start."""
        # Check if first event is already a system message
        if events and isinstance(events[0], MessageAction) and events[0].source == EventSource.ENVIRONMENT:
            return  # Already has system message
            
        # Add default system message
        messages.append(Message(
            role="system",
            content=[TextContent(text="You are a helpful AI assistant.")]
        ))

    def _has_initial_user_message(self, events: List[Event]) -> bool:
        """Check if events contain an initial user message."""
        for event in events:
            if isinstance(event, (MessageAction)):
                if event.source == EventSource.USER:
                    return True
        return False

    def _filter_unmatched_tool_calls(
        self, messages: List[Message]
    ) -> Generator[Message, None, None]:
        """Filter out unmatched tool calls and responses."""
        # Collect tool call IDs and response IDs
        tool_call_ids = set()
        tool_response_ids = set()
        
        for msg in messages:
            if msg.role == "assistant" and msg.tool_calls:
                for tc in msg.tool_calls:
                    if tc.id:
                        tool_call_ids.add(tc.id)
            elif msg.role == "tool" and msg.tool_call_id:
                tool_response_ids.add(msg.tool_call_id)

        # Filter messages
        for msg in messages:
            if msg.role == "tool" and msg.tool_call_id:
                # Only include tool responses with matching calls
                if msg.tool_call_id in tool_call_ids:
                    yield msg
            elif msg.role == "assistant" and msg.tool_calls:
                # Only include tool calls with matching responses
                matched_calls = [
                    tc for tc in msg.tool_calls 
                    if tc.id in tool_response_ids
                ]
                if matched_calls:
                    yield msg.model_copy(update={"tool_calls": matched_calls})
            else:
                # Include all other messages
                yield msg

    def _apply_message_formatting(self, messages: List[Message]) -> List[Message]:
        """Apply final formatting to messages."""
        # Add spacing between consecutive user messages
        formatted = []
        prev_role = None
        
        for msg in messages:
            if msg.role == "user" and prev_role == "user" and msg.content:
                # Add spacing to first text content
                for content in msg.content:
                    if isinstance(content, TextContent):
                        content.text = "\n\n" + content.text
                        break
            
            formatted.append(msg)
            prev_role = msg.role
            
        return formatted