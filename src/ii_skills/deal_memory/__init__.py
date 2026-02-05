"""
Deal Memory Skill

Persistent deal context across conversations. Stores deal notes, decisions,
assumptions, company research, and user preferences so they persist between sessions.

Wraps existing infrastructure:
- DealMemory (shared/memory.py) for company/deal knowledge
- MemoryService (shared/memory.py) for general memory ops
- DataStore (shared/datastore.py) for deal CRUD

Usage:
    skill = DealMemorySkill()
    skill.initialize()

    # Store deal context
    result = skill.execute("remember_deal_context", user_id="user1",
        deal_id="abc123", context_type="assumption",
        content={"key": "revenue_growth", "value": "8%", "rationale": "Management guidance"})

    # Recall all context for a deal
    result = skill.execute("recall_deal_context", user_id="user1", deal_id="abc123")
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any

from ii_skills import BaseSkill, register_skill

logger = logging.getLogger(__name__)

__version__ = "1.0.0"
__author__ = "II-Agent System"


@register_skill
class DealMemorySkill(BaseSkill):
    """Persistent deal context and memory across conversations."""

    name = "deal_memory"
    version = __version__
    description = "Persistent deal context, company knowledge, and user preferences across sessions"

    SKILL_DIR = Path(__file__).parent
    OUTPUT_DIR = SKILL_DIR / "output"

    def __init__(self, config: Optional[Dict] = None):
        super().__init__(config)
        self.OUTPUT_DIR.mkdir(exist_ok=True)

    def validate_config(self) -> List[str]:
        return []

    def get_capabilities(self) -> List[str]:
        return [
            "remember_deal_context",
            "recall_deal_context",
            "remember_company_fact",
            "recall_company_facts",
            "list_active_deals",
            "list_past_deals",
            "search_deal_history",
            "remember_user_preference",
            "get_user_preferences",
            "export_deal_context",
        ]

    def execute(self, action: str, **kwargs) -> Dict:
        """Execute a deal memory action."""
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, self._execute_async(action, **kwargs))
                return future.result()
        return asyncio.run(self._execute_async(action, **kwargs))

    async def _execute_async(self, action: str, **kwargs) -> Dict:
        """Async action router."""
        actions = {
            "remember_deal_context": self._remember_deal_context,
            "recall_deal_context": self._recall_deal_context,
            "remember_company_fact": self._remember_company_fact,
            "recall_company_facts": self._recall_company_facts,
            "list_active_deals": self._list_active_deals,
            "list_past_deals": self._list_past_deals,
            "search_deal_history": self._search_deal_history,
            "remember_user_preference": self._remember_user_preference,
            "get_user_preferences": self._get_user_preferences,
            "export_deal_context": self._export_deal_context,
        }

        handler = actions.get(action)
        if not handler:
            raise NotImplementedError(f"Action '{action}' not implemented")
        return await handler(**kwargs)

    # ------------------------------------------------------------------
    # Deal Context
    # ------------------------------------------------------------------

    async def _remember_deal_context(
        self,
        user_id: str,
        deal_id: str,
        content: Dict[str, Any],
        context_type: str = "note",
        **kwargs,
    ) -> Dict:
        """Store a deal-specific note, decision, or assumption.

        Args:
            user_id: User identifier
            deal_id: Deal to associate with
            content: Content dict to store
            context_type: One of 'note', 'assumption', 'decision', 'risk', 'update'
        """
        from ii_skills.shared.memory import MemoryService, MemoryType

        memory = MemoryService(user_id=user_id, skill_name="deal_memory")
        timestamp = datetime.now(timezone.utc).isoformat()
        key = f"deal_{deal_id}_{context_type}_{timestamp}"

        await memory.remember(
            key=key,
            content={
                "deal_id": deal_id,
                "context_type": context_type,
                "data": content,
                "stored_at": timestamp,
            },
            memory_type=MemoryType.DEAL,
        )

        return {"success": True, "deal_id": deal_id, "key": key, "context_type": context_type}

    async def _recall_deal_context(
        self,
        user_id: str,
        deal_id: str,
        context_type: Optional[str] = None,
        **kwargs,
    ) -> Dict:
        """Get all stored context for a deal."""
        from ii_skills.shared.memory import MemoryService, MemoryType
        from ii_skills.shared.datastore import DataStore

        # Get deal record
        store = DataStore()
        deal = await store.get_deal(deal_id)

        # Get all deal memories
        memory = MemoryService(user_id=user_id, skill_name="deal_memory")
        all_memories = await memory.recall_all(memory_type=MemoryType.DEAL, limit=200)

        # Filter to this deal
        contexts = []
        for mem in all_memories:
            mem_deal_id = mem.content.get("deal_id", "")
            if mem_deal_id == deal_id:
                if context_type and mem.content.get("context_type") != context_type:
                    continue
                contexts.append(mem.to_dict())

        return {
            "success": True,
            "deal": deal,
            "contexts": contexts,
            "total_items": len(contexts),
        }

    # ------------------------------------------------------------------
    # Company Knowledge
    # ------------------------------------------------------------------

    async def _remember_company_fact(
        self,
        user_id: str,
        symbol: str,
        company_name: str,
        facts: Dict[str, Any],
        **kwargs,
    ) -> Dict:
        """Store company-specific research and knowledge."""
        from ii_skills.shared.memory import DealMemory

        deal_mem = DealMemory(user_id=user_id)
        await deal_mem.remember_company(symbol=symbol, company_name=company_name, facts=facts)

        return {"success": True, "symbol": symbol, "company_name": company_name}

    async def _recall_company_facts(
        self,
        user_id: str,
        symbol: str,
        **kwargs,
    ) -> Dict:
        """Get all stored knowledge about a company."""
        from ii_skills.shared.memory import DealMemory

        deal_mem = DealMemory(user_id=user_id)
        knowledge = await deal_mem.get_company_knowledge(symbol)

        return {"success": True, "symbol": symbol, "knowledge": knowledge}

    # ------------------------------------------------------------------
    # Deal Listing
    # ------------------------------------------------------------------

    async def _list_active_deals(self, user_id: str, **kwargs) -> Dict:
        """List all in-progress deals."""
        from ii_skills.shared.datastore import DataStore

        store = DataStore()
        deals = await store.get_deals(user_id=user_id, status="in_progress", limit=50)

        return {"success": True, "deals": deals, "count": len(deals)}

    async def _list_past_deals(self, user_id: str, **kwargs) -> Dict:
        """List completed deals with outcomes."""
        from ii_skills.shared.datastore import DataStore

        store = DataStore()
        deals = await store.get_deals(user_id=user_id, status="completed", limit=50)

        return {"success": True, "deals": deals, "count": len(deals)}

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    async def _search_deal_history(
        self,
        user_id: str,
        query: str,
        deal_type: Optional[str] = None,
        **kwargs,
    ) -> Dict:
        """Search across all deal memories."""
        from ii_skills.shared.memory import MemoryService, MemoryType, DealMemory

        memory = MemoryService(user_id=user_id, skill_name="deal_memory")

        # Search memories
        results = await memory.search(
            query=query,
            memory_types=[MemoryType.DEAL, MemoryType.COMPANY],
            limit=kwargs.get("limit", 10),
        )

        # Also search for similar deals if deal_type provided
        similar_deals = []
        if deal_type:
            deal_mem = DealMemory(user_id=user_id)
            similar_deals = await deal_mem.get_similar_deals(deal_type=deal_type, limit=5)

        return {
            "success": True,
            "memory_results": [r.to_dict() for r in results],
            "similar_deals": similar_deals,
            "total_results": len(results),
        }

    # ------------------------------------------------------------------
    # Preferences
    # ------------------------------------------------------------------

    async def _remember_user_preference(
        self,
        user_id: str,
        key: str,
        value: Any,
        **kwargs,
    ) -> Dict:
        """Store a user preference for deal analysis."""
        from ii_skills.shared.memory import DealMemory

        deal_mem = DealMemory(user_id=user_id)
        await deal_mem.remember_preference(key=key, value=value)

        return {"success": True, "key": key, "value": value}

    async def _get_user_preferences(
        self,
        user_id: str,
        keys: Optional[List[str]] = None,
        **kwargs,
    ) -> Dict:
        """Get user preferences for deal analysis."""
        from ii_skills.shared.memory import DealMemory

        deal_mem = DealMemory(user_id=user_id)

        if keys:
            prefs = {}
            for key in keys:
                prefs[key] = await deal_mem.get_preference(key)
            return {"success": True, "preferences": prefs}

        # Get all preferences by recalling all preference-type memories
        from ii_skills.shared.memory import MemoryService, MemoryType

        memory = MemoryService(user_id=user_id, skill_name="ib_toolkit")
        all_prefs = await memory.recall_all(memory_type=MemoryType.PREFERENCE, limit=100)

        prefs = {}
        for mem in all_prefs:
            prefs[mem.key] = mem.content.get("value")

        return {"success": True, "preferences": prefs}

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    async def _export_deal_context(
        self,
        user_id: str,
        deal_id: str,
        **kwargs,
    ) -> Dict:
        """Export all deal context as a structured dict."""
        # Get deal record
        from ii_skills.shared.datastore import DataStore

        store = DataStore()
        deal = await store.get_deal(deal_id)
        if not deal:
            return {"success": False, "error": f"Deal {deal_id} not found"}

        # Get all contexts
        context_result = await self._recall_deal_context(user_id=user_id, deal_id=deal_id)

        # Get company knowledge if symbol available
        company_knowledge = None
        if deal.get("company_symbol"):
            company_result = await self._recall_company_facts(
                user_id=user_id, symbol=deal["company_symbol"]
            )
            company_knowledge = company_result.get("knowledge")

        export = {
            "deal": deal,
            "contexts": context_result.get("contexts", []),
            "company_knowledge": company_knowledge,
            "exported_at": datetime.now(timezone.utc).isoformat(),
        }

        # Save to output directory
        safe_name = deal.get("deal_name", deal_id).replace(" ", "_").replace("/", "_")
        output_path = self.OUTPUT_DIR / f"{safe_name}_context.json"
        with open(output_path, "w") as f:
            json.dump(export, f, indent=2, default=str)

        return {
            "success": True,
            "deal_id": deal_id,
            "output_path": str(output_path),
            "context_count": len(export["contexts"]),
        }


def get_deal_memory(config: Optional[Dict] = None) -> DealMemorySkill:
    """Get an instance of the Deal Memory skill."""
    skill = DealMemorySkill(config)
    skill.initialize()
    return skill
