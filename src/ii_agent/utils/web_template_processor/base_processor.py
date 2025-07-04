from abc import ABC, abstractmethod
from typing_extensions import final
from ii_agent.prompts.system_prompt import SystemPromptBuilder
from ii_agent.sandbox.config import SandboxSettings
from ii_agent.tools.clients.terminal_client import TerminalClient
from ii_agent.utils.workspace_manager import WorkspaceManager


class BaseProcessor(ABC):
    project_rule: str
    template_name: str
    project_name: str

    def __init__(
        self,
        workspace_manager: WorkspaceManager,
        terminal_client: TerminalClient,
        system_prompt_builder: SystemPromptBuilder,
        project_name: str,
    ):
        self.workspace_manager = workspace_manager
        self.terminal_client = terminal_client
        self.system_prompt_builder = system_prompt_builder
        self.project_name = project_name
        self.sandbox_settings = SandboxSettings()

    @abstractmethod
    def install_dependencies(self):
        raise NotImplementedError("install_dependencies method not implemented")

    @abstractmethod
    def get_processor_message(self) -> str:
        raise NotImplementedError("get_processor_message method not implemented")

    @final
    def copy_project_template(self):
        copy_result = self.terminal_client.shell_exec(
            self.sandbox_settings.system_shell,
            f"cp -rf /app/templates/{self.template_name} {self.project_name}",  # TODO: put  /app/template in the system shell
            exec_dir=str(self.workspace_manager.root_path()),
            timeout=999999,  # Quick fix: No Timeout
        )
        if not copy_result.success:
            raise Exception(f"Failed to copy project template: {copy_result.output}")

    @final
    def start_up_project(self):
        try:
            self.copy_project_template()
            self.install_dependencies()
            self.system_prompt_builder.update_web_dev_rules(self.get_project_rule())
        except Exception as e:
            raise Exception(f"Failed to start up project: {e}")

    @final
    def get_project_rule(self) -> str:
        if self.project_rule is None:
            raise Exception("Project rule is not set")
        return self.project_rule
