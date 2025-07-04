from typing import Any, Optional
from ii_agent.llm.message_history import MessageHistory
from ii_agent.prompts.system_prompt import SystemPromptBuilder
from ii_agent.sandbox.config import SandboxSettings
from ii_agent.tools.base import LLMTool, ToolImplOutput
from ii_agent.tools.clients.terminal_client import TerminalClient
from ii_agent.utils.web_template_processor.web_processor_registry import (
    WebProcessorRegistry,
)
from ii_agent.utils.workspace_manager import WorkspaceManager


class FullStackInitTool(LLMTool):
    name = "fullstack_project_init"
    description = "Shortcut to create a new web project from a framework template. Choose the best framework for the full-stack project. Do not use this tool if the desired framework is not listed."

    input_schema = {
        "type": "object",
        "properties": {
            "project_name": {
                "type": "string",
                "description": "A name for your project (lowercase, no spaces, use hyphens - if needed). Example: `my-app`, `todo-app`",
            },
            "framework": {
                "type": "string",
                "description": f"The framework to use for the project. Choose from: {', '.join(WebProcessorRegistry.list_frameworks())}",
            },
        },
        "required": ["project_name", "framework"],
    }

    def __init__(
        self,
        workspace_manager: WorkspaceManager,
        terminal_client: TerminalClient,
        system_prompt_builder: SystemPromptBuilder,
    ) -> None:
        super().__init__()
        self.terminal_client = terminal_client
        self.workspace_manager = workspace_manager
        self.system_prompt_builder = system_prompt_builder
        self.sandbox_settings = SandboxSettings()

    async def run_impl(
        self,
        tool_input: dict[str, Any],
        message_history: Optional[MessageHistory] = None,
    ) -> ToolImplOutput:
        project_name = tool_input["project_name"]
        framework = tool_input["framework"]
        processor = WebProcessorRegistry.create(
            framework,
            self.workspace_manager,
            self.terminal_client,
            self.system_prompt_builder,
            project_name,
        )
        try:
            processor.start_up_project()
        except Exception as e:
            return ToolImplOutput(
                f"Failed to start up project: {e}", "Failed to start up project"
            )

        return ToolImplOutput(
            processor.get_processor_message(),
            "Successfully initialized fullstack web application",
            auxiliary_data={"success": True},
        )
