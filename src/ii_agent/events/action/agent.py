"""Agent-specific action classes."""

from __future__ import annotations

from typing import ClassVar, Optional, Any

from ii_agent.core.schema import ActionType, SecurityRisk, AgentState
from ii_agent.events.action.action import Action


class AgentThinkAction(Action):
    """Action representing agent's internal thinking/reasoning."""
    
    thought: str = ""
    action: str = ActionType.THINK
    runnable: ClassVar[bool] = False
    
    @property
    def message(self) -> str:
        return f"Agent thinking: {self.thought[:50]}{'...' if len(self.thought) > 50 else ''}"

    def __str__(self) -> str:
        return f"**AgentThinkAction**\nTHOUGHT: {self.thought}"


class AgentFinishAction(Action):
    """Action indicating the agent has completed its task."""
    
    final_answer: str = ""
    action: str = ActionType.FINISH
    runnable: ClassVar[bool] = False
    
    @property
    def message(self) -> str:
        return f"Task completed: {self.final_answer[:50]}{'...' if len(self.final_answer) > 50 else ''}"
    
    def __str__(self) -> str:
        return f"**AgentFinishAction**\nFINAL_ANSWER: {self.final_answer}"


class AgentRejectAction(Action):
    """Action indicating the agent rejects or cannot complete the task."""
    
    reason: str = ""
    action: str = ActionType.REJECT
    runnable: ClassVar[bool] = False
    
    @property
    def message(self) -> str:
        return f"Agent rejects task: {self.reason}"
    
    def __str__(self) -> str:
        return f"**AgentRejectAction**\nREASON: {self.reason}"


class AgentDelegateAction(Action):
    """Action indicating the agent delegates to another agent or system."""
    
    delegate_to: str = ""
    task_description: str = ""
    action: str = ActionType.DELEGATE
    runnable: ClassVar[bool] = True
    
    @property
    def message(self) -> str:
        return f"Delegating to {self.delegate_to}: {self.task_description[:50]}{'...' if len(self.task_description) > 50 else ''}"
    
    def __str__(self) -> str:
        return f"**AgentDelegateAction**\nDELEGATE_TO: {self.delegate_to}\nTASK: {self.task_description}"


class ChangeAgentStateAction(Action):
    """Action to change the agent's state."""
    
    agent_state: AgentState = AgentState.RUNNING
    action: str = ActionType.CHANGE_AGENT_STATE
    runnable: ClassVar[bool] = True
    
    @property
    def message(self) -> str:
        return f"Changing agent state to: {self.agent_state}"
    
    def __str__(self) -> str:
        return f"**ChangeAgentStateAction**\nNEW_STATE: {self.agent_state}"


class RecallAction(Action):
    """Action to recall information from memory or previous context."""
    
    query: str = ""
    memories: Optional[list[Any]] = None
    action: str = ActionType.RECALL
    runnable: ClassVar[bool] = True
    
    @property
    def message(self) -> str:
        return f"Recalling: {self.query}"
    
    def __str__(self) -> str:
        ret = f"**RecallAction**\nQUERY: {self.query}"
        if self.memories:
            ret += f"\nMEMORIES: {len(self.memories)} items"
        return ret


# Legacy ii-agent actions for backward compatibility
class CompleteAction(AgentFinishAction):
    """Legacy alias for AgentFinishAction."""
    
    def __init__(self, final_answer: str = "", **kwargs):
        super().__init__(final_answer=final_answer, **kwargs)


class ToolCallAction(Action):
    """Legacy ii-agent action for tool calls."""
    
    tool_name: str = ""
    tool_input: dict = None
    tool_call_id: str = ""
    action: str = ActionType.TOOL_CALL
    runnable: ClassVar[bool] = True
    
    def __post_init__(self):
        super().__post_init__()
        if self.tool_input is None:
            self.tool_input = {}
        # Set tool call metadata for this action
        if self.tool_call_id and self.tool_name:
            from ii_agent.events.tool import ToolCallMetadata
            self.tool_call_metadata = ToolCallMetadata(
                function_name=self.tool_name,
                tool_call_id=self.tool_call_id
            )
    
    @property
    def message(self) -> str:
        return f"Calling tool: {self.tool_name}"
    
    def __str__(self) -> str:
        return f"**ToolCallAction**\nTOOL: {self.tool_name}\nID: {self.tool_call_id}"