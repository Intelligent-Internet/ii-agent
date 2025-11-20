"""RecallContext tool - query historical checkpoints."""

import json
from typing import Any, Dict

from ii_agent.server.chat.tools.base import BaseTool, ToolInfo, ToolResponse, ToolCallInput
from ii_agent.server.chat.models import ToolResultContent
from ii_agent.storage.slab_checkpoint import SlabCheckpoint
from ii_agent.storage.breadcrumbs import Breadcrumb, BreadcrumbTrail, BreadcrumbRelationType
from datetime import datetime


class RecallContextTool(BaseTool):
    """Tool for querying historical checkpoints via breadcrumb trails."""

    def __init__(self):
        from ii_agent.server.chat.context_manager import ContextWindowManager
        self.checkpoint_system = ContextWindowManager.get_checkpoint_system()

    @property
    def name(self) -> str:
        return "RecallContext"

    def info(self) -> ToolInfo:
        """Get tool definition for LLM."""
        return ToolInfo(
            name="RecallContext",
            description="Query historical context beyond current window. Returns breadcrumb trail showing semantic path through previous checkpoints. Use when you need to recall earlier work, decisions, or context that may have been checkpointed.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Query describing what historical context you need (e.g., 'OAuth implementation', 'bug fix for token expiration', 'test failures')"
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of checkpoints to return (default 5)",
                        "default": 5
                    }
                },
            },
            required=["query"]
        )

    async def run(self, tool_call: ToolCallInput) -> ToolResponse:
        """Execute the tool."""
        params = json.loads(tool_call.input)
        query = params.get("query")
        max_results = params.get("max_results", 5)

        result = await self._execute(query, max_results)

        return ToolResponse(
            output=ToolResultContent(content=result)
        )

    async def _execute(self, query: str, max_results: int = 5) -> str:
        """Execute recall query and return breadcrumb trail."""
        # Query checkpoints
        slab_ids = self.checkpoint_system.query_checkpoints(query)

        if not slab_ids:
            return f"No checkpoints found for query: {query}"

        # Build breadcrumbs
        breadcrumbs = []
        for slab_id in slab_ids[:max_results]:
            meta = self.checkpoint_system.checkpoint_metadata.get(slab_id)
            if not meta:
                continue

            crumb = Breadcrumb(
                slab_id=slab_id,
                slab_type="payload",
                primary_topic=", ".join(meta.get("topics", [])[:2]) or "checkpoint",
                keywords=meta.get("keywords", [])[:5],
                file_refs=meta.get("file_refs", [])[:3],
                created_at=datetime.fromisoformat(meta["created_at"]),
                turn_range=(0, 0),
                inbound_relations=[],
                outbound_relations=[],
                relevance_score=1.0,
            )
            breadcrumbs.append(crumb)

        # Sort by timestamp
        breadcrumbs.sort(key=lambda c: c.created_at)

        # Infer CONTINUATION relations
        relations = []
        for i in range(len(breadcrumbs) - 1):
            relations.append((i, i + 1, BreadcrumbRelationType.CONTINUATION))

        trail = BreadcrumbTrail(
            query=query,
            breadcrumbs=breadcrumbs,
            relations=relations
        )

        return trail.render_text()
