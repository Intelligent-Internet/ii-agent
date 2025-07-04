"""Tool-related metadata classes for events."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional, Dict
from pydantic import BaseModel, Field


class LLMMetrics(BaseModel):
    """Metrics for LLM usage tracking."""
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    cost_usd: Optional[float] = None
    model_name: Optional[str] = None
    provider: Optional[str] = None
    latency_ms: Optional[float] = None


class ToolCallMetadata(BaseModel):
    """Metadata about a tool call associated with an event.
    
    This is used to track tool calls through the event system,
    especially important for converting events back to LLM messages.
    Based on OpenHands' ToolCallMetadata pattern.
    """
    function_name: str  # Name of the function that was called
    tool_call_id: str  # ID of the tool call
    
    # LLM response tracking
    model_response: Optional[Any] = None  # The full LLM response object
    total_calls_in_response: int = 1  # Total number of tool calls in the response
    
    # Enhanced metadata
    response_id: Optional[str] = None  # ID of the LLM response
    request_id: Optional[str] = None  # ID of the original request
    timestamp: Optional[datetime] = Field(default_factory=datetime.now)
    
    # Usage metrics
    llm_metrics: Optional[LLMMetrics] = None
    
    # Additional context
    context: Dict[str, Any] = Field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "function_name": self.function_name,
            "tool_call_id": self.tool_call_id,
            "response_id": self.response_id,
            "request_id": self.request_id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "total_calls_in_response": self.total_calls_in_response,
            "llm_metrics": {
                "prompt_tokens": self.llm_metrics.prompt_tokens,
                "completion_tokens": self.llm_metrics.completion_tokens,
                "total_tokens": self.llm_metrics.total_tokens,
                "cost_usd": self.llm_metrics.cost_usd,
                "model_name": self.llm_metrics.model_name,
                "provider": self.llm_metrics.provider,
                "latency_ms": self.llm_metrics.latency_ms,
            } if self.llm_metrics else None,
            "context": self.context,
        }
    
    @classmethod
    def from_llm_response(
        cls,
        function_name: str,
        tool_call_id: str,
        model_response: Any,
        total_calls: int = 1,
        **kwargs
    ) -> "ToolCallMetadata":
        """Create metadata from LLM response object.
        
        Args:
            function_name: Name of the function called
            tool_call_id: ID of the specific tool call
            model_response: Full LLM response object
            total_calls: Total tool calls in this response
            **kwargs: Additional context
            
        Returns:
            ToolCallMetadata: Populated metadata object
        """
        # Extract response ID
        response_id = None
        if hasattr(model_response, 'id'):
            response_id = model_response.id
        elif isinstance(model_response, dict):
            response_id = model_response.get('id')
            
        # Extract usage metrics
        llm_metrics = None
        if hasattr(model_response, 'usage'):
            usage = model_response.usage
            llm_metrics = LLMMetrics(
                prompt_tokens=getattr(usage, 'prompt_tokens', None),
                completion_tokens=getattr(usage, 'completion_tokens', None),
                total_tokens=getattr(usage, 'total_tokens', None),
                model_name=getattr(model_response, 'model', None),
            )
        elif isinstance(model_response, dict) and 'usage' in model_response:
            usage = model_response['usage']
            llm_metrics = LLMMetrics(
                prompt_tokens=usage.get('prompt_tokens'),
                completion_tokens=usage.get('completion_tokens'),
                total_tokens=usage.get('total_tokens'),
                model_name=model_response.get('model'),
            )
            
        return cls(
            function_name=function_name,
            tool_call_id=tool_call_id,
            model_response=model_response,
            total_calls_in_response=total_calls,
            response_id=response_id,
            llm_metrics=llm_metrics,
            context=kwargs,
        )