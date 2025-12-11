from typing import Dict
from ii_tool.interfaces.sandbox import SandboxInterface
from ii_tool.core.workspace import WorkspaceManager
from ii_tool.tools.agent.message_user import MessageUserTool
from ii_tool.tools.dev.database import GetDatabaseConnection

from ii_tool.tools.shell import (
    ShellInit,
    ShellRunCommand,
    ShellView,
    ShellStopCommand,
    ShellList,
    TmuxSessionManager,
    ShellWriteToProcessTool,
)

# from ii_tool.tools.codex import CodexExecuteTool  # Now using MCP stdio versions
from ii_tool.tools.file_system import (
    ASTGrepTool,
    GrepTool,
    FileReadTool,
    FileWriteTool,
    FileEditTool,
    ApplyPatchTool,
    StrReplaceEditorTool,
)
from ii_tool.tools.productivity import TodoReadTool, TodoWriteTool
from ii_tool.tools.media import (
    VideoGenerateTool,
    ImageGenerateTool,
)
from ii_tool.tools.dev import FullStackInitTool, RegisterPort, SaveCheckpointTool
from ii_tool.tools.web import (
    WebSearchTool,
    WebVisitTool,
    ImageSearchTool,
    WebVisitCompressTool,
    ReadRemoteImageTool,
    WebBatchSearchTool,
)
from ii_tool.tools.slide_system.slide_edit_tool import SlideEditTool
from ii_tool.tools.slide_system.slide_write_tool import SlideWriteTool
from ii_tool.tools.slide_system.slide_patch import SlideApplyPatchTool

# from ii_tool.tools.codex import CodexExecuteTool  # Now using MCP stdio versions
from ii_tool.tools.browser import (
    BrowserClickTool,
    BrowserWaitTool,
    BrowserViewTool,
    BrowserScrollDownTool,
    BrowserScrollUpTool,
    BrowserSwitchTabTool,
    BrowserOpenNewTabTool,
    BrowserGetSelectOptionsTool,
    BrowserSelectDropdownOptionTool,
    BrowserNavigationTool,
    BrowserRestartTool,
    BrowserEnterTextTool,
    BrowserPressKeyTool,
    BrowserDragTool,
    BrowserEnterMultipleTextsTool,
)
from ii_tool.browser.browser import Browser
from ii_tool.tools.sbll_knowledge_tool import SBLLKnowledgeTool


def get_common_tools(
    sandbox: SandboxInterface,
):
    tools = [
        # Sandbox tools
        RegisterPort(sandbox=sandbox),
        MessageUserTool(),
        SBLLKnowledgeTool(),
    ]

    return tools


def get_sandbox_tools(workspace_path: str, credential: Dict):
    terminal_manager = TmuxSessionManager()
    workspace_manager = WorkspaceManager(workspace_path)
    browser = Browser()

    tools = [
        # Shell tools
        ShellInit(terminal_manager, workspace_manager),
        ShellRunCommand(terminal_manager, workspace_manager),
        ShellView(terminal_manager),
        ShellStopCommand(terminal_manager),
        ShellList(terminal_manager),
        ShellWriteToProcessTool(terminal_manager),
        # File system tools
        FileReadTool(workspace_manager),
        FileWriteTool(workspace_manager),
        FileEditTool(workspace_manager),
        ApplyPatchTool(workspace_manager),
        StrReplaceEditorTool(workspace_manager),
        ASTGrepTool(workspace_manager),
        GrepTool(workspace_manager),
        FullStackInitTool(workspace_manager),
        SaveCheckpointTool(workspace_manager),
        # Media tools
        ImageGenerateTool(workspace_manager, credential),
        VideoGenerateTool(workspace_manager, credential),
        # Web tools
        WebSearchTool(credential),
        WebVisitTool(credential),
        WebVisitCompressTool(credential),
        ImageSearchTool(credential),
        ReadRemoteImageTool(),
        WebBatchSearchTool(credential),
        # Database tools
        GetDatabaseConnection(credential),
        # Todo tools
        TodoReadTool(),
        TodoWriteTool(),
        # Slide tools
        SlideWriteTool(workspace_manager),
        SlideEditTool(workspace_manager),
        SlideApplyPatchTool(workspace_manager),
        # Browser tools
        BrowserClickTool(browser),
        BrowserWaitTool(browser),
        BrowserViewTool(browser),
        BrowserScrollDownTool(browser),
        BrowserScrollUpTool(browser),
        BrowserSwitchTabTool(browser),
        BrowserOpenNewTabTool(browser),
        BrowserGetSelectOptionsTool(browser),
        BrowserSelectDropdownOptionTool(browser),
        BrowserNavigationTool(browser),
        BrowserRestartTool(browser),
        BrowserEnterTextTool(browser),
        BrowserPressKeyTool(browser),
        BrowserDragTool(browser),
        BrowserEnterMultipleTextsTool(browser),
    ]

    return tools
