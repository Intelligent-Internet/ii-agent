"""Type definitions for MoA system to avoid circular imports."""

from dataclasses import dataclass
from typing import Dict, Any, Optional
from ii_agent.llm.base import AssistantContentBlock


@dataclass
class LayerResponse:
    """Represents a response from a single layer in the MoA system."""
    layer_index: int
    client_key: str
    content_blocks: list[AssistantContentBlock]
    metadata: Optional[Dict[str, Any]] = None
    processing_time: Optional[float] = None
    error: Optional[str] = None
    
    @property
    def is_successful(self) -> bool:
        """Check if this layer response was successful."""
        return self.error is None and bool(self.content_blocks)
    
    @property
    def text_content(self) -> str:
        """Get the text content from all blocks."""
        return "\n".join(
            block.content for block in self.content_blocks 
            if hasattr(block, 'content')
        )


@dataclass
class MoAMetrics:
    """Performance metrics for MoA operations."""
    total_processing_time: float
    layer_processing_times: Dict[int, float]
    successful_clients: list[str]
    failed_clients: list[str]
    total_requests: int
    successful_requests: int
    parallel_efficiency: float