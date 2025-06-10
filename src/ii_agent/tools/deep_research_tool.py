"""Tool for performing deep research on a complex topic."""

from typing import Any, Optional
from ii_agent.llm.message_history import MessageHistory
from ii_agent.tools.base import LLMTool, ToolImplOutput
from ii_researcher.reasoning.agent import ReasoningAgent
from ii_researcher.reasoning.builders.report import ReportType
import asyncio


def on_token(token: str):
    """Callback for processing streamed tokens."""
    print(token, end="", flush=True)


def get_event_loop():
    try:
        # Try to get the existing event loop
        loop = asyncio.get_event_loop()
    except RuntimeError:
        # If no event loop exists, create a new one
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop


class DeepResearchTool(LLMTool):
    name = "deep_research"
    """The model should call this tool when it needs to perform a deep research on a complex topic. This tool is good for providing a comprehensive survey and deep analysis of a topic or niche answers that are hard to find with single search. You can also use this tool to gain large amount of context information."""

    description = """Perform comprehensive, multi-source research on complex topics requiring deep analysis.

This tool goes far beyond basic web search to provide thorough research reports with analysis and synthesis.

Use this tool when you need:
- Comprehensive analysis of complex topics with multiple perspectives
- Academic-level research with source citations and evidence
- Deep investigation into niche or specialized subjects
- Synthesis of information from multiple authoritative sources
- Detailed background research for complex projects or decisions

Key differences from web_search:
- Takes significantly longer (several minutes vs. seconds)
- Searches multiple sources and databases
- Provides analysis, not just raw information
- Generates structured research reports
- Includes source verification and cross-referencing

Best queries for this tool:
- "Impact of artificial intelligence on healthcare diagnostics"
- "Renewable energy policies in developing countries"
- "Latest research on quantum computing applications"
- "Comprehensive analysis of blockchain technology adoption"

Note: This tool is resource-intensive. Use web_search for quick facts or simple questions."""
    input_schema = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The query to perform deep research on.",
            },
        },
        "required": ["query"],
    }

    def __init__(self):
        super().__init__()
        self.answer: str = ""

    @property
    def should_stop(self):
        return self.answer != ""

    def reset(self):
        self.answer = ""

    def run_impl(
        self,
        tool_input: dict[str, Any],
        message_history: Optional[MessageHistory] = None,
    ) -> ToolImplOutput:
        print(f"Performing deep research on {tool_input['query']}")
        agent = ReasoningAgent(
            question=tool_input["query"], report_type=ReportType.BASIC
        )
        result = get_event_loop().run_until_complete(
            agent.run(on_token=on_token, is_stream=True)
        )

        assert result, "Model returned empty answer"
        self.answer = result
        return ToolImplOutput(result, "Task completed")

    def get_tool_start_message(self, tool_input: dict[str, Any]) -> str:
        return f"Performing deep research on {tool_input['query']}"
