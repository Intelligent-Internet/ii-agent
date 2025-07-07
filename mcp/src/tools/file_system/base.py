from src.tools.base import BaseTool
from src.core.workspace import WorkspaceManager


class BaseFileSystemTool(BaseTool):
    def __init__(self, workspace_manager: WorkspaceManager):
        self.workspace_manager = workspace_manager