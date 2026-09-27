import asyncio
from types import SimpleNamespace

import pytest

from ii_agent.agents.factory.mcp.base import MCPTool
from ii_agent.agents.factory.mcp.composio_mcp import ComposioMCPTool
from ii_agent.agents.factory.mcp.user_mcp_tool import UserMCPTool


@pytest.mark.parametrize("tool_class", [MCPTool, UserMCPTool, ComposioMCPTool])
@pytest.mark.asyncio
async def test_parallel_mcp_calls_use_separate_clients(tool_class):
    clients = []

    class Client:
        def __init__(self):
            self.active = False

        async def __aenter__(self):
            assert not self.active
            self.active = True
            return self

        async def __aexit__(self, *_args):
            self.active = False

        async def call_tool(self, _name, _input, timeout):
            assert timeout > 0
            await asyncio.sleep(0)
            return SimpleNamespace(
                content=[],
                structured_content={"user_display_content": "created", "is_error": False},
            )

    def new_client(_url):
        client = Client()
        clients.append(client)
        return client

    tool = tool_class(
        name="str_replace_based_edit_tool",
        display_name="Edit",
        description="Edit files",
        input_schema={},
        read_only=False,
    )
    tool.sandbox = SimpleNamespace(get_mcp_client=new_client)
    tool._sandbox_url = "http://sandbox:6060"

    results = await asyncio.gather(
        tool.execute({"path": "/workspace/a.py"}), tool.execute({"path": "/workspace/b.py"})
    )

    assert len(clients) == 2
    assert all(
        not result.is_error and result.user_display_content == "created" for result in results
    )
