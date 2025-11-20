"""Pure ReAct loop FSM - no presentation, no persistence."""

from dataclasses import dataclass
from typing import AsyncIterator, Any, List, Dict, Optional
from enum import Enum

from ii_agent.server.chat.models import (
    Message,
    ToolCall,
    FinishReason,
    RunResponseOutput,
)


class EventType(str, Enum):
    """ReAct loop event types."""
    LLM_RESPONSE = "llm_response"
    LLM_COMPLETE = "llm_complete"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    TASK_COMPLETE = "task_complete"
    ERROR = "error"


@dataclass
class ReactEvent:
    """Domain event from ReAct loop."""
    type: EventType
    data: Dict[str, Any]


class ReactLoop:
    """Pure ReAct FSM - separates state transitions from I/O."""

    @staticmethod
    async def run(
        messages: List[Message],
        provider: Any,
        tools: List[Dict[str, Any]],
        tool_executor: Any,
        max_turns: int = 50,
    ) -> AsyncIterator[ReactEvent]:
        """Execute ReAct loop, yielding domain events.

        Args:
            messages: Conversation history (mutable - updated in place)
            provider: LLM provider with .stream() method
            tools: Tool definitions to pass to LLM
            tool_executor: Callable that executes tools
            max_turns: Maximum loop iterations

        Yields:
            ReactEvent: Domain events (llm_response, tool_call, etc.)
        """
        turn_count = 0

        while True:
            # Safety: max turns check
            turn_count += 1
            if turn_count > max_turns:
                yield ReactEvent(
                    type=EventType.ERROR,
                    data={"message": "Max turns exceeded"}
                )
                return

            # State: WAITING_FOR_LLM
            # Call LLM and stream response
            run_response: Optional[RunResponseOutput] = None

            async for event in provider.stream(messages=messages, tools=tools):
                # Forward LLM streaming events
                if event.type == "complete":
                    run_response = event.response
                else:
                    yield ReactEvent(
                        type=EventType.LLM_RESPONSE,
                        data={"event": event}
                    )

            if not run_response:
                yield ReactEvent(
                    type=EventType.ERROR,
                    data={"message": "No response from LLM"}
                )
                return

            # Emit completion event (for usage tracking)
            yield ReactEvent(
                type=EventType.LLM_COMPLETE,
                data={
                    "response": run_response,
                    "usage": run_response.usage,
                }
            )

            # State transition decision
            if run_response.finish_reason == FinishReason.TOOL_USE:
                # State: EXECUTING_TOOLS
                tool_calls = [
                    part for part in run_response.content
                    if isinstance(part, ToolCall) and not part.provider_executed
                ]

                # Execute each tool
                tool_results = []
                for tool_call in tool_calls:
                    # Emit tool call event
                    yield ReactEvent(
                        type=EventType.TOOL_CALL,
                        data={"tool_call": tool_call}
                    )

                    # Execute tool
                    tool_result = await tool_executor(tool_call)
                    tool_results.append(tool_result)

                    # Emit tool result event
                    yield ReactEvent(
                        type=EventType.TOOL_RESULT,
                        data={"tool_result": tool_result}
                    )

                # Update messages in place (caller's responsibility to persist)
                # This is the FSM state update - not persistence
                # messages.append(assistant_message)
                # messages.append(tool_results_message)
                # Note: Caller must add messages before next iteration

                # Transition back to WAITING_FOR_LLM
                continue

            else:
                # State: TERMINAL (no tool calls)
                yield ReactEvent(
                    type=EventType.TASK_COMPLETE,
                    data={
                        "response": run_response,
                        "finish_reason": run_response.finish_reason,
                    }
                )
                return
