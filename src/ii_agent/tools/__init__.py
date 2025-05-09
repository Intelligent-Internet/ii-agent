from ii_agent.tools.web_search_tool import WebSearchTool
from ii_agent.tools.visit_webpage_tool import VisitWebpageTool
from ii_agent.tools.str_replace_tool import StrReplaceEditorTool
from ii_agent.tools.static_deploy_tool import StaticDeployTool
from ii_agent.tools.sequential_thinking_tool import SequentialThinkingTool
from ii_agent.tools.complete_tool import CompleteTool
from ii_agent.tools.bash_tool import create_bash_tool, create_docker_bash_tool, BashTool
from ii_agent.tools.deep_research_tool import DeepResearchTool

# Tools that need input truncation (ToolCall)
TOOLS_NEED_INPUT_TRUNCATION = {
    SequentialThinkingTool.name: ["thought"],
    StrReplaceEditorTool.name: ["file_text", "old_str", "new_str"],
    BashTool.name: ["command"],
}

# Tools that need output truncation with file save (ToolFormattedResult)
TOOLS_NEED_OUTPUT_FILE_SAVE = {VisitWebpageTool.name}

__all__ = [
    "VisitWebpageTool",
    "WebSearchTool",
    "DeepResearchTool",
    "StrReplaceEditorTool",
    "StaticDeployTool",
    "SequentialThinkingTool",
    "CompleteTool",
    "BashTool",
    "create_bash_tool",
    "create_docker_bash_tool",
    "TOOLS_NEED_INPUT_TRUNCATION",
    "TOOLS_NEED_OUTPUT_FILE_SAVE",
]
