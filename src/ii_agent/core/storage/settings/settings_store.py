from __future__ import annotations

from abc import ABC, abstractmethod

from ii_agent.core.config.ii_agent_config import IIAgentConfig
from ii_agent.core.storage.models.settings import Settings


class SettingsStore(ABC):
    """Abstract base class for storing user settings."""

    @abstractmethod
    async def load(self) -> Settings | None:
        """Load session init data."""

    @abstractmethod
    async def store(self, settings: Settings) -> None:
        """Store session init data."""

    @classmethod
    @abstractmethod
    async def get_instance(
        cls, config: IIAgentConfig, user_id: str | None
    ) -> SettingsStore:
        """Get a store for the user represented by the token given."""
