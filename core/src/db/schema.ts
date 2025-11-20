import { z } from 'zod';

// Models based on Python SQLAlchemy models and Frontend interfaces

export const UserSchema = z.object({
  id: z.string().uuid().optional(),
  email: z.string().email().optional(), // Optional for anonymous
  role: z.string().default('user'),
  is_anonymous: z.boolean().default(false),
  created_at: z.string().optional(),
});

export type User = z.infer<typeof UserSchema>;

export const SessionSchema = z.object({
  id: z.string().uuid().optional(),
  user_id: z.string(),
  name: z.string().optional(),
  status: z.enum(['pending', 'active', 'pause']).default('active'),
  llm_setting_id: z.string().optional(),
  prompt_tokens: z.number().default(0),
  completion_tokens: z.number().default(0),
  cost: z.number().default(0.0),
  is_public: z.boolean().default(false),
  workspace_dir: z.string().optional(), // Added to match frontend ISession
  created_at: z.string().optional(),
  updated_at: z.string().optional(),
});

export type Session = z.infer<typeof SessionSchema>;

// Matching frontend IModel
export const LLMSettingSchema = z.object({
  id: z.string().uuid().optional(),
  user_id: z.string(),
  model: z.string(),
  api_type: z.enum(['openai', 'anthropic', 'gemini', 'custom']).or(z.string()),
  base_url: z.string().optional(),
  encrypted_api_key: z.string().optional(), // Stored encrypted
  context_length: z.number().optional(),
  input_price_per_token: z.number().optional(),
  output_price_per_token: z.number().optional(),
  supports_function_calling: z.boolean().default(true),
  supports_vision: z.boolean().default(false),
  description: z.string().optional(),
  source: z.enum(['user', 'system']).default('user'),
  created_at: z.string().optional(),
  updated_at: z.string().optional(),
});

export type LLMSetting = z.infer<typeof LLMSettingSchema>;

// Matching frontend IMcpSettings
export const MCPServerConfigSchema = z.object({
  command: z.string().optional(),
  args: z.array(z.string()).optional(),
  capabilities: z.array(z.string()).optional(),
  env: z.record(z.string()).optional(),
  url: z.string().optional(),
  headers: z.record(z.string()).optional(),
});

export const MCPConfigSchema = z.object({
  mcpServers: z.record(MCPServerConfigSchema).optional(),
  servers: z.record(MCPServerConfigSchema).optional(),
});

export const MCPMetadataSchema = z.object({
    auth_json: z.record(z.any()).optional(),
    model: z.string().optional(),
    apikey: z.string().optional(),
    model_reasoning_effort: z.string().optional(),
    search: z.boolean().optional(),
});

export const MCPSettingSchema = z.object({
  id: z.string().uuid().optional(),
  user_id: z.string(),
  mcp_config: MCPConfigSchema,
  metadata: MCPMetadataSchema.optional(),
  is_active: z.boolean().default(true),
  created_at: z.string().optional(),
  updated_at: z.string().optional(),
});

export type MCPSetting = z.infer<typeof MCPSettingSchema>;
