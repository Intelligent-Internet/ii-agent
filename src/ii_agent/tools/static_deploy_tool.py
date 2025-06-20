from typing import Any, Optional
from pathlib import Path
import os

from ii_agent.tools.base import (
    ToolImplOutput,
    LLMTool,
)
from ii_agent.llm.message_history import MessageHistory
from ii_agent.utils import WorkspaceManager


class StaticDeployTool(LLMTool):
    """Tool for managing static file deployments"""

    name = "static_deploy"
    description = "Get the public URL for static files in the workspace"

    input_schema = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Path to the static file (relative to workspace)",
            }
        },
        "required": ["file_path"],
    }

    def __init__(self, workspace_manager: WorkspaceManager):
        super().__init__()
        self.workspace_manager = workspace_manager
        # TODO: this is a hack to get the base URL for the static files
        # TODO: we should use a proper URL for the static files
        default_base_url = f"file://{workspace_manager.root.parent.parent.absolute()}"
        self.base_url = os.getenv("STATIC_FILE_BASE_URL", default_base_url)

    async def run_impl(
        self,
        tool_input: dict[str, Any],
        message_history: Optional[MessageHistory] = None,
    ) -> ToolImplOutput:
        file_path = tool_input["file_path"]
        ws_path = self.workspace_manager.workspace_path(Path(file_path))

        # Validate path
        if not ws_path.exists():
            return ToolImplOutput(
                f"Path does not exist: {file_path}",
                f"Path does not exist: {file_path}",
            )

        if not ws_path.is_file():
            return ToolImplOutput(
                f"Path is not a file: {file_path}",
                f"Path is not a file: {file_path}",
            )

        # Get the UUID from the workspace path (it's the last directory in the path)
        connection_uuid = self.workspace_manager.root.name

        # Get the relative path from workspace root
        rel_path = ws_path.relative_to(self.workspace_manager.root)

        # Construct the public URL using the base URL and connection UUID
        public_url = f"{self.base_url}/workspace/{connection_uuid}/{rel_path}"

        return ToolImplOutput(
            public_url,
            f"Static file available at: {public_url}",
        )
