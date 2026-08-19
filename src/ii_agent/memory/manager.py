"""MemoryManager — async orchestrator for user memory extraction and management.

Uses a secondary LLM call with tool-calling to decide what to add/update/delete.
This class is used by the agent at runtime (not by the HTTP API).
It manages its own DB sessions via get_db_session_local().
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from textwrap import dedent
from typing import Any, Callable, Dict, List, Optional, Type, Union

from pydantic import BaseModel

from ii_agent.agents.models.base import Model
from ii_agent.agents.models.message import Message
from ii_agent.agents.tools.function import Function
from ii_agent.core.db.base import get_db_session_local
from ii_agent.memory.models import UserMemory
from ii_agent.memory.schemas import MemorySearchResponse

logger = logging.getLogger(__name__)


async def _evict_memory_cache(user_id: str) -> None:
    """Evict all memory cache entries for a user after a write in MemoryManager.

    Tries the container's MemoryService first (shares the same cache instance).
    Falls back to create_entity_cache() which works correctly with Redis.
    """
    try:
        from ii_agent.core.container import get_app_container

        container = get_app_container()
        await container.memory_service._cache.evict_user_memory_data(user_id)
        return
    except (RuntimeError, AttributeError):
        pass  # Container not initialised yet (tests, CLI)

    try:
        from ii_agent.core.redis.cache import create_entity_cache
        from ii_agent.memory.cache_service import MemoryCacheService

        cache_backend = create_entity_cache(namespace="memory", ttl=600)
        cache_svc = MemoryCacheService(cache=cache_backend)
        await cache_svc.evict_user_memory_data(user_id)
    except Exception as e:
        logger.debug(f"Could not evict memory cache for {user_id}: {e}")


@dataclass
class MemoryManager:
    """Async memory manager for creating, retrieving, and managing user memories.

    Operates outside the request scope — creates its own DB sessions.
    """

    model: Optional[Model] = None

    system_message: Optional[str] = None
    memory_capture_instructions: Optional[str] = None
    additional_instructions: Optional[str] = None

    add_memories: bool = True
    update_memories: bool = True
    delete_memories: bool = False
    clear_memories: bool = False

    memories_updated: bool = field(default=False, init=False)

    # ------------------------------------------------------------------
    # Public API — read
    # ------------------------------------------------------------------

    async def aget_user_memories(self, user_id: Optional[str] = None) -> list[dict[str, Any]]:
        """Return all memories for a user as dicts.

        Hot path — called every agent message (context injection + existing check).
        Optimised to avoid DB session acquire when cache hits.

        Strategy:
        1. Try cache directly (no DB session needed) — O(1) Redis GET
        2. On miss: open DB session, query, populate cache
        3. Fallback: direct DB query (tests/CLI without container)
        """
        user_id = user_id or "default"
        user_uuid = uuid.UUID(user_id)

        # 1. Try cache-only path (no DB session)
        try:
            from ii_agent.core.container import get_app_container

            cache_svc = get_app_container().memory_service._cache
            cached = await cache_svc.get_user_memories(user_id)
            if cached is not None:
                # Cache stores list[dict] with memory_id, memory, topics etc.
                # Return directly — no Pydantic round-trip needed.
                return cached
        except (RuntimeError, AttributeError):
            cache_svc = None  # Container not initialised (tests, CLI)

        # 2. Cache miss — need DB session to populate cache
        async with get_db_session_local() as db:
            from ii_agent.memory.repository import MemoryRepository
            from ii_agent.memory.schemas import MemoryData

            repo = MemoryRepository()
            rows = await repo.get_user_memories(db, user_uuid)

            # Use MemoryData.model_dump(mode="json") to guarantee the same
            # serialisation format that MemoryService uses, so either writer
            # can populate the cache and either reader can consume it.
            full_dicts = [
                MemoryData(
                    memory_id=r.memory_id,
                    memory=r.memory,
                    topics=r.topics,
                    user_id=r.user_id,
                    input=r.input,
                    agent_id=r.agent_id,
                    created_at=r.created_at,
                    updated_at=r.updated_at,
                ).model_dump(mode="json")
                for r in rows
            ]

        # Populate cache for next call (same format as MemoryService)
        if cache_svc is not None:
            await cache_svc.set_user_memories(user_id, full_dicts)

        return full_dicts

    # ------------------------------------------------------------------
    # Public API — create / update (auto mode)
    # ------------------------------------------------------------------

    async def acreate_user_memories(
        self,
        *,
        message: Optional[str] = None,
        messages: Optional[List[Message]] = None,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
    ) -> str:
        """Extract memories from messages and persist them."""
        if not messages and not message:
            raise ValueError("Provide either message or messages")

        if message:
            messages = [Message(role="user", content=message)]
        if not messages:
            raise ValueError("Invalid messages list")

        user_id = user_id or "default"
        existing = await self.aget_user_memories(user_id=user_id)

        return await self._acreate_or_update_memories(
            messages=messages,
            existing_memories=existing,
            user_id=user_id,
            agent_id=agent_id,
        )

    # ------------------------------------------------------------------
    # Public API — task-based mutation (agentic mode)
    # ------------------------------------------------------------------

    async def aupdate_memory_task(
        self,
        task: str,
        user_id: Optional[str] = None,
    ) -> str:
        """Execute a free-text task against the memory store."""
        user_id = user_id or "default"
        existing = await self.aget_user_memories(user_id=user_id)

        return await self._arun_memory_task(
            task=task,
            existing_memories=existing,
            user_id=user_id,
        )

    # ------------------------------------------------------------------
    # Public API — clear
    # ------------------------------------------------------------------

    async def aclear_user_memories(self, user_id: Optional[str] = None) -> None:
        user_id = user_id or "default"
        async with get_db_session_local() as db:
            from ii_agent.memory.repository import MemoryRepository

            repo = MemoryRepository()
            await repo.clear_user_memories(db, uuid.UUID(user_id))

    # ------------------------------------------------------------------
    # Public API — search
    # ------------------------------------------------------------------

    async def asearch_user_memories(
        self,
        query: str,
        user_id: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> list[dict[str, Any]]:
        """Agentic semantic search over user memories."""
        user_id = user_id or "default"
        all_memories = await self.aget_user_memories(user_id=user_id)
        if not all_memories:
            return []
        return await self._asearch_agentic(all_memories, query, limit)

    # ------------------------------------------------------------------
    # Internals — LLM-based memory extraction
    # ------------------------------------------------------------------

    def _get_model(self) -> Model:
        if self.model is None:
            raise ValueError("MemoryManager requires a model")
        return self.model

    def _get_system_message(
        self,
        existing_memories: Optional[List[Dict[str, Any]]] = None,
    ) -> Message:
        if self.system_message is not None:
            return Message(role="system", content=self.system_message)

        capture_instructions = self.memory_capture_instructions or dedent("""\
            Memories should capture personal information about the user that is relevant to the current conversation, such as:
            - Personal facts: name, age, occupation, location, interests, and preferences
            - Opinions and preferences: what the user likes, dislikes, enjoys, or finds frustrating
            - Significant life events or experiences shared by the user
            - Important context about the user's current situation, challenges, or goals
            - Any other details that offer meaningful insight into the user's personality, perspective, or needs
        """)

        lines = [
            "You are a Memory Manager responsible for managing information and preferences about the user. "
            "You will be provided with criteria for memories to capture and a list of existing memories.",
            "",
            "## When to add or update memories",
            "- Decide if a memory needs to be added, updated, or deleted based on the user's message, or if no changes are needed.",
            "- If the user's message meets the criteria below and that information is not already captured, you should capture it.",
            "- If existing memories already capture all relevant information, no changes are needed.",
            "",
            "## How to add or update memories",
            "- Create brief, third-person statements that encapsulate the most important aspect of the user's input.",
            "- Don't make a single memory too long — create multiple memories if needed.",
            "- Don't repeat the same information in multiple memories.",
            "- When updating a memory, append new information rather than overwriting.",
            "",
            "<memories_to_capture>",
            capture_instructions,
            "</memories_to_capture>",
            "",
            "## Available actions",
        ]
        if self.add_memories:
            lines.append("  - Add a new memory using the `add_memory` tool.")
        if self.update_memories:
            lines.append("  - Update an existing memory using the `update_memory` tool.")
        if self.delete_memories:
            lines.append("  - Delete an existing memory using the `delete_memory` tool.")
        if self.clear_memories:
            lines.append("  - Clear all memories using the `clear_memory` tool.")
        lines.append("You can call multiple tools in a single response if needed.")

        if existing_memories:
            lines.append("\n<existing_memories>")
            for mem in existing_memories:
                lines.append(f"ID: {mem['memory_id']}")
                lines.append(f"Memory: {mem['memory']}")
                lines.append("")
            lines.append("</existing_memories>")

        if self.additional_instructions:
            lines.append(self.additional_instructions)

        return Message(role="system", content="\n".join(lines))

    def _build_db_tools(
        self,
        user_id: str,
        input_string: str,
        agent_id: Optional[str] = None,
    ) -> List[Callable]:
        """Build closure-based tool functions that write directly to the store."""

        async def add_memory(memory: str, topics: Optional[List[str]] = None) -> str:
            """Add a new memory to the database.
            Args:
                memory: The memory text to store.
                topics: Optional topic tags (e.g. ["name", "hobbies"]).
            Returns:
                Status message.
            """
            try:
                async with get_db_session_local() as db:
                    from ii_agent.memory.repository import MemoryRepository

                    repo = MemoryRepository()
                    record = UserMemory(
                        memory_id=str(uuid.uuid4()),
                        user_id=uuid.UUID(user_id),
                        agent_id=agent_id,
                        memory=memory,
                        topics=topics,
                        input=input_string,
                    )
                    await repo.upsert(db, record)
                await _evict_memory_cache(user_id)
                return "Memory added successfully"
            except Exception as e:
                logger.warning(f"Error adding memory: {e}")
                return f"Error adding memory: {e}"

        async def update_memory(
            memory_id: str, memory: str, topics: Optional[List[str]] = None
        ) -> str:
            """Update an existing memory.
            Args:
                memory_id: The ID of the memory to update.
                memory: The updated memory text.
                topics: Optional updated topic tags.
            Returns:
                Status message.
            """
            if not memory:
                return "Cannot update memory with empty string."
            try:
                async with get_db_session_local() as db:
                    from ii_agent.memory.repository import MemoryRepository

                    repo = MemoryRepository()
                    record = UserMemory(
                        memory_id=memory_id,
                        user_id=uuid.UUID(user_id),
                        memory=memory,
                        topics=topics,
                        input=input_string,
                    )
                    await repo.upsert(db, record)
                await _evict_memory_cache(user_id)
                return "Memory updated successfully"
            except Exception as e:
                logger.warning(f"Error updating memory: {e}")
                return f"Error updating memory: {e}"

        async def delete_memory(memory_id: str) -> str:
            """Delete a single memory.
            Args:
                memory_id: The ID of the memory to delete.
            Returns:
                Status message.
            """
            try:
                async with get_db_session_local() as db:
                    from ii_agent.memory.repository import MemoryRepository

                    repo = MemoryRepository()
                    await repo.delete_by_memory_id(db, memory_id, uuid.UUID(user_id))
                await _evict_memory_cache(user_id)
                return "Memory deleted successfully"
            except Exception as e:
                logger.warning(f"Error deleting memory: {e}")
                return f"Error deleting memory: {e}"

        async def clear_memory() -> str:
            """Remove all memories for this user.
            Returns:
                Status message.
            """
            await self.aclear_user_memories(user_id=user_id)
            await _evict_memory_cache(user_id)
            return "Memory cleared successfully"

        tools: List[Callable] = []
        if self.add_memories:
            tools.append(add_memory)
        if self.update_memories:
            tools.append(update_memory)
        if self.delete_memories:
            tools.append(delete_memory)
        if self.clear_memories:
            tools.append(clear_memory)
        return tools

    def _callables_to_functions(self, callables: List[Callable]) -> List[Union[Function, dict]]:
        """Convert callable tool functions to Function objects for the model."""
        functions: List[Union[Function, dict]] = []
        seen: set = set()
        for tool in callables:
            name = tool.__name__
            if name in seen:
                continue
            seen.add(name)
            try:
                func = Function.from_callable(tool, strict=True)
                func.strict = True
                functions.append(func)
            except Exception as e:
                logger.warning(f"Could not register function {name}: {e}")
        return functions

    async def _acreate_or_update_memories(
        self,
        messages: List[Message],
        existing_memories: List[Dict[str, Any]],
        user_id: str,
        agent_id: Optional[str] = None,
    ) -> str:
        model = self._get_model()

        if len(messages) == 1:
            input_string = messages[0].content or ""
        else:
            input_string = ", ".join(
                str(m.content) for m in messages if m.role == "user" and m.content
            )

        tools = self._callables_to_functions(
            self._build_db_tools(user_id, input_string, agent_id=agent_id)
        )

        messages_for_model = [
            self._get_system_message(existing_memories=existing_memories),
            *messages,
        ]

        response = await model.aresponse(messages=messages_for_model, tools=tools)
        if response.tool_calls:
            self.memories_updated = True

        return response.content or "No response from model"

    async def _arun_memory_task(
        self,
        task: str,
        existing_memories: List[Dict[str, Any]],
        user_id: str,
    ) -> str:
        model = self._get_model()

        tools = self._callables_to_functions(self._build_db_tools(user_id, task))

        messages_for_model = [
            self._get_system_message(existing_memories=existing_memories),
            Message(role="user", content=task),
        ]

        response = await model.aresponse(messages=messages_for_model, tools=tools)
        if response.tool_calls:
            self.memories_updated = True

        return response.content or "No response from model"

    async def _asearch_agentic(
        self,
        memories: List[Dict[str, Any]],
        query: str,
        limit: Optional[int] = None,
    ) -> list[dict[str, Any]]:
        model = self._get_model()

        system_lines = [
            "Your task is to search through user memories and return the IDs of the memories related to the query.\n",
            "<user_memories>",
        ]
        for mem in memories:
            system_lines.append(f"ID: {mem['memory_id']}")
            system_lines.append(f"Memory: {mem['memory']}")
            if mem.get("topics"):
                system_lines.append(f"Topics: {','.join(mem['topics'])}")
            system_lines.append("")
        system_lines.append("</user_memories>")
        system_lines.append("\nRETURN ONLY the IDs of memories related to the query.")

        response_format: Union[Dict[str, Any], Type[BaseModel]]
        if model.supports_native_structured_outputs:
            response_format = MemorySearchResponse
        elif model.supports_json_schema_outputs:
            response_format = {
                "type": "json_schema",
                "json_schema": {
                    "name": MemorySearchResponse.__name__,
                    "schema": MemorySearchResponse.model_json_schema(),
                },
            }
        else:
            response_format = {"type": "json_object"}

        messages_for_model = [
            Message(role="system", content="\n".join(system_lines)),
            Message(role="user", content=f"Return memory IDs related to: {query}"),
        ]

        response = await model.aresponse(
            messages=messages_for_model, response_format=response_format
        )

        search_result: Optional[MemorySearchResponse] = None
        if (
            model.supports_native_structured_outputs
            and response.parsed is not None
            and isinstance(response.parsed, MemorySearchResponse)
        ):
            search_result = response.parsed
        elif isinstance(response.content, str):
            try:
                from ii_agent.agents.utils.string import parse_response_model_str

                search_result = parse_response_model_str(response.content, MemorySearchResponse)
            except Exception as e:
                logger.warning(f"Failed to parse search response: {e}")
                return []

        if search_result is None:
            return []

        id_set = set(search_result.memory_ids)
        matched = [m for m in memories if m["memory_id"] in id_set]
        return matched[:limit] if limit else matched
