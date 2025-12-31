export interface ChatQueryPayload {
    session_id?: string
    model_id: string
    text: string
    files: string[]
    tools?: {
        web_search: boolean
        web_visit: boolean
        image_search: boolean
    }
}

export type ChatStreamEvent =
    | {
          type: 'session'
          session_id: string
          is_new_session?: boolean
          name?: string
          agent_type?: string
          model_id?: string
          created_at?: string
      }
    | {
          type: 'content_start'
      }
    | {
          type: 'token'
          content: string
      }
    | {
          type: 'thinking'
          status: 'delta'
          delta: string
          signature?: string
      }
    | {
          type: 'tool_call_start'
          id: string
          name: string
          call_type: string
      }
    | {
          type: 'tool_call_delta'
          id: string
          delta: string
      }
    | {
          type: 'tool_call_stop'
          id: string
          name: string
          input: string
      }
    | {
          type: 'tool_result'
          tool_call_id: string
          name: string
          output: string
          is_error?: boolean
      }
    | {
          type: 'usage'
          input_tokens: number
          output_tokens: number
          cache_creation_tokens: number
          cache_read_tokens: number
          total_tokens: number
      }
    | {
          type: 'complete'
          message_id?: string
          finish_reason?: string
          elapsed_ms?: number
      }
    | {
          type: 'done'
      }
    | {
          type: 'error'
          message?: string
      }

export interface ChatStreamOptions {
    signal?: AbortSignal
    onEvent: (event: ChatStreamEvent) => void
    /** Timeout in milliseconds - defaults to 120000 (2 minutes) */
    timeoutMs?: number
}

export type ContentPart =
    | {
          type: 'text'
          text: string
      }
    | {
          type: 'reasoning'
          id?: string
          thinking: string
          signature?: string
          started_at?: number | null
          finished_at?: number | null
      }
    | {
          type: 'tool_call'
          id: string
          name: string
          input: string
          finished: boolean
      }
    | {
          type: 'tool_result'
          tool_call_id: string
          name: string
          content: string
          metadata: string
          is_error: boolean
      }
    | {
          type: 'code_block'
          id: string
          content: string
          status: string
          outputs?: Array<Record<string, unknown>> | null
          container_id?: string | null
      }

export enum FinishReason {
    END_TURN = 'end_turn',
    MAX_TOKENS = 'max_tokens',
    TOOL_USE = 'tool_use',
    CANCELED = 'canceled',
    ERROR = 'error',
    PERMISSION_DENIED = 'permission_denied',
    PAUSE_TURN = 'pause_turn',
    UNKNOWN = 'unknown'
}

export interface ChatHistoryMessage {
    id: string
    role: 'user' | 'assistant' | 'tool'
    content: ContentPart[] // Direct array of ContentPart objects
    usage: {
        completion_tokens: number
        prompt_tokens: number
        total_tokens: number
        completion_tokens_details: {
            reasoning_tokens: number
        } | null
        prompt_tokens_details: unknown | null
    } | null
    tokens: number | null
    model: string
    created_at: string
    files: {
        id: string
        file_name: string
        file_size: number
        content_type: string
        created_at: string
    }[]
    finish_reason: FinishReason | null
}

export interface ChatHistoryResponse {
    messages: ChatHistoryMessage[]
    has_more: boolean
    total_count: number
}

/**
 * Extracts text content from a message's content field
 * @param message - The chat message containing content parts
 * @returns The concatenated text content from all text parts
 */
export function extractTextFromMessage(message: ChatHistoryMessage): string {
    return message.content
        .filter(
            (part): part is Extract<ContentPart, { type: 'text' }> =>
                part.type === 'text'
        )
        .map((part) => part.text)
        .join('')
}
