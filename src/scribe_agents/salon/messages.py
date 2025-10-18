"""Message models used by the Scribe salon WebSocket handlers."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class SalonStartPayload(BaseModel):
    """Client payload for starting a salon session."""

    topic: str
    context: Optional[str] = None
    mode: str = "discussion"
    participant_personas: List[str] = []


class SalonMessagePayload(BaseModel):
    """Client payload for sending a message into the salon."""

    participant_id: str
    content: str
    turn_number: Optional[int] = None
    metadata: Dict[str, Any] = {}


class SalonStatusPayload(BaseModel):
    """Server message describing current salon status."""

    salon_id: str
    state: str
    mode: str
    current_turn: int
    participants: List[Dict[str, Any]]
    message_count: int


class SalonConsensusPayload(BaseModel):
    """Server message describing consensus analysis."""

    level: str
    consensus_points: List[Dict[str, Any]]
    areas_of_disagreement: List[str]
    synthesis: Optional[str] = None
    confidence: float
