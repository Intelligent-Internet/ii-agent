from typing import Any, List, Optional
import uuid

from ii_agent.agents.base import BaseAgent
from ii_agent.llm.base import LLMClient, TextResult, ToolParam, ToolCall, TextPrompt
from ii_agent.core.config.agent_config import AgentConfig
from ii_agent.core.logger import logger
from ii_agent.utils.constants import COMPLETE_MESSAGE


class FunctionCallAgent(BaseAgent):
    """A thin agent that converts state to actions using LLM."""
    
    name = "general_agent"
    description = """\
A general agent that can accomplish tasks and answer questions.

If you are faced with a task that involves more than a few steps, or if the task is complex, or if the instructions are very long,
try breaking down the task into smaller steps. After call this tool to update or create a plan, use write_file or str_replace_tool to update the plan to todo.md
"""

    def __init__(
        self,
        llm: LLMClient,
        config: AgentConfig,
        system_prompt: str,
        available_tools: List[ToolParam],
    ):
        """Initialize the thin agent.
        
        Args:
            llm: The LLM client to use for decision making
            config: Agent configuration
            system_prompt: System prompt for the agent
            available_tools: List of available tools the agent can use
        """
        super().__init__(llm, config)
        self.system_prompt = system_prompt
        self.available_tools = available_tools

    def step(self, state) -> "Action":
        """Convert state to action using LLM.
        
        Args:
            state: Current state containing event history
            
        Returns:
            Action: The action to take next
        """
        # Runtime imports to avoid circular dependencies
        from ii_agent.events.action import CompleteAction
        from ii_agent.events.event import EventSource
        
        # Build messages from state for LLM
        messages = self._build_messages_from_state(state)
        # Get response from LLM
        try:
            model_response, _ = self.llm.generate(
                messages=messages,
                max_tokens=self.config.max_tokens_per_turn,
                tools=self.available_tools,
                system_prompt=self.system_prompt,
                temperature=self.config.temperature,
            )
        except Exception as e:
            logger.error(f"LLM generation failed: {e}")
            return CompleteAction(
                final_answer=f"Agent error: {e}",
                source=EventSource.AGENT
            )

        if len(model_response) == 0:
            # No response, agent is complete
            return CompleteAction(
                final_answer=COMPLETE_MESSAGE,
                source=EventSource.AGENT
            )

        # Process the response and convert to action
        return self._convert_response_to_action(model_response)

    def _build_messages_from_state(self, state) -> List[List[Any]]:
        """Build LLM messages from the state history.
        
        Args:
            state: Current state
            
        Returns:
            List of message turns for the LLM
        """
        # Runtime imports
        from ii_agent.events.observation import UserMessageObservation, SystemObservation
        from ii_agent.events.action import MessageAction
        from ii_agent.events.action.mcp import MCPAction
        from ii_agent.events.event import EventSource
        from ii_agent.llm.base import ToolFormattedResult
        
        messages = []
        
        # Get the most recent events and convert them to LLM format
        for event in state.history:
            if isinstance(event, MessageAction) and event.source == EventSource.USER:
                # User message turn
                user_turn = [TextPrompt(text=event.message)]
                messages.append(user_turn)
                
            elif isinstance(event, MessageAction) and event.source == EventSource.AGENT:
                # Agent message turn
                agent_turn = [TextResult(text=event.content)]
                messages.append(agent_turn)
                
            elif isinstance(event, MCPAction):
                # Tool call from agent
                tool_call = ToolCall(
                    tool_call_id=getattr(event, 'id', ''),
                    tool_name=event.name,
                    tool_input=event.arguments
                )
                # Add to the last assistant turn or create new one
                if messages and isinstance(messages[-1][-1], (TextResult, ToolCall)):
                    messages[-1].append(tool_call)
                else:
                    messages.append([tool_call])
                    
            elif isinstance(event, SystemObservation):
                # System observation - convert to text result
                text_result = TextResult(text=event.content)
                messages.append([text_result])

        return messages

    def _convert_response_to_action(self, model_response: List[Any]) -> "Action":
        """Convert LLM response to an action.
        
        Args:
            model_response: Response from the LLM
            
        Returns:
            Action: The converted action
        """
        # Runtime imports
        from ii_agent.events.action import MessageAction, CompleteAction
        from ii_agent.events.action.mcp import MCPAction
        from ii_agent.events.event import EventSource
        from ii_agent.events.tool import ToolCallMetadata
        
        # Check for tool calls first
        tool_calls = [item for item in model_response if isinstance(item, ToolCall)]
        text_results = [item for item in model_response if isinstance(item, TextResult)]
        
        if tool_calls:
            # Agent wants to call a tool
            tool_call = tool_calls[0]  # Take first tool call
            
            # Create tool call metadata
            metadata = ToolCallMetadata(
                function_name=tool_call.tool_name,
                tool_call_id=tool_call.tool_call_id,
                model_response=model_response,  # Store the full response
                total_calls_in_response=len(tool_calls)
            )
            
            action = MCPAction(
                name=tool_call.tool_name,
                arguments=tool_call.tool_input,
                source=EventSource.AGENT
            )
            action.tool_call_metadata = metadata
            return action
        
        elif text_results:
            # Agent provided a text response
            text_result = text_results[0]
            
            # Check if this looks like a completion
            if COMPLETE_MESSAGE.lower() in text_result.text.lower():
                return CompleteAction(
                    final_answer=text_result.text,
                    source=EventSource.AGENT
                )
            else:
                return MessageAction(
                    content=text_result.text,
                    source=EventSource.AGENT
                )
        
        else:
            # No recognizable response, complete the task
            return CompleteAction(
                final_answer="Task completed",
                source=EventSource.AGENT
            )