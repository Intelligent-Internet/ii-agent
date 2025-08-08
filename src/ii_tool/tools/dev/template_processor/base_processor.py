from abc import ABC, abstractmethod
import subprocess
from typing_extensions import final
from ii_tool.tools.utils import get_project_root


class BaseProcessor(ABC):
    project_rule: str
    template_name: str

    def __init__(
        self,
        project_dir: str,
    ):
        self.project_dir = project_dir

    @abstractmethod
    def install_dependencies(self):
        raise NotImplementedError("install_dependencies method not implemented")

    @final
    def copy_project_template(self):
        out = subprocess.run(
            f"cp -rf {get_project_root()}/.templates/{self.template_name}/* .",
            shell=True,
            cwd=self.project_dir,
            capture_output=True,
        )
        if out.returncode != 0:
            raise Exception(
                f"Failed to copy project template: {out.stderr.decode('utf-8')}. Please initialize the project manually"
            )

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
