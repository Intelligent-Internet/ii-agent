import { z } from 'zod';

// Common interfaces for LLM interaction, mirroring core concepts from the Python backend

export type ToolParam = {
  type: 'function' | 'custom';
  name: string;
  description: string;
  input_schema: Record<string, any>;
};

export type ToolCall = {
  tool_call_id: string;
  tool_name: string;
  tool_input: any;
  tool_id?: string;
  thought_signature?: string;
};

export type ToolResult = {
  tool_call_id: string;
  tool_name: string;
  tool_output: any;
};

export type TextPrompt = {
  type: 'text_prompt';
  text: string;
};

export type ImageBlock = {
  type: 'image';
  source: {
    type: 'base64' | 'url';
    media_type: string;
    data: string;
  };
};

export type TextResult = {
  type: 'text_result';
  text: string;
  id?: string;
  thought_signature?: string;
  thought?: boolean;
};

// Union types
export type UserContentBlock = TextPrompt | ImageBlock;
export type AssistantContentBlock = TextResult | ToolCall;

export type Message = {
  role: 'user' | 'assistant' | 'system' | 'tool';
  content: string | UserContentBlock[] | AssistantContentBlock[];
  tool_call_id?: string; // For tool results
  name?: string; // For tool results
  tool_calls?: ToolCall[]; // For assistant messages
};

export interface LLMConfig {
  model: string;
  apiKey?: string;
  baseUrl?: string;
  temperature?: number;
  maxTokens?: number;
}

export interface LLMProvider {
  generateStream(
    messages: Message[],
    config?: LLMConfig,
    tools?: ToolParam[]
  ): AsyncGenerator<AssistantContentBlock | string, void, unknown>;
}
