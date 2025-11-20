import Fastify from 'fastify';
import cors from '@fastify/cors';
import { Server } from 'socket.io';
import dotenv from 'dotenv';
import { setupSocket } from './socket/index.js';
import { authRoutes } from './routes/auth.js';
import { fileRoutes } from './routes/files.js';
import { sessionRoutes } from './routes/sessions.js';
import { settingsRoutes } from './routes/settings.js';
import { connectorRoutes } from './routes/connectors.js';
import { billingRoutes } from './routes/billing.js';

dotenv.config();

const fastify = Fastify({
  logger: true,
});

// Register CORS
fastify.register(cors, {
  origin: '*', // In production, lock this down
});

// Register Routes
fastify.register(authRoutes, { prefix: '/auth' });
fastify.register(fileRoutes, { prefix: '/files' });
fastify.register(sessionRoutes, { prefix: '/sessions' });
fastify.register(settingsRoutes, { prefix: '/user-settings' });
fastify.register(connectorRoutes, { prefix: '/connectors' });
fastify.register(billingRoutes, { prefix: '/billing' });

const start = async () => {
  try {
    await fastify.ready();

    // Initialize Socket.IO
    const io = new Server(fastify.server, {
      cors: {
        origin: "*", // In production, lock this down
        methods: ["GET", "POST"]
      }
    });

    setupSocket(io);

    const PORT = process.env.PORT ? parseInt(process.env.PORT) : 3000;
    await fastify.listen({ port: PORT, host: '0.0.0.0' });
    console.log(`Server listening on port ${PORT}`);
  } catch (err) {
    fastify.log.error(err);
    process.exit(1);
  }
};

start();
