"""
Shared utilities for ii-skills integration.

This module provides common interfaces for skills to interact with
the ii-agent infrastructure (database, storage, research, etc.)

Components:
- DataStore: Unified database access (portfolio, prices, outputs, deals, memory)
- SkillStorage: Cloud storage for skill outputs (GCS integration)
- SkillConfig: Unified configuration (API keys, credentials, settings)
- ResearchClient: Web search and content extraction
- MemoryService: Persistent memory across sessions
- PriceFeedService: Real-time price feeds with caching
- AlertEngine: Price and portfolio alert rules
"""

from ii_skills.shared.datastore import DataStore, get_datastore
from ii_skills.shared.storage import SkillStorage, get_skill_storage
from ii_skills.shared.skill_config import SkillConfig, get_skill_config
from ii_skills.shared.research import ResearchClient, get_research_client
from ii_skills.shared.memory import (
    MemoryService,
    MemoryType,
    Memory,
    ConversationMemory,
    DealMemory,
)
from ii_skills.shared.price_feeds import (
    PriceFeedService,
    PriceData,
    AssetClass,
    PriceSource,
    PortfolioTracker,
)
from ii_skills.shared.alerts import (
    AlertEngine,
    PriceAlert,
    PortfolioAlert,
    AlertCondition,
    AlertPriority,
    AlertStatus,
    NotificationChannel,
    create_price_below_alert,
    create_price_above_alert,
    create_price_change_alert,
    create_portfolio_change_alert,
)

__all__ = [
    # DataStore
    "DataStore",
    "get_datastore",
    # Storage
    "SkillStorage",
    "get_skill_storage",
    # Config
    "SkillConfig",
    "get_skill_config",
    # Research
    "ResearchClient",
    "get_research_client",
    # Memory (Phase 4)
    "MemoryService",
    "MemoryType",
    "Memory",
    "ConversationMemory",
    "DealMemory",
    # Price Feeds (Phase 4)
    "PriceFeedService",
    "PriceData",
    "AssetClass",
    "PriceSource",
    "PortfolioTracker",
    # Alerts (Phase 4)
    "AlertEngine",
    "PriceAlert",
    "PortfolioAlert",
    "AlertCondition",
    "AlertPriority",
    "AlertStatus",
    "NotificationChannel",
    "create_price_below_alert",
    "create_price_above_alert",
    "create_price_change_alert",
    "create_portfolio_change_alert",
]
