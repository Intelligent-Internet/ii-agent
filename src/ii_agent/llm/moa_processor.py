import asyncio
import logging
import time
from typing import List, Dict, Any, Tuple, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from ii_agent.llm.base import LLMClient, AssistantContentBlock, ToolParam, LLMMessages, TextResult, TextPrompt
from ii_agent.llm.moa_types import LayerResponse, MoAMetrics
# Remove circular import - will import AsyncMoAExecutor inside methods
from ii_agent.llm.moa_error_handler import MoAErrorHandler
from ii_agent.core.config.moa_config import MoAConfig

logger = logging.getLogger(__name__)


from dataclasses import dataclass

@dataclass
class LayerResult:
    """Represents the complete result from processing a layer."""
    layer_index: int
    responses: List[LayerResponse]
    aggregated_response: Optional[List[AssistantContentBlock]] = None
    aggregation_metadata: Optional[Dict[str, Any]] = None
    total_processing_time: float = 0.0
    success_rate: float = 0.0


class MoALayerProcessor:
    """Handles layered processing in the MoA system."""
    
    def __init__(self, moa_config: MoAConfig, reference_clients: Dict[str, LLMClient], aggregator_client: LLMClient, error_handler: MoAErrorHandler = None):
        """Initialize the layer processor.
        
        Args:
            moa_config: MoA configuration
            reference_clients: Dictionary of reference model clients
            aggregator_client: Aggregator model client
            error_handler: Error handler for managing failures (optional)
        """
        self.moa_config = moa_config
        self.reference_clients = reference_clients
        self.aggregator_client = aggregator_client
        
        # Initialize error handler
        self.error_handler = error_handler or MoAErrorHandler()
        
        # Initialize async executor for optimized parallel processing
        from ii_agent.llm.moa_async import AsyncMoAExecutor
        self.async_executor = AsyncMoAExecutor(
            max_workers=moa_config.max_concurrent_requests,
            enable_batching=True
        )
        
    def process_layers(
        self,
        messages: LLMMessages,
        max_tokens: int,
        system_prompt: str | None = None,
        temperature: float = 0.0,
        tools: list[ToolParam] = [],
        tool_choice: dict[str, str] | None = None,
        thinking_tokens: int | None = None,
    ) -> Tuple[List[AssistantContentBlock], Dict[str, Any]]:
        """Process all layers in the MoA system.
        
        Args:
            messages: Input messages
            max_tokens: Maximum tokens per response
            system_prompt: System prompt
            temperature: Temperature for generation
            tools: Available tools
            tool_choice: Tool choice preference
            thinking_tokens: Thinking tokens for models that support it
            
        Returns:
            Final aggregated response and comprehensive metadata
        """
        start_time = time.time()
        layer_results = []
        
        # Current messages for processing (starts with input messages)
        current_messages = messages
        for layer_idx in range(self.moa_config.num_layers):
            logger.info(f"Processing MoA layer {layer_idx + 1}/{self.moa_config.num_layers}")
            
            # Process reference layer (aggregation happens inside _process_reference_layer)
            layer_result = self._process_reference_layer(
                layer_idx, current_messages, max_tokens, system_prompt, 
                temperature, tools, None, None  # tool_choice=None, thinking_tokens=None
            )
            
            layer_results.append(layer_result)
            
            # Update current messages for next layer if needed
            if layer_result.aggregated_response and layer_idx < self.moa_config.num_layers - 1:
                # Add aggregated response to message history for next layer
                current_messages = current_messages + [layer_result.aggregated_response]
        
        # Get final response from the last layer
        final_layer = layer_results[-1]
        final_response = final_layer.aggregated_response or []
        
        # Compile comprehensive metadata
        total_time = time.time() - start_time
        metadata = self._compile_metadata(layer_results, total_time)
        
        logger.info(f"MoA layered processing completed in {total_time:.2f}s")
        
        return final_response, metadata
    
    def _process_reference_layer(
        self,
        layer_idx: int,
        messages: LLMMessages,
        max_tokens: int,
        system_prompt: str | None,
        temperature: float,
        tools: list[ToolParam],
        tool_choice: dict[str, str] | None,
        thinking_tokens: int | None,
    ) -> LayerResult:
        """Process the reference model layer (Layer 1)."""
        start_time = time.time()
        responses = []
        
        if self.moa_config.parallel_execution:
            responses = self._process_reference_parallel(
                layer_idx, messages, max_tokens, system_prompt, 
                temperature, tools, tool_choice, thinking_tokens
            )
        else:
            responses = self._process_reference_sequential(
                layer_idx, messages, max_tokens, system_prompt, 
                temperature, tools, tool_choice, thinking_tokens
            )
        
        # Calculate success rate
        successful_responses = [r for r in responses if r.is_successful]
        success_rate = len(successful_responses) / len(responses) if responses else 0.0
        
        # Aggregate responses for this layer
        aggregated_response, aggregation_metadata = self._aggregate_layer_responses(
            messages, responses, max_tokens, system_prompt, temperature, tools, tool_choice
        )
        
        total_time = time.time() - start_time
        
        return LayerResult(
            layer_index=layer_idx,
            responses=responses,
            aggregated_response=aggregated_response,
            aggregation_metadata=aggregation_metadata,
            total_processing_time=total_time,
            success_rate=success_rate,
        )
    
    def _process_reference_parallel(
        self,
        layer_idx: int,
        messages: LLMMessages,
        max_tokens: int,
        system_prompt: str | None,
        temperature: float,
        tools: list[ToolParam],
        tool_choice: dict[str, str] | None,
        thinking_tokens: int | None,
    ) -> List[LayerResponse]:
        """Process reference models in parallel using async execution."""
        # Apply optimizations
        optimized_messages = self._apply_model_optimizations(messages, temperature)
        
        # Use async executor for better performance
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            responses = loop.run_until_complete(
                self.async_executor.execute_parallel_generation(
                    self.reference_clients, layer_idx, optimized_messages, max_tokens,
                    system_prompt, temperature, tools, tool_choice, thinking_tokens
                )
            )
            return responses
        finally:
            loop.close()
    
    def _process_reference_sequential(
        self,
        layer_idx: int,
        messages: LLMMessages,
        max_tokens: int,
        system_prompt: str | None,
        temperature: float,
        tools: list[ToolParam],
        tool_choice: dict[str, str] | None,
        thinking_tokens: int | None,
    ) -> List[LayerResponse]:
        """Process reference models sequentially using async execution."""
        # Apply optimizations
        optimized_messages = self._apply_model_optimizations(messages, temperature)
        
        # Use async executor for consistent interface
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            responses = loop.run_until_complete(
                self.async_executor.execute_sequential_generation(
                    self.reference_clients, layer_idx, optimized_messages, max_tokens,
                    system_prompt, temperature, tools, tool_choice, thinking_tokens
                )
            )
            return responses
        finally:
            loop.close()
    
    def _generate_single_response(
        self,
        client: LLMClient,
        client_key: str,
        layer_idx: int,
        messages: LLMMessages,
        max_tokens: int,
        system_prompt: str | None,
        temperature: float,
        tools: list[ToolParam],
        tool_choice: dict[str, str] | None,
        thinking_tokens: int | None,
    ) -> LayerResponse:
        """Generate a single response from a client."""
        start_time = time.time()
        
        try:
            # Call client.generate() exactly like normal agent does
            response_blocks, metadata = client.generate(
                messages=messages, 
                max_tokens=max_tokens, 
                system_prompt=system_prompt, 
                temperature=temperature,
                tools=tools
            )
            
            processing_time = time.time() - start_time
            
            return LayerResponse(
                layer_index=layer_idx,
                client_key=client_key,
                content_blocks=response_blocks,
                metadata=metadata,
                processing_time=processing_time,
                error=None
            )
            
        except Exception as e:
            processing_time = time.time() - start_time
            
            return LayerResponse(
                layer_index=layer_idx,
                client_key=client_key,
                content_blocks=[],
                metadata={},
                processing_time=processing_time,
                error=str(e)
            )
    
    def _aggregate_layer_responses(
        self,
        original_messages: LLMMessages,
        layer_responses: List[LayerResponse],
        max_tokens: int,
        system_prompt: str | None,
        temperature: float,
        tools: list[ToolParam],
        tool_choice: dict[str, str] | None,
    ) -> Tuple[List[AssistantContentBlock], Dict[str, Any]]:
        """Aggregate responses from a layer using the aggregator model."""
        successful_responses = [r for r in layer_responses if r.is_successful]
        
        if not successful_responses:
            raise ValueError("No successful responses to aggregate")
        
        # Build aggregation messages
        aggregation_messages = original_messages.copy()
        
        # Format all responses as text
        response_texts = []
        for response in successful_responses:
            response_text = f"{response.client_key} Response: {str(response.content_blocks)}"
            response_texts.append(response_text)
        
        # Add formatted responses as a user message
        formatted_responses = "\n\n".join(response_texts)
        summary_message = [TextPrompt(text=formatted_responses)]
        aggregation_messages.append(summary_message)
        
        # Use the aggregator system prompt from configuration
        aggregator_system_prompt = self.moa_config.aggregator_system_prompt
        
        # Generate the aggregated response with tools support
        return self.aggregator_client.generate(
            aggregation_messages, max_tokens, aggregator_system_prompt, temperature, tools, tool_choice, None
        )
    
    def _extract_text_from_blocks(self, blocks: List[AssistantContentBlock]) -> str:
        """Extract text from assistant content blocks."""
        text_parts = []
        for block in blocks:
            if isinstance(block, TextResult):
                text_parts.append(block.text)
        return "\n".join(text_parts) if text_parts else "No text response"
    
    def _compile_metadata(self, layer_results: List[LayerResult], total_time: float) -> Dict[str, Any]:
        """Compile comprehensive metadata from all layers."""
        metadata = {
            "moa_enabled": True,
            "num_layers": len(layer_results),
            "total_processing_time": total_time,
            "layers": [],
        }
        
        total_reference_responses = 0
        total_successful_responses = 0
        
        for layer_result in layer_results:
            layer_meta = {
                "layer_index": layer_result.layer_index,
                "num_responses": len(layer_result.responses),
                "success_rate": layer_result.success_rate,
                "processing_time": layer_result.total_processing_time,
                "has_aggregation": layer_result.aggregated_response is not None,
            }
            
            if layer_result.responses:
                successful_responses = [r for r in layer_result.responses if r.is_successful]
                total_reference_responses += len(layer_result.responses)
                total_successful_responses += len(successful_responses)
                
                layer_meta["response_details"] = [
                    {
                        "client_key": r.client_key,
                        "success": r.is_successful,
                        "processing_time": r.processing_time,
                        "error": r.error if not r.is_successful else None,
                    }
                    for r in layer_result.responses
                ]
            
            metadata["layers"].append(layer_meta)
        
        metadata["total_reference_responses"] = total_reference_responses
        metadata["total_successful_responses"] = total_successful_responses
        metadata["overall_success_rate"] = (total_successful_responses / total_reference_responses 
                                          if total_reference_responses > 0 else 0.0)
        
        return metadata
    
    def _apply_model_optimizations(self, messages: LLMMessages, base_temperature: float) -> LLMMessages:
        """Apply model-specific optimizations to messages."""
        # For now, return messages as-is
        # In the future, we could apply per-model prompt optimizations
        return messages
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """Get performance statistics from the async executor."""
        return self.async_executor.get_performance_stats()
    
    def cleanup(self):
        """Clean up resources."""
        if hasattr(self, 'async_executor'):
            self.async_executor.close()