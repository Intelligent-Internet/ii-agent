import { FastifyInstance } from 'fastify';
import { storageService } from '../services/storage.js';
import { db } from '../db/index.js';
import multipart from '@fastify/multipart';

export async function fileRoutes(fastify: FastifyInstance) {
  // Register multipart support
  fastify.register(multipart, {
      limits: {
          fileSize: 50 * 1024 * 1024, // 50MB limit
      }
  });

  // Multipart upload endpoint
  fastify.post('/upload', async (request, reply) => {
      try {
          const data = await request.file();
          if (!data) {
              return reply.status(400).send({ error: 'No file uploaded' });
          }

          // Fields are usually inside the multipart stream, but extracting session_id requires careful handling
          // For standard generic uploads, we often just care about the file.
          // If session_id is needed, it should be passed as a field before the file or in query params.
          // Let's check query params for simplicity or try to parse fields.

          // Simple query param approach for session_id
          const query = request.query as { session_id?: string };
          const session_id = query.session_id;

          const buffer = await data.toBuffer();
          const filename = data.filename;

          const relativePath = await storageService.saveFile(filename, buffer, session_id);

          // Save metadata to DB
          const fileRecord = db.create('file', {
              filename,
              path: relativePath,
              size: buffer.length,
              session_id,
              mimetype: data.mimetype
          });

          return { status: 'success', file: fileRecord.content };
      } catch (error) {
          request.log.error(error);
          return reply.status(500).send({ error: 'Upload failed' });
      }
  });

  fastify.get('/:id', async (request, reply) => {
      const { id } = request.params as { id: string };
      const fileDoc = db.get<any>(id);

      if (!fileDoc) {
          return reply.status(404).send({ error: 'File not found' });
      }

      try {
          const buffer = await storageService.getFile(fileDoc.content.path);

          reply.header('Content-Disposition', `attachment; filename="${fileDoc.content.filename}"`);
          if (fileDoc.content.mimetype) {
              reply.type(fileDoc.content.mimetype);
          }

          return buffer;
      } catch (error) {
          request.log.error(error);
          return reply.status(500).send({ error: 'Failed to read file' });
      }
  });
}
