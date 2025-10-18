"""
Salon Orchestrator Tool for Agent-S integration.

Exposes salon functionality as an Agent-S tool, allowing AI agents to
initiate and manage multi-LLM cognitive salons.
"""

import logging
from typing import Dict, Any, Optional

from adapters.ii_bridge.tool_base import LLMTool
from . import get_default_personas

logger = logging.getLogger(__name__)


class SalonOrchestratorTool(LLMTool):
    """
    Tool for managing multi-LLM cognitive salons.

    Allows Agent-S personas to:
    - Start salons with specific topics and modes
    - Send messages to active salons
    - Query consensus status
    - Stop salon sessions

    This tool bridges Agent-S orchestrator with the salon infrastructure,
    enabling complex collaborative problem-solving via multiple AI personas.
    """

    def get_info(self) -> Dict[str, Any]:
        """Return tool metadata for LLM tool use."""
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["start", "send_message", "get_consensus", "get_status", "stop"],
                    "description": "The salon action to perform",
                },
                "topic": {
                    "type": "string",
                    "description": "Topic or question for the salon (required for 'start')",
                },
                "context": {
                    "type": "string",
                    "description": "Additional context for the salon topic (optional)",
                },
                "mode": {
                    "type": "string",
                    "enum": ["debate", "discussion", "panel", "consensus", "brainstorm"],
                    "description": "Salon conversation mode (default: discussion)",
                },
                "participant_personas": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of persona IDs to include (dr_research, the_critic, design_lead, tech_lead, the_facilitator, the_innovator)",
                },
                "message": {
                    "type": "string",
                    "description": "Message to send to the salon (required for 'send_message')",
                },
                "participant_id": {
                    "type": "string",
                    "description": "ID of participant sending the message (default: 'user')",
                },
            },
            "required": ["action"],
        }

    def function_name(self) -> str:
        """Return the function name for LLM tool calling."""
        return "salon_orchestrator"

    def function_description(self) -> str:
        """Return a description of the tool's purpose."""
        return """Orchestrate multi-LLM cognitive salons for collaborative problem-solving.

Use this tool to:
- Start a salon with multiple AI personas debating, discussing, or building consensus on a topic
- Send messages or questions to an active salon
- Check the consensus level among participants
- Get current salon status (participants, turns, messages)
- Stop an active salon session

Salon modes:
- debate: Adversarial discussion with opposing viewpoints
- discussion: Collaborative exploration of ideas
- panel: Expert Q&A format with moderated turns
- consensus: Agreement-seeking with synthesis
- brainstorm: Free-form creative ideation

Available personas:
- dr_research: Evidence-based analyst
- the_critic: Constructive skeptic
- design_lead: User-focused designer
- tech_lead: Pragmatic engineer
- the_facilitator: Synthesis moderator
- the_innovator: Creative problem-solver

Example usage:
1. Start a salon: action="start", topic="How to optimize API performance", mode="discussion", participant_personas=["dr_research", "tech_lead", "the_critic"]
2. Send message: action="send_message", message="What about caching strategies?", participant_id="user"
3. Check consensus: action="get_consensus"
4. Get status: action="get_status"
5. Stop salon: action="stop"
"""

    async def __call__(
        self,
        action: str,
        topic: Optional[str] = None,
        context: Optional[str] = None,
        mode: str = "discussion",
        participant_personas: Optional[list] = None,
        message: Optional[str] = None,
        participant_id: str = "user",
    ) -> str:
        """
        Execute a salon orchestrator action.

        Args:
            action: The action to perform (start, send_message, get_consensus, get_status, stop)
            topic: Topic for the salon (required for 'start')
            context: Additional context (optional)
            mode: Conversation mode (debate, discussion, panel, consensus, brainstorm)
            participant_personas: List of persona IDs to include
            message: Message to send (required for 'send_message')
            participant_id: ID of the message sender

        Returns:
            Status message describing the result
        """
        try:
            # TODO: This is a stub implementation
            # In production, this would interact with the WebSocket session's
            # salon manager to perform the requested action
            #
            # The full implementation would:
            # 1. Get reference to the active WebSocket session
            # 2. Call the appropriate handler method
            # 3. Return formatted results
            #
            # For now, we return mock responses to demonstrate the interface

            if action == "start":
                if not topic:
                    return "Error: 'topic' is required for starting a salon"

                personas = participant_personas or [
                    "dr_research",
                    "tech_lead",
                    "the_critic",
                ]

                # Mock response
                return f"""Salon started successfully!

Topic: {topic}
Mode: {mode}
Participants: {', '.join(personas)}
Context: {context or 'None provided'}

The salon is now active. Participants will begin discussing in {mode} mode.
Use action='send_message' to contribute to the conversation.
Use action='get_status' to check current state.
Use action='get_consensus' to analyze agreement levels.

Note: This is a mock response. Full implementation requires WebSocket session integration.
"""

            elif action == "send_message":
                if not message:
                    return "Error: 'message' is required for sending a message"

                # Mock response
                return f"""Message sent to salon:

From: {participant_id}
Content: {message}

The salon participants will respond based on the current turn strategy.
Wait for responses to appear in the salon message stream.

Note: This is a mock response. Full implementation requires WebSocket session integration.
"""

            elif action == "get_consensus":
                # Mock response
                return """Consensus Analysis:

Level: PARTIAL
Confidence: 0.65

Points of Agreement:
- Caching is essential for performance (85% support)
- Database queries are the main bottleneck (75% support)

Areas of Disagreement:
- Whether to use Redis or in-memory caching
- Trade-offs between consistency and performance

Synthesis: The participants generally agree that caching and query optimization
are critical, but disagree on specific implementation strategies. More discussion
needed on cache invalidation approaches.

Note: This is a mock response. Full implementation requires WebSocket session integration.
"""

            elif action == "get_status":
                # Mock response
                return """Salon Status:

State: ACTIVE
Mode: discussion
Current Turn: 5
Message Count: 12
Participants: dr_research, tech_lead, the_critic

Recent Activity:
- Turn 5: tech_lead discussing cache implementation strategies
- Turn 4: the_critic raised concerns about cache invalidation
- Turn 3: dr_research cited performance benchmarks

Note: This is a mock response. Full implementation requires WebSocket session integration.
"""

            elif action == "stop":
                # Mock response
                return """Salon stopped successfully.

Final Statistics:
- Total turns: 5
- Total messages: 12
- Consensus level: PARTIAL
- Duration: N/A

The salon session has ended. You can start a new salon with action='start'.

Note: This is a mock response. Full implementation requires WebSocket session integration.
"""

            else:
                return f"Error: Unknown action '{action}'. Valid actions: start, send_message, get_consensus, get_status, stop"

        except Exception as e:
            logger.error(f"Error in salon orchestrator: {e}")
            return f"Error executing salon action: {str(e)}"

    def __str__(self) -> str:
        return "SalonOrchestratorTool"
