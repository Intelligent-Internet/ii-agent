from mcp.types import ToolAnnotations
from fastmcp import FastMCP
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from argparse import ArgumentParser
from ii_tool.core.workspace import WorkspaceManager
from ii_tool.core.config import WebSearchConfig, WebVisitConfig, ImageSearchConfig, VideoGenerateConfig, ImageGenerateConfig, FullStackDevConfig
from ii_tool.tools.shell import TmuxWindowManager
from ii_tool.tools.manager import get_default_tools
from dotenv import load_dotenv

load_dotenv()


async def create_mcp(workspace_dir: str, session_id: str):
    terminal_manager = TmuxWindowManager(chat_session_id=session_id)
    workspace_manager = WorkspaceManager(workspace_path=workspace_dir)
    web_search_config = WebSearchConfig()
    web_visit_config = WebVisitConfig()
    image_search_config = ImageSearchConfig()
    video_generate_config = VideoGenerateConfig()
    image_generate_config = ImageGenerateConfig()
    fullstack_dev_config = FullStackDevConfig()
    
    tools = get_default_tools(
        workspace_manager=workspace_manager,
        terminal_manager=terminal_manager,
        web_search_config=web_search_config,
        web_visit_config=web_visit_config,
        image_search_config=image_search_config,
        video_generate_config=video_generate_config,
        image_generate_config=image_generate_config,
        fullstack_dev_config=fullstack_dev_config,
    )

    mcp = FastMCP()
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
            tool.execute_mcp_wrapper,
            name=tool.name,
            description=tool.description,
            annotations=ToolAnnotations(
                title=tool.display_name,
                readOnlyHint=tool.read_only,
            ),
        )

        # NOTE: this is a temporary fix to set the parameters of the tool
        _mcp_tool = await mcp._tool_manager.get_tool(tool.name)
        _mcp_tool.parameters = tool.input_schema

    return mcp

async def main():
    parser = ArgumentParser()
    parser.add_argument("--workspace_dir", type=str)
    parser.add_argument("--session_id", type=str, default=None)
    parser.add_argument("--port", type=int, default=6060)
    
    args = parser.parse_args()
    
    mcp = await create_mcp(
        workspace_dir=args.workspace_dir,
        session_id=args.session_id,
    )
    await mcp.run_async(transport="http", host="0.0.0.0", port=args.port)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())