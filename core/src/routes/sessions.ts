import { FastifyInstance } from 'fastify';
import { db } from '../db/index.js';
import { Session, SessionSchema } from '../db/schema.js';
import { chatService } from '../services/chat.js';
import { agentService } from '../services/agent.js';
import { SSEStreamAdapter } from '../utils/stream.js';
import { Message } from '../llm/types.js';
import { v4 as uuidv4 } from 'uuid';

export async function sessionRoutes(fastify: FastifyInstance) {

    // POST /sessions/:id/chat (Hybrid REST/SSE endpoint)
    fastify.post('/:id/chat', async (request, reply) => {
        const userId = (request as any).user?.id;
        if (!userId) return reply.status(401).send({ error: 'Unauthorized' });
        const { id } = request.params as { id: string };

        // Validate session ownership
        const doc = db.get<Session>(id);
        if (!doc) return reply.status(404).send({ error: 'Session not found' });
        if (doc.content.user_id !== userId) return reply.status(403).send({ error: 'Forbidden' });

        const body = request.body as any;
        const content = body.content || '';
        const attachments = body.file_ids || []; // In future, map file IDs to attachment objects if needed

        // We might need to resolve file_ids to actual attachment data or pass IDs to agent
        // For now, pass as empty or basic structure

        const streamAdapter = new SSEStreamAdapter(reply);

        // We MUST await this to keep the connection open until streaming finishes
        await agentService.runChat(id, content, streamAdapter, attachments);

        // Return the reply object to satisfy Fastify typings, though the response is already handled via raw writes
        return reply;
    });

    // GET /sessions
    fastify.get('/', async (request, reply) => {
        const userId = (request as any).user?.id;
        if (!userId) return reply.status(401).send({ error: 'Unauthorized' });

        const { page = 1, per_page = 20, public_only = 'false' } = request.query as any;
        const isPublicOnly = public_only === 'true';
        const limit = parseInt(per_page);
        const offset = (parseInt(page) - 1) * limit;

        // Naive pagination in memory
        let sessions = db.find<Session>('session', (s) => {
            if (isPublicOnly) return s.is_public === true;
            return s.user_id === userId;
        });

        // Sort by created_at desc (assuming ISO string comparison works)
        sessions.sort((a, b) => (b.content.created_at || '').localeCompare(a.content.created_at || ''));

        const slice = sessions.slice(offset, offset + limit);

        return { sessions: slice.map(s => s.content) };
    });

    // POST /sessions
    fastify.post('/', async (request, reply) => {
        const userId = (request as any).user?.id;
        if (!userId) return reply.status(401).send({ error: 'Unauthorized' });

        const body = request.body as any;
        // Note: Frontend sends { deviceId, name }. We ignore deviceId for now as we use user_id.

        const newSession: Session = {
            id: uuidv4(),
            user_id: userId,
            name: body.name || 'New Session',
            status: 'active',
            prompt_tokens: 0,
            completion_tokens: 0,
            cost: 0,
            is_public: false,
            // workspace_dir: ??? (Maybe generate one or leave undefined for now)
        };

        const doc = db.create('session', newSession);
        return doc.content;
    });

    // GET /sessions/:id
    fastify.get('/:id', async (request, reply) => {
        const userId = (request as any).user?.id;
        const { id } = request.params as { id: string };

        const doc = db.get<Session>(id);
        if (!doc) return reply.status(404).send({ error: 'Session not found' });

        // Check access: Owner OR Public
        if (doc.content.user_id !== userId && !doc.content.is_public) {
             return reply.status(403).send({ error: 'Forbidden' });
        }

        return doc.content;
    });

    // PATCH /sessions/:id
    fastify.patch('/:id', async (request, reply) => {
        const userId = (request as any).user?.id;
        if (!userId) return reply.status(401).send({ error: 'Unauthorized' });
        const { id } = request.params as { id: string };

        const doc = db.get<Session>(id);
        if (!doc) return reply.status(404).send({ error: 'Session not found' });
        if (doc.content.user_id !== userId) return reply.status(403).send({ error: 'Forbidden' });

        const body = request.body as any;
        const updates: Partial<Session> = {};
        if (body.name !== undefined) updates.name = body.name;
        if (body.status !== undefined) updates.status = body.status;
        // Add other fields as needed

        const updated = db.update<Session>(id, updates);
        return updated?.content;
    });

    // DELETE /sessions/:id
    fastify.delete('/:id', async (request, reply) => {
        const userId = (request as any).user?.id;
        if (!userId) return reply.status(401).send({ error: 'Unauthorized' });
        const { id } = request.params as { id: string };

        const doc = db.get<Session>(id);
        if (!doc) return reply.status(404).send({ error: 'Session not found' });
        if (doc.content.user_id !== userId) return reply.status(403).send({ error: 'Forbidden' });

        db.delete(id);
        // Also delete messages? Ideally yes, but for now strict file separation.
        // db.deleteMany('chat_message', m => m.session_id === id); // Not implemented in simple DB

        return { success: true };
    });

    // GET /sessions/:id/events (Chat History)
    fastify.get('/:id/events', async (request, reply) => {
         const userId = (request as any).user?.id;
         const { id } = request.params as { id: string };

         const doc = db.get<Session>(id);
         if (!doc) return reply.status(404).send({ error: 'Session not found' });

         // Check access
         if (doc.content.user_id !== userId && !doc.content.is_public) {
             return reply.status(403).send({ error: 'Forbidden' });
         }

         const history = await chatService.getHistory(id);

         // Map to IEvent format
         // frontend/src/typings/agent.ts defines IEvent
         const events = history.map((msg, index) => {
             // This mapping is tricky because frontend expects specific AgentEvents.
             // We'll map basic messages to 'user_message' and 'agent_response'
             let type = 'user_message';
             if (msg.role === 'assistant') type = 'agent_response';
             if (msg.role === 'system') type = 'system';
             if (msg.role === 'tool') type = 'tool_result';

             // If assistant has tool_calls, we might want to represent that differently?
             // For now, just return the content.

             return {
                 id: uuidv4(), // Message doesn't have ID in `Message` type, but DB doc does. history returns `content` only.
                 type: type,
                 content: msg, // Send the raw message content structure
                 timestamp: new Date().toISOString(), // We lost the timestamp in conversion
                 workspace_dir: doc.content.workspace_dir || ''
             };
         });

         return { events };
    });

    // GET /sessions/:id/files
    fastify.get('/:id/files', async (request, reply) => {
         const userId = (request as any).user?.id;
         const { id } = request.params as { id: string };

         const doc = db.get<Session>(id);
         if (!doc) return reply.status(404).send({ error: 'Session not found' });
         if (doc.content.user_id !== userId && !doc.content.is_public) {
             return reply.status(403).send({ error: 'Forbidden' });
         }

         // Mock implementation or scan directory if `workspace_dir` exists
         // For now, return empty list to satisfy contract
         return [];
    });

    // GET /sessions/:id/public (Alias to get if public)
    fastify.get('/:id/public', async (request, reply) => {
        const { id } = request.params as { id: string };
        const doc = db.get<Session>(id);
        if (!doc || !doc.content.is_public) {
            return reply.status(404).send({ error: 'Session not found or not public' });
        }
        return doc.content;
    });

    // GET /sessions/:id/public/events
    fastify.get('/:id/public/events', async (request, reply) => {
        const { id } = request.params as { id: string };
        const doc = db.get<Session>(id);
        if (!doc || !doc.content.is_public) {
            return reply.status(404).send({ error: 'Session not found or not public' });
        }

        const history = await chatService.getHistory(id);
        const events = history.map(msg => ({
             id: uuidv4(),
             type: msg.role === 'user' ? 'user_message' : 'agent_response',
             content: msg,
             timestamp: new Date().toISOString(),
             workspace_dir: doc.content.workspace_dir || ''
        }));
        return { events };
    });

    // POST /sessions/:id/publish
    fastify.post('/:id/publish', async (request, reply) => {
        const userId = (request as any).user?.id;
        if (!userId) return reply.status(401).send({ error: 'Unauthorized' });
        const { id } = request.params as { id: string };

        const doc = db.get<Session>(id);
        if (!doc) return reply.status(404).send({ error: 'Session not found' });
        if (doc.content.user_id !== userId) return reply.status(403).send({ error: 'Forbidden' });

        db.update<Session>(id, { is_public: true });
        return { success: true };
    });

    // POST /sessions/:id/unpublish
    fastify.post('/:id/unpublish', async (request, reply) => {
        const userId = (request as any).user?.id;
        if (!userId) return reply.status(401).send({ error: 'Unauthorized' });
        const { id } = request.params as { id: string };

        const doc = db.get<Session>(id);
        if (!doc) return reply.status(404).send({ error: 'Session not found' });
        if (doc.content.user_id !== userId) return reply.status(403).send({ error: 'Forbidden' });

        db.update<Session>(id, { is_public: false });
        return { success: true };
    });

    // POST /sessions/:id/stop
    fastify.post('/:id/stop', async (request, reply) => {
        const userId = (request as any).user?.id;
        if (!userId) return reply.status(401).send({ error: 'Unauthorized' });
        const { id } = request.params as { id: string };

        const doc = db.get<Session>(id);
        if (!doc) return reply.status(404).send({ error: 'Session not found' });
        if (doc.content.user_id !== userId) return reply.status(403).send({ error: 'Forbidden' });

        agentService.stopSession(id);
        return { success: true };
    });
}
