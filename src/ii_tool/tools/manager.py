from ii_tool.core.workspace import WorkspaceManager
from ii_tool.core.config import ImageSearchConfig, WebSearchConfig, WebVisitConfig, VideoGenerateConfig
from ii_tool.tools.shell import ShellInit, ShellRunCommand, ShellView, ShellKill, ShellStopCommand, ShellList, TmuxWindowManager
from ii_tool.tools.file_system import GlobTool, GrepTool, LSTool, FileReadTool, FileWriteTool, FileEditTool, MultiEditTool
from ii_tool.tools.productivity import TodoReadTool, TodoWriteTool
from ii_tool.tools.web import WebSearchTool, WebVisitTool, ImageSearchTool
from ii_tool.tools.media import VideoGenerateFromTextTool, VideoGenerateFromImageTool, LongVideoGenerateFromTextTool, LongVideoGenerateFromImageTool


def get_default_tools(
    workspace_manager: WorkspaceManager,
    terminal_manager: TmuxWindowManager,
    web_search_config: WebSearchConfig,
    web_visit_config: WebVisitConfig,
    image_search_config: ImageSearchConfig,
    video_generate_config: VideoGenerateConfig,
):
    """
    Get the default tools for the workspace manager and terminal manager.
    """
    
    shell_tools = [
        ShellInit(terminal_manager, workspace_manager),
        ShellRunCommand(terminal_manager),
        ShellView(terminal_manager),
        ShellKill(terminal_manager),
        ShellStopCommand(terminal_manager),
        ShellList(terminal_manager),
    ]

    file_system_tools = [
        GlobTool(workspace_manager),
        GrepTool(workspace_manager),
        LSTool(workspace_manager),
        FileReadTool(workspace_manager),
        FileWriteTool(workspace_manager),
        FileEditTool(workspace_manager),
        MultiEditTool(workspace_manager),
    ]

    productivity_tools = [
        TodoReadTool(),
        TodoWriteTool(),
    ]

    web_tools = [
        ImageSearchTool(settings=image_search_config),
        WebSearchTool(settings=web_search_config),
        WebVisitTool(settings=web_visit_config),
    ]

    media_tools = [
        VideoGenerateFromTextTool(workspace_manager, video_generate_config),
        VideoGenerateFromImageTool(workspace_manager, video_generate_config),
        LongVideoGenerateFromTextTool(workspace_manager, video_generate_config),
        LongVideoGenerateFromImageTool(workspace_manager, video_generate_config),
    ]

    tools = shell_tools + file_system_tools + productivity_tools + web_tools + media_tools

    return tools