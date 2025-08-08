import subprocess
from ii_tool.tools.dev.template_processor.base_processor import BaseProcessor
from ii_tool.tools.dev.template_processor.registry import WebProcessorRegistry


def deployment_rule(project_path: str) -> str:
    return f"""
Project directory `{project_path}` created successfully. Application code is in `{project_path}/src`. File tree:
```
{project_path}/
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
Add components with `cd {project_path} && bunx shadcn@latest add -y -o`. Import components with `@/` alias. Note, 'toast' is deprecated, use 'sonner' instead. Before editing, run `cd {project_path} && bun install` to install dependencies. Run `cd {project_path} && bun run dev` to start the dev server ASAP to catch any runtime errors. Remember that all terminal commands must be run from the project directory.
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
        project_dir: str,
    ):
        super().__init__(project_dir)
        self.project_rule = deployment_rule(project_dir)

    def install_dependencies(self):
        install_result = subprocess.run(
            "bun install",
            shell=True,
            cwd=self.project_dir,
            capture_output=True,
        )
        if install_result.returncode != 0:
            raise Exception(
                f"Failed to install dependencies automatically: {install_result.stderr.decode('utf-8')}. Please fix the error and run `bun install` in the project directory manually"
            )
