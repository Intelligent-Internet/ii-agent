"""WebSocket handlers for Scribe salon orchestration."""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from typing import Dict, Optional

from scribe_agents.salon import (
    ConsensusEngine,
    LLMInvoker,
    SalonManager,
    SalonMode,
    SalonState,
    TurnCoordinator,
    TurnStrategy,
    get_default_personas,
)
from scribe_agents.salon.messages import (
    SalonConsensusPayload,
    SalonMessagePayload,
    SalonStartPayload,
    SalonStatusPayload,
)
from scribe_agents.salon.salon_personas import SalonTopic, create_participant
from scribe_core.provider_router import ProviderRouter

logger = logging.getLogger(__name__)


@dataclass
class SalonRuntime:
    """In-memory runtime state for an active salon session."""

    salon_id: str
    manager: SalonManager
    turn_coordinator: TurnCoordinator
    consensus_engine: ConsensusEngine
    personas: Dict[str, object]
    participants: list
    llm_invoker: LLMInvoker
    router: ProviderRouter
    created_by: str = "system"
    metadata: Dict[str, object] = field(default_factory=dict)


class SalonWebSocketHandlers:
    """Encapsulates salon WebSocket command handlers for the Scribe runtime."""

    def __init__(self, router: Optional[ProviderRouter] = None):
        self.router = router or ProviderRouter()
        self._runtime: Optional[SalonRuntime] = None

    @property
    def is_active(self) -> bool:
        return self._runtime is not None

    async def handle_start(self, payload: SalonStartPayload) -> SalonStatusPayload:
        """Bootstrap a new salon session."""

        logger.debug("Starting salon - topic=%s mode=%s", payload.topic, payload.mode)

        personas = get_default_personas()

        participants = []
        for persona_id in payload.participant_personas or personas.keys():
            persona = personas.get(persona_id)
            if not persona:
                logger.warning("Persona %s not found; skipping", persona_id)
                continue
            participant = create_participant(
                persona=persona,
                llm_config={
                    "provider": "anthropic",
                    "model": "claude-sonnet-4-5",
                    "temperature": 0.7,
                    "max_tokens": 1000,
                },
            )
            participants.append(participant)

        if len(participants) < 2:
            raise ValueError("At least two personas are required to start a salon session.")

        topic = SalonTopic(
            id=str(uuid.uuid4()),
            question=payload.topic,
            context=payload.context or "",
        )

        salon_id = str(uuid.uuid4())
        manager = SalonManager(
            salon_id=salon_id,
            mode=SalonMode(payload.mode),
            topic=topic,
            participants=[p.id for p in participants],
        )

        turn_coordinator = TurnCoordinator(
            participants=[p.id for p in participants],
            strategy=self._get_turn_strategy(payload.mode),
        )

        consensus_engine = ConsensusEngine(
            participants=[p.id for p in participants],
            threshold=0.6,
        )

        llm_invoker = LLMInvoker(router=self.router)

        manager.start()

        self._runtime = SalonRuntime(
            salon_id=salon_id,
            manager=manager,
            turn_coordinator=turn_coordinator,
            consensus_engine=consensus_engine,
            personas=personas,
            participants=participants,
            llm_invoker=llm_invoker,
            router=self.router,
        )

        return self._status_payload()

    async def handle_message(self, payload: SalonMessagePayload) -> SalonStatusPayload:
        """Process a message sent into the salon."""

        runtime = self._require_runtime()
        runtime.manager.add_message(
            participant_id=payload.participant_id,
            content=payload.content,
            metadata=payload.metadata,
        )

        if payload.participant_id != "user":
            next_speaker_id = runtime.turn_coordinator.get_next_speaker()
            if next_speaker_id and next_speaker_id != "user":
                await self._invoke_participant(runtime, next_speaker_id)

        runtime.manager.advance_turn()
        return self._status_payload()

    async def handle_status(self) -> SalonStatusPayload:
        """Return the latest salon status payload."""

        return self._status_payload()

    async def handle_consensus(self) -> SalonConsensusPayload:
        """Compute the current consensus snapshot."""

        runtime = self._require_runtime()
        messages = runtime.manager.get_messages()
        consensus = runtime.consensus_engine.analyze_consensus(messages)

        return SalonConsensusPayload(
            level=consensus.level.value,
            consensus_points=[
                {"point": point.text, "support": point.support}
                for point in consensus.consensus_points
            ],
            areas_of_disagreement=consensus.areas_of_disagreement,
            synthesis=consensus.synthesis,
            confidence=consensus.confidence,
        )

    async def handle_stop(self) -> None:
        """Stop and clear the active salon session."""

        runtime = self._require_runtime()
        runtime.manager.complete()
        self._runtime = None

    def _require_runtime(self) -> SalonRuntime:
        if not self._runtime:
            raise ValueError("No active salon session.")
        return self._runtime

    def _status_payload(self) -> SalonStatusPayload:
        runtime = self._require_runtime()
        manager = runtime.manager
        participant_details = [
            {
                "id": participant.id,
                "persona_id": participant.persona_id,
                "role": participant.persona.role,
                "avatar_color": participant.persona.avatar_color,
            }
            for participant in runtime.participants
        ]

        return SalonStatusPayload(
            salon_id=manager.salon_id,
            state=manager.state.value if isinstance(manager.state, SalonState) else manager.state,
            mode=manager.mode.value if isinstance(manager.mode, SalonMode) else manager.mode,
            current_turn=manager.current_turn,
            participants=participant_details,
            message_count=len(manager.get_messages()),
        )

    async def _invoke_participant(self, runtime: SalonRuntime, participant_id: str) -> None:
        participant = next((p for p in runtime.participants if p.id == participant_id), None)
        if not participant:
            logger.error("Participant %s not registered with salon %s", participant_id, runtime.salon_id)
            return

        history = runtime.manager.format_conversation_history()
        persona = runtime.personas.get(participant.persona_id)
        if not persona:
            logger.error("Persona %s missing for participant %s", participant.persona_id, participant_id)
            return

        result = await runtime.llm_invoker.invoke_participant(
            participant=participant,
            persona=persona,
            topic=runtime.manager.topic.question,
            conversation_history=history,
        )

        error = result.meta.get("error")
        if error:
            logger.error("Invocation error for participant %s: %s", participant_id, error)
            return

        message_metadata = {
            "provider": result.provider,
            "model": result.model,
        }
        message_metadata.update(result.meta)

        runtime.manager.add_message(
            participant_id=participant_id,
            content=result.content,
            metadata=message_metadata,
        )

    def _get_turn_strategy(self, mode: str) -> TurnStrategy:
        """Map a salon mode to its default turn strategy."""

        return {
            "debate": TurnStrategy.DEBATE,
            "discussion": TurnStrategy.ROUND_ROBIN,
            "panel": TurnStrategy.MODERATED,
            "consensus": TurnStrategy.PRIORITY,
            "brainstorm": TurnStrategy.FREE_FORM,
        }.get(mode, TurnStrategy.ROUND_ROBIN)
