from abc import ABC, abstractmethod
from typing_extensions import final
from ii_tool.tools.shell.terminal_manager import BaseShellManager
from ii_tool.tools.utils import get_project_root


class BaseProcessor(ABC):
    project_rule: str
    template_name: str
    bash_session: str

    def __init__(
        self,
        project_dir: str,
        terminal_client: BaseShellManager,
        bash_session: str,
    ):
        self.project_dir = project_dir
        self.terminal_client = terminal_client
        self.bash_session = bash_session

    @abstractmethod
    def install_dependencies(self):
        raise NotImplementedError("install_dependencies method not implemented")

    @final
    def copy_project_template(self):
        copy_result = self.terminal_client.run_command(
            self.bash_session,
            f"cp -rf {get_project_root()}/.templates/{self.template_name}/* . && echo 'Project template copied successfully'",
            run_dir=self.project_dir,
            timeout=999999,
            wait_for_output=True,
        )
        if (
            copy_result is None
            or "Project template copied successfully" not in copy_result.split("\n")[-2]
        ):
            raise Exception(f"Failed to copy project template: {copy_result}")

    @final
    def start_up_project(self):
        try:
            self.copy_project_template()
            self.install_dependencies()
        except Exception as e:
            raise Exception(f"Failed to start up project: {e}")

    @final
    def get_project_rule(self) -> str:
        if self.project_rule is None:
            raise Exception("Project rule is not set")
        return self.project_rule
