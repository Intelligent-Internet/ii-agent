from __future__ import annotations

import time
from datetime import datetime
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field, field_validator, computed_field, model_validator

from .tool import ToolCallMetadata


class EventSource(Enum):
    """Source of an event."""
    USER = "user"
    AGENT = "agent"
    ENVIRONMENT = "environment"


class Event(BaseModel):
    """Base class for all events in the system."""
    # Core fields - using Field with alias for property-based access
    id: Optional[int] = Field(default=None, alias='_id')
    timestamp: Optional[str] = Field(default=None, alias='_timestamp')
    source: Optional[str] = Field(default=None, alias='_source')
    cause: Optional[int] = Field(default=None, alias='_cause')
    tool_call_metadata: Optional[ToolCallMetadata] = Field(default=None, alias='_tool_call_metadata')
    response_id: Optional[str] = Field(default=None, alias='_response_id')
    
    # Direct fields
    hidden: bool = False  # Whether this event should be hidden from logs/UI
    
    @model_validator(mode='after')
    def ensure_defaults(self) -> 'Event':
        """Post-initialization to ensure consistent state."""
        # Set default ID if not provided
        if self.id is None:
            self.id = int(time.time() * 1000000)  # microsecond timestamp as ID
        
        # Set default timestamp if not provided
        if self.timestamp is None:
            self.timestamp = datetime.now().isoformat()
        
        # Set default source if not provided
        if self.source is None:
            self.source = EventSource.ENVIRONMENT.value
        
        return self
    
    @field_validator('source', mode='before')
    @classmethod
    def validate_source(cls, v):
        """Validate source field."""
        if v is None:
            return None
        if isinstance(v, EventSource):
            return v.value
        return v
    
    def set_timestamp(self, value: datetime) -> None:
        """Set timestamp from datetime object."""
        if isinstance(value, datetime):
            self.timestamp = value.isoformat()
        elif isinstance(value, str):
            self.timestamp = value
    
    def get_source_enum(self) -> Optional[EventSource]:
        """Get the event source as an enum."""
        if self.source is not None:
            return EventSource(self.source)
        return None
    
    def set_source_enum(self, value: Optional[EventSource]) -> None:
        """Set the event source from an enum."""
        if value is not None:
            self.source = value.value if isinstance(value, EventSource) else str(value)
        else:
            self.source = None
    
    @property
    def message(self) -> str:
        """Get a human-readable message for this event.
        
        Subclasses should override this to provide specific messages.
        """
        return f"Event {self.__class__.__name__}"