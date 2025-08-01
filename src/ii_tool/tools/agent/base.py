from typing import Any, List
from ii_tool.tools.base import BaseTool, ToolResult
from ii_tool.core import WorkspaceManager
from ii_agent.core.event_stream import EventStream
from ii_agent.llm.context_manager.base import ContextManager
from ii_agent.controller.agent import Agent
from ii_agent.controller.agent_controller import AgentController
from ii_agent.controller.tool_manager import AgentToolManager
from ii_agent.controller.state import State


class BaseAgentTool(BaseTool):
    name: str
    display_name: str
    description: str
    input_schema: dict[str, Any]
    read_only: bool

    def __init__(
        self,
        agent: Agent,
        tools: List[BaseTool],
        context_manager: ContextManager,
        event_stream: EventStream,
        workspace_manager: WorkspaceManager,
        max_turns: int = 200,
    ):
        self.agent = agent
        self.tools = tools
        self.context_manager = context_manager
        self.event_stream = event_stream
        self.workspace_manager = workspace_manager
        self.max_turns = max_turns
        
    
    def _setup_agent_controller(self) -> AgentController:
        tool_manager = AgentToolManager()
        tool_manager.register_tools(self.tools)

        return AgentController(
            agent=self.agent,
            tool_manager=tool_manager,
            init_history=State(),
            workspace_manager=self.workspace_manager,
            event_stream=self.event_stream,
            context_manager=self.context_manager,
            max_turns=self.max_turns,
            interactive_mode=False, # Not supported for agent as tools
            agent_as_tool=True,
            agent_tool_name=self.name,
        )