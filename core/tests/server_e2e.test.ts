import { describe, it, expect, beforeAll, afterAll, vi } from 'vitest';
import Fastify, { FastifyInstance } from 'fastify';
import { createTestUser, createTestSession } from './utils.js';
import { sessionRoutes } from '../src/routes/sessions.js';
import { authRoutes } from '../src/routes/auth.js';
import { db } from '../src/db/index.js';
import { LangChainProvider } from '../src/llm/service.js';
import supertest from 'supertest';

// We need to mock the LLM provider again to avoid real calls during HTTP tests
// Ideally we share this mock setup

describe('Server E2E (Streaming)', () => {
    let server: FastifyInstance;
    let userId: string;
    let sessionId: string;
    let token: string;

    beforeAll(async () => {
        // Setup DB
        const user = createTestUser();
        userId = user.id;
        token = userId; // In our auth mock, token IS user id
        const session = createTestSession(userId);
        sessionId = session.id;

        // Setup Server
        server = Fastify();
        // Register minimal routes needed
        // We need to mock 'request.user' middleware or similar if we used it globally
        // In `server.ts`, we rely on `authRoutes` or specific middleware?
        // `sessionRoutes` checks `request.user?.id`. We need to simulate that.

        server.addHook('preHandler', async (request, reply) => {
             // Simple mock auth middleware
             const authHeader = request.headers.authorization;
             if (authHeader) {
                 const t = authHeader.replace('Bearer ', '');
                 if (t === userId) {
                     (request as any).user = { id: userId };
                 }
             }
        });

        server.register(sessionRoutes, { prefix: '/sessions' });

        await server.ready();
    });

    afterAll(async () => {
        await server.close();
    });

    it('should stream SSE events correctly via POST /sessions/:id/chat', async () => {
        // Mock LLM
        const generateStreamSpy = vi.spyOn(LangChainProvider.prototype, 'generateStream');
        async function* mockGenerator() {
            yield "HTTP ";
            yield "Stream";
        }
        generateStreamSpy.mockReturnValue(mockGenerator());

        const response = await supertest(server.server)
            .post(`/sessions/${sessionId}/chat`)
            .set('Authorization', `Bearer ${token}`)
            .send({ content: "Hello HTTP" })
            .expect(200)
            .expect('Content-Type', /text\/event-stream/);

        // Supertest buffers the response, so we check the text body
        const body = response.text;

        // Expected SSE format:
        // event: content\ndata: {"status":"start"}\n\n
        // event: content\ndata: {"status":"delta","delta":"HTTP "}\n\n
        // ...

        expect(body).toContain('event: content');
        expect(body).toContain('data: {"status":"start"}');
        expect(body).toContain('data: {"status":"delta","delta":"HTTP "}');
        expect(body).toContain('data: {"status":"delta","delta":"Stream"}');
        expect(body).toContain('data: [DONE]');

        generateStreamSpy.mockRestore();
    });
});
