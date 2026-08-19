"""Summarize strategy: combine all memories into a single comprehensive summary."""

import logging
from textwrap import dedent
from uuid import uuid4

from ii_agent.agents.models.base import Model
from ii_agent.agents.models.message import Message
from ii_agent.memory.schemas import MemoryData
from ii_agent.memory.strategies.base import MemoryOptimizationStrategy

logger = logging.getLogger(__name__)


class SummarizeStrategy(MemoryOptimizationStrategy):
    """Combine all memories into a single comprehensive summary.

    Achieves maximum compression by eliminating redundancy.
    """

    def _get_system_prompt(self) -> str:
        return dedent("""\
            You are a memory compression assistant. Your task is to summarize multiple memories about a user
            into a single comprehensive summary while preserving all key facts.

            Requirements:
            - Combine related information from all memories
            - Preserve all factual information
            - Remove redundancy and consolidate repeated facts
            - Create a coherent narrative about the user
            - Maintain third-person perspective
            - Do not add information not present in the original memories

            Return only the summarized memory text, nothing else.\
        """)

    async def aoptimize(
        self,
        memories: list[MemoryData],
        model: Model,
    ) -> list[MemoryData]:
        if not memories:
            raise ValueError("No memories to optimize")

        user_id = memories[0].user_id
        if user_id is None:
            raise ValueError("Cannot determine user_id from first memory")

        memory_contents = [m.memory for m in memories if m.memory]
        all_topics: list[str] = []
        for m in memories:
            if m.topics:
                all_topics.extend(m.topics)
        summarized_topics = list(set(all_topics)) if all_topics else None

        agent_ids = {m.agent_id for m in memories if m.agent_id}
        summarized_agent_id = list(agent_ids)[0] if len(agent_ids) == 1 else None

        combined_content = "\n\n".join(
            [f"Memory {i + 1}: {content}" for i, content in enumerate(memory_contents)]
        )

        messages_for_model = [
            Message(role="system", content=self._get_system_prompt()),
            Message(
                role="user",
                content=f"Summarize these memories into a single summary:\n\n{combined_content}",
            ),
        ]

        response = await model.aresponse(messages=messages_for_model)
        summarized_content = response.content or " ".join(memory_contents)

        summarized_memory = MemoryData(
            memory_id=str(uuid4()),
            memory=summarized_content.strip(),
            topics=summarized_topics,
            user_id=user_id,
            agent_id=summarized_agent_id,
        )

        logger.debug(
            f"Summarized {len(memories)} memories into 1: "
            f"{self.count_tokens(memories)} -> {self.count_tokens([summarized_memory])} tokens"
        )

        return [summarized_memory]
