import logging
from typing import List
from ii_agent.controller.agent import Agent
from ii_agent.llm.base import LLMClient, ToolParam, AssistantContentBlock
from ii_agent.llm.moa_client import MoALLMClient
from ii_agent.controller.state import State
from ii_agent.core.config.agent_config import AgentConfig
from ii_agent.core.config.moa_config import MoAConfig, create_default_moa_config

logger = logging.getLogger(__name__)


class MoAAgent(Agent):
    """Mixture-of-Agents agent that leverages multiple LLMs for enhanced performance."""
    
    def __init__(
        self,
        llm: LLMClient,
        config: AgentConfig,
        tools: List[ToolParam],
    ):
        """Initialize the MoA agent.
        
        Args:
            llm: The LLM client to use (can be regular or MoA client)
            config: The configuration for the agent
            tools: List of tools to use
        """
        super().__init__(llm, config)
        self.tools = tools
        
        # Initialize MoA-specific components
        self.moa_config = config.moa_config
        self.moa_enabled = self.moa_config and self.moa_config.enabled
        
        if self.moa_enabled:
            logger.info("Initializing MoA agent with multi-model support")
            
            # Create MoA LLM client if needed
            if not isinstance(llm, MoALLMClient):
                self.moa_llm = MoALLMClient(self.moa_config)
                logger.info(f"Created MoA LLM client with {len(self.moa_llm.reference_clients)} reference models")
            else:
                self.moa_llm = llm
                logger.info("Using provided MoA LLM client")
        else:
            logger.info("MoA disabled, using standard agent behavior")
            self.moa_llm = None
    
    def step(self, state: State) -> list[AssistantContentBlock]:
        """Execute one step of the agent using MoA methodology if enabled.
        
        Args:
            state: Current state of the conversation
            
        Returns:
            List of assistant content blocks
        """
        if self.moa_enabled and self.moa_llm:
            return self._moa_step(state)
        else:
            return self._standard_step(state)
    
    def _moa_step(self, state: State) -> list[AssistantContentBlock]:
        """Execute MoA step with multiple models."""
        logger.debug("Executing MoA step with multiple models")
        
        try:
            # Generate response using MoA methodology
            model_response, metadata = self.moa_llm.generate(
                messages=state.get_messages_for_llm(),
                max_tokens=self.config.max_tokens_per_turn,
                tools=self.tools,
                system_prompt=self.config.system_prompt,
                temperature=self.config.temperature,
            )
            
            # Log MoA-specific metrics
            if metadata.get("moa_enabled"):
                logger.info(
                    f"MoA step completed: "
                    f"{metadata.get('num_reference_models', 0)} reference models, "
                    f"{metadata.get('reference_responses', 0)} responses, "
                    f"processing time: {metadata.get('total_processing_time', 0):.2f}s"
                )
            
            return model_response
            
        except Exception as e:
            logger.error(f"MoA step failed: {str(e)}")
            
            # Fallback to standard behavior if MoA fails
            if self.moa_config and self.moa_config.fallback_to_single_model:
                logger.info("Falling back to standard agent behavior")
                return self._standard_step(state)
            else:
                raise e
    
    def _standard_step(self, state: State) -> list[AssistantContentBlock]:
        """Execute standard agent step (single model)."""
        logger.debug("Executing standard step with single model")
        
        model_response, _ = self.llm.generate(
            messages=state.get_messages_for_llm(),
            max_tokens=self.config.max_tokens_per_turn,
            tools=self.tools,
            system_prompt=self.config.system_prompt,
            temperature=self.config.temperature,
        )
        return model_response
    
    def is_moa_enabled(self) -> bool:
        """Check if MoA is enabled for this agent."""
        return self.moa_enabled
    
    def get_moa_info(self) -> dict:
        """Get information about the MoA configuration."""
        if self.moa_enabled and self.moa_llm:
            return self.moa_llm.get_model_info()
        else:
            return {"type": "standard", "moa_enabled": False}
    
    def enable_moa(self, moa_config: MoAConfig = None):
        """Enable MoA for this agent.
        
        Args:
            moa_config: MoA configuration. If None, uses default configuration.
        """
        if moa_config is None:
            moa_config = create_default_moa_config()
        
        self.moa_config = moa_config
        self.config.moa_config = moa_config
        self.moa_enabled = True
        self.moa_llm = MoALLMClient(moa_config)
        
        logger.info(f"MoA enabled with {len(self.moa_llm.reference_clients)} reference models")
    
    def disable_moa(self):
        """Disable MoA for this agent."""
        self.moa_enabled = False
        self.moa_llm = None
        
        if self.config.moa_config:
            self.config.moa_config.enabled = False
        
        logger.info("MoA disabled, using standard agent behavior")
    
    def update_moa_config(self, moa_config: MoAConfig):
        """Update the MoA configuration and reinitialize if needed.
        
        Args:
            moa_config: New MoA configuration
        """
        self.moa_config = moa_config
        self.config.moa_config = moa_config
        
        if moa_config.enabled:
            self.moa_enabled = True
            self.moa_llm = MoALLMClient(moa_config)
            logger.info(f"MoA configuration updated with {len(self.moa_llm.reference_clients)} reference models")
        else:
            self.disable_moa()


def create_moa_agent(
    llm: LLMClient,
    tools: List[ToolParam],
    moa_config: MoAConfig = None,
    agent_config: AgentConfig = None,
) -> MoAAgent:
    """Factory function to create a MoA agent with default configuration.
    
    Args:
        llm: The LLM client to use
        tools: List of tools for the agent
        moa_config: MoA configuration. If None, creates default config.
        agent_config: Agent configuration. If None, creates default config.
        
    Returns:
        Configured MoA agent
    """
    if moa_config is None:
        moa_config = create_default_moa_config()
    
    if agent_config is None:
        agent_config = AgentConfig()
    
    agent_config.moa_config = moa_config
    
    return MoAAgent(llm, agent_config, tools)
