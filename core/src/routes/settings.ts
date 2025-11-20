import { FastifyInstance } from 'fastify';
import { db, Document } from '../db/index.js';
import { LLMSetting, LLMSettingSchema, MCPSetting, MCPSettingSchema } from '../db/schema.js';
import { encrypt, decrypt } from '../utils/crypto.js';
import { v4 as uuidv4 } from 'uuid';
import { z } from 'zod';

export async function settingsRoutes(fastify: FastifyInstance) {

  // --- Models API ---

  fastify.get('/models', async (request, reply) => {
    const userId = (request as any).user?.id;
    if (!userId) return reply.status(401).send({ error: 'Unauthorized' });

    const models = db.find<LLMSetting>('llm_setting', (item) => item.user_id === userId);

    // Return with decrypted keys? Usually we don't return keys, but frontend might expect masking.
    // Frontend IModel has `api_key` field.
    const responseModels = models.map(doc => {
        const { encrypted_api_key, ...rest } = doc.content;
        return {
            ...rest,
            api_key: encrypted_api_key ? decrypt(encrypted_api_key) : undefined
        };
    });

    return { models: responseModels };
  });

  fastify.post('/models', async (request, reply) => {
    const userId = (request as any).user?.id;
    if (!userId) return reply.status(401).send({ error: 'Unauthorized' });

    try {
      const body = request.body as any;

      // Handle API key encryption
      let encrypted_api_key;
      if (body.api_key) {
          encrypted_api_key = encrypt(body.api_key);
          delete body.api_key;
      }

      // Validate
      // We allow partial validation against schema because ID/dates are generated
      const partialSchema = LLMSettingSchema.partial({
          id: true, created_at: true, updated_at: true, user_id: true
      });

      const parsed = partialSchema.parse(body);

      const newModel: LLMSetting = {
          ...parsed,
          user_id: userId,
          encrypted_api_key,
          // Default type to custom if not specified, though schema has constraints
          api_type: parsed.api_type || 'custom',
      } as LLMSetting;

      const doc = db.create('llm_setting', newModel);

      const { encrypted_api_key: enc, ...rest } = doc.content;
      return {
          ...rest,
          api_key: enc ? decrypt(enc) : undefined
      };

    } catch (error) {
      request.log.error(error);
      return reply.status(400).send({ error: 'Invalid request' });
    }
  });

  fastify.put('/models/:id', async (request, reply) => {
    const userId = (request as any).user?.id;
    const { id } = request.params as { id: string };
    if (!userId) return reply.status(401).send({ error: 'Unauthorized' });

    try {
        const existing = db.get<LLMSetting>(id);
        if (!existing || existing.content.user_id !== userId) {
            return reply.status(404).send({ error: 'Model not found' });
        }

        const body = request.body as any;
        let updates: Partial<LLMSetting> = {};

        if (body.api_key) {
            updates.encrypted_api_key = encrypt(body.api_key);
        }

        // Copy other fields
        const allowedFields = [
            'model', 'api_type', 'base_url', 'context_length',
            'input_price_per_token', 'output_price_per_token',
            'supports_function_calling', 'supports_vision', 'description', 'source'
        ];

        for (const field of allowedFields) {
            if (body[field] !== undefined) {
                (updates as any)[field] = body[field];
            }
        }

        const updatedDoc = db.update<LLMSetting>(id, updates);

        if (!updatedDoc) return reply.status(500).send({ error: 'Failed to update' });

        const { encrypted_api_key: enc, ...rest } = updatedDoc.content;
        return {
            ...rest,
            api_key: enc ? decrypt(enc) : undefined
        };

    } catch (error) {
        request.log.error(error);
        return reply.status(400).send({ error: 'Invalid request' });
    }
  });

  fastify.delete('/models/:id', async (request, reply) => {
    const userId = (request as any).user?.id;
    const { id } = request.params as { id: string };
    if (!userId) return reply.status(401).send({ error: 'Unauthorized' });

    const existing = db.get<LLMSetting>(id);
    if (!existing || existing.content.user_id !== userId) {
        return reply.status(404).send({ error: 'Model not found' });
    }

    db.delete(id);
    return { success: true };
  });

  fastify.get('/models/:id', async (request, reply) => {
      const userId = (request as any).user?.id;
      const { id } = request.params as { id: string };
      if (!userId) return reply.status(401).send({ error: 'Unauthorized' });

      const existing = db.get<LLMSetting>(id);
      if (!existing || existing.content.user_id !== userId) {
          return reply.status(404).send({ error: 'Model not found' });
      }

      const { encrypted_api_key: enc, ...rest } = existing.content;
      return {
          ...rest,
          api_key: enc ? decrypt(enc) : undefined
      };
  });


  // --- MCP API ---

  fastify.get('/mcp', async (request, reply) => {
    const userId = (request as any).user?.id;
    if (!userId) return reply.status(401).send({ error: 'Unauthorized' });

    const settings = db.find<MCPSetting>('mcp_setting', (item) => item.user_id === userId);
    return { settings: settings.map(doc => doc.content) };
  });

  fastify.post('/mcp', async (request, reply) => {
    const userId = (request as any).user?.id;
    if (!userId) return reply.status(401).send({ error: 'Unauthorized' });

    try {
        const body = request.body as any;
        // Basic validation
        const newSetting: MCPSetting = {
            user_id: userId,
            mcp_config: body.mcp_config || {},
            metadata: body.metadata,
            is_active: body.is_active !== undefined ? body.is_active : true
        };

        const doc = db.create('mcp_setting', newSetting);
        return doc.content;
    } catch (error) {
        request.log.error(error);
        return reply.status(400).send({ error: 'Invalid request' });
    }
  });

  fastify.put('/mcp/:id', async (request, reply) => {
      const userId = (request as any).user?.id;
      const { id } = request.params as { id: string };
      if (!userId) return reply.status(401).send({ error: 'Unauthorized' });

      const existing = db.get<MCPSetting>(id);
      if (!existing || existing.content.user_id !== userId) {
          return reply.status(404).send({ error: 'Setting not found' });
      }

      const body = request.body as any;
      const updates: Partial<MCPSetting> = {};
      if (body.mcp_config) updates.mcp_config = body.mcp_config;
      if (body.metadata) updates.metadata = body.metadata;
      if (body.is_active !== undefined) updates.is_active = body.is_active;

      const updatedDoc = db.update<MCPSetting>(id, updates);
      return updatedDoc?.content;
  });

  fastify.delete('/mcp/:id', async (request, reply) => {
    const userId = (request as any).user?.id;
    const { id } = request.params as { id: string };
    if (!userId) return reply.status(401).send({ error: 'Unauthorized' });

    const existing = db.get<MCPSetting>(id);
    if (!existing || existing.content.user_id !== userId) {
        return reply.status(404).send({ error: 'Setting not found' });
    }

    db.delete(id);
    return { success: true };
  });

  // Helper to find or create special MCP settings
  const getSpecialMCP = (userId: string, typeName: string) => {
       // We can use metadata.model or a convention in mcp_config to identify
       // For now, let's assume we store a marker in metadata?
       // Or simpler: the frontend seems to treat these as singletons.
       // Let's look at db.find.
       // We'll use a convention: metadata.type = 'codex' or 'claude-code' if needed,
       // OR just check if the config looks like it.
       // Actually, the frontend calls `/user-settings/mcp/codex`.
       // We can store a `type` in metadata.
       return db.findOne<MCPSetting>('mcp_setting',
           (item) => item.user_id === userId && (item.metadata as any)?.special_type === typeName
       );
  }

  // Codex Endpoint
  fastify.get('/mcp/codex', async (request, reply) => {
      const userId = (request as any).user?.id;
      if (!userId) return reply.status(401).send({ error: 'Unauthorized' });

      const doc = getSpecialMCP(userId, 'codex');
      return doc ? doc.content : null;
  });

  fastify.post('/mcp/codex', async (request, reply) => {
      const userId = (request as any).user?.id;
      if (!userId) return reply.status(401).send({ error: 'Unauthorized' });

      const body = request.body as any;
      let doc = getSpecialMCP(userId, 'codex');

      const metadata = {
          ...body,
          special_type: 'codex'
      };

      // Encrypt apikey if present in body
      // Wait, body is { auth_json, model, apikey... }
      // We should encrypt apikey? The frontend sends it plain text likely.
      // Since `MCPMetadataSchema` has `apikey`, let's encrypt it if we want consistency,
      // but `MCPMetadataSchema` is generic JSON blob mostly.
      // Let's keep it simple and store as is for now unless we want to manage encryption manually there too.
      // Given instructions "Basic no-configuration cryptography", let's encrypt the apikey field if it exists.

      if (metadata.apikey) {
          metadata.encrypted_apikey = encrypt(metadata.apikey);
          delete metadata.apikey;
      }

      if (doc) {
          const updated = db.update<MCPSetting>(doc.id, { metadata });
          // Decrypt for response
          if (updated?.content.metadata?.encrypted_apikey) {
              updated.content.metadata.apikey = decrypt(updated.content.metadata.encrypted_apikey);
              delete updated.content.metadata.encrypted_apikey;
          }
          return updated?.content;
      } else {
          const newSetting: MCPSetting = {
              user_id: userId,
              mcp_config: {}, // Empty config for codex? Frontend seems to send config in metadata?
              metadata,
              is_active: true
          };
          const created = db.create('mcp_setting', newSetting);
          if (created.content.metadata?.encrypted_apikey) {
              created.content.metadata.apikey = decrypt(created.content.metadata.encrypted_apikey);
              delete created.content.metadata.encrypted_apikey;
          }
          return created.content;
      }
  });

  // Claude Code Endpoint
  fastify.get('/mcp/claude-code', async (request, reply) => {
      const userId = (request as any).user?.id;
      if (!userId) return reply.status(401).send({ error: 'Unauthorized' });

      const doc = getSpecialMCP(userId, 'claude-code');
      return doc ? doc.content : null;
  });

  fastify.post('/mcp/claude-code', async (request, reply) => {
      const userId = (request as any).user?.id;
      if (!userId) return reply.status(401).send({ error: 'Unauthorized' });

      const body = request.body as any;
      let doc = getSpecialMCP(userId, 'claude-code');

      const metadata = {
          ...body,
          special_type: 'claude-code'
      };

      if (doc) {
          const updated = db.update<MCPSetting>(doc.id, { metadata });
          return updated?.content;
      } else {
           const newSetting: MCPSetting = {
              user_id: userId,
              mcp_config: {},
              metadata,
              is_active: true
          };
          const created = db.create('mcp_setting', newSetting);
          return created.content;
      }
  });
}
