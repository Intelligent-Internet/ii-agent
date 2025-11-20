import { ToolParam } from '../llm/types.js';
import { listToolsFromMCP, callMCPTool } from '../mcp/client.js';
import { db } from '../db/index.js';
import { MCPSetting } from '../db/schema.js';

// This function fetches all active MCP tools for a user
export async function getMCPTools(userId: string): Promise<ToolParam[]> {
    const settings = db.find<MCPSetting>('mcp_setting', s => s.user_id === userId && s.is_active);

    const allTools: ToolParam[] = [];

    for (const setting of settings) {
        const config = setting.content.mcp_config;
        // Structure of mcp_config: { mcpServers: { name: { command, args... } } }
        // Or sometimes it's just the config itself? The schema has `mcpServers`.

        if (config.mcpServers) {
            for (const [serverName, serverConfig] of Object.entries(config.mcpServers)) {
                const tools = await listToolsFromMCP(serverConfig);
                for (const tool of tools) {
                    allTools.push({
                        type: 'function',
                        name: tool.name, // Potentially namespace this? e.g. `mcp__serverName__toolName`
                        description: tool.description || '',
                        input_schema: tool.inputSchema as any
                    });
                }
            }
        }
    }

    return allTools;
}

// This function handles execution
export async function handleMCPToolCall(userId: string, toolName: string, args: any) {
    const settings = db.find<MCPSetting>('mcp_setting', s => s.user_id === userId && s.is_active);

    // We need to find which server provides this tool.
    // This is inefficient if we query every time. In a real app, we'd cache "ToolName -> ServerConfig".

    for (const setting of settings) {
         const config = setting.content.mcp_config;
         if (config.mcpServers) {
            for (const [serverName, serverConfig] of Object.entries(config.mcpServers)) {
                // Check if tool exists on this server
                // Optimization: Assume unique tool names or try calling?
                // Safer: list tools again or cache.
                // For MVP, let's list tools.
                const tools = await listToolsFromMCP(serverConfig);
                if (tools.find(t => t.name === toolName)) {
                    return await callMCPTool(serverConfig, toolName, args);
                }
            }
         }
    }

    throw new Error(`Tool ${toolName} not found in any active MCP server.`);
}
