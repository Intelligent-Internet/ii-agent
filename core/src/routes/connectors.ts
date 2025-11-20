import { FastifyInstance } from 'fastify';

export async function connectorRoutes(fastify: FastifyInstance) {
    // Stub implementation for Connectors
    // Since we are avoiding auth, we won't implement actual Google Drive OAuth here.
    // This satisfies the requirement to have the framework structure.

    fastify.get('/', async (request, reply) => {
        return { connectors: [] };
    });

    fastify.get('/google-drive/status', async (request, reply) => {
        return {
            is_connected: false,
            connector_type: 'google_drive'
        };
    });
}
