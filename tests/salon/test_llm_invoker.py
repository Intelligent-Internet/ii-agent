"""Unit tests for the Salon LLM invoker."""

import pytest

from scribe_agents.salon import LLMInvoker
from scribe_agents.salon.salon_personas import PersonaRole, SalonParticipant, SalonPersona


@pytest.mark.asyncio
async def test_llm_invoker_initialization():
    invoker = LLMInvoker(max_concurrent=3, timeout_seconds=42.5, retry_attempts=1)

    assert invoker.max_concurrent == 3
    assert invoker.timeout_seconds == 42.5
    assert invoker.retry_attempts == 1


@pytest.mark.asyncio
async def test_llm_invoker_mock_invocation():
    persona = SalonPersona(
        id="test-persona",
        name="Test Persona",
        role=PersonaRole.RESEARCHER,
        description="A persona used for unit tests.",
        system_prompt_template="Topic: {topic}\nHistory: {history}\nRespond accordingly.",
        communication_style="Test style",
        expertise_areas=["testing"],
    )

    participant = SalonParticipant(
        id="participant-1",
        persona=persona,
        llm_config={"provider": "anthropic", "model": "claude-3-haiku", "temperature": 0.3},
    )

    invoker = LLMInvoker()
    result = await invoker.invoke_participant(
        participant=participant,
        persona=persona,
        topic="How do we ensure high test coverage?",
        conversation_history="Previous message from user.",
    )

    assert result.provider == "anthropic"
    assert result.model == "claude-3-haiku"
    assert isinstance(result.content, str)
    assert result.content
    assert result.meta["participant_id"] == participant.id
    assert result.meta["persona_id"] == persona.id
