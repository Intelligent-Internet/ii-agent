import { useCallback, useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'

import {
    chatService,
    type ChatQueryPayload,
    type ChatStreamEvent
} from '@/services/chat.service'
import {
    useAppDispatch,
    useAppSelector,
    setLoading,
    setIsCreatingSession,
    setIsFromNewQuestion,
    setCurrentQuestion,
    setRequireClearFiles,
    resetSlideTemplate,
    setActiveSessionId,
    selectSelectedModel,
    selectAvailableModels,
    selectSelectedSlideTemplate,
    clearCurrentMessageFileIds,
    selectCurrentMessageFileIds,
    selectChatToolSettings,
    selectActiveSessionId,
    userApi,
    sessionApi
} from '@/state'

interface UseChatTransportOptions {
    autoStopOnUnmount?: boolean
}

export type StreamCallbacks = {
    onSession?: (params: { sessionId: string; isNewSession: boolean }) => void
    onThinking?: (params: { delta: string; signature?: string }) => void
    onContentStart?: () => void
    onToken?: (token: string) => void
    onToolCallStart?: (params: { id: string; name: string }) => void
    onToolCallDelta?: (params: { id: string; delta: string }) => void
    onToolCallStop?: (params: {
        id: string
        name: string
        input: string
    }) => void
    onToolResult?: (params: {
        tool_call_id: string
        name: string
        output: string
        is_error: boolean
    }) => void
    onUsage?: (params: {
        input_tokens: number
        output_tokens: number
        total_tokens: number
    }) => void
    onDone?: () => void
    onError?: (message?: string) => void
}

export type SubmitOptions =
    | string
    | {
        sessionId?: string
        callbacks?: StreamCallbacks
    }

type SubmitOptionsExtracted = {
    sessionId?: string
    callbacks?: StreamCallbacks
}

function extractSubmitOptions(value?: SubmitOptions): SubmitOptionsExtracted {
    if (!value) return { sessionId: undefined, callbacks: undefined }
    if (typeof value === 'string') {
        return { sessionId: value, callbacks: undefined }
    }
    return {
        sessionId: value.sessionId,
        callbacks: value.callbacks
    }
}

export function useChatTransport(options?: UseChatTransportOptions) {
    const autoStopOnUnmount = options?.autoStopOnUnmount ?? true
    const dispatch = useAppDispatch()
    const selectedModelId = useAppSelector(selectSelectedModel)
    const availableModels = useAppSelector(selectAvailableModels)
    const selectedSlideTemplate = useAppSelector(selectSelectedSlideTemplate)
    const currentMessageFileIds = useAppSelector(selectCurrentMessageFileIds)
    const chatToolSettings = useAppSelector(selectChatToolSettings)
    const activeSessionId = useAppSelector(selectActiveSessionId)

    const [isSubmitting, setIsSubmitting] = useState(false)
    const activeStreamControllerRef = useRef<AbortController | null>(null)
    const activeSessionIdRef = useRef<string | null>(null)

    // Keep ref in sync with Redux state
    useEffect(() => {
        activeSessionIdRef.current = activeSessionId
    }, [activeSessionId])

    const stopActiveStream = useCallback(() => {
        if (activeStreamControllerRef.current) {
            activeStreamControllerRef.current.abort()
            activeStreamControllerRef.current = null

            // Call the backend API to cancel the running task for chat mode
            // Read from ref to get the latest session ID value
            if (activeSessionIdRef.current) {
                chatService.stopConversation(activeSessionIdRef.current).catch((error) => {
                    console.error('Failed to stop conversation on server:', error)
                })
            }
        }
    }, [])

    const submitChatQuery = useCallback(
        async (question: string, options?: SubmitOptions): Promise<void> => {
            const trimmedQuestion = question.trim()
            if (!trimmedQuestion) {
                toast.error('Please enter a question before submitting.')
                return undefined
            }

            stopActiveStream()

            setIsSubmitting(true)
            dispatch(setLoading(true))

            const { sessionId, callbacks } = extractSubmitOptions(options)

            if (!sessionId) {
                dispatch(setIsCreatingSession(true))
            }

            try {
                const model =
                    availableModels.find(
                        (item) => item.id === selectedModelId
                    ) ?? availableModels[0]

                if (!model) {
                    toast.error(
                        'No AI model is configured. Please add a model in settings first.'
                    )
                    throw new Error('No model available')
                }

                const payload: ChatQueryPayload = {
                    session_id: sessionId,
                    model_id: model.id,
                    text: trimmedQuestion,
                    files: currentMessageFileIds,
                    tools: chatToolSettings
                }

                dispatch(setCurrentQuestion(''))
                dispatch(setRequireClearFiles(true))
                if (selectedSlideTemplate) {
                    dispatch(resetSlideTemplate())
                }

                const controller = new AbortController()
                activeStreamControllerRef.current = controller
                let sessionEstablished = Boolean(sessionId)

                await chatService.streamQuery(payload, {
                    signal: controller.signal,
                    onEvent: (event: ChatStreamEvent) => {
                        switch (event.type) {
                            case 'session': {
                                const isNewSession =
                                    event.is_new_session ?? !sessionEstablished
                                sessionEstablished = true
                                dispatch(setActiveSessionId(event.session_id))
                                dispatch(setIsCreatingSession(false))
                                if (isNewSession) {
                                    dispatch(setIsFromNewQuestion(true))
                                    // Invalidate sessions cache to refresh the session list
                                    dispatch(
                                        sessionApi.util.invalidateTags([
                                            { type: 'Sessions', id: 'LIST' }
                                        ])
                                    )
                                }
                                callbacks?.onSession?.({
                                    sessionId: event.session_id,
                                    isNewSession
                                })
                                break
                            }
                            case 'thinking': {
                                callbacks?.onThinking?.({
                                    delta: event.delta,
                                    signature: event.signature
                                })
                                break
                            }
                            case 'content_start': {
                                callbacks?.onContentStart?.()
                                break
                            }
                            case 'token': {
                                callbacks?.onToken?.(event.content)
                                break
                            }
                            case 'tool_call_start': {
                                callbacks?.onToolCallStart?.({
                                    id: event.id,
                                    name: event.name
                                })
                                break
                            }
                            case 'tool_call_delta': {
                                callbacks?.onToolCallDelta?.({
                                    id: event.id,
                                    delta: event.delta
                                })
                                break
                            }
                            case 'tool_call_stop': {
                                callbacks?.onToolCallStop?.({
                                    id: event.id,
                                    name: event.name,
                                    input: event.input
                                })
                                break
                            }
                            case 'tool_result': {
                                callbacks?.onToolResult?.({
                                    tool_call_id: event.tool_call_id,
                                    name: event.name,
                                    output: event.output,
                                    is_error: event.is_error ?? false
                                })
                                break
                            }
                            case 'usage': {
                                callbacks?.onUsage?.({
                                    input_tokens: event.input_tokens,
                                    output_tokens: event.output_tokens,
                                    total_tokens: event.total_tokens
                                })
                                break
                            }
                            case 'done': {
                                activeStreamControllerRef.current = null
                                // Invalidate credit cache to refresh balance and usage
                                dispatch(
                                    userApi.util.invalidateTags([
                                        'CreditBalance',
                                        'CreditUsage'
                                    ])
                                )
                                callbacks?.onDone?.()
                                break
                            }
                            case 'error': {
                                activeStreamControllerRef.current = null
                                const errorMessage = event.message || 'An error occurred'
                                callbacks?.onError?.(errorMessage)
                                // Show toast for user-facing errors
                                if (errorMessage.includes('timeout')) {
                                    toast.error('Request timed out. The server took too long to respond.')
                                } else if (errorMessage) {
                                    toast.error(errorMessage)
                                }
                                break
                            }
                            default:
                                break
                        }
                    }
                })
                dispatch(clearCurrentMessageFileIds())
            } catch (error) {
                console.error('Failed to submit chat query', error)
                callbacks?.onError?.(
                    error instanceof Error ? error.message : undefined
                )
                toast.error(
                    'Unable to submit your question right now. Please try again.'
                )
                throw error
            } finally {
                stopActiveStream()
                dispatch(setIsCreatingSession(false))
                dispatch(setLoading(false))
                setIsSubmitting(false)
            }
        },
        [
            availableModels,
            currentMessageFileIds,
            clearCurrentMessageFileIds,
            dispatch,
            selectedModelId,
            selectedSlideTemplate,
            stopActiveStream,
            chatToolSettings
        ]
    )

    useEffect(() => {
        if (!autoStopOnUnmount) {
            return undefined
        }

        return () => {
            stopActiveStream()
        }
    }, [autoStopOnUnmount, stopActiveStream])

    return { submitChatQuery, isSubmitting, stopActiveStream }
}
