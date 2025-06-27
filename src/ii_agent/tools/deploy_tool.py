"""Tool for starting a development server for a project."""

import os
import hashlib
from typing import Any, Optional
from ii_agent.llm.message_history import MessageHistory
from ii_agent.tools.base import LLMTool, ToolImplOutput
from ii_agent.tools.clients.terminal_client import TerminalClient
from ii_agent.utils.workspace_manager import WorkspaceManager


class DeployTool(LLMTool):
    name = "deploy"
    """The model should call this tool when it needs to deploy a project to public internet."""

    description = "You should call this tool when user give you permission to deploy a nextjs without websocket project to public internet. Only use this tool when you can run build command successfully. Do not use this tool for other projects. Send all the required environment variables that is in .env or .env.local file."
    input_schema = {
        "type": "object",
        "properties": {
            "project_path": {
                "type": "string",
                "description": "The full path to the project.",
            },
            "env_vars": {
                "type": "array",
                "description": "The environment variables to deploy the project with. You can deploy to multiple environments. The environment name should be a unique name for the environment.",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "The name of the environment variable. This should be a unique name for the environment variable.",
                        },
                        "value": {
                            "type": "string",
                            "description": "The value of the environment variable. This should be a string.",
                        },
                    },
                    "required": ["name", "value"],
                },
            },
        },
        "required": ["project_path"],
    }

    def __init__(
        self, terminal_client: TerminalClient, workspace_manager: WorkspaceManager
    ):
        super().__init__()
        self.terminal_client = terminal_client
        self.workspace_manager = workspace_manager

    async def run_impl(
        self,
        tool_input: dict[str, Any],
        message_history: Optional[MessageHistory] = None,
    ) -> ToolImplOutput:
        session_id = self.workspace_manager.session_id
        # Hash the UUID to make it smaller (using first 8 characters of SHA256)
        session_id_hash = hashlib.sha256(session_id.encode()).hexdigest()[:8]
        print(f"Deploying project to {tool_input.get('project_path')}")
        project_name = os.path.basename(tool_input.get("project_path"))
        project_id = project_name + "-" + "ii" + "-" + session_id_hash

        link_command = f"vercel link  --yes --project {project_id} --token {os.getenv('VERCEL_TOKEN')}"
        output = self.terminal_client.shell_exec(
            session_id,
            link_command,
            exec_dir=tool_input.get("project_path"),
            timeout=9999,
        )
        if output.success:
            print(f"Linked project {project_id} to {tool_input.get('project_path')}")
        else:
            print(
                f"Failed to link project {project_id} to {tool_input.get('project_path')}"
            )
            return ToolImplOutput(output.output, "Task failed")

        deploy_command = f"vercel --prod --token {os.getenv('VERCEL_TOKEN')} -y"
        if tool_input.get("env_vars") is not None:
            for env_var in tool_input.get("env_vars"):
                deploy_command += f""" --env {env_var["name"]}="{env_var["value"]}" """

        output = self.terminal_client.shell_exec(
            session_id,
            deploy_command,
            exec_dir=tool_input.get("project_path"),
            timeout=9999,
        )
        if output.success:
            ls = self.terminal_client.shell_exec(
                session_id,
                f"Deployment live at https://{project_id}.vercel.app",
                exec_dir=tool_input.get("project_path"),
                timeout=9999,
            )
            return ToolImplOutput(ls.output, "Task completed")
        else:
            return ToolImplOutput(output.output, "Task failed")
