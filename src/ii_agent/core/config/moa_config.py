from dataclasses import dataclass
from typing import List, Optional, Dict
from pydantic import BaseModel, Field
from ii_agent.core.config.llm_config import LLMConfig


@dataclass
class MoALayerConfig:
    """Configuration for a single MoA layer."""
    layer_index: int
    llm_configs: List[LLMConfig]
    aggregator_config: Optional[LLMConfig] = None
    temperature: float = 0.0
    max_tokens: int = 8192


class MoAConfig(BaseModel):
    """Configuration for Mixture-of-Agents system.
    
    Attributes:
        enabled: Whether MoA is enabled.
        num_layers: Number of MoA layers (minimum 2).
        layer_configs: Configuration for each layer.
        default_models: Default model configurations for each provider.
        aggregator_model: Default aggregator model configuration.
        parallel_execution: Whether to execute reference models in parallel.
        max_concurrent_requests: Maximum number of concurrent LLM requests.
        fallback_to_single_model: Whether to fallback to single model on failure.
        aggregation_prompt_template: Template for aggregation prompts.
    """
    enabled: bool = Field(default=False)
    num_layers: int = Field(default=2, ge=1, le=5)
    layer_configs: List[MoALayerConfig] = Field(default_factory=list)
    
    # Default model configurations
    claude_config: Optional[LLMConfig] = Field(default=None)
    openai_config: Optional[LLMConfig] = Field(default=None)
    gemini_config: Optional[LLMConfig] = Field(default=None)
    aggregator_config: Optional[LLMConfig] = Field(default=None)
    
    # Execution settings
    parallel_execution: bool = Field(default=True)
    max_concurrent_requests: int = Field(default=3)
    fallback_to_single_model: bool = Field(default=True)
    
    # Aggregation settings
    aggregation_prompt_template: str = Field(
        default="""You have been given responses from multiple AI models to the following query. 
Your task is to synthesize these responses into a single, high-quality, comprehensive answer.

Query: {query}

Model Responses:
{responses}

Please provide a synthesized response that:
1. Combines the best insights from all responses
2. Resolves any contradictions or inconsistencies
3. Provides a clear, coherent, and comprehensive answer
4. Maintains accuracy and factual correctness

Synthesized Response:"""
    )
    
    aggregator_system_prompt: str = Field(
        default="""You are an expert AI synthesizer tasked with creating the optimal response by analyzing and combining multiple AI model outputs. Your goal is to leverage the collective intelligence while mitigating individual weaknesses.

## Core Responsibilities:
1. **Critical Analysis**: Evaluate each response for accuracy, completeness, relevance, and potential biases
2. **Intelligent Synthesis**: Combine the strongest elements from all responses into a cohesive, superior answer
3. **Quality Enhancement**: Improve clarity, structure, and depth beyond what any single model provided
4. **Error Correction**: Identify and correct factual errors, inconsistencies, or logical flaws
5. **Gap Filling**: Address any important aspects that were missed by the individual models

## Synthesis Guidelines:
- Prioritize accuracy and factual correctness above all else
- Maintain the most helpful and actionable aspects from each response
- Resolve contradictions by selecting the most well-supported position
- Enhance explanations with better examples, analogies, or structure when beneficial
- Preserve the appropriate tone and style for the context

## Tool Usage Rules:
If the responses contain tool calls, analyze their purposes and effectiveness:
- Make AT MOST ONE tool call that best serves the user's needs
- Synthesize multiple similar tool calls into the most comprehensive version
- Choose the most appropriate tool and parameters based on the collective insights
- Only use tools when they genuinely add value to the response

## Output Requirements:
- Provide a single, well-structured response that represents the best possible answer
- Ensure logical flow and coherent organization
- Match or exceed the quality of the best individual response
- Be concise while maintaining completeness and accuracy"""
    )
    
    def get_reference_configs(self, layer_index: int = 0) -> List[LLMConfig]:
        """Get reference model configurations for a specific layer."""
        if layer_index < len(self.layer_configs):
            return self.layer_configs[layer_index].llm_configs
        
        # Return default reference models
        configs = []
        if self.claude_config:
            configs.append(self.claude_config)
        if self.openai_config:
            configs.append(self.openai_config)
        if self.gemini_config:
            configs.append(self.gemini_config)
        return configs
    
    def get_aggregator_config(self, layer_index: int = 0) -> Optional[LLMConfig]:
        """Get aggregator model configuration for a specific layer."""
        if layer_index < len(self.layer_configs):
            return self.layer_configs[layer_index].aggregator_config
        
        # Return default aggregator
        return self.aggregator_config or self.claude_config
    
    def validate_configuration(self) -> bool:
        """Validate the MoA configuration."""
        if not self.enabled:
            return True
            
        # Check if we have at least 1 reference model
        reference_configs = self.get_reference_configs()
        if len(reference_configs) < 1:
            raise ValueError("MoA requires at least 1 reference model")
        
        # Check if we have an aggregator model
        if not self.get_aggregator_config():
            raise ValueError("MoA requires an aggregator model")
        
        return True


def create_default_moa_config() -> MoAConfig:
    """Create a default MoA configuration with Claude and Gemini."""
    from ii_agent.core.config.llm_config import APITypes
    
    # Default Claude configuration (using Vertex AI)
    claude_config = LLMConfig(
        model="claude-sonnet-4@20250514",
        api_type=APITypes.ANTHROPIC,
        vertex_project_id="backend-alpha-97077",
        vertex_region="us-east5",
        temperature=0.0,
        max_retries=3,
    )
    
    # Default Gemini configuration
    gemini_config = LLMConfig(
        model="gemini-2.5-pro",
        api_type=APITypes.GEMINI,
        vertex_project_id="backend-alpha-97077",
        vertex_region="us-central1",
        temperature=0.0,
        max_retries=3,
    )
    
    # Default OpenAI configuration
    from pydantic import SecretStr
    openai_config = LLMConfig(
        model="glm-4.5",
        base_url="http://localhost:30000/v1",
        api_key=SecretStr("EMPTY"),
        api_type=APITypes.OPENAI,
        temperature=0.0,
        max_retries=3,
    )
    
    
    return MoAConfig(
        enabled=True,
        num_layers=1,
        claude_config=claude_config,
        openai_config=openai_config,  # Added OpenAI
        gemini_config=gemini_config,
        aggregator_config=claude_config,  # Use Claude as default aggregator
        parallel_execution=True,
        max_concurrent_requests=3,  # Increased to 3 for all models
        fallback_to_single_model=True,
    )
