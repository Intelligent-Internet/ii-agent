from ii_agent.prompts.system_prompt import SystemPromptBuilder
from ii_agent.tools.clients.terminal_client import TerminalClient
from ii_agent.utils.web_template_processor.base_processor import BaseProcessor
from ii_agent.utils.web_template_processor.web_processor_registry import (
    WebProcessorRegistry,
)
from ii_agent.utils.workspace_manager import WorkspaceManager


def get_react_fastapi_project_init_message(project_name: str) -> str:
    return f"""Successfully initialized codebase:
```
{project_name}
├── backend/
│   ├── README.md
│   ├── requirements.txt
│   └── src/
│       ├── __init__.py
│       ├── main.py
│       └── tests/
│           └── __init__.py
└── frontend/
    ├── README.md
    ├── eslint.config.js
    ├── index.html
    ├── package.json
    ├── public/
    │   └── _redirects
    ├── src/
    │   ├── App.jsx
    │   ├── components/
    │   ├── context/
    │   ├── index.css
    │   ├── lib/
    │   ├── main.jsx
    │   ├── pages/
    │   └── services/
    └── vite.config.js
```

Installed dependencies:
- Frontend:
  * `bun install`
  * `bun install tailwindcss @tailwindcss/vite`
  * `bun add axios lucide-react react-router-dom`
- Backend:
  * `pip install -r requirements.txt`
  * Contents of `requirements.txt`:
```
fastapi
uvicorn
sqlalchemy
python-dotenv
pydantic
pydantic-settings
pytest
pytest-asyncio
httpx
openai
bcrypt
python-jose[cryptography]
python-multipart
cryptography
requests
```
<service_deployment_rules>
- Default ports:
  * Backend: `8080`
  * Frontend: `3030`
  * If unavailable, increment by +1
- After local deployment, use the `register_deployment` tool to obtain the public URL (for both backend and frontend)
- Use the backend's public URL in your frontend code for API access
</service_deployment_rules>
<backend_rules>
- Technology stack: Python, FastAPI, SQLite
- Write comprehensive tests for all endpoints and business logic
  * Cover all scenarios for each endpoint, including edge cases
  * All tests must be passed before proceeding
</backend_rules>

<frontend_rules>
- Technology stack: JavaScript, React, CSS Tailwind, Vite, bun
- Use CSS Tailwind for beautiful UI. In latest version:
  * No need of `postcss.config.js`, `tailwind.config.js`  
  * Add an `@import "tailwindcss";` to your CSS file that imports Tailwind CSS
  * Make sure your compiled CSS is included in the `<head>` then start using Tailwind's utility classes to style your content
- Do not fallback to raw HTML - the frontend must be developed and built entirely using React
</frontend_rules>
<debug_rules>
- Use Python `requests` to call the backend endpoint
- Use the `browser` tool to visit the public URL to debug the frontend
- View the shell output to debug errors
- Search the internet about the error to find the solution if needed
</debug_rules>

You don't need to re-install the dependencies above, they are already installed"""


@WebProcessorRegistry.register("react-tailwind-python")
class ReactTailwindPythonProcessor(BaseProcessor):
    template_name = "react-tailwind-python"

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
        self.project_rule = get_react_fastapi_project_init_message(project_name)

    def install_dependencies(self):
        install_result = self.terminal_client.shell_exec(
            self.sandbox_settings.system_shell,
            f"cd {self.project_name}/frontend && bun install",
            exec_dir=str(self.workspace_manager.root_path()),
            timeout=999999,  # Quick fix: No Timeout
        )
        if not install_result.success:
            raise Exception(
                f"Failed to install frontend dependencies: {install_result.output}"
            )

        install_result = self.terminal_client.shell_exec(
            self.sandbox_settings.system_shell,
            f"cd {self.project_name}/backend && pip install -r requirements.txt",
            exec_dir=str(self.workspace_manager.root_path()),
            timeout=999999,  # Quick fix: No Timeout
        )
        if not install_result.success:
            raise Exception(
                f"Failed to install backend dependencies: {install_result.output}"
            )

    def get_processor_message(self) -> str:
        return self.project_rule
