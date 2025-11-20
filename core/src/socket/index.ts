import { Server, Socket } from 'socket.io';
import { authService } from '../services/auth.js';
import { chatService } from '../services/chat.js';
import { db } from '../db/index.js';
import { Session, SessionSchema } from '../db/schema.js';
import { v4 as uuidv4 } from 'uuid';
import { LangChainProvider } from '../llm/service.js';
import { Message, ToolCall } from '../llm/types.js';
import { z } from 'zod';
import { tools, toolMap } from '../tools/index.js';
import { getMCPTools, handleMCPToolCall } from '../tools/mcp.js';

// Simple in-memory session store for active sockets
const sessionSockets = new Map<string, Set<string>>(); // session_id -> Set<socket_id>
const socketSessions = new Map<string, string>(); // socket_id -> session_id

export function setupSocket(io: Server) {
  // Middleware for authentication
  io.use(async (socket, next) => {
    const token = socket.handshake.auth.token;
    if (!token) {
      return next(new Error('Authentication token required'));
    }

    try {
        // In our simplified auth, token IS the user_id
      const user = await authService.getUser(token);
      if (!user) {
        return next(new Error('Invalid token'));
      }
      socket.data.user = user.content;
      next();
    } catch (err) {
      next(new Error('Authentication failed'));
    }
  });

  io.on('connection', async (socket) => {
    console.log(`User connected: ${socket.id}, UserID: ${socket.data.user.id}`);

    socket.on('join_session', async (data: { session_uuid?: string }) => {
      try {
        let sessionId = data.session_uuid;
        let session;

        if (sessionId) {
          // Try to find existing session
          const sessionDoc = db.get<Session>(sessionId);
          // Verify ownership
          if (sessionDoc && sessionDoc.content.user_id === socket.data.user.id) {
            session = sessionDoc.content;
          }
        }

        if (!session) {
          // Create new session
          sessionId = uuidv4();
          const newSession: Session = {
            id: sessionId,
            user_id: socket.data.user.id!, // anonymous user has ID
            status: 'active',
            prompt_tokens: 0,
            completion_tokens: 0,
            cost: 0
          };
          db.create('session', newSession);
          session = newSession;
        }

        // Join room
        await socket.join(sessionId!);
        socketSessions.set(socket.id, sessionId!);

        if (!sessionSockets.has(sessionId!)) {
            sessionSockets.set(sessionId!, new Set());
        }
        sessionSockets.get(sessionId!)?.add(socket.id);

        // Initialize history if needed (check if empty)
        const history = await chatService.getHistory(sessionId!);
        if (history.length === 0) {
             await chatService.addMessage(sessionId!, { role: 'system', content: 'You are a helpful AI assistant.' });
        }

        // Emit session info
        socket.emit('chat_event', {
            type: 'system',
            content: {
                message: 'Session created/joined',
                session_id: sessionId
            }
        });

        // Handshake
        socket.emit('chat_event', {
            type: 'connection_established',
            content: {
                message: 'Connected to Agent Core',
            }
        });

      } catch (error) {
        console.error('Error joining session:', error);
        socket.emit('chat_event', { type: 'error', content: { message: 'Failed to join session' } });
      }
    });

    socket.on('chat_message', async (data: { type: string, content: any }) => {
        const sessionId = socketSessions.get(socket.id);
        if (!sessionId) {
            socket.emit('chat_event', { type: 'error', content: { message: 'No active session' } });
            return;
        }

        if (data.type === 'user_message') {
            // Add user message to history
            await chatService.addMessage(sessionId, { role: 'user', content: data.content.message });

            // Get updated history
            const history = await chatService.getHistory(sessionId);

            // Invoke LLM
            handleLLMInteraction(io, sessionId, history);
        }
    });

    socket.on('disconnect', () => {
      const sessionId = socketSessions.get(socket.id);
      if (sessionId) {
          const sockets = sessionSockets.get(sessionId);
          sockets?.delete(socket.id);
          if (sockets?.size === 0) {
              sessionSockets.delete(sessionId);
          }
      }
      socketSessions.delete(socket.id);
      console.log('User disconnected:', socket.id);
    });
  });
}

async function handleLLMInteraction(io: Server, sessionId: string, messages: Message[]) {
    const provider = new LangChainProvider();
    // Hardcoded config for now, should fetch from DB/Session
    const config = {
        model: 'gpt-4o', // Default to OpenAI for now
        temperature: 0.7
    };

    try {
        // Fetch active MCP tools for this user
        // We need user_id. Session has user_id.
        const sessionDoc = db.get<Session>(sessionId);
        const userId = sessionDoc?.content.user_id;

        let activeTools = [...tools];
        if (userId) {
            try {
                const mcpTools = await getMCPTools(userId);
                activeTools = [...activeTools, ...mcpTools];
            } catch (e) {
                console.error("Error fetching MCP tools:", e);
            }
        }

        let currentMessages = [...messages];
        let keepGoing = true;

        while (keepGoing) {
            keepGoing = false;
            const stream = provider.generateStream(currentMessages, config, activeTools);

            let fullResponse = "";
            let toolCalls: ToolCall[] = [];

            for await (const chunk of stream) {
                if (typeof chunk === 'string') {
                    fullResponse += chunk;
                    io.to(sessionId).emit('chat_event', {
                        type: 'token',
                        content: { token: chunk }
                    });
                } else if (chunk && 'tool_call_id' in chunk) {
                    // Accumulate tool calls
                    toolCalls.push(chunk as ToolCall);
                     io.to(sessionId).emit('chat_event', {
                        type: 'tool_call',
                        content: chunk
                    });
                }
            }

            // If we had tool calls, execute them and continue
            if (toolCalls.length > 0) {
                 // Add assistant message with tool calls to history
                 const assistantMsg: Message = {
                     role: 'assistant',
                     content: fullResponse,
                     tool_calls: toolCalls
                 };
                 currentMessages.push(assistantMsg);
                 await chatService.addMessage(sessionId, assistantMsg);

                 for (const tc of toolCalls) {
                     let result = "Error: Tool not found";

                     try {
                         if (toolMap[tc.tool_name]) {
                             // Local tool
                             const output = await toolMap[tc.tool_name](tc.tool_input, { sessionId });
                             result = typeof output === 'string' ? output : JSON.stringify(output);
                         } else if (userId) {
                             // Try MCP tool
                             const output = await handleMCPToolCall(userId, tc.tool_name, tc.tool_input);
                             result = typeof output === 'string' ? output : JSON.stringify(output);
                         }
                     } catch (e) {
                         result = `Error executing tool: ${e}`;
                     }

                     // Send tool output to client
                     io.to(sessionId).emit('chat_event', {
                         type: 'tool_output',
                         content: {
                             tool_call_id: tc.tool_call_id,
                             output: result
                         }
                     });

                     // Add to history
                     const toolMsg: Message = {
                         role: 'tool',
                         tool_call_id: tc.tool_call_id,
                         name: tc.tool_name,
                         content: result
                     };
                     currentMessages.push(toolMsg);
                     await chatService.addMessage(sessionId, toolMsg);
                 }

                 // Continue loop to let LLM see results and respond
                 keepGoing = true;
            } else {
                // Final response
                // Update history
                await chatService.addMessage(sessionId, { role: 'assistant', content: fullResponse });

                 io.to(sessionId).emit('chat_event', {
                    type: 'stop',
                    content: {
                        text: fullResponse
                    }
                });
            }
        }

    } catch (error) {
        console.error("LLM Error:", error);
         io.to(sessionId).emit('chat_event', {
            type: 'error',
            content: { message: error instanceof Error ? error.message : 'Unknown error' }
        });
    }
}
