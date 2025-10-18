"""Multi-LLM Salon Orchestration System.

This module provides a framework for orchestrating conversations between
multiple LLM participants in various cognitive salon modes (debate, discussion,
panel, consensus-building).
"""

from .salon_manager import (
    SalonManager,
    SalonState,
    SalonMode,
)
from .turn_coordinator import (
    TurnCoordinator,
    TurnStrategy,
    Turn,
)
from .consensus_engine import (
    ConsensusEngine,
    ConsensusLevel,
    ConsensusResult,
)
from .salon_personas import (
    SalonPersona,
    SalonParticipant,
    get_default_personas,
)
from .llm_invoker import LLMInvoker, InvokeResult
from .messages import (
    SalonStartPayload,
    SalonMessagePayload,
    SalonStatusPayload,
    SalonConsensusPayload,
)

__all__ = [
    "SalonManager",
    "SalonState",
    "SalonMode",
    "TurnCoordinator",
    "TurnStrategy",
    "Turn",
    "ConsensusEngine",
    "ConsensusLevel",
    "ConsensusResult",
    "SalonPersona",
    "SalonParticipant",
    "get_default_personas",
    "LLMInvoker",
    "InvokeResult",
    "SalonStartPayload",
    "SalonMessagePayload",
    "SalonStatusPayload",
    "SalonConsensusPayload",
]
