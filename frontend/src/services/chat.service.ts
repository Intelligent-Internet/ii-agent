import axiosInstance from '@/lib/axios'
import { ACCESS_TOKEN } from '@/constants/auth'
import type {
    ChatQueryPayload,
    ChatStreamEvent,
    ChatStreamOptions,
    ChatHistoryResponse
} from '@/typings/chat'

export type {
    ChatQueryPayload,
    ChatStreamEvent,
    ChatStreamOptions,
    ChatHistoryResponse
}

function getApiBaseUrl(): string {
    return (
        axiosInstance.defaults.baseURL ||
        import.meta.env.VITE_API_URL ||
        'http://localhost:8000'
    )
}

class ChatService {
    async getFileContent({
        fileId,
        sessionId
    }: {
        fileId: string
        sessionId: string
    }): Promise<Blob> {
        const response = await axiosInstance.get(
            `/chat/${sessionId}/files/${fileId}`,
            { responseType: 'blob' }
        )
        return response.data
    }

    async getChatHistory(sessionId: string): Promise<ChatHistoryResponse> {
        const response = await axiosInstance.get<ChatHistoryResponse>(
            `/sessions/${sessionId}/events`
        )
        return response.data
    }

    async getPublicChatHistory(
        sessionId: string
    ): Promise<ChatHistoryResponse> {
        const response = await axiosInstance.get<ChatHistoryResponse>(
            `/sessions/${sessionId}/public/events`
        )
        return response.data
    }

    async stopConversation(sessionId: string): Promise<void> {
        await axiosInstance.post(`/sessions/${sessionId}/stop`)
    }

    async streamQuery(
        payload: ChatQueryPayload,
        options: ChatStreamOptions
    ): Promise<void> {
        const { signal, onEvent } = options
        const controller = new AbortController()
        const mergedSignal = controller.signal

        if (signal) {
            if (signal.aborted) {
                controller.abort()
            } else {
                signal.addEventListener('abort', () => controller.abort(), {
                    once: true
                })
            }
        }

        const headers = new Headers({
            'Content-Type': 'application/json',
            Accept: 'text/event-stream'
        })

        const token = localStorage.getItem(ACCESS_TOKEN)
        if (token) {
            headers.set('Authorization', `Bearer ${token}`)
        }

        const response = await fetch(
            `${getApiBaseUrl()}/sessions/${payload.session_id}/chat`,
            {
                method: 'POST',
                headers,
                body: JSON.stringify({
                    content: payload.text,
                    model_id: payload.model_id,
                    // session_id is in URL now
                    file_ids: payload.files,
                    tools: payload.tools ?? {
                        web_search: true,
                        image_search: true,
                        web_visit: true,
                        code_interpreter: true
                    }
                }),
                signal: mergedSignal
            }
        )

        if (!response.ok || !response.body) {
            throw new Error('Failed to start chat stream')
        }

        const reader = response.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ''

        const parseSSEBlock = (
            block: string
        ): { event?: string; data?: string } | null => {
            const trimmed = block.trim()
            if (!trimmed) return null

            let eventName: string | undefined
            const dataLines: string[] = []

            for (const rawLine of trimmed.split('\n')) {
                const line = rawLine.trim()
                if (!line) continue

                if (line.startsWith('event:')) {
                    eventName = line.slice(6).trim()
                    continue
                }

                if (line.startsWith('data:')) {
                    dataLines.push(line.slice(5).trim())
                    continue
                }

                if (!line.startsWith(':')) {
                    dataLines.push(line)
                }
            }

            if (!dataLines.length) {
                return eventName ? { event: eventName } : null
            }

            return {
                event: eventName,
                data: dataLines.join('\n')
            }
        }

        const normalizeStreamEvent = (
            eventName: string | undefined,
            raw: unknown
        ): ChatStreamEvent[] => {
            const events: ChatStreamEvent[] = []

            if (raw === '[DONE]') {
                events.push({ type: 'done' })
                return events
            }

            if (!raw || typeof raw !== 'object') {
                return events
            }

            const record = raw as Record<string, unknown>
            const readString = (
                source: Record<string, unknown> | undefined,
                key: string
            ): string | undefined => {
                if (!source) return undefined
                const value = source[key]
                return typeof value === 'string' ? value : undefined
            }
            const readNumber = (
                source: Record<string, unknown> | undefined,
                key: string
            ): number | undefined => {
                if (!source) return undefined
                const value = source[key]
                return typeof value === 'number' ? value : undefined
            }

            // Handle session event
            if (eventName === 'session') {
                const status = readString(record, 'status')
                const sessionId = readString(record, 'session_id')
                if (sessionId) {
                    events.push({
                        type: 'session',
                        session_id: sessionId,
                        is_new_session: status === 'created',
                        name: readString(record, 'name'),
                        agent_type: readString(record, 'agent_type'),
                        model_id: readString(record, 'model_id'),
                        created_at: readString(record, 'created_at')
                    })
                }
                return events
            }

            // Handle thinking event
            if (eventName === 'thinking') {
                const status = readString(record, 'status')
                if (status === 'delta') {
                    const delta = readString(record, 'delta')
                    if (delta) {
                        events.push({
                            type: 'thinking',
                            status: 'delta',
                            delta,
                            signature: readString(record, 'signature')
                        })
                    }
                }
                return events
            }

            // Handle content event
            if (eventName === 'content') {
                const status = readString(record, 'status')
                if (status === 'start') {
                    events.push({ type: 'content_start' })
                } else if (status === 'delta') {
                    const delta = readString(record, 'delta')
                    if (delta) {
                        events.push({ type: 'token', content: delta })
                    }
                }
                // Ignore 'stop' status as per user request
                return events
            }

            // Handle complete event
            if (eventName === 'complete') {
                const status = readString(record, 'status')
                if (status === 'done') {
                    events.push({
                        type: 'complete',
                        message_id: readString(record, 'message_id'),
                        finish_reason: readString(record, 'finish_reason'),
                        elapsed_ms: readNumber(record, 'elapsed_ms')
                    })
                    events.push({ type: 'done' })
                }
                return events
            }

            // Handle tool_call event
            if (eventName === 'tool_call') {
                const status = readString(record, 'status')
                const id = readString(record, 'id')
                const name = readString(record, 'name')

                if (status === 'start' && id && name) {
                    events.push({
                        type: 'tool_call_start',
                        id,
                        name,
                        call_type: readString(record, 'type') ?? 'function'
                    })
                } else if (status === 'delta' && id) {
                    const delta = readString(record, 'delta')
                    if (delta) {
                        events.push({
                            type: 'tool_call_delta',
                            id,
                            delta
                        })
                    }
                } else if (status === 'stop' && id && name) {
                    const input = readString(record, 'input')
                    if (input) {
                        events.push({
                            type: 'tool_call_stop',
                            id,
                            name,
                            input
                        })
                    }
                }
                return events
            }

            // Handle tool_result event
            if (eventName === 'tool_result') {
                const status = readString(record, 'status')
                if (status === 'info') {
                    const toolCallId = readString(record, 'tool_call_id')
                    const name = readString(record, 'name')
                    const output =
                        typeof record?.output === 'object'
                            ? JSON.stringify(record?.output)
                            : readString(record, 'output')

                    if (toolCallId && name && output !== undefined) {
                        events.push({
                            type: 'tool_result',
                            tool_call_id: toolCallId,
                            name,
                            output,
                            is_error: record.is_error === true
                        })
                    }
                }
                return events
            }

            // Handle error event
            if (eventName === 'error') {
                const message =
                    readString(record, 'message') ?? readString(record, 'error')
                events.push({ type: 'error', message })
                return events
            }

            return events
        }

        const flushBuffer = async (
            remaining: string,
            finalize = false
        ): Promise<boolean> => {
            let working = remaining
            let separatorIndex = working.indexOf('\n\n')

            while (separatorIndex !== -1) {
                const chunk = working.slice(0, separatorIndex)
                const parsed = parseSSEBlock(chunk)

                if (parsed?.data) {
                    try {
                        const raw = JSON.parse(parsed.data)
                        const events = normalizeStreamEvent(parsed.event, raw)
                        for (const event of events) {
                            onEvent(event)
                            if (event.type === 'done') {
                                buffer = ''
                                try {
                                    await reader.cancel()
                                } catch {
                                    // Ignore cancel errors
                                }
                                return true // Signal stream is done
                            }
                        }
                    } catch (error) {
                        console.error('Failed to parse stream chunk', error)
                    }
                } else if (parsed?.event && !parsed.data) {
                    const events = normalizeStreamEvent(parsed.event, {})
                    for (const event of events) {
                        onEvent(event)
                        if (event.type === 'done') {
                            buffer = ''
                            try {
                                await reader.cancel()
                            } catch {
                                // Ignore cancel errors
                            }
                            return true // Signal stream is done
                        }
                    }
                }

                working = working.slice(separatorIndex + 2)
                separatorIndex = working.indexOf('\n\n')
            }

            if (finalize) {
                const parsed = parseSSEBlock(working)
                if (parsed?.data) {
                    try {
                        const raw = JSON.parse(parsed.data)
                        const events = normalizeStreamEvent(parsed.event, raw)
                        for (const event of events) {
                            onEvent(event)
                        }
                    } catch (error) {
                        console.error(
                            'Failed to parse trailing stream chunk',
                            error
                        )
                    }
                }
            } else {
                buffer = working
            }

            return false // Continue processing
        }

        try {
            while (true) {
                const { value, done } = await reader.read()
                buffer += decoder.decode(value, { stream: !done })

                if (done) {
                    await flushBuffer(buffer, true)
                    break
                }

                const shouldStop = await flushBuffer(buffer)
                if (shouldStop) {
                    break
                }

                if (controller.signal.aborted) break
            }
        } catch (error) {
            if ((error as DOMException).name !== 'AbortError') {
                console.error('Chat stream interrupted', error)
                onEvent({
                    type: 'error',
                    message:
                        error instanceof Error
                            ? error.message
                            : 'Unexpected streaming error'
                })
            }
        } finally {
            try {
                await reader.cancel()
            } catch {
                // Ignore cancel errors
            }
            controller.abort()
        }
    }
}

export const chatService = new ChatService()
