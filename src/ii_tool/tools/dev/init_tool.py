import os

from typing import Any
from ii_tool.tools.dev.template_processor.registry import WebProcessorRegistry
from ii_tool.tools.shell.terminal_manager import BaseShellManager
from ii_tool.core.config import FullStackDevConfig
from ii_tool.tools.base import BaseTool, ToolResult
from ii_tool.core.workspace import WorkspaceManager


# Name
NAME = "fullstack_project_init"
DISPLAY_NAME = "Initialize application template"

# Description
DESCRIPTION = """\
This tool initializes a fullstack web application environment by using the development template.

<backend_rules>
- Write comprehensive tests for all endpoints and business logic
  * Cover all scenarios for each endpoint, including edge cases
  * All tests must be passed before proceeding
</backend_rules>

<frontend_rules>
- Technology stack: JavaScript, React, CSS Tailwind, Vite, bun
- Use CSS Tailwind for modern beautiful UI. In latest version:
  * No need of `postcss.config.js`, `tailwind.config.js`  
  * Add an `@import "tailwindcss";` to your CSS file that imports Tailwind CSS
  * Make sure your compiled CSS is included in the `<head>` then start using Tailwind's utility classes to style your content
- Do not fallback to raw HTML - the frontend must be developed and built entirely using React
</frontend_rules>

<deployment_rules>
- Default ports:
  * Backend: `8080`
  * Frontend: `3030`
  * If unavailable, increment by +1
</deployment_rules>

<debug_rules>
- Test backend endpoint by calling api with the suitable stack
- View the shell output to debug errors
- Search the internet about the error to find the solution if needed
</debug_rules>
"""

# Input schema
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "project_name": {
            "type": "string",
            "description": "A name for your project (lowercase, no spaces, use hyphens - if needed). Example: `my-app`, `todo-app`",
        },
        "framework": {
            "type": "string",
            "description": "The framework to use for the project",
            "enum": ["nextjs-shadcn", "react-tailwind-python"],
        },
    },
    "required": ["project_name", "framework"],
}

BASH_SESSION = "fullstack_init_system"


class FullStackInitTool(BaseTool):
    name = NAME
    display_name = DISPLAY_NAME
    description = DESCRIPTION
    input_schema = INPUT_SCHEMA
    read_only = False

    def __init__(
        self,
        workspace_manager: WorkspaceManager,
        terminal_manager: BaseShellManager,
        settings: FullStackDevConfig,
    ) -> None:
        super().__init__()
        self.workspace_manager = workspace_manager
        self.terminal_manager = terminal_manager
        self.settings = settings

    async def execute(
        self,
        tool_input: dict[str, Any],
    ) -> ToolResult:
        project_name = tool_input["project_name"]
        framework = tool_input["framework"]
        project_dir = os.path.join(
            self.workspace_manager.get_workspace_path(), project_name
        )
        if os.path.exists(project_dir):
            return ToolResult(
                llm_content=f"Project directory {project_dir} already exists, please choose a different project name",
                user_display_content="Project directory already exists, please choose a different project name",
                is_error=True,
            )

        os.makedirs(project_dir, exist_ok=True)
        init_session_id = BASH_SESSION + "_" + project_name
        self.terminal_manager.create_session(init_session_id, str(project_dir))

        processor = WebProcessorRegistry.create(
            framework,
            project_dir,
            self.terminal_manager,
            init_session_id,
        )
        try:
            processor.start_up_project()
        except Exception as e:
            return ToolResult(
                llm_content=f"Failed to start up project: {e}",
                user_display_content="Failed to start up project",
                is_error=True,
            )

        return ToolResult(
            llm_content=processor.get_project_rule(),
            user_display_content="Successfully initialized fullstack web application",
            is_error=False,
        )

    async def execute_mcp_wrapper(
        self,
        project_name: str,
    ):
        return await self._mcp_wrapper(
            tool_input={
                "project_name": project_name,
            }
        )
