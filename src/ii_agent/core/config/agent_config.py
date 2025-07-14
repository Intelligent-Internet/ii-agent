from dataclasses import dataclass
from typing import Optional


@dataclass
class AgentConfig:
    """Configuration for agents."""
    max_tokens_per_turn: int = 8192
    system_prompt: Optional[str] = None
    temperature: float = 0.0
    timeout: Optional[int] = None