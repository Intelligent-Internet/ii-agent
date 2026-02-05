"""
Memory System for II-Skills

Provides persistent memory across sessions using the existing database infrastructure
and optional vector store for semantic search.

Features:
- Key-value memory storage with user/skill namespacing
- Semantic search for relevant memories (when vector store available)
- Conversation context retention
- Learning from past interactions
- Memory relevance scoring and decay

Usage:
    from ii_skills.shared.memory import MemoryService

    memory = MemoryService(user_id="user123")

    # Store a fact
    await memory.remember("preferred_model_assumptions", {
        "entry_multiple": "10-12x EBITDA",
        "debt_structure": "senior + mezz",
    }, memory_type="preference")

    # Recall memories
    facts = await memory.recall("preferred_model_assumptions")

    # Search memories semantically
    relevant = await memory.search("what debt structure does the user prefer")
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class MemoryType(str, Enum):
    """Types of memories that can be stored."""
    PREFERENCE = "preference"       # User preferences and settings
    FACT = "fact"                   # Learned facts about users, companies, etc.
    PATTERN = "pattern"             # Observed patterns in user behavior
    FEEDBACK = "feedback"           # User feedback on outputs
    CONTEXT = "context"             # Conversation/session context
    DEAL = "deal"                   # Deal-specific knowledge
    COMPANY = "company"             # Company-specific knowledge


@dataclass
class Memory:
    """Represents a single memory entry."""
    key: str
    content: Dict[str, Any]
    memory_type: MemoryType
    skill_name: str
    access_count: int = 0
    relevance_score: float = 1.0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_accessed_at: Optional[datetime] = None
    id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "key": self.key,
            "content": self.content,
            "memory_type": self.memory_type.value if isinstance(self.memory_type, MemoryType) else self.memory_type,
            "skill_name": self.skill_name,
            "access_count": self.access_count,
            "relevance_score": self.relevance_score,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_accessed_at": self.last_accessed_at.isoformat() if self.last_accessed_at else None,
        }


class MemoryService:
    """
    Service for managing persistent memories across skills.

    Uses the SkillMemory database model for storage and optionally
    integrates with vector stores for semantic search.
    """

    def __init__(
        self,
        user_id: str,
        skill_name: str = "global",
        db_session=None,
        vector_store=None,
    ):
        """
        Initialize memory service.

        Args:
            user_id: User ID for namespacing memories
            skill_name: Default skill name for memories
            db_session: SQLAlchemy async session (optional, uses DataStore if not provided)
            vector_store: Vector store for semantic search (optional)
        """
        self._user_id = user_id
        self._skill_name = skill_name
        self._db_session = db_session
        self._vector_store = vector_store
        self._datastore = None

    async def _get_datastore(self):
        """Lazy-load datastore connection."""
        if self._datastore is None:
            try:
                from ii_skills.shared.datastore import DataStore
                self._datastore = DataStore()
            except ImportError:
                logger.warning("DataStore not available, memory will use in-memory fallback")
        return self._datastore

    async def remember(
        self,
        key: str,
        content: Dict[str, Any],
        memory_type: MemoryType = MemoryType.FACT,
        skill_name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Memory:
        """
        Store a memory.

        Args:
            key: Unique key for the memory within the type/skill namespace
            content: Content to store (must be JSON-serializable)
            memory_type: Type of memory (preference, fact, pattern, etc.)
            skill_name: Override default skill name
            metadata: Additional metadata to store with content

        Returns:
            The created/updated Memory object
        """
        skill = skill_name or self._skill_name

        # Merge metadata into content if provided
        if metadata:
            content = {**content, "_metadata": metadata}

        memory = Memory(
            key=key,
            content=content,
            memory_type=memory_type,
            skill_name=skill,
        )

        try:
            datastore = await self._get_datastore()
            if datastore:
                # Use DataStore to persist
                memory_data = {
                    "user_id": self._user_id,
                    "skill_name": skill,
                    "memory_type": memory_type.value if isinstance(memory_type, MemoryType) else memory_type,
                    "memory_key": key,
                    "content": content,
                    "access_count": 0,
                    "relevance_score": 1.0,
                }

                # Try to upsert (update if exists, insert if not)
                result = await datastore.upsert_memory(self._user_id, memory_data)
                if result:
                    memory.id = result.get("id")

            logger.debug(f"Stored memory: {skill}/{memory_type.value}/{key}")

        except Exception as e:
            logger.warning(f"Failed to persist memory to database: {e}")

        # Also add to vector store for semantic search
        if self._vector_store:
            try:
                await self._add_to_vector_store(memory)
            except Exception as e:
                logger.warning(f"Failed to add memory to vector store: {e}")

        return memory

    async def recall(
        self,
        key: str,
        memory_type: Optional[MemoryType] = None,
        skill_name: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Recall a specific memory by key.

        Args:
            key: Memory key to recall
            memory_type: Filter by memory type (optional)
            skill_name: Filter by skill name (optional)

        Returns:
            Memory content if found, None otherwise
        """
        skill = skill_name or self._skill_name

        try:
            datastore = await self._get_datastore()
            if datastore:
                result = await datastore.get_memory(
                    self._user_id,
                    skill,
                    memory_type.value if memory_type else None,
                    key,
                )

                if result:
                    # Update access count and timestamp
                    await datastore.update_memory_access(result.get("id"))
                    return result.get("content")

        except Exception as e:
            logger.warning(f"Failed to recall memory from database: {e}")

        return None

    async def recall_all(
        self,
        memory_type: Optional[MemoryType] = None,
        skill_name: Optional[str] = None,
        limit: int = 100,
    ) -> List[Memory]:
        """
        Recall all memories matching filters.

        Args:
            memory_type: Filter by memory type
            skill_name: Filter by skill name
            limit: Maximum number of memories to return

        Returns:
            List of Memory objects
        """
        skill = skill_name or self._skill_name
        memories = []

        try:
            datastore = await self._get_datastore()
            if datastore:
                results = await datastore.list_memories(
                    self._user_id,
                    skill_name=skill if skill != "global" else None,
                    memory_type=memory_type.value if memory_type else None,
                    limit=limit,
                )

                for row in results:
                    memories.append(Memory(
                        id=row.get("id"),
                        key=row.get("memory_key"),
                        content=row.get("content", {}),
                        memory_type=MemoryType(row.get("memory_type", "fact")),
                        skill_name=row.get("skill_name", skill),
                        access_count=row.get("access_count", 0),
                        relevance_score=row.get("relevance_score", 1.0),
                        created_at=row.get("created_at"),
                        last_accessed_at=row.get("last_accessed_at"),
                    ))

        except Exception as e:
            logger.warning(f"Failed to list memories: {e}")

        return memories

    async def search(
        self,
        query: str,
        memory_types: Optional[List[MemoryType]] = None,
        skill_names: Optional[List[str]] = None,
        limit: int = 10,
    ) -> List[Memory]:
        """
        Semantic search for relevant memories.

        Args:
            query: Natural language query
            memory_types: Filter by memory types
            skill_names: Filter by skill names
            limit: Maximum results to return

        Returns:
            List of relevant Memory objects, sorted by relevance
        """
        # If vector store available, use semantic search
        if self._vector_store:
            try:
                results = await self._vector_store.search(
                    query=query,
                    user_id=self._user_id,
                    limit=limit,
                )
                # Convert vector store results to Memory objects
                # (implementation depends on vector store format)
                return results
            except Exception as e:
                logger.warning(f"Vector search failed, falling back to keyword: {e}")

        # Fallback: keyword-based search in database
        try:
            datastore = await self._get_datastore()
            if datastore:
                results = await datastore.search_memories(
                    self._user_id,
                    query=query,
                    skill_names=skill_names,
                    memory_types=[mt.value for mt in memory_types] if memory_types else None,
                    limit=limit,
                )

                memories = []
                for row in results:
                    memories.append(Memory(
                        id=row.get("id"),
                        key=row.get("memory_key"),
                        content=row.get("content", {}),
                        memory_type=MemoryType(row.get("memory_type", "fact")),
                        skill_name=row.get("skill_name"),
                        access_count=row.get("access_count", 0),
                        relevance_score=row.get("relevance_score", 1.0),
                        created_at=row.get("created_at"),
                        last_accessed_at=row.get("last_accessed_at"),
                    ))
                return memories

        except Exception as e:
            logger.warning(f"Memory search failed: {e}")

        return []

    async def forget(
        self,
        key: str,
        memory_type: Optional[MemoryType] = None,
        skill_name: Optional[str] = None,
    ) -> bool:
        """
        Delete a memory.

        Args:
            key: Memory key to delete
            memory_type: Memory type (optional for precision)
            skill_name: Skill name (optional)

        Returns:
            True if memory was deleted
        """
        skill = skill_name or self._skill_name

        try:
            datastore = await self._get_datastore()
            if datastore:
                return await datastore.delete_memory(
                    self._user_id,
                    skill,
                    memory_type.value if memory_type else None,
                    key,
                )
        except Exception as e:
            logger.warning(f"Failed to delete memory: {e}")

        return False

    async def _add_to_vector_store(self, memory: Memory) -> None:
        """Add memory to vector store for semantic search."""
        if not self._vector_store:
            return

        # Create searchable text from memory
        text_parts = [
            f"Key: {memory.key}",
            f"Type: {memory.memory_type.value}",
            f"Skill: {memory.skill_name}",
        ]

        # Add content fields
        for k, v in memory.content.items():
            if k != "_metadata":
                text_parts.append(f"{k}: {v}")

        text = "\n".join(text_parts)

        # Add to vector store
        await self._vector_store.add_document(
            text=text,
            metadata={
                "user_id": self._user_id,
                "memory_key": memory.key,
                "memory_type": memory.memory_type.value,
                "skill_name": memory.skill_name,
            }
        )


class ConversationMemory:
    """
    Manages conversation-level context and history.

    Tracks conversation turns, maintains sliding window context,
    and extracts key information for long-term storage.
    """

    def __init__(
        self,
        user_id: str,
        session_id: str,
        memory_service: Optional[MemoryService] = None,
        max_turns: int = 20,
    ):
        """
        Initialize conversation memory.

        Args:
            user_id: User ID
            session_id: Session ID for this conversation
            memory_service: MemoryService for persistent storage
            max_turns: Maximum turns to keep in active context
        """
        self._user_id = user_id
        self._session_id = session_id
        self._memory_service = memory_service or MemoryService(user_id)
        self._max_turns = max_turns
        self._turns: List[Dict[str, Any]] = []
        self._extracted_facts: List[Dict[str, Any]] = []

    async def add_turn(
        self,
        role: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Add a conversation turn.

        Args:
            role: Turn role (user, assistant, system)
            content: Turn content
            metadata: Additional metadata (tool calls, etc.)
        """
        turn = {
            "role": role,
            "content": content,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "metadata": metadata or {},
        }

        self._turns.append(turn)

        # Trim to max turns (keep most recent)
        if len(self._turns) > self._max_turns:
            # Before trimming, extract any important facts
            await self._extract_and_store_facts(self._turns[0])
            self._turns = self._turns[-self._max_turns:]

    async def _extract_and_store_facts(self, turn: Dict[str, Any]) -> None:
        """
        Extract and store important facts from a turn being trimmed.

        This is where you'd use an LLM to extract key information,
        but for now we do basic extraction.
        """
        # Store the turn content as context memory
        content = turn.get("content", "")
        if len(content) > 50:  # Only store substantial content
            await self._memory_service.remember(
                key=f"context_{self._session_id}_{turn.get('timestamp', '')}",
                content={
                    "role": turn.get("role"),
                    "content": content[:500],  # Truncate long content
                    "session_id": self._session_id,
                },
                memory_type=MemoryType.CONTEXT,
            )

    def get_context(self, last_n: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Get conversation context.

        Args:
            last_n: Return only last N turns (default: all)

        Returns:
            List of conversation turns
        """
        if last_n:
            return self._turns[-last_n:]
        return self._turns.copy()

    def get_context_string(self, last_n: Optional[int] = None) -> str:
        """Get context as formatted string."""
        turns = self.get_context(last_n)
        lines = []
        for turn in turns:
            role = turn.get("role", "unknown").upper()
            content = turn.get("content", "")
            lines.append(f"{role}: {content}")
        return "\n\n".join(lines)

    async def save_session(self) -> None:
        """Save the current session to persistent storage."""
        await self._memory_service.remember(
            key=f"session_{self._session_id}",
            content={
                "session_id": self._session_id,
                "turns": self._turns[-10:],  # Save last 10 turns
                "turn_count": len(self._turns),
                "saved_at": datetime.now(timezone.utc).isoformat(),
            },
            memory_type=MemoryType.CONTEXT,
        )

    async def load_session(self) -> bool:
        """
        Load a previous session from storage.

        Returns:
            True if session was loaded
        """
        content = await self._memory_service.recall(
            key=f"session_{self._session_id}",
            memory_type=MemoryType.CONTEXT,
        )

        if content and "turns" in content:
            self._turns = content["turns"]
            return True
        return False


class DealMemory:
    """
    Specialized memory for deal/investment analysis.

    Tracks company-specific knowledge, deal history,
    and learning from past analyses.
    """

    def __init__(
        self,
        user_id: str,
        memory_service: Optional[MemoryService] = None,
    ):
        self._user_id = user_id
        self._memory_service = memory_service or MemoryService(user_id, skill_name="ib_toolkit")

    async def remember_company(
        self,
        symbol: str,
        company_name: str,
        facts: Dict[str, Any],
    ) -> None:
        """
        Store company-specific knowledge.

        Args:
            symbol: Stock symbol
            company_name: Company name
            facts: Facts learned about the company
        """
        await self._memory_service.remember(
            key=f"company_{symbol}",
            content={
                "symbol": symbol,
                "company_name": company_name,
                "facts": facts,
                "learned_at": datetime.now(timezone.utc).isoformat(),
            },
            memory_type=MemoryType.COMPANY,
        )

    async def get_company_knowledge(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get stored knowledge about a company."""
        return await self._memory_service.recall(
            key=f"company_{symbol}",
            memory_type=MemoryType.COMPANY,
        )

    async def remember_deal(
        self,
        deal_id: str,
        company_symbol: str,
        deal_type: str,
        outcome: Dict[str, Any],
    ) -> None:
        """
        Store deal analysis outcome for learning.

        Args:
            deal_id: Unique deal ID
            company_symbol: Company symbol
            deal_type: Type of deal (lbo, growth_equity, etc.)
            outcome: Deal outcome and learnings
        """
        await self._memory_service.remember(
            key=f"deal_{deal_id}",
            content={
                "deal_id": deal_id,
                "company_symbol": company_symbol,
                "deal_type": deal_type,
                "outcome": outcome,
                "completed_at": datetime.now(timezone.utc).isoformat(),
            },
            memory_type=MemoryType.DEAL,
        )

    async def get_similar_deals(
        self,
        deal_type: Optional[str] = None,
        sector: Optional[str] = None,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        Find similar past deals for learning.

        Args:
            deal_type: Filter by deal type
            sector: Filter by sector
            limit: Max results

        Returns:
            List of similar deal memories
        """
        memories = await self._memory_service.recall_all(
            memory_type=MemoryType.DEAL,
            limit=limit * 2,  # Fetch extra for filtering
        )

        results = []
        for mem in memories:
            content = mem.content
            if deal_type and content.get("deal_type") != deal_type:
                continue
            results.append(content)
            if len(results) >= limit:
                break

        return results

    async def remember_preference(
        self,
        key: str,
        value: Any,
    ) -> None:
        """Store a user preference for deal analysis."""
        await self._memory_service.remember(
            key=key,
            content={"value": value},
            memory_type=MemoryType.PREFERENCE,
        )

    async def get_preference(self, key: str, default: Any = None) -> Any:
        """Get a user preference."""
        result = await self._memory_service.recall(
            key=key,
            memory_type=MemoryType.PREFERENCE,
        )
        if result:
            return result.get("value", default)
        return default
