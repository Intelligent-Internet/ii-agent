from ii_tool.core.workspace import WorkspaceManager
from ii_tool.core.config import (
    ImageSearchConfig,
    WebSearchConfig,
    WebVisitConfig,
    VideoGenerateConfig,
    ImageGenerateConfig,
    FullStackDevConfig,
)
from ii_tool.tools.shell import (
    ShellInit,
    ShellRunCommand,
    ShellView,
    ShellKill,
    ShellStopCommand,
    ShellList,
    TmuxWindowManager,
)
from ii_tool.tools.file_system import (
    GlobTool,
    GrepTool,
    LSTool,
    FileReadTool,
    FileWriteTool,
    FileEditTool,
    MultiEditTool,
    ReadManyFilesTool,
)
from ii_tool.tools.productivity import TodoReadTool, TodoWriteTool
from ii_tool.tools.web import WebSearchTool, WebVisitTool, ImageSearchTool
from ii_tool.tools.media import (
    VideoGenerateFromTextTool,
    VideoGenerateFromImageTool,
    LongVideoGenerateFromTextTool,
    LongVideoGenerateFromImageTool,
    ImageGenerateTool,
)
from ii_tool.tools.dev import FullStackInitTool


def get_default_tools(
    chat_session_id: str,
    workspace_path: str,
    web_search_config: WebSearchConfig,
    web_visit_config: WebVisitConfig,
    fullstack_dev_config: FullStackDevConfig | None = None,
    image_search_config: ImageSearchConfig | None = None,
    video_generate_config: VideoGenerateConfig | None = None,
    image_generate_config: ImageGenerateConfig | None = None,
):
    """
    Get the default tools for the workspace manager and terminal manager.
    """

    terminal_manager = TmuxWindowManager(chat_session_id)
    workspace_manager = WorkspaceManager(workspace_path)

    tools = [
        # Shell tools
        ShellInit(terminal_manager, workspace_manager),
        ShellRunCommand(terminal_manager),
        ShellView(terminal_manager),
        ShellKill(terminal_manager),
        ShellStopCommand(terminal_manager),
        ShellList(terminal_manager),
        # File system tools
        GlobTool(workspace_manager),
        GrepTool(workspace_manager),
        LSTool(workspace_manager),
        FileReadTool(workspace_manager),
        FileWriteTool(workspace_manager),
        FileEditTool(workspace_manager),
        MultiEditTool(workspace_manager),
        ReadManyFilesTool(workspace_manager),
        # Todo tools
        TodoReadTool(),
        TodoWriteTool(),
        # Web tools
        WebSearchTool(settings=web_search_config),
        WebVisitTool(settings=web_visit_config),
    ]

    # Dev tools
    if fullstack_dev_config is not None:
        tools.append(FullStackInitTool(workspace_manager, fullstack_dev_config))

    if image_search_config is not None:
        tools.append(ImageSearchTool(settings=image_search_config))

    if video_generate_config is not None:
        video_generate_tools = [
            VideoGenerateFromTextTool(workspace_manager, video_generate_config),
            VideoGenerateFromImageTool(workspace_manager, video_generate_config),
            LongVideoGenerateFromTextTool(workspace_manager, video_generate_config),
            LongVideoGenerateFromImageTool(workspace_manager, video_generate_config),
        ]
        tools.extend(video_generate_tools)

    if image_generate_config is not None:
        tools.append(ImageGenerateTool(workspace_manager, image_generate_config))

    return tools