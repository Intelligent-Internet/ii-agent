import { ToolParam } from '../llm/types.js';
import { weatherToolDefinition } from './weather.js';
import { zodToJsonSchema } from 'zod-to-json-schema';

export const tools: ToolParam[] = [
  {
    type: 'function',
    name: weatherToolDefinition.name,
    description: weatherToolDefinition.description,
    // @ts-ignore - Zod version mismatch issue potentially, usually works
    input_schema: zodToJsonSchema(weatherToolDefinition.schema) as any
  }
];

export const toolMap: Record<string, (input: any) => Promise<any>> = {
  [weatherToolDefinition.name]: async (input: any) => {
    // Mock implementation
    return {
      temperature: 22,
      unit: input.unit || 'celsius',
      description: 'Sunny'
    };
  }
};
