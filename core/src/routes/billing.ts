import { FastifyInstance } from 'fastify';

export async function billingRoutes(fastify: FastifyInstance) {
    // Stub implementation for Billing
    // Returns "free" status to ensure UI works without real payments.

    fastify.get('/subscription', async (request, reply) => {
        return {
            status: 'active',
            plan: 'free_tier',
            credits: 999999
        };
    });

    fastify.get('/portal', async (request, reply) => {
         return { url: '#' };
    });
}
