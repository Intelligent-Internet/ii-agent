from ii_tool.tools.base import BaseTool
from ii_tool.core.workspace import WorkspaceManager


class BaseFileSystemTool(BaseTool):
    def __init__(self, workspace_manager: WorkspaceManager):
        self.workspace_manager = workspace_manager