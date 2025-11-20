import Fastify from 'fastify';
import cors from '@fastify/cors';
import { Server } from 'socket.io';
import dotenv from 'dotenv';
import { setupSocket } from './socket/index.js';
import { authRoutes } from './routes/auth.js';

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
