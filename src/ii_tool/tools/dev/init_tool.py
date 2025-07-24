import os
import subprocess

from typing import Any
from ii_tool.core.config import FullStackDevConfig
from ii_tool.tools.base import BaseTool, ToolResult
from ii_tool.core.workspace import WorkspaceManager


# Name
NAME = "fullstack_project_init"
DISPLAY_NAME = "Initialize application template"

# Description
DESCRIPTION = """\
This tool initializes a fullstack web application environment by using the development template. It constructs a `frontend` and `backend` template directory inside the project path, and installs all necessary packages.

<backend_rules>
- Technology stack: Python, FastAPI, SQLite
- Write comprehensive tests for all endpoints and business logic
  * Cover all scenarios for each endpoint, including edge cases
  * All tests must be passed before proceeding
</backend_rules>

<frontend_rules>
- Technology stack: JavaScript, React, CSS Tailwind, Vite, bun
- Use CSS Tailwind for modern beautiful UI. In latest version:
  * No need of `postcss.config.js`, `tailwind.config.js`  
  * Add an `@import "tailwindcss";` to your CSS file that imports Tailwind CSS
  * Make sure your compiled CSS is included in the `<head>` then start using Tailwind's utility classes to style your content
- Do not fallback to raw HTML - the frontend must be developed and built entirely using React
</frontend_rules>

<deployment_rules>
- Default ports:
  * Backend: `8080`
  * Frontend: `3030`
  * If unavailable, increment by +1
</deployment_rules>

<debug_rules>
- Use Python `requests` to call the backend endpoint
- View the shell output to debug errors
- Search the internet about the error to find the solution if needed
</debug_rules>
"""

# Input schema
INPUT_SCHEMA = {
        "type": "object",
        "properties": {
            "project_name": {
                "type": "string",
                "description": "A name for your project (lowercase, no spaces, use hyphens - if needed). Example: `my-app`, `todo-app`",
            },
        },
        "required": ["project_name"],
    }

class FullStackInitTool(BaseTool):
    name = NAME
    display_name = DISPLAY_NAME
    description = DESCRIPTION
    input_schema = INPUT_SCHEMA
    read_only = False

    def __init__(
        self,
        workspace_manager: WorkspaceManager,
        settings: FullStackDevConfig,
    ) -> None:
        super().__init__()
        self.workspace_manager = workspace_manager
        self.settings = settings

    async def execute(
        self,
        tool_input: dict[str, Any],
    ) -> ToolResult:
        project_name = tool_input["project_name"]
        
        # Create the frontend directory if it doesn't exist
        workspace_dir = str(self.workspace_manager.get_workspace_path())
        project_dir = f"{workspace_dir}/{project_name}"
        frontend_dir = f"{project_dir}/frontend"
        backend_dir = f"{project_dir}/backend"
        
        os.makedirs(project_dir, exist_ok=True)

        print("Creating project directory: ", project_dir)

        template_path = self.settings.template_path.rstrip("/")

        get_template_command = f"cp -r {template_path}/* {project_dir}"
        subprocess.run(get_template_command, shell=True)
        
        print("Copy template done, see the project directory: ", project_dir)

        # Install dependencies
        # frontend
        frontend_install_command = f"bun install"
        subprocess.run(frontend_install_command, shell=True, cwd=frontend_dir)
        
        frontend_add_command = "bun add axios lucide-react react-router-dom"
        subprocess.run(frontend_add_command, shell=True, cwd=frontend_dir)

        # backend
        backend_install_command = "pip install -r requirements.txt"
        subprocess.run(backend_install_command, shell=True, cwd=backend_dir)

        print("Installed dependencies")

        output_message = f"""Successfully initialized codebase:
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

You don't need to re-install the dependencies above, they are already installed"""

        return ToolResult(llm_content=output_message, user_display_content="Successfully initialized fullstack web application")

    async def execute_mcp_wrapper(
        self,
        project_name: str,
    ):
        return await self._mcp_wrapper(
            tool_input={
                "project_name": project_name,
            }
        )