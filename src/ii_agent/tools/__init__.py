from ii_agent.tools.web_search import DuckDuckGoSearchTool
from ii_agent.tools.visit_webpage import VisitWebpageTool
from ii_agent.tools.tavily_web_search import TavilySearchTool
from ii_agent.tools.tavily_visit_webpage import TavilyVisitWebpageTool
from ii_agent.tools.str_replace_tool import StrReplaceEditorTool
from ii_agent.tools.static_deploy_tool import StaticDeployTool
from ii_agent.tools.sequential_thinking_tool import SequentialThinkingTool
from ii_agent.tools.file_write_tool import FileWriteTool
from ii_agent.tools.complete_tool import CompleteTool
from ii_agent.tools.bash_tool import create_bash_tool, create_docker_bash_tool, BashTool

# Tools that need input truncation (ToolCall)
TOOLS_NEED_INPUT_TRUNCATION = {
    SequentialThinkingTool.name: ["thought"],
    StrReplaceEditorTool.name: ["file_text", "old_str", "new_str"],
    BashTool.name: ["command"],
}

# Tools that need output truncation (ToolFormattedResult)
TOOLS_NEED_OUTPUT_TRUNCATION = {TavilyVisitWebpageTool.name}

__all__ = [
    "DuckDuckGoSearchTool",
    "VisitWebpageTool",
    "TavilySearchTool",
    "TavilyVisitWebpageTool",
    "StrReplaceEditorTool",
    "StaticDeployTool",
    "SequentialThinkingTool",
    "FileWriteTool",
    "CompleteTool",
    "BashTool",
    "create_bash_tool",
    "create_docker_bash_tool",
    "TOOLS_NEED_INPUT_TRUNCATION",
    "TOOLS_NEED_OUTPUT_TRUNCATION",
]
