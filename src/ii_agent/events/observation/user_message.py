"""User message observations for ii-agent."""
from __future__ import annotations

from typing import Any, Dict
from pydantic import model_validator

from ii_agent.core.schema import ObservationType
from ii_agent.events.observation.observation import Observation
from ii_agent.events.event import EventSource

# class UserMessageObservation(Observation):
#     """Observation representing a user message."""
    
#     user_message: str = ""
#     files: list = []
#     data: Dict[str, Any] = {}
#     observation: str = ObservationType.USER_MESSAGE
    
#     @model_validator(mode='after')
#     def ensure_user_source(self) -> 'UserMessageObservation':
#         """Ensure this observation is marked as from user."""
#         super().ensure_observation_defaults()
#         self.source = EventSource.USER.value
#         return self
    
#     @property
#     def message_text(self) -> str:
#         return self.user_message
        
#     @property
#     def message(self) -> str:
#         return f"User message: {self.user_message[:50]}{'...' if len(self.user_message) > 50 else ''}"
    
#     def __str__(self) -> str:
#         header = "[👤 User Message]"
#         file_info = f" (with {len(self.files)} files)" if self.files else ""
#         return f"{header}{file_info}\n{self.user_message}"