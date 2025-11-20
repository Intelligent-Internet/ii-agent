"""Context manager with slab checkpointing (Strategy 5)."""

from typing import List
from ii_agent.llm.base import GeneralContentBlock
from ii_agent.llm.context_manager.base import ContextManager
from ii_agent.llm.token_counter import TokenCounter
from ii_agent.storage.slab_checkpoint import SlabCheckpoint
from ii_agent.utils.constants import TOKEN_BUDGET
from ii_agent.core.logger import logger


class SlabCheckpointManager(ContextManager):
    """Context manager that creates checkpoints without evicting context."""

    def __init__(
        self,
        token_counter: TokenCounter,
        token_budget: int = TOKEN_BUDGET,
        checkpoint_threshold: float = 0.9,
    ):
        super().__init__(token_counter=token_counter, token_budget=token_budget)
        self.checkpoint_threshold = checkpoint_threshold
        self.checkpoint_system = SlabCheckpoint()
        self.last_checkpoint_id: str | None = None

    def should_truncate(self, message_lists: list[list[GeneralContentBlock]]) -> bool:
        """Never truncate - we checkpoint instead."""
        # We still check for checkpoint threshold but don't truncate
        return False

    async def apply_truncation(
        self, message_lists: list[list[GeneralContentBlock]]
    ) -> list[list[GeneralContentBlock]]:
        """Create checkpoint if needed but DON'T truncate."""
        current_tokens = self.count_tokens(message_lists)
        checkpoint_threshold = int(self._token_budget * self.checkpoint_threshold)

        if current_tokens >= checkpoint_threshold:
            # Create checkpoint (context NOT evicted)
            self.last_checkpoint_id = await self.checkpoint_system.create_checkpoint(
                message_lists
            )
            logger.info(
                f"Checkpoint {self.last_checkpoint_id} created at {current_tokens} tokens "
                f"(threshold: {checkpoint_threshold}). Context NOT evicted."
            )

        # Return original messages unchanged
        return message_lists

    def get_last_checkpoint_id(self) -> str | None:
        """Get ID of most recent checkpoint."""
        return self.last_checkpoint_id
