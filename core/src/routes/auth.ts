import { FastifyInstance } from 'fastify';
import { authService } from '../services/auth.js';

export async function authRoutes(fastify: FastifyInstance) {
  fastify.post('/anonymous', async (request, reply) => {
    try {
      const user = await authService.createAnonymousUser();
      // In a real app, we would issue a JWT or session cookie here.
      // For now, we return the user object (including ID).
      return {
        status: 'success',
        user: user.content,
        token: user.id // Simple token for now
      };
    } catch (error) {
      request.log.error(error);
      reply.status(500).send({ error: 'Failed to create anonymous user' });
    }
  });

  fastify.get('/me', async (request, reply) => {
      // Extract token from header (simple implementation)
      const token = request.headers.authorization?.replace('Bearer ', '');
      if (!token) {
          return reply.status(401).send({ error: 'Unauthorized' });
      }

      const user = await authService.getUser(token);
      if (!user) {
           return reply.status(401).send({ error: 'Invalid token' });
      }

      return { status: 'success', user: user.content };
  })
}
