import { z } from 'zod';

// Models based on Python SQLAlchemy models

export const UserSchema = z.object({
  id: z.string().uuid().optional(),
  email: z.string().email().optional(), // Optional for anonymous
  role: z.string().default('user'),
  is_anonymous: z.boolean().default(false),
  created_at: z.string().optional(),
  // ... add other fields as needed
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
  // ...
});

export type Session = z.infer<typeof SessionSchema>;

export const LLMSettingSchema = z.object({
  id: z.string().uuid().optional(),
  user_id: z.string(),
  model: z.string(),
  api_type: z.string(), // 'openai', 'anthropic', etc.
  encrypted_api_key: z.string().optional(),
  temperature: z.number().default(0.0),
  // ...
});

export type LLMSetting = z.infer<typeof LLMSettingSchema>;
