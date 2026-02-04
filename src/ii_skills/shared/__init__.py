"""
Shared utilities for ii-skills integration.

This module provides common interfaces for skills to interact with
the ii-agent infrastructure (database, storage, etc.)

Components:
- DataStore: Unified database access (portfolio, prices, outputs, deals, memory)
- SkillStorage: Cloud storage for skill outputs (GCS integration)
- SkillConfig: Unified configuration (API keys, credentials, settings)
"""

from ii_skills.shared.datastore import DataStore, get_datastore
from ii_skills.shared.storage import SkillStorage, get_skill_storage
from ii_skills.shared.skill_config import SkillConfig, get_skill_config

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
]
