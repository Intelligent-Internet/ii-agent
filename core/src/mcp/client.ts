import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StdioClientTransport } from '@modelcontextprotocol/sdk/client/stdio.js';

// Cache clients to avoid spawning too many processes
const clients: Record<string, Client> = {};

export async function getMCPClient(config: any) {
    // config matches MCPServerConfigSchema (command, args, etc.)
    // We generate a key based on command + args
    const key = JSON.stringify(config);

    if (clients[key]) {
        return clients[key];
    }

    const transport = new StdioClientTransport({
        command: config.command,
        args: config.args,
        env: config.env
    });

    const client = new Client(
        {
            name: "agent-client",
            version: "1.0.0",
        },
        {
            capabilities: {
                prompts: {},
                resources: {},
                tools: {},
            },
        }
    );

    await client.connect(transport);

    clients[key] = client;
    return client;
}

export async function listToolsFromMCP(config: any) {
    try {
        const client = await getMCPClient(config);
        const result = await client.listTools();
        return result.tools;
    } catch (e) {
        console.error("Failed to list MCP tools", e);
        return [];
    }
}

export async function callMCPTool(config: any, toolName: string, args: any) {
    const client = await getMCPClient(config);
    const result = await client.callTool({
        name: toolName,
        arguments: args
    });
    return result;
}
