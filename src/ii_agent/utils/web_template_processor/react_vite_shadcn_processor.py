from ii_agent.prompts.system_prompt import SystemPromptBuilder
from ii_agent.tools.clients.terminal_client import TerminalClient
from ii_agent.utils.web_template_processor.base_processor import BaseProcessor
from ii_agent.utils.workspace_manager import WorkspaceManager
from ii_agent.utils.web_template_processor.web_processor_registry import (
    WebProcessorRegistry,
)


def vite_react_deployment_rule(project_name: str) -> str:
    return f"""
Project directory `{project_name}` created successfully. Application code is in `{project_name}/src`. File tree:
```
 {project_name}/
│   ├── .gitignore              # Git ignore file
│   ├── biome.json              # Biome linter/formatter configuration
│   ├── bun.lock               # Lock file for dependencies
│   ├── components.json         # shadcn/ui configuration
│   ├── index.html              # HTML entry point
│   ├── netlify.toml            # ignore for now
│   ├── package.json            # Project dependencies and scripts
│   ├── postcss.config.js       # PostCSS configuration
│   ├── public/                 # Static assets directory
│       ├── _redirects          # ignore for now
│   ├── README.md               # Project documentation
│   ├── src/                    # Source code directory
│   │   ├── App.tsx             # Main App component
│   │   ├── index.css           # Global styles
│   │   ├── lib/                # Utility functions and libraries
│   │       └── utils.ts        # Utility functions
│   │   ├── components/         # Components directory
│   │   │   └── ui/             # shadcn/ui components
│   │   │       └── button.tsx  # Button component
│   │   ├── main.tsx            # Entry point
│   │   └── vite-env.d.ts       # Vite TypeScript declarations
│   ├── tailwind.config.js      # Tailwind CSS configuration
│   ├── tsconfig.json           # TypeScript configuration
    └── vite.config.ts          # Vite bundler configuration
```
IMPORTANT NOTE: This project is built with TypeScript(tsx) and Vite + React.

Add components with `cd {project_name} && bunx shadcn@latest add -y -o`. Import components with `@/` alias. Note, 'toast' is deprecated, use 'sonner' instead. Before editing, run `cd {project_name} && bun install` to install dependencies. Run `cd {project_name} && bun run dev` to start the dev server ASAP to catch any runtime errors. Remember that all terminal commands must be run from the project directory. 
Use Chart.js for charts. Moveable for Draggable, Resizable, Scalable, Rotatable, Warpable, Pinchable, Groupable, Snappable components.
Use AOS for scroll animations.
Use and install Framer Motion, Anime.js, and React Three Fiber for advance animations.
If you are unsure how to use a library, use search tool to find the documentation.
"""


@WebProcessorRegistry.register("react-vite-shadcn")
class ReactViteShadcnProcessor(BaseProcessor):
    template_name = "react-vite-shadcn"

    def __init__(
        self,
        workspace_manager: WorkspaceManager,
        terminal_client: TerminalClient,
        system_prompt_builder: SystemPromptBuilder,
        project_name: str,
    ):
        super().__init__(
            workspace_manager, terminal_client, system_prompt_builder, project_name
        )
        self.project_rule = vite_react_deployment_rule(project_name)

    def install_dependencies(self):
        install_result = self.terminal_client.shell_exec(
            self.sandbox_settings.system_shell,
            f"cd {self.project_name} && bun install",
            exec_dir=str(self.workspace_manager.root_path()),
            timeout=999999,  # Quick fix: No Timeout
        )
        if not install_result.success:
            raise Exception(f"Failed to install dependencies: {install_result.output}")

    def get_processor_message(self) -> str:
        return self.project_rule
