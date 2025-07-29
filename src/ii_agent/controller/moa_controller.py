import logging
from typing import Any, Optional, List

from ii_agent.controller.agent_controller import AgentController
from ii_agent.agents.moa_agent import MoAAgent, create_moa_agent
from ii_agent.llm.base import ToolParam
from ii_agent.llm.moa_client import MoALLMClient
from ii_agent.controller.state import State
from ii_agent.core.config.agent_config import AgentConfig
from ii_agent.core.config.moa_config import MoAConfig, create_default_moa_config
from ii_agent.controller.tool_manager import AgentToolManager
from ii_agent.utils.workspace_manager import WorkspaceManager
from ii_agent.core.event_stream import EventStream
from ii_agent.llm.context_manager.base import ContextManager
from ii_agent.core.event import EventType, RealtimeEvent

logger = logging.getLogger(__name__)


class MoAAgentController(AgentController):
    """Agent controller with Mixture-of-Agents (MoA) support."""
    
    def __init__(
        self,
        agent: MoAAgent,
        tool_manager: AgentToolManager,
        init_history: State,
        workspace_manager: WorkspaceManager,
        event_stream: EventStream,
        context_manager: ContextManager,
        max_turns: int = 200,
        interactive_mode: bool = True,
        config: Optional[Any] = None,
    ):
        """Initialize the MoA agent controller.
        
        Args:
            agent: The MoA agent to use
            tool_manager: Tool manager
            init_history: Initial history to use
            workspace_manager: Workspace manager for file operations
            event_stream: Event stream for publishing events
            context_manager: Context manager for token counting and truncation
            max_turns: Maximum number of turns
            interactive_mode: Whether to use interactive mode
            config: Configuration object
        """
        super().__init__(
            agent, tool_manager, init_history, workspace_manager,
            event_stream, context_manager, max_turns, interactive_mode, config
        )
        
        # Store MoA-specific agent reference
        self.moa_agent = agent
        
    def get_moa_status(self) -> dict[str, Any]:
        """Get the current MoA status and configuration."""
        if not isinstance(self.agent, MoAAgent):
            return {"moa_enabled": False, "error": "Agent is not a MoA agent"}
        
        moa_info = self.moa_agent.get_moa_info()
        
        # Add performance stats if available
        if self.moa_agent.moa_enabled and self.moa_agent.moa_llm:
            try:
                performance_stats = self.moa_agent.moa_llm.layer_processor.get_performance_stats()
                moa_info["performance_stats"] = performance_stats
            except Exception as e:
                logger.warning(f"Could not get performance stats: {str(e)}")
        
        return moa_info
    
    def enable_moa(self, moa_config: Optional[MoAConfig] = None) -> dict[str, Any]:
        """Enable MoA for the current agent.
        
        Args:
            moa_config: Optional MoA configuration. If None, uses default.
            
        Returns:
            Status of the operation
        """
        try:
            if not isinstance(self.agent, MoAAgent):
                return {
                    "success": False,
                    "error": "Current agent does not support MoA"
                }
            
            if moa_config is None:
                moa_config = create_default_moa_config()
            
            self.moa_agent.enable_moa(moa_config)
            
            # Emit event for MoA activation
            self.event_stream.add_event(
                RealtimeEvent(
                    type=EventType.AGENT_RESPONSE,
                    content={
                        "text": f"MoA enabled with {len(moa_config.get_reference_configs())} reference models"
                    }
                )
            )
            
            logger.info("MoA enabled successfully")
            return {
                "success": True,
                "moa_info": self.moa_agent.get_moa_info()
            }
            
        except Exception as e:
            logger.error(f"Failed to enable MoA: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def disable_moa(self) -> dict[str, Any]:
        """Disable MoA for the current agent.
        
        Returns:
            Status of the operation
        """
        try:
            if not isinstance(self.agent, MoAAgent):
                return {
                    "success": False,
                    "error": "Current agent does not support MoA"
                }
            
            self.moa_agent.disable_moa()
            
            # Emit event for MoA deactivation
            self.event_stream.add_event(
                RealtimeEvent(
                    type=EventType.AGENT_RESPONSE,
                    content={"text": "MoA disabled, using standard agent behavior"}
                )
            )
            
            logger.info("MoA disabled successfully")
            return {"success": True}
            
        except Exception as e:
            logger.error(f"Failed to disable MoA: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def update_moa_config(self, moa_config: MoAConfig) -> dict[str, Any]:
        """Update the MoA configuration.
        
        Args:
            moa_config: New MoA configuration
            
        Returns:
            Status of the operation
        """
        try:
            if not isinstance(self.agent, MoAAgent):
                return {
                    "success": False,
                    "error": "Current agent does not support MoA"
                }
            
            self.moa_agent.update_moa_config(moa_config)
            
            # Emit event for configuration update
            self.event_stream.add_event(
                RealtimeEvent(
                    type=EventType.AGENT_RESPONSE,
                    content={"text": "MoA configuration updated successfully"}
                )
            )
            
            logger.info("MoA configuration updated successfully")
            return {
                "success": True,
                "moa_info": self.moa_agent.get_moa_info()
            }
            
        except Exception as e:
            logger.error(f"Failed to update MoA configuration: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }


def create_moa_controller(
    tool_manager: AgentToolManager,
    tools: List[ToolParam],
    init_history: State,
    workspace_manager: WorkspaceManager,
    event_stream: EventStream,
    context_manager: ContextManager,
    moa_config: Optional[MoAConfig] = None,
    agent_config: Optional[AgentConfig] = None,
    max_turns: int = 200,
    interactive_mode: bool = True,
    config: Optional[Any] = None,
) -> MoAAgentController:
    """Factory function to create a MoA agent controller.
    
    Args:
        tool_manager: Tool manager with registered tools
        tools: List of tools for the agent (as ToolParam)
        init_history: Initial history state
        workspace_manager: Workspace manager
        event_stream: Event stream
        context_manager: Context manager
        moa_config: MoA configuration (optional)
        agent_config: Agent configuration (optional)
        max_turns: Maximum number of turns
        interactive_mode: Whether to use interactive mode
        config: General configuration object
        
    Returns:
        Configured MoA agent controller
    """
    # Create default configurations if not provided
    if moa_config is None:
        moa_config = create_default_moa_config()
    
    if agent_config is None:
        agent_config = AgentConfig()
    
    agent_config.moa_config = moa_config
    
    # Create MoA agent with proper fallback LLM client
    # Create a fallback LLM client using the first reference model
    reference_configs = moa_config.get_reference_configs()
    if reference_configs:
        from ii_agent.llm import get_client
        fallback_llm = get_client(reference_configs[0])
        logger.info(f"Created fallback LLM client with model: {reference_configs[0].model}")
    else:
        raise ValueError("No reference models configured for MoA")
    
    moa_agent = create_moa_agent(fallback_llm, tools, moa_config, agent_config)
    
    # Create controller
    controller = MoAAgentController(
        agent=moa_agent,
        tool_manager=tool_manager,
        init_history=init_history,
        workspace_manager=workspace_manager,
        event_stream=event_stream,
        context_manager=context_manager,
        max_turns=max_turns,
        interactive_mode=interactive_mode,
        config=config,
    )
    
    logger.info(f"Created MoA controller with {len(moa_config.get_reference_configs())} reference models")
    
    return controller


class MoAControllerFactory:
    """Factory class for creating MoA controllers with different configurations."""
    
    @staticmethod
    def create_high_performance_controller(
        tools: List[ToolParam],
        init_history: State,
        workspace_manager: WorkspaceManager,
        event_stream: EventStream,
        context_manager: ContextManager,
        **kwargs
    ) -> MoAAgentController:
        """Create a high-performance MoA controller optimized for quality."""
        moa_config = create_default_moa_config()
        moa_config.parallel_execution = True
        moa_config.max_concurrent_requests = 3
        
        return create_moa_controller(
            tools, init_history, workspace_manager, event_stream,
            context_manager, moa_config, **kwargs
        )
    
    @staticmethod
    def create_cost_optimized_controller(
        tools: List[ToolParam],
        init_history: State,
        workspace_manager: WorkspaceManager,
        event_stream: EventStream,
        context_manager: ContextManager,
        **kwargs
    ) -> MoAAgentController:
        """Create a cost-optimized MoA controller with reduced model usage."""
        moa_config = create_default_moa_config()
        moa_config.parallel_execution = False  # Sequential to reduce API calls
        moa_config.num_layers = 2  # Minimum layers
        
        return create_moa_controller(
            tools, init_history, workspace_manager, event_stream,
            context_manager, moa_config, **kwargs
        )
    
    @staticmethod
    def create_research_controller(
        tools: List[ToolParam],
        init_history: State,
        workspace_manager: WorkspaceManager,
        event_stream: EventStream,
        context_manager: ContextManager,
        **kwargs
    ) -> MoAAgentController:
        """Create a MoA controller optimized for research tasks."""
        moa_config = create_default_moa_config()
        moa_config.num_layers = 3  # Extra layer for refinement
        moa_config.parallel_execution = True
        
        # Custom aggregation prompt for research
        moa_config.aggregation_prompt_template = """You are synthesizing responses from multiple AI models for a research query. 
Your task is to create a comprehensive, well-researched answer that combines the best insights.

Research Query: {query}

Model Responses:
{responses}

Please provide a synthesized response that:
1. Combines factual information from all sources
2. Identifies and resolves any contradictions
3. Provides comprehensive coverage of the topic
4. Includes relevant details and examples
5. Maintains academic rigor and accuracy
6. Structures the response logically

Synthesized Research Response:"""
        
        return create_moa_controller(
            tools, init_history, workspace_manager, event_stream,
            context_manager, moa_config, **kwargs
        )