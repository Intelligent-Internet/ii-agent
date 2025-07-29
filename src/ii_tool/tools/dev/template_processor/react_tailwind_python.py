import os
from ii_tool.tools.dev.template_processor.base_processor import BaseProcessor
from ii_tool.tools.dev.template_processor.registry import WebProcessorRegistry
from ii_tool.tools.shell.terminal_manager import BaseShellManager


def deployment_rule(project_path: str) -> str:
    return f"""Successfully initialized codebase:
```
{project_path}
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


@WebProcessorRegistry.register("react-tailwind-python")
class ReactTailwindPythonProcessor(BaseProcessor):
    template_name = "react-tailwind-python"

    def __init__(
        self,
        project_dir: str,
        terminal_client: BaseShellManager,
        bash_session: str,
    ):
        super().__init__(project_dir, terminal_client, bash_session)
        self.project_rule = deployment_rule(project_dir)

    def install_dependencies(self):
        frontend_dir = os.path.join(self.project_dir, "frontend")
        backend_dir = os.path.join(self.project_dir, "backend")

        install_result = self.terminal_client.run_command(
            self.bash_session,
            "bun install && echo 'Frontend dependencies installed successfully'",
            run_dir=frontend_dir,
            timeout=999999,
            wait_for_output=True,
        )
        if (
            not install_result
            or "Frontend dependencies installed successfully"
            not in install_result.split("\n")[-2]
        ):
            raise Exception(
                f"Failed to install frontend dependencies: {install_result}"
            )

        install_result = self.terminal_client.run_command(
            self.bash_session,
            "pip install -r requirements.txt && echo 'Dependencies installed successfully'",
            run_dir=backend_dir,
            timeout=999999,  # Quick fix: No Timeout
            wait_for_output=True,
        )
        if (
            not install_result
            or "Dependencies installed successfully"
            not in install_result.split("\n")[-2]
        ):
            raise Exception(f"Failed to install backend dependencies: {install_result}")
