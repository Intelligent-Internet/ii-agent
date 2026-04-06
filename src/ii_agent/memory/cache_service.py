"""Redis cache service for memory system.

Uses create_entity_cache() which auto-selects Redis vs in-memory
based on whether a Redis client has been initialised.
"""

import logging
import time
from typing import Any

from ii_agent.core.redis.cache import EntityCache

logger = logging.getLogger(__name__)


class MemoryCacheService:
    """Cache layer for user memory CRUD operations."""

    # TTL values (seconds)
    TTL_USER_PREFS = 3600  # 1 hour
    TTL_USER_MEMORIES = 600  # 10 minutes
    TTL_USER_TOPICS = 600  # 10 minutes
    TTL_PAGINATED = 300  # 5 minutes
    TTL_PAGE_VERSION = 600  # 10 minutes

    def __init__(self, cache: EntityCache) -> None:
        self._cache = cache

    # ---- User preferences (has_memory flag) ----
    # Key convention: namespace "memory" is added by EntityCache._make_key(),
    # so keys here are just the semantic part: "prefs:{uid}", "list:{uid}", etc.
    # Final Redis key example: "memory:prefs:<uuid>"

    async def get_user_prefs(self, user_id: str) -> dict[str, Any] | None:
        try:
            result = await self._cache.get(f"prefs:{user_id}")
            if result is not None and isinstance(result, dict):
                return result
        except Exception as e:
            logger.warning(f"Cache get error for prefs:{user_id}: {e}")
        return None

    async def set_user_prefs(self, user_id: str, prefs: dict[str, Any]) -> None:
        try:
            await self._cache.set(f"prefs:{user_id}", prefs, ttl=self.TTL_USER_PREFS)
        except Exception as e:
            logger.warning(f"Cache set error for prefs:{user_id}: {e}")

    async def evict_user_prefs(self, user_id: str) -> None:
        try:
            await self._cache.evict(f"prefs:{user_id}")
        except Exception as e:
            logger.warning(f"Cache evict error for prefs:{user_id}: {e}")

    # ---- User memories list ----

    async def get_user_memories(self, user_id: str) -> list[dict[str, Any]] | None:
        try:
            result = await self._cache.get(f"list:{user_id}")
            if result is not None and isinstance(result, list):
                return result
        except Exception as e:
            logger.warning(f"Cache get error for list:{user_id}: {e}")
        return None

    async def set_user_memories(self, user_id: str, memories: list[dict[str, Any]]) -> None:
        try:
            await self._cache.set(f"list:{user_id}", memories, ttl=self.TTL_USER_MEMORIES)
        except Exception as e:
            logger.warning(f"Cache set error for list:{user_id}: {e}")

    async def evict_user_memories(self, user_id: str) -> None:
        try:
            await self._cache.evict(f"list:{user_id}")
        except Exception as e:
            logger.warning(f"Cache evict error for list:{user_id}: {e}")

    # ---- User distinct topics ----

    async def get_user_topics(self, user_id: str) -> list[str] | None:
        try:
            result = await self._cache.get(f"topics:{user_id}")
            if result is not None and isinstance(result, list):
                return result
        except Exception as e:
            logger.warning(f"Cache get error for topics:{user_id}: {e}")
        return None

    async def set_user_topics(self, user_id: str, topics: list[str]) -> None:
        try:
            await self._cache.set(f"topics:{user_id}", topics, ttl=self.TTL_USER_TOPICS)
        except Exception as e:
            logger.warning(f"Cache set error for topics:{user_id}: {e}")

    async def evict_user_topics(self, user_id: str) -> None:
        try:
            await self._cache.evict(f"topics:{user_id}")
        except Exception as e:
            logger.warning(f"Cache evict error for topics:{user_id}: {e}")

    # ---- Paginated memories (version-based invalidation) ----

    async def _get_page_version(self, user_id: str) -> str:
        try:
            result = await self._cache.get(f"pver:{user_id}")
            if result is not None:
                return str(result)
            ver = str(int(time.time() * 1000))
            await self._cache.set(f"pver:{user_id}", ver, ttl=self.TTL_PAGE_VERSION)
            return ver
        except Exception as e:
            logger.warning(f"Cache error for page version: {e}")
            return ""

    async def get_paginated_memories(
        self, user_id: str, params_hash: str
    ) -> dict[str, Any] | None:
        try:
            ver = await self._get_page_version(user_id)
            if not ver:
                return None
            key = f"page:{user_id}:{ver}:{params_hash}"
            result = await self._cache.get(key)
            if result is not None and isinstance(result, dict):
                return result
        except Exception as e:
            logger.warning(f"Cache get error for paginated memories: {e}")
        return None

    async def set_paginated_memories(
        self, user_id: str, params_hash: str, data: dict[str, Any]
    ) -> None:
        try:
            ver = await self._get_page_version(user_id)
            if not ver:
                return
            key = f"page:{user_id}:{ver}:{params_hash}"
            await self._cache.set(key, data, ttl=self.TTL_PAGINATED)
        except Exception as e:
            logger.warning(f"Cache set error for paginated memories: {e}")

    async def evict_paginated_version(self, user_id: str) -> None:
        try:
            await self._cache.evict(f"pver:{user_id}")
        except Exception as e:
            logger.warning(f"Cache evict error for page version: {e}")

    # ---- Bulk invalidation helper ----

    async def evict_user_memory_data(self, user_id: str) -> None:
        """Invalidate memories list, topics, and paginated cache for a user.

        Call this after any write operation (upsert, delete, clear).
        """
        await self.evict_user_memories(user_id)
        await self.evict_user_topics(user_id)
        await self.evict_paginated_version(user_id)
