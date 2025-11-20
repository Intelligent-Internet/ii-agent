"""MicrocontextSubroutine tool - temporary context expansion."""

import json
from typing import Any, Dict, List

from ii_agent.server.chat.tools.base import BaseTool, ToolInfo, ToolResponse, ToolCallInput
from ii_agent.server.chat.models import ToolResultContent
from ii_agent.storage.slab_checkpoint import SlabCheckpoint
from ii_agent.storage.breadcrumbs import Breadcrumb, BreadcrumbTrail, BreadcrumbRelationType
from datetime import datetime
from ii_agent.core.logger import logger


class MicrocontextSubroutineTool(BaseTool):
    """Tool for temporarily expanding context with checkpoint data."""

    def __init__(self):
        from ii_agent.server.chat.context_manager import ContextWindowManager
        self.checkpoint_system = ContextWindowManager.get_checkpoint_system()

    @property
    def name(self) -> str:
        return "MicrocontextSubroutine"

    def info(self) -> ToolInfo:
        """Get tool definition for LLM."""
        return ToolInfo(
            name="MicrocontextSubroutine",
            description="Temporarily expand context by digesting historical checkpoints. Use when a tool needs extensive historical context to operate correctly. Context expansion is temporary and discarded after tool execution returns to coherence level.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Query describing what historical context is needed"
                    },
                    "depth": {
                        "type": "integer",
                        "description": "Number of checkpoints to digest (1-5, default 3)",
                        "default": 3,
                        "minimum": 1,
                        "maximum": 5
                    },
                    "focus": {
                        "type": "string",
                        "description": "Focus area: 'operational' (todos, files, tests) or 'semantic' (reasoning, decisions, explanations)",
                        "enum": ["operational", "semantic"],
                        "default": "operational"
                    }
                },
            },
            required=["query"]
        )

    async def run(self, tool_call: ToolCallInput) -> ToolResponse:
        """Execute the tool."""
        params = json.loads(tool_call.input)
        query = params.get("query")
        depth = params.get("depth", 3)
        focus = params.get("focus", "operational")

        result = await self._execute(query, depth, focus)

        return ToolResponse(
            output=ToolResultContent(content=result)
        )

    async def _execute(self, query: str, depth: int = 3, focus: str = "operational") -> str:
        """Execute microcontext expansion and return digest."""
        # Query checkpoints
        slab_ids = self.checkpoint_system.query_checkpoints(query)

        if not slab_ids:
            return f"No checkpoints found for query: {query}"

        # Digest checkpoints
        digests = []
        for slab_id in slab_ids[:depth]:
            if focus == "operational":
                digest = self._digest_payload(slab_id)
            else:
                digest = self._digest_backdrop(slab_id)

            if digest:
                digests.append(f"=== Checkpoint {slab_id} ===\n{digest}")

        if not digests:
            return f"No checkpoint data found for query: {query}"

        # Combine digests
        result = f"Microcontext expansion for: {query}\n\n"
        result += "\n\n".join(digests)
        result += "\n\n[NOTE: This context is temporary and will be discarded after returning to coherence level]"

        logger.info(f"Microcontext expansion: {len(digests)} checkpoints digested for '{query}'")
        return result

    def _digest_payload(self, slab_id: str) -> str:
        """Digest operational state from payload."""
        payload = self.checkpoint_system.get_checkpoint(slab_id, slab_type="payload")
        if not payload:
            return ""

        lines = []

        # Pending todos
        todos = payload.get("todos", [])
        pending = [t for t in todos if t.get("status") != "completed"]
        if pending:
            lines.append("Pending Tasks:")
            for todo in pending[:5]:
                lines.append(f"  - {todo.get('content', 'Unknown')}")

        # Files modified
        file_refs = payload.get("file_refs", [])
        if file_refs:
            lines.append(f"\nFiles Referenced: {', '.join(file_refs[:5])}")

        # Code changes
        code_changes = payload.get("code_changes", [])
        if code_changes:
            lines.append("\nCode Changes:")
            for change in code_changes[:3]:
                lines.append(f"  - {change.get('file', 'Unknown')}")

        # Test results
        test_results = payload.get("test_results", [])
        if test_results:
            lines.append(f"\nTests: {len(test_results)} executions")

        return "\n".join(lines)

    def _digest_backdrop(self, slab_id: str) -> str:
        """Digest semantic context from backdrop."""
        backdrop = self.checkpoint_system.get_checkpoint(slab_id, slab_type="backdrop")
        if not backdrop:
            return ""

        lines = []

        # User intent
        user_intent = backdrop.get("user_intent", [])
        if user_intent:
            lines.append("User Intent:")
            lines.append(f"  {user_intent[0][:200]}...")

        # Key topics
        topics = backdrop.get("topics", [])
        if topics:
            lines.append(f"\nTopics: {', '.join(topics[:5])}")

        # Thinking excerpts
        thinking = backdrop.get("thinking", [])
        if thinking:
            lines.append(f"\nReasoning: {len(thinking)} thinking blocks captured")

        # Explanations
        explanations = backdrop.get("explanations", [])
        if explanations:
            lines.append(f"\nExplanations: {len(explanations)} responses")

        return "\n".join(lines)
