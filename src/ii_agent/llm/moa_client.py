import asyncio
import logging
from typing import Any, Dict, List, Tuple, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

from ii_agent.llm.base import LLMClient, AssistantContentBlock, ToolParam, LLMMessages, TextResult, TextPrompt
from ii_agent.llm.anthropic import AnthropicDirectClient
from ii_agent.llm.openai import OpenAIDirectClient
from ii_agent.llm.gemini import GeminiDirectClient
from ii_agent.llm.moa_processor import MoALayerProcessor
from ii_agent.llm.moa_error_handler import MoAErrorHandler
from ii_agent.core.config.llm_config import LLMConfig, APITypes
from ii_agent.core.config.moa_config import MoAConfig

logger = logging.getLogger(__name__)


class MoALLMClient(LLMClient):
    """Mixture-of-Agents LLM client that orchestrates multiple LLMs."""
    
    def __init__(self, moa_config: MoAConfig):
        """Initialize the MoA LLM client.
        
        Args:
            moa_config: Configuration for the MoA system.
        """
        self.moa_config = moa_config
        self.moa_config.validate_configuration()
        
        # Initialize LLM clients for reference models
        self.reference_clients: Dict[str, LLMClient] = {}
        self.aggregator_client: Optional[LLMClient] = None
        
        self._initialize_clients()
        
        # Initialize error handler
        self.error_handler = MoAErrorHandler(
            max_retries=self.moa_config.max_retries if hasattr(self.moa_config, 'max_retries') else 3
        )
        
        # Initialize the layer processor
        self.layer_processor = MoALayerProcessor(
            self.moa_config, self.reference_clients, self.aggregator_client, self.error_handler
        )
        
    def _initialize_clients(self):
        """Initialize all LLM clients based on configuration."""
        # Initialize reference model clients
        reference_configs = self.moa_config.get_reference_configs()
        for i, config in enumerate(reference_configs):
            client_key = f"reference_{i}_{config.api_type.value}"
            self.reference_clients[client_key] = self._create_llm_client(config)
            logger.info(f"Initialized reference client: {client_key} with model {config.model}")
        
        # Initialize aggregator client
        aggregator_config = self.moa_config.get_aggregator_config()
        if aggregator_config:
            self.aggregator_client = self._create_llm_client(aggregator_config)
            logger.info(f"Initialized aggregator client with model {aggregator_config.model}")
    
    def _create_llm_client(self, config: LLMConfig) -> LLMClient:
        """Create an LLM client based on configuration.
        
        Args:
            config: LLM configuration.
            
        Returns:
            Initialized LLM client.
        """
        if config.api_type == APITypes.ANTHROPIC:
            return AnthropicDirectClient(config)
        elif config.api_type == APITypes.OPENAI:
            return OpenAIDirectClient(config)
        elif config.api_type == APITypes.GEMINI:
            return GeminiDirectClient(config)
        else:
            raise ValueError(f"Unsupported API type: {config.api_type}")
    
    def generate(
        self,
        messages: LLMMessages,
        max_tokens: int,
        system_prompt: str | None = None,
        temperature: float = 0.0,
        tools: list[ToolParam] = [],
        tool_choice: dict[str, str] | None = None,
        thinking_tokens: int | None = None,
    ) -> Tuple[list[AssistantContentBlock], dict[str, Any]]:
        """Generate responses using MoA methodology.
        
        Args:
            messages: A list of messages.
            max_tokens: The maximum number of tokens to generate.
            system_prompt: A system prompt.
            temperature: The temperature.
            tools: A list of tools.
            tool_choice: A tool choice.
            thinking_tokens: Number of thinking tokens.
            
        Returns:
            A generated response from the MoA system.
        """
        try:
            # Use the layer processor with same parameters as normal agent
            return self.layer_processor.process_layers(
                messages=messages,
                max_tokens=max_tokens, 
                system_prompt=system_prompt,
                temperature=temperature,
                tools=tools,
                tool_choice=None,
                thinking_tokens=None
            )
            
        except Exception as e:
            logger.error(f"MoA generation failed: {str(e)}")
            
            # Fallback to single model if enabled
            if self.moa_config.fallback_to_single_model and self.aggregator_client:
                logger.info("Falling back to single aggregator model")
                return self.aggregator_client.generate(
                    messages, max_tokens, system_prompt, temperature, tools, tool_choice, thinking_tokens
                )
            else:
                raise e
    
    def get_model_info(self) -> Dict[str, Any]:
        """Get information about the MoA configuration."""
        reference_configs = self.moa_config.get_reference_configs()
        aggregator_config = self.moa_config.get_aggregator_config()
        
        return {
            "type": "mixture_of_agents",
            "enabled": self.moa_config.enabled,
            "num_layers": self.moa_config.num_layers,
            "reference_models": [config.model for config in reference_configs],
            "aggregator_model": aggregator_config.model if aggregator_config else None,
            "parallel_execution": self.moa_config.parallel_execution,
            "max_concurrent_requests": self.moa_config.max_concurrent_requests,
            "error_handler_stats": self.error_handler.get_health_report() if hasattr(self, 'error_handler') else None,
        }
    
    def get_error_handler(self) -> MoAErrorHandler:
        """Get the error handler instance."""
        return self.error_handler