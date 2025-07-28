import asyncio
import logging
import time
from typing import List, Dict, Any, Tuple, Optional, Coroutine
from concurrent.futures import ThreadPoolExecutor
import functools

from ii_agent.llm.base import LLMClient, AssistantContentBlock, ToolParam, LLMMessages
from ii_agent.llm.moa_types import LayerResponse

logger = logging.getLogger(__name__)


class AsyncMoAExecutor:
    """Handles async execution of MoA operations with optimizations."""
    
    def __init__(self, max_workers: int = 3, enable_batching: bool = True):
        """Initialize the async executor.
        
        Args:
            max_workers: Maximum number of concurrent workers
            enable_batching: Whether to enable request batching optimizations
        """
        self.max_workers = max_workers
        self.enable_batching = enable_batching
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        
        # Performance tracking
        self.request_count = 0
        self.total_time = 0.0
        self.failed_requests = 0
        
    async def execute_parallel_generation(
        self,
        clients: Dict[str, LLMClient],
        layer_idx: int,
        messages: LLMMessages,
        max_tokens: int,
        system_prompt: str | None,
        temperature: float,
        tools: list[ToolParam],
        tool_choice: dict[str, str] | None,
        thinking_tokens: int | None,
    ) -> List[LayerResponse]:
        """Execute parallel generation across multiple clients using async.
        
        Args:
            clients: Dictionary of client_key -> LLMClient
            layer_idx: Current layer index
            messages: Input messages
            max_tokens: Maximum tokens per response
            system_prompt: System prompt
            temperature: Temperature for generation
            tools: Available tools
            tool_choice: Tool choice preference
            thinking_tokens: Thinking tokens for supported models
            
        Returns:
            List of layer responses from all clients
        """
        start_time = time.time()
        
        # Create async tasks for all clients
        tasks = []
        for client_key, client in clients.items():
            task = self._create_generation_task(
                client, client_key, layer_idx, messages, max_tokens,
                system_prompt, temperature, tools, tool_choice, thinking_tokens
            )
            tasks.append(task)
        
        # Execute all tasks concurrently with timeout and error handling
        responses = await self._execute_with_timeout(tasks, timeout=120.0)
        # Update performance metrics
        total_time = time.time() - start_time
        self.request_count += len(clients)
        self.total_time += total_time
        successful_responses = [r for r in responses if r.is_successful]
        self.failed_requests += len(responses) - len(successful_responses)
        
        logger.info(
            f"Async parallel execution completed: "
            f"{len(successful_responses)}/{len(responses)} successful, "
            f"time: {total_time:.2f}s"
        )
        
        return responses
    
    async def _create_generation_task(
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
        """Create an async task for a single client generation."""
        loop = asyncio.get_event_loop()
        
        # Run the synchronous LLM generation in a thread pool
        task = functools.partial(
            self._safe_generate,
            client, client_key, layer_idx, messages, max_tokens,
            system_prompt, temperature, tools, tool_choice, thinking_tokens
        )
        
        try:
            response = await loop.run_in_executor(self.executor, task)
            return response
        except Exception as e:
            logger.error(f"Async task failed for {client_key}: {str(e)}")
            return LayerResponse(
                layer_index=layer_idx,
                client_key=client_key,
                content_blocks=[],
                metadata={},
                processing_time=0.0,
                error=str(e)
            )
    
    def _safe_generate(
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
        """Safely generate a response with error handling."""
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
    
    async def _execute_with_timeout(
        self, 
        tasks: List[Coroutine], 
        timeout: float = 120.0
    ) -> List[LayerResponse]:
        """Execute tasks with timeout and collect all results."""
        try:
            # Use asyncio.gather with return_exceptions=True to handle individual failures
            results = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=timeout
            )
            
            # Process results and handle exceptions
            responses = []
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.error(f"Task {i} failed with exception: {str(result)}")
                    # Create a failed response
                    responses.append(LayerResponse(
                        layer_index=0,  # Will be updated by caller
                        client_key=f"task_{i}",
                        content_blocks=[],
                        metadata={},
                        processing_time=0.0,
                        success=False,
                        error_message=str(result)
                    ))
                else:
                    responses.append(result)
            
            return responses
            
        except asyncio.TimeoutError:
            logger.error(f"Async execution timed out after {timeout}s")
            # Return empty responses for timeout
            return [LayerResponse(
                layer_index=0,
                client_key="timeout",
                content_blocks=[],
                metadata={},
                processing_time=timeout,
                success=False,
                error_message="Execution timeout"
            )]
    
    async def execute_sequential_generation(
        self,
        clients: Dict[str, LLMClient],
        layer_idx: int,
        messages: LLMMessages,
        max_tokens: int,
        system_prompt: str | None,
        temperature: float,
        tools: list[ToolParam],
        tool_choice: dict[str, str] | None,
        thinking_tokens: int | None,
    ) -> List[LayerResponse]:
        """Execute sequential generation with async yielding between requests."""
        responses = []
        
        for client_key, client in clients.items():
            # Yield control between each request
            await asyncio.sleep(0.01)
            
            response = await self._create_generation_task(
                client, client_key, layer_idx, messages, max_tokens,
                system_prompt, temperature, tools, tool_choice, thinking_tokens
            )
            responses.append(response)
            
            # Add small delay to prevent rate limiting
            if not response.is_successful:
                await asyncio.sleep(0.1)
        
        return responses
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """Get performance statistics for the async executor."""
        avg_time = self.total_time / max(self.request_count, 1)
        success_rate = 1.0 - (self.failed_requests / max(self.request_count, 1))
        
        return {
            "total_requests": self.request_count,
            "failed_requests": self.failed_requests,
            "success_rate": success_rate,
            "total_time": self.total_time,
            "average_time_per_request": avg_time,
            "max_workers": self.max_workers,
        }
    
    def reset_stats(self):
        """Reset performance statistics."""
        self.request_count = 0
        self.total_time = 0.0
        self.failed_requests = 0
    
    def close(self):
        """Clean up the executor."""
        self.executor.shutdown(wait=True)


class MoAOptimizations:
    """Collection of optimization techniques for MoA."""
    
    @staticmethod
    def optimize_prompt_for_model(prompt: str, model_type: str) -> str:
        """Optimize prompts for specific model types.
        
        Args:
            prompt: Original prompt
            model_type: Type of model (anthropic, openai, gemini)
            
        Returns:
            Optimized prompt for the specific model
        """
        if model_type == "anthropic":
            # Claude prefers structured thinking
            return f"Please think step by step about this request:\n\n{prompt}"
        elif model_type == "openai":
            # GPT models work well with clear instructions
            return f"Task: {prompt}\n\nPlease provide a comprehensive and accurate response."
        elif model_type == "gemini":
            # Gemini benefits from explicit context
            return f"Context: You are helping with the following request.\n\nRequest: {prompt}\n\nResponse:"
        else:
            return prompt
    
    @staticmethod
    def adjust_temperature_for_diversity(base_temp: float, model_index: int, total_models: int) -> float:
        """Adjust temperature to promote diversity across models.
        
        Args:
            base_temp: Base temperature setting
            model_index: Index of the current model (0-based)
            total_models: Total number of models
            
        Returns:
            Adjusted temperature for this model
        """
        if total_models <= 1:
            return base_temp
        
        # Vary temperature slightly across models to promote diversity
        temp_variation = 0.1
        adjustment = (model_index / (total_models - 1) - 0.5) * temp_variation
        
        return max(0.0, min(1.0, base_temp + adjustment))
    
    @staticmethod
    def should_use_thinking_tokens(model_type: str, complexity_score: float) -> bool:
        """Determine if thinking tokens should be used based on complexity.
        
        Args:
            model_type: Type of model
            complexity_score: Estimated complexity score (0.0 to 1.0)
            
        Returns:
            Whether to enable thinking tokens
        """
        # Only Anthropic models support thinking tokens currently
        if model_type != "anthropic":
            return False
        
        # Use thinking tokens for complex queries
        return complexity_score > 0.5
    
    @staticmethod
    def estimate_complexity(prompt: str) -> float:
        """Estimate the complexity of a prompt.
        
        Args:
            prompt: The input prompt
            
        Returns:
            Complexity score between 0.0 and 1.0
        """
        complexity_indicators = [
            "explain", "analyze", "compare", "evaluate", "synthesize",
            "create", "design", "implement", "optimize", "solve",
            "multiple", "complex", "detailed", "comprehensive",
        ]
        
        prompt_lower = prompt.lower()
        score = 0.0
        
        # Length factor (longer prompts tend to be more complex)
        length_score = min(len(prompt) / 1000.0, 0.3)
        score += length_score
        
        # Keyword factor
        keyword_count = sum(1 for keyword in complexity_indicators if keyword in prompt_lower)
        keyword_score = min(keyword_count / 5.0, 0.4)
        score += keyword_score
        
        # Question count (multiple questions increase complexity)
        question_count = prompt.count('?')
        question_score = min(question_count / 3.0, 0.3)
        score += question_score
        
        return min(score, 1.0)
