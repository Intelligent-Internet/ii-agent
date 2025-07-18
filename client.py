from fastmcp import Client
import asyncio
from ii_agent.mcp.server import create_mcp

# The Client automatically uses StreamableHttpTransport for HTTP URLs
# client = Client("http://127.0.0.1:6060/mcp")

mcp = create_mcp(
    workspace_dir="/home/pvduy/phu/ii-agent/tmp",
    session_id="test_mcp",
)

client = Client(mcp)

async def main():
    async with client:
        tools = await client.list_tools()
        # resources = await client.list_resources()
        print(f"Number of available tools: {len(tools)}")
        
        print("--------------------------------")
        print(tools[0])
        print(type(tools[0]))
        print("--------------------------------")

        result = await client.call_tool("TodoWrite", {
            "todos": [
                {
                    "content": "Write a new tool",
                    "status": "pending",
                    "priority": "low",
                    "id": 1,
                }
            ]
        })
        print(result)

        result = await client.call_tool("TodoRead", {})
        print(result)

        result = await client.call_tool("BashInit", {
            "session_name": "abc",
            "start_directory": "/home/pvduy/phu/ii-agent/tmp",
        })
        print(result)

        result = await client.call_tool("BashList", {
        })
        print(result)

asyncio.run(main())