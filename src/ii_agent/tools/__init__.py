from ii_agent.tools.web_search import DuckDuckGoSearchTool
from ii_agent.tools.visit_webpage import VisitWebpageTool
from ii_agent.tools.tavily_web_search import TavilySearchTool
from ii_agent.tools.tavily_visit_webpage import TavilyVisitWebpageTool
from ii_agent.tools.str_replace_tool import StrReplaceEditorTool
from ii_agent.tools.static_deploy_tool import StaticDeployTool
from ii_agent.tools.sequential_thinking_tool import SequentialThinkingTool
from ii_agent.tools.complete_tool import CompleteTool
from ii_agent.tools.bash_tool import create_bash_tool, create_docker_bash_tool, BashTool
from ii_agent.tools.visualizer import DisplayLocalImageTool
from ii_agent.tools.text_inspector_tool import TextInspectorTool

# Tools that need input truncation (ToolCall)
TOOLS_NEED_INPUT_TRUNCATION = {
    SequentialThinkingTool.name: ["thought"],
    StrReplaceEditorTool.name: ["file_text", "old_str", "new_str"],
    BashTool.name: ["command"],
}

# Tools that need output truncation with file save (ToolFormattedResult)
TOOLS_NEED_OUTPUT_FILE_SAVE = {TavilyVisitWebpageTool.name}

__all__ = [
    "DuckDuckGoSearchTool",
    "VisitWebpageTool",
    "TavilySearchTool",
    "TavilyVisitWebpageTool",
    "StrReplaceEditorTool",
    "StaticDeployTool",
    "SequentialThinkingTool",
    "CompleteTool",
    "BashTool",
    "create_bash_tool",
    "create_docker_bash_tool",
    "TOOLS_NEED_INPUT_TRUNCATION",
    "TOOLS_NEED_OUTPUT_FILE_SAVE",
    "DisplayLocalImageTool",
    "TextInspectorTool",
]
