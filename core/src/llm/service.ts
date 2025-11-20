import { ChatOpenAI } from '@langchain/openai';
import { ChatAnthropic } from '@langchain/anthropic';
import { HumanMessage, AIMessage, SystemMessage, BaseMessage, ToolMessage } from '@langchain/core/messages';
import { LLMProvider, Message, LLMConfig, ToolParam, AssistantContentBlock, TextResult, ToolCall } from './types.js';

export class LangChainProvider implements LLMProvider {
  private getModel(config: LLMConfig) {
    const { model, apiKey, baseUrl, temperature } = config;

    if (model.startsWith('gpt') || model.startsWith('o1')) {
      return new ChatOpenAI({
        modelName: model,
        openAIApiKey: apiKey || process.env.OPENAI_API_KEY,
        temperature: temperature ?? 0,
        configuration: {
          baseURL: baseUrl
        }
      });
    } else if (model.startsWith('claude')) {
      return new ChatAnthropic({
        modelName: model,
        anthropicApiKey: apiKey || process.env.ANTHROPIC_API_KEY,
        temperature: temperature ?? 0,
        clientOptions: {
           baseURL: baseUrl
        }
      });
    }

    throw new Error(`Unsupported model: ${model}`);
  }

  private convertMessages(messages: Message[]): BaseMessage[] {
    return messages.map(m => {
      if (m.role === 'user') {
        if (typeof m.content === 'string') {
          return new HumanMessage(m.content);
        }
        // Handle multimodal content for LangChain
        const content = (m.content as any[]).map(c => {
            if (c.type === 'text_prompt') return { type: 'text', text: c.text };
            if (c.type === 'image') return { type: 'image_url', image_url: { url: c.source.data }};
            return c;
        });
        return new HumanMessage({ content });
      } else if (m.role === 'assistant') {
        const content = typeof m.content === 'string' ? m.content : '';
        // Check for tool_calls property
        if (m.tool_calls && m.tool_calls.length > 0) {
             return new AIMessage({
                 content: content,
                 tool_calls: m.tool_calls.map(tc => ({
                     id: tc.tool_call_id,
                     name: tc.tool_name,
                     args: tc.tool_input,
                     type: "tool_call"
                 }))
             });
        }
        return new AIMessage(content);
      } else if (m.role === 'system') {
        return new SystemMessage(m.content as string);
      } else if (m.role === 'tool') {
         return new ToolMessage({
             content: m.content as string,
             tool_call_id: m.tool_call_id!,
             name: m.name
         });
      }
      throw new Error(`Unknown role ${m.role}`);
    });
  }

  async *generateStream(
    messages: Message[],
    config: LLMConfig,
    tools?: ToolParam[]
  ): AsyncGenerator<AssistantContentBlock | string, void, unknown> {
    const model = this.getModel(config);
    const langchainMessages = this.convertMessages(messages);

    // Bind tools if present
    let runnable = model;
    if (tools && tools.length > 0) {
      // Convert generic ToolParam to LangChain tool structure
      // This usually requires Zod schema or specific structure
      // For this simplified pass, we rely on the model knowing how to handle raw definitions if supported,
      // or we skip binding if complex. LangChain usually expects StructuredTool objects.
      // simpler:
        const lcTools = tools.map(t => ({
            name: t.name,
            description: t.description,
            schema: t.input_schema
        }));
        // @ts-ignore - bind tools typings are complex
        runnable = model.bindTools(lcTools);
    }

    // @ts-ignore - Runnable stream types are complex
    const stream = await runnable.stream(langchainMessages);

    for await (const chunk of stream) {
      // Yield text content
      if (chunk.content) {
          if (typeof chunk.content === 'string') {
               yield chunk.content;
          } else if (Array.isArray(chunk.content)) {
               // Handle complex content
               for (const c of chunk.content) {
                   // @ts-ignore
                   if ('text' in c) yield c.text;
               }
          }
      }

      // Yield tool calls
      if (chunk.tool_calls && chunk.tool_calls.length > 0) {
        for (const tc of chunk.tool_calls) {
          yield {
            tool_call_id: tc.id!,
            tool_name: tc.name,
            tool_input: tc.args,
          } as ToolCall;
        }
      }
    }
  }
}
