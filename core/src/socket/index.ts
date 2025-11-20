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
import { agentService } from '../services/agent.js';
import { SocketStreamAdapter } from '../utils/stream.js';

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
            // Use AgentService with SocketStreamAdapter
            // Note: AgentService expects `userMessage` string. data.content.message should be the string.
            // If data.content is object, check struct.
            // Legacy frontend sent { message: "text" } inside content.

            const messageText = data.content.message || (typeof data.content === 'string' ? data.content : '');

            // We can handle attachments if needed, but legacy socket didn't send them well?
            // Let's assume just text for now or extract attachments if in payload.

            const streamAdapter = new SocketStreamAdapter(socket, sessionId);
            // No await, run in background
            agentService.runChat(sessionId, messageText, streamAdapter);
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
