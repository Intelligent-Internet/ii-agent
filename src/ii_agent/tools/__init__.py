from ii_agent.tools.visit_webpage_tool import VisitWebpageTool
from ii_agent.tools.str_replace_tool import StrReplaceEditorTool
from ii_agent.tools.sequential_thinking_tool import SequentialThinkingTool
from ii_agent.tools.bash_tool import BashTool
from ii_agent.tools.tool_manager import get_system_tools, AgentToolManager

# Tools that need input truncation (ToolCall)
TOOLS_NEED_INPUT_TRUNCATION = {
    SequentialThinkingTool.name: ["thought"],
    StrReplaceEditorTool.name: ["file_text", "old_str", "new_str"],
    BashTool.name: ["command"],
}

# Tools that need output truncation with file save (ToolFormattedResult)
TOOLS_NEED_OUTPUT_FILE_SAVE = {VisitWebpageTool.name}

__all__ = [
    "AgentToolManager",
    "TOOLS_NEED_INPUT_TRUNCATION",
    "TOOLS_NEED_OUTPUT_FILE_SAVE",
    "get_system_tools",
]
