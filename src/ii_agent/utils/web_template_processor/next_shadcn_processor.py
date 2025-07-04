from ii_agent.prompts.system_prompt import SystemPromptBuilder
from ii_agent.tools.clients.terminal_client import TerminalClient
from ii_agent.utils.web_template_processor.base_processor import BaseProcessor
from ii_agent.utils.workspace_manager import WorkspaceManager
from ii_agent.utils.web_template_processor.web_processor_registry import (
    WebProcessorRegistry,
)


def next_shadcn_deployment_rule(project_name: str) -> str:
    return f"""
Project directory `{project_name}` created successfully. Application code is in `{project_name}/src`. File tree:
```
{project_name}/
│   ├── .gitignore              # Git ignore file
│   ├── biome.json              # Biome linter/formatter configuration
│   ├── jest.config.js          # Jest configuration
│   ├── bun.lock               # Lock file for dependencies
│   ├── components.json         # shadcn/ui configuration
│   ├── eslint.config.mjs       # ESLint configuration
│   ├── next-env.d.ts           # Next.js TypeScript declarations
│   ├── next.config.js          # Next.js configuration
│   ├── package.json            # Project dependencies and scripts
│   ├── postcss.config.mjs      # PostCSS configuration
│   ├── README.md               # Project documentation
│   ├── __tests__/              # Jest test directory
│   ├── src/                    # Source code directory
│   │   ├── app/                # Next.js App Router directory
│   │   │   ├── ClientBody.tsx  # Client-side body component
│   │   │   ├── globals.css     # Global styles
│   │   │   ├── layout.tsx      # Root layout component
│   │   ├── page.tsx            # Home page component
│       └── lib/                # Utility functions and libraries
│           └── utils.ts        # Utility functions
│       └── components/         # Components directory
│           └── ui/             # shadcn/ui components
│               └── button.tsx  # Button component
│   ├── tailwind.config.ts      # Tailwind CSS configuration
    └── tsconfig.json           # TypeScript configuration
```
IMPORTANT NOTE: This project is built with TypeScript(tsx) and Next.js App Router.
Add components with `cd {project_name} && bunx shadcn@latest add -y -o`. Import components with `@/` alias. Note, 'toast' is deprecated, use 'sonner' instead. Before editing, run `cd {project_name} && bun install` to install dependencies. Run `cd {project_name} && bun run dev` to start the dev server ASAP to catch any runtime errors. Remember that all terminal commands must be run from the project directory.
Any database operations must be done with Prisma ORM.
Authentication must be done with NextAuth. Use bcrypt for password hashing.
Use Chart.js for charts. Moveable for Draggable, Resizable, Scalable, Rotatable, Warpable, Pinchable, Groupable, Snappable components.
Use AOS for scroll animations. React-Player for video player.
Advance animations must be done with Framer Motion, Anime.js, and React Three Fiber.
Before writing the frontend integration, you must write an openapi spec for the backend then you must write test for all the expected http requests and responses using supertest (already installed).
Run the test by running `bun test`. Any backend operations must pass all test before you begin your deployment
The integration must follow the api contract strictly. Your predecessor was killed because he did not follow the api contract.

IMPORTANT: All the todo list must be done before you can return to the user.

If you need to use websocket, follow this guide: https://socket.io/how-to/use-with-nextjs
You must use socket.io and (IMPORTANT) socket.io-client for websocket.
Socket.io rules:
"Separate concerns, sanitize data, handle failures gracefully"

    NEVER send objects with circular references or function properties
    ALWAYS validate data serializability before transmission
    SEPARATE connection management from business logic storage
    SANITIZE all data crossing network boundaries
    CLEANUP resources and event listeners to prevent memory leaks
    HANDLE network failures, timeouts, and reconnections
    VALIDATE all incoming data on both client and server
    TEST with multiple concurrent connections under load

APPLIES TO: Any real-time system (WebSockets, Server-Sent Events, WebRTC, polling)


Banned libraries (will break with this template): Quill

"""


@WebProcessorRegistry.register("nextjs-shadcn")
class NextShadcnProcessor(BaseProcessor):
    template_name = "nextjs-shadcn"

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
        self.project_rule = next_shadcn_deployment_rule(project_name)

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
