"""SBLL Knowledge Chain tool wrapper for ii_tool framework."""
import json
from typing import Any, Dict
from ii_tool.tools.base import BaseTool, ToolResult


class SBLLKnowledgeTool(BaseTool):
    """Wraps the ProductionKnowledgeChainTool for use as an ii_tool."""
    # class-level name so it can be referenced in AgentTypeConfig.TOOLSETS
    name: str = "sbll_knowledge_chain"

    def __init__(self):
        # Lazy import to avoid import-time cost
        from modules.sbll_knowledge_chain.deployment import ProductionKnowledgeChainTool

        self._impl = ProductionKnowledgeChainTool(use_optimized=True)
        self._name = "sbll_knowledge_chain"
        self.name = self._name
        self.description = "Store and query philosophical insights on the SBLL blockchain. Actions: contribute, query, analyze, analytics."
        self.input_schema = {
            "type": "object",
            "properties": {
                "action": {"type": "string"},
                "content": {"type": "string"},
                "tradition": {"type": "string"},
                "min_confidence": {"type": "integer"},
                "synthesize": {"type": "boolean"},
            },
            "required": ["action", "content"],
        }
        self.read_only = False
        self.display_name = "SBLL Knowledge Chain"

    async def execute(self, tool_input: Dict[str, Any]) -> ToolResult:
        # tool_input is expected to be a dict; some callers pass JSON strings
        try:
            if isinstance(tool_input, str):
                params = json.loads(tool_input)
            else:
                params = tool_input

            action = params.get("action")
            content = params.get("content", "")
            tradition = params.get("tradition", "MODERN_SCIENTIFIC")
            # pass through other kwargs
            kwargs = {k: v for k, v in params.items() if k not in ("action", "content", "tradition")}

            result = self._impl.run(action=action, content=content, tradition=tradition, **kwargs)

            return ToolResult(llm_content=result, user_display_content=result, is_error=False)
        except Exception as e:
            return ToolResult(llm_content=f"Error executing SBLL tool: {e}", user_display_content=str(e), is_error=True)
