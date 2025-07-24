from fastmcp import FastMCP
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from argparse import ArgumentParser
from ii_tool.core.workspace import WorkspaceManager
from ii_tool.tools.shell import ShellInit, ShellRunCommand, ShellView, ShellKill, ShellStopCommand, ShellList
from ii_tool.tools.shell.terminal_manager import TmuxWindowManager
from ii_tool.tools.file_system import GlobTool, GrepTool, LSTool, FileReadTool, FileWriteTool, FileEditTool, MultiEditTool
from ii_tool.tools.productivity import TodoReadTool, TodoWriteTool


def create_mcp(workspace_dir: str, session_id: str):
    terminal_manager = TmuxWindowManager(chat_session_id=session_id)
    workspace_manager = WorkspaceManager(workspace_path=workspace_dir)
    
    shell_tools = [
        ShellInit(terminal_manager, workspace_manager),
        ShellRunCommand(terminal_manager),
        ShellView(terminal_manager),
        ShellKill(terminal_manager),
        ShellStopCommand(terminal_manager),
        ShellList(terminal_manager),
    ]

    file_system_tools = [
        GlobTool(workspace_manager),
        GrepTool(workspace_manager),
        LSTool(workspace_manager),
        FileReadTool(workspace_manager),
        FileWriteTool(workspace_manager),
        FileEditTool(workspace_manager),
        MultiEditTool(workspace_manager),
    ]

    productivity_tools = [
        TodoReadTool(),
        TodoWriteTool(),
    ]

    tools = shell_tools + file_system_tools + productivity_tools

    mcp = FastMCP(name="ii-mcp")

    # Add CORS middleware to allow all hosts
    custom_middleware = [
        Middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    ]
    mcp.http_app(middleware=custom_middleware)

    for tool in tools:
        mcp.tool(
            tool.run_impl,
            name=tool.name,
            description=tool.description,
        )

    return mcp

if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument("--workspace_dir", type=str)
    parser.add_argument("--session_id", type=str, default=None)
    parser.add_argument("--port", type=int, default=6060)
    
    args = parser.parse_args()
    
    mcp = create_mcp(
        workspace_dir=args.workspace_dir,
        session_id=args.session_id,
    )
    mcp.run(transport="http", host="0.0.0.0", port=args.port)