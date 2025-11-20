
import { describe, it, expect, beforeAll, afterAll } from 'vitest';
import Fastify from 'fastify';
import { sessionRoutes } from '../src/routes/sessions';
import { settingsRoutes } from '../src/routes/settings';
import { authRoutes } from '../src/routes/auth';
import { db } from '../src/db/index';
import { authService } from '../src/services/auth';

process.env.DB_PATH = 'test_core.sqlite';

const fastify = Fastify();
fastify.register(authRoutes, { prefix: '/auth' });
fastify.register(sessionRoutes, { prefix: '/sessions' });
fastify.register(settingsRoutes, { prefix: '/user-settings' });

fastify.addHook('preHandler', async (request, reply) => {
    const userId = request.headers['x-test-user-id'] as string;
    if (userId) {
        (request as any).user = { id: userId };
    }
});

describe('API Integration Tests', () => {
    let userId: string;

    beforeAll(async () => {
        await fastify.ready();
    });

    afterAll(async () => {
        await fastify.close();
    });

    it('should create an anonymous user', async () => {
        const response = await fastify.inject({
            method: 'POST',
            url: '/auth/anonymous'
        });
        expect(response.statusCode).toBe(200);
        const body = response.json();
        expect(body.user).toBeDefined();
        expect(body.user.id).toBeDefined();
        userId = body.user.id;
    });

    it('should create a session', async () => {
        const response = await fastify.inject({
            method: 'POST',
            url: '/sessions',
            headers: { 'x-test-user-id': userId },
            payload: { name: 'Test Session' }
        });
        expect(response.statusCode).toBe(200);
        const session = response.json();
        expect(session.name).toBe('Test Session');
        expect(session.user_id).toBe(userId);
    });

    it('should list sessions', async () => {
        const response = await fastify.inject({
            method: 'GET',
            url: '/sessions',
            headers: { 'x-test-user-id': userId }
        });
        expect(response.statusCode).toBe(200);
        const body = response.json();
        expect(body.sessions).toHaveLength(1);
        expect(body.sessions[0].name).toBe('Test Session');
    });

    it('should create a model setting and return decrypted key', async () => {
        const response = await fastify.inject({
            method: 'POST',
            url: '/user-settings/models',
            headers: { 'x-test-user-id': userId },
            payload: {
                model: 'gpt-4-test',
                api_type: 'openai',
                api_key: 'sk-test-key-123'
            }
        });
        expect(response.statusCode).toBe(200);
        const model = response.json();
        expect(model.model).toBe('gpt-4-test');
        // The API returns the key decrypted for convenience/verification immediately after creation
        expect(model.api_key).toBe('sk-test-key-123');
        expect(model.encrypted_api_key).toBeUndefined();
    });

    it('should create MCP settings', async () => {
        const response = await fastify.inject({
            method: 'POST',
            url: '/user-settings/mcp',
            headers: { 'x-test-user-id': userId },
            payload: {
                mcp_config: { servers: { test: { command: 'echo' } } },
                metadata: { note: 'test' }
            }
        });
        expect(response.statusCode).toBe(200);
        const setting = response.json();
        expect(setting.mcp_config.servers.test.command).toBe('echo');
    });
});
