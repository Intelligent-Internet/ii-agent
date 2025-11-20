import { db } from '../db/index.js';
import { Session } from '../db/schema.js';
import { ChatService, chatService } from './chat.js';
import { LangChainProvider } from '../llm/service.js';
import { Message, ToolCall } from '../llm/types.js';
import { tools, toolMap } from '../tools/index.js';
import { getMCPTools, handleMCPToolCall } from '../tools/mcp.js';
import { StreamAdapter, AgentEvent } from '../utils/stream.js';
import { v4 as uuidv4 } from 'uuid';

export class AgentService {
    private provider: LangChainProvider;

    constructor() {
        this.provider = new LangChainProvider();
    }

    // Map of running abort controllers for sessions
    private abortControllers = new Map<string, AbortController>();

    stopSession(sessionId: string) {
        const controller = this.abortControllers.get(sessionId);
        if (controller) {
            controller.abort();
            this.abortControllers.delete(sessionId);
        }
    }

    async runChat(sessionId: string, userMessage: string, stream: StreamAdapter, attachments: any[] = []) {
        // Create abort controller
        const controller = new AbortController();
        this.abortControllers.set(sessionId, controller);
        const signal = controller.signal;

        try {
            if (signal.aborted) throw new Error('Aborted');

            // 1. Fetch Session & User
            const sessionDoc = db.get<Session>(sessionId);
            if (!sessionDoc) throw new Error('Session not found');
            const userId = sessionDoc.content.user_id;

            // 2. Update History with User Message
            // Handle attachments if any (convert to image blocks etc)
            let content: any = userMessage;
            if (attachments && attachments.length > 0) {
                content = [
                    { type: 'text_prompt', text: userMessage },
                    ...attachments.map(a => ({
                        type: 'image',
                        source: {
                            type: 'base64',
                            media_type: a.mimeType || 'image/jpeg',
                            data: a.base64
                        }
                    }))
                ];
            }

            await chatService.addMessage(sessionId, { role: 'user', content });

            // Emit initial events (optional, but helpful for UI latency perception)
            // In the new structure, frontend handles optimistic updates, but we can ack?

            // 3. Prepare Context (Tools & History)
            const history = await chatService.getHistory(sessionId);

            let activeTools = [...tools];
            if (userId) {
                try {
                    const mcpTools = await getMCPTools(userId);
                    activeTools = [...activeTools, ...mcpTools];
                } catch (e) {
                    console.error("Error fetching MCP tools:", e);
                }
            }

            // 4. Config (Load from Settings or Session)
            // For now hardcoded or derived
            const config = {
                model: 'gpt-4o',
                temperature: 0.7
            };

            // 5. LLM Loop
            let currentMessages = [...history];
            let keepGoing = true;

            // Emit 'content_start'
            stream.emit({ type: 'content', status: 'start' });

            while (keepGoing) {
                if (signal.aborted) break;

                keepGoing = false;
                const llmStream = this.provider.generateStream(currentMessages, config, activeTools);

                let fullResponse = "";
                let currentToolCall: Partial<ToolCall> | null = null;
                let toolCalls: ToolCall[] = [];

                for await (const chunk of llmStream) {
                    if (signal.aborted) break;

                    if (typeof chunk === 'string') {
                        fullResponse += chunk;
                        stream.emit({ type: 'content', status: 'delta', delta: chunk });
                    } else if (chunk && 'tool_call_id' in chunk) {
                         // Tool Call start/delta logic if needed, but LangChain often gives full objects or chunks
                         // Our `generateStream` in `llm/service.ts` currently yields full `ToolCall` objects
                         // Let's check `llm/service.ts`: it yields `{ tool_call_id, tool_name, tool_input }` fully formed?
                         // "yield { tool_call_id: tc.id!, tool_name: tc.name, tool_input: tc.args }"
                         // Yes, it yields full calls.

                         const tc = chunk as ToolCall;
                         toolCalls.push(tc);

                         // Emit tool call event
                         stream.emit({
                             type: 'tool_call',
                             status: 'start',
                             id: tc.tool_call_id,
                             name: tc.tool_name
                         });
                         // Emit input immediately as we get it full
                         stream.emit({
                             type: 'tool_call',
                             status: 'stop',
                             id: tc.tool_call_id,
                             name: tc.tool_name,
                             input: JSON.stringify(tc.tool_input)
                         });
                    }
                }

                if (toolCalls.length > 0) {
                    // Save Assistant Message with Tool Calls
                     const assistantMsg: Message = {
                         role: 'assistant',
                         content: fullResponse,
                         tool_calls: toolCalls
                     };
                     currentMessages.push(assistantMsg);
                     await chatService.addMessage(sessionId, assistantMsg);

                     // Execute Tools
                     for (const tc of toolCalls) {
                         let output = "";
                         let isError = false;

                         try {
                             if (toolMap[tc.tool_name]) {
                                 const result = await toolMap[tc.tool_name](tc.tool_input, { sessionId });
                                 output = typeof result === 'string' ? result : JSON.stringify(result);
                             } else if (userId) {
                                 const result = await handleMCPToolCall(userId, tc.tool_name, tc.tool_input);
                                 output = typeof result === 'string' ? result : JSON.stringify(result);
                             } else {
                                 output = "Error: Tool not found";
                                 isError = true;
                             }
                         } catch (e) {
                             output = `Error executing tool: ${e}`;
                             isError = true;
                         }

                         // Emit result
                         stream.emit({
                             type: 'tool_result',
                             status: 'info',
                             tool_call_id: tc.tool_call_id,
                             name: tc.tool_name,
                             output: output,
                             is_error: isError
                         });

                         // Save Tool Message
                         const toolMsg: Message = {
                             role: 'tool',
                             tool_call_id: tc.tool_call_id,
                             name: tc.tool_name,
                             content: output
                         };
                         currentMessages.push(toolMsg);
                         await chatService.addMessage(sessionId, toolMsg);
                     }

                     keepGoing = true;
                     // New content block for next turn
                     stream.emit({ type: 'content', status: 'start' });
                } else {
                    // Done
                    await chatService.addMessage(sessionId, { role: 'assistant', content: fullResponse });
                    stream.emit({
                        type: 'complete',
                        status: 'done',
                        message_id: uuidv4(),
                        finish_reason: 'stop'
                    });
                }
            }

            stream.emit({ type: 'done' });
            stream.close();

        } catch (error) {
            // If aborted, we might want to emit nothing or a specific abort message
            // For now, just close cleanly or log
            if (signal.aborted) {
                console.log(`Session ${sessionId} aborted`);
                stream.emit({ type: 'error', message: 'Session aborted by user' });
                stream.close();
                return;
            }

            console.error("Agent Error:", error);
            stream.emit({ type: 'error', message: error instanceof Error ? error.message : String(error) });
            stream.close();
        } finally {
            this.abortControllers.delete(sessionId);
        }
    }
}

export const agentService = new AgentService();
