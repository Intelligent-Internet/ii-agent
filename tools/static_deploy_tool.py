from typing import Any, Optional
from pathlib import Path
from utils.common import DialogMessages, LLMTool, ToolImplOutput
from utils.workspace_manager import WorkspaceManager


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

    def __init__(self, workspace_manager: WorkspaceManager, file_server_port: int):
        super().__init__()
        self.workspace_manager = workspace_manager
        self.file_server_port = file_server_port

    def run_impl(
        self,
        tool_input: dict[str, Any],
        dialog_messages: Optional[DialogMessages] = None,
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

        # Get the relative path from workspace root
        rel_path = ws_path.relative_to(self.workspace_manager.root)

        # Construct the public URL using the file server port
        public_url = f"http://localhost:{self.file_server_port}/{rel_path}"

        # return {"url": public_url, "message": f"Static file available at: {public_url}"}
        return ToolImplOutput(
            public_url,
            f"Static file available at: {public_url}",
        )
