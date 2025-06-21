from typing import Any, Optional
from ii_agent.llm.message_history import MessageHistory
from ii_agent.sandbox.config import SandboxSettings
from ii_agent.tools.base import LLMTool, ToolImplOutput
from ii_agent.tools.clients.terminal_client import TerminalClient
from ii_agent.utils.workspace_manager import WorkspaceManager
from ii_agent.utils import deployment_rule


class ProjectStartUpTool(LLMTool):
    name = "project_start_up"
    description = "Shortcut to create a new web project from a framework template. Each is configured with TypeScript, Biome, and pnpm. Choose the best framework for the project. Do not use this tool if the desired framework is not listed."
    input_schema = {
        "type": "object",
        "properties": {
            "project_name": {
                "type": "string",
                "description": "The name of the project",
            },
            "framework": {
                "type": "string",
                "description": "The framework to use for the project. Choose from: nextjs-shadcn, react-vite-shadcn",
            },
        },
        "required": ["project_name", "framework"],
    }

    supported_frameworks = {
        "nextjs-shadcn": {"description": deployment_rule.next_shadcn_deployment_rule},
        "react-vite-shadcn": {
            "description": deployment_rule.vite_react_deployment_rule,
        },
    }

    def __init__(
        self,
        workspace_manager: WorkspaceManager,
        terminal_client: TerminalClient,
    ) -> None:
        super().__init__()
        self.terminal_client = terminal_client
        self.workspace_manager = workspace_manager
        self.sandbox_settings = SandboxSettings()

    async def run_impl(
        self,
        tool_input: dict[str, Any],
        message_history: Optional[MessageHistory] = None,
    ) -> ToolImplOutput:
        try:
            project_name = tool_input["project_name"]
            framework = tool_input["framework"]

            project_dir = str(self.workspace_manager.relative_path(f"./{project_name}"))
            self.terminal_client.shell_exec(
                self.sandbox_settings.system_shell,
                f"cp -rf /app/templates/{framework} {project_dir}",
                exec_dir=str(self.workspace_manager.root_path()),
                timeout=999999,  # Quick fix: No Timeout
            )

            # Clone the reveal.js repository to the specified path
            install_command = f"cd {project_dir} && pnpm install"
            install_result = self.terminal_client.shell_exec(
                self.sandbox_settings.system_shell,
                install_command,
                exec_dir=str(self.workspace_manager.root_path()),
                timeout=999999,  # Quick fix: No Timeout
            )

            if not install_result.success:
                return ToolImplOutput(
                    f"Failed to install dependencies: {install_result.output}",
                    "Failed to install dependencies",
                    auxiliary_data={"success": False, "error": install_result.output},
                )

            return ToolImplOutput(
                self.supported_frameworks[framework]["description"](project_name),
                "Successfully initialized project",
                auxiliary_data={
                    "success": True,
                    "install_output": install_result.output,
                },
            )

        except Exception as e:
            return ToolImplOutput(
                f"Error initializing project: {str(e)}",
                "Error initializing project",
                auxiliary_data={"success": False, "error": str(e)},
            )
