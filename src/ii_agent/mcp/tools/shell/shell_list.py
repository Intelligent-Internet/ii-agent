from ii_agent.mcp.tools.shell.terminal_manager import BaseShellManager
from ii_agent.mcp.tools.shell import ShellView

class ShellList:
    name = "BashList"
    description = "List all available bash sessions"

    def __init__(self, BaseShellManager: BaseShellManager) -> None:
        self.shell_manager = BaseShellManager

    def run_impl(
        self,
    ):
        all_current_sessions = self.shell_manager.get_all_sessions()
        
        result = f"Available sessions: {all_current_sessions}\n"
        result += f"For the detailed output of a session, use `{ShellView.name}`."

        return result