from pdb import run
from typing import Any, List, Optional
from uuid import UUID
from ii_tool.tools.base import BaseTool
from ii_tool.core import WorkspaceManager
from ii_agent.core.event import EventType, RealtimeEvent
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
        max_turns: int = 200,
        config: Optional[Any] = None,
        session_id: Optional[UUID] = None,
        run_id: Optional[UUID] = None,
    ):
        self.agent = agent
        self.tools = tools
        self.context_manager = context_manager
        self.event_stream = event_stream
        self.max_turns = max_turns
        self.config = config
        self.session_id = session_id
        self.run_id = run_id
        self._setup_agent_controller()

    def cancel(self):
        self.controller.cancel()

    async def emit_completion_event(self, is_interrupted: bool = False, message: str = "Sub agent completed"):
        """Emit the appropriate completion event based on whether the subagent was interrupted."""
        if is_interrupted:
            event_type = EventType.SUB_AGENT_INTERRUPTED
            message = "Sub agent interrupted"
        else:
            event_type = EventType.SUB_AGENT_COMPLETE
        await self.event_stream.publish(
            RealtimeEvent(
                type=event_type,
                session_id=self._get_session_id(),
                run_id=self._get_run_id(),
                content={"text": message, "is_interrupted": is_interrupted},
            )
        )

    def _setup_agent_controller(self):
        tool_manager = AgentToolManager()
        tool_manager.register_tools(self.tools)

        self.controller = AgentController(
            agent=self.agent,
            tool_manager=tool_manager,
            history=State(),
            event_stream=self.event_stream,
            context_manager=self.context_manager,
            max_turns=self.max_turns,
            interactive_mode=False,  # Not supported for agent as tools
            config=self.config,
            is_sub_agent=True,
            session_id=self.session_id,
            run_id=self.run_id,
        )

        # Note: Sub-agents don't typically use pubsub, so we don't call initialize_pubsub()
        # If needed, this would need to be made async and called from an async context

    def _get_session_id(self) -> Optional[UUID]:
        """Return session_id UUID if available."""
        return self.session_id

    def _get_run_id(self) -> Optional[UUID]:
        """Return run_id UUID if available."""
        return self.run_id
