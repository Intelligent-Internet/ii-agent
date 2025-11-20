import { ToolParam } from '../llm/types.js';
import { weatherToolDefinition } from './weather.js';
import { fsDefinitions, fsHandlers } from './fs.js';
import { codeExecutorToolDefinition, executeCode } from './codeExecutor.js';
import { browserToolDefinitions, browserHandlers } from './browser.js';
import { zodToJsonSchema } from 'zod-to-json-schema';

export const tools: ToolParam[] = [
  {
    type: 'function',
    name: weatherToolDefinition.name,
    description: weatherToolDefinition.description,
    // @ts-ignore - Zod version mismatch issue potentially, usually works
    input_schema: zodToJsonSchema(weatherToolDefinition.schema) as any
  },
  {
    type: 'function',
    name: codeExecutorToolDefinition.name,
    description: codeExecutorToolDefinition.description,
    // @ts-ignore
    input_schema: zodToJsonSchema(codeExecutorToolDefinition.schema) as any
  },
  ...browserToolDefinitions.map(def => ({
      type: 'function' as const,
      name: def.name,
      description: def.description,
      // @ts-ignore
      input_schema: zodToJsonSchema(def.schema) as any
  })),
  ...fsDefinitions.map(def => ({
      type: 'function' as const,
      name: def.name,
      description: def.description,
      // @ts-ignore
      input_schema: zodToJsonSchema(def.schema) as any
  }))
];

export const toolMap: Record<string, (input: any, context?: any) => Promise<any>> = {
  [weatherToolDefinition.name]: async (input: any) => {
    // Mock implementation
    return {
      temperature: 22,
      unit: input.unit || 'celsius',
      description: 'Sunny'
    };
  },
  [codeExecutorToolDefinition.name]: executeCode,
  ...browserHandlers,
  ...fsHandlers
};
