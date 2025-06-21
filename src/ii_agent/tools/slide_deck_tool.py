from typing import Any, Optional
from ii_agent.llm.message_history import MessageHistory
from ii_agent.sandbox.config import SandboxSettings
from ii_agent.tools.base import LLMTool, ToolImplOutput
from ii_agent.tools.clients.str_replace_client import StrReplaceClient
from ii_agent.tools.clients.terminal_client import TerminalClient
from ii_agent.utils.workspace_manager import WorkspaceManager


class SlideDeckInitTool(LLMTool):
    name = "slide_deck_init"
    description = "This tool initializes a presentation environment by cloning the reveal.js framework and setting up all necessary dependencies. It creates a presentation directory structure, downloads the reveal.js HTML presentation framework from GitHub, and installs all required npm packages to enable slide deck creation and presentation capabilities."
    input_schema = {
        "type": "object",
        "properties": {},
        "required": [],
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
            # Create the presentation directory if it doesn't exist
            presentation_dir = str(
                self.workspace_manager.relative_path("./presentation")
            )
            self.terminal_client.shell_exec(
                self.sandbox_settings.system_shell,
                f"mkdir -p {presentation_dir}",
                exec_dir=str(self.workspace_manager.root_path()),
                timeout=999999,  # Quick fix: No Timeout
            )

            # Clone the reveal.js repository to the specified path
            clone_command = "git clone https://github.com/Intelligent-Internet/reveal.js.git presentation/reveal.js"
            clone_result = self.terminal_client.shell_exec(
                self.sandbox_settings.system_shell,
                clone_command,
                exec_dir=str(self.workspace_manager.root_path()),
                timeout=999999,  # Quick fix: No Timeout
            )

            if not clone_result.success:
                return ToolImplOutput(
                    f"Failed to clone reveal.js repository: {clone_result.output}",
                    "Failed to clone reveal.js repository",
                    auxiliary_data={"success": False, "error": clone_result.output},
                )

            # Install dependencies
            install_command = "npm install"
            install_result = self.terminal_client.shell_exec(
                self.sandbox_settings.system_shell,
                install_command,
                exec_dir=f"{self.workspace_manager.root_path()}/presentation/reveal.js",
                timeout=999999,  # Quick fix: No Timeout
            )

            if not install_result.success:
                return ToolImplOutput(
                    f"Failed to install dependencies: {install_result.output}",
                    "Failed to install dependencies",
                    auxiliary_data={"success": False, "error": install_result.output},
                )

            return ToolImplOutput(
                f"Successfully initialized slide deck in {self.workspace_manager.relative_path(presentation_dir)}. Repository cloned into `./presentation/reveal.js` and dependencies installed (npm install).",
                "Successfully initialized slide deck",
                auxiliary_data={
                    "success": True,
                    "clone_output": clone_result.output,
                    "install_output": install_result.output,
                },
            )

        except Exception as e:
            return ToolImplOutput(
                f"Error initializing slide deck: {str(e)}",
                "Error initializing slide deck",
                auxiliary_data={"success": False, "error": str(e)},
            )


SLIDE_IFRAME_TEMPLATE = """\
        <section>
            <iframe src="{slide_path}" scrolling="auto" style="width: 100%; height: 100%;"></iframe>
        </section>"""


class SlideDeckCompleteTool(LLMTool):
    name = "slide_deck_complete"

    description = "This tool finalizes a presentation by combining multiple individual slide files into a complete reveal.js presentation. It takes an ordered list of slide file paths and embeds them as iframes into the main index.html file, creating a cohesive slideshow that can be viewed in a web browser. The slides will be displayed in the exact order specified in the slide_paths parameter."
    input_schema = {
        "type": "object",
        "properties": {
            "slide_paths": {
                "type": "array",
                "items": {"type": "string"},
                "description": "The ordered paths of the slides to be combined",
            },
        },
        "required": ["slide_paths"],
    }

    def __init__(
        self, workspace_manager: WorkspaceManager, str_replace_client: StrReplaceClient
    ) -> None:
        super().__init__()
        self.workspace_manager = workspace_manager
        self.str_replace_client = str_replace_client

    async def run_impl(
        self,
        tool_input: dict[str, Any],
        message_history: Optional[MessageHistory] = None,
    ) -> ToolImplOutput:
        slide_paths = tool_input["slide_paths"]
        for slide_path in slide_paths:
            # Normalize path by removing ./ prefix if present
            normalized_path = slide_path.lstrip("./")
            if not normalized_path.startswith("slides/"):
                return ToolImplOutput(
                    f"Error: Slide path '{slide_path}' must be in the slides/ subdirectory (e.g. `./slides/introduction.html`, `./slides/conclusion.html`)",
                    "Invalid slide path",
                    auxiliary_data={
                        "success": False,
                        "error": "Invalid slide path format",
                    },
                )
        slide_iframes = [
            SLIDE_IFRAME_TEMPLATE.format(slide_path=slide_path)
            for slide_path in slide_paths
        ]
        index_path = str(
            self.workspace_manager.relative_path("./presentation/reveal.js/index.html")
        )
        try:
            index_content = self.str_replace_client.read_file(index_path).file_content
        except Exception as e:
            return ToolImplOutput(
                f"Error reading `index.html`: {str(e)}",
                "Error reading `index.html`",
                auxiliary_data={"success": False, "error": str(e)},
            )

        slide_iframes_str = "\n".join(slide_iframes)
        index_content = index_content.replace(
            "<!--PLACEHOLDER SLIDES REPLACE THIS-->", slide_iframes_str
        )
        self.str_replace_client.write_file(index_path, index_content)

        message = f"Successfully combined slides with order {slide_paths} into `presentation/reveal.js/index.html`. If the order is not correct, you can use the `slide_deck_complete` tool again to correct the order. The final presentation is now available in `presentation/reveal.js/index.html`."

        return ToolImplOutput(
            message,
            message,
            auxiliary_data={"success": True, "slide_paths": slide_paths},
        )
