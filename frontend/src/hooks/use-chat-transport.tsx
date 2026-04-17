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
    selectSelectedChatModel,
    selectAvailableModels,
    selectSelectedSlideTemplate,
    clearCurrentMessageFileIds,
    selectCurrentMessageFileIds,
    selectChatToolSettings,
    selectActiveSessionId,
    selectSelectedGitHubRepository,
    selectChatMediaPreference,
    selectCouncilPreference,
    userApi,
    sessionApi
} from '@/state'
import {
    buildMediaPreferencesPayload,
    getEffectiveMediaFileIds
} from '@/hooks/use-chat-media-preference'

interface UseChatTransportOptions {
    autoStopOnUnmount?: boolean
}

export type StreamCallbacks = {
    onSession?: (params: {
        sessionId: string
        isNewSession: boolean
        name?: string
        titlePending?: boolean
        agentType?: string
        createdAt?: string
    }) => void
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
    onToolProgress?: (params: {
        tool_call_id: string
        name: string
        output: string
    }) => void
    onUsage?: (params: {
        input_tokens: number
        output_tokens: number
        total_tokens: number
    }) => void
    onCouncilMember?: (params: {
        status: 'start' | 'delta' | 'complete' | 'error'
        model_id: string
        model_name?: string
        delta?: string
        content?: string
        error?: string
    }) => void
    onCouncilSynthesis?: (params: {
        status: 'start' | 'delta' | 'complete' | 'error'
        model_id?: string
        delta?: string
        content?: string
        error?: string
    }) => void
    onDone?: () => void
    onError?: (message?: string, code?: string) => void
}

export type SubmitOptions =
    | string
    | {
          sessionId?: string
          files?: string[]
          callbacks?: StreamCallbacks
      }

type SubmitOptionsExtracted = {
    sessionId?: string
    files?: string[]
    callbacks?: StreamCallbacks
}

function extractSubmitOptions(value?: SubmitOptions): SubmitOptionsExtracted {
    if (!value) return { sessionId: undefined, callbacks: undefined }
    if (typeof value === 'string') {
        return { sessionId: value, callbacks: undefined }
    }
    return {
        sessionId: value.sessionId,
        files: value.files,
        callbacks: value.callbacks
    }
}

export function useChatTransport(options?: UseChatTransportOptions) {
    const autoStopOnUnmount = options?.autoStopOnUnmount ?? true
    const dispatch = useAppDispatch()
    const selectedModelId = useAppSelector(selectSelectedChatModel)
    const availableModels = useAppSelector(selectAvailableModels)
    const selectedSlideTemplate = useAppSelector(selectSelectedSlideTemplate)
    const currentMessageFileIds = useAppSelector(selectCurrentMessageFileIds)
    const chatToolSettings = useAppSelector(selectChatToolSettings)
    const activeSessionId = useAppSelector(selectActiveSessionId)
    const selectedGitHubRepository = useAppSelector(
        selectSelectedGitHubRepository
    )
    const chatMediaPreference = useAppSelector(selectChatMediaPreference)
    const councilPreference = useAppSelector(selectCouncilPreference)

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
                chatService
                    .stopConversation(activeSessionIdRef.current)
                    .catch((error) => {
                        console.error(
                            'Failed to stop conversation on server:',
                            error
                        )
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

            const { sessionId, callbacks, files: overrideFileIds } =
                extractSubmitOptions(options)

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

                const baseFileIds =
                    overrideFileIds && overrideFileIds.length > 0
                        ? overrideFileIds
                        : currentMessageFileIds
                const effectiveFileIds = getEffectiveMediaFileIds(
                    chatMediaPreference,
                    baseFileIds
                )
                const { messageFileIds, mediaPreferences } =
                    buildMediaPreferencesPayload(
                        chatMediaPreference,
                        effectiveFileIds
                    )

                // Build council preferences if enabled
                const councilPayload =
                    councilPreference.enabled &&
                    councilPreference.councilModelIds.length >= 2
                        ? {
                              enabled: true,
                              council_models: councilPreference.councilModelIds.map(
                                  (id) => ({ model_id: id })
                              ),
                              synthesis_model_id:
                                  councilPreference.synthesisModelId || model.id
                          }
                        : undefined

                const payload: ChatQueryPayload = {
                    session_id: sessionId,
                    model_id: model.id,
                    text: trimmedQuestion,
                    files: messageFileIds,
                    tools: chatToolSettings,
                    media_preferences: mediaPreferences,
                    github_repository: selectedGitHubRepository,
                    council_preferences: councilPayload
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
                                    isNewSession,
                                    name: event.name,
                                    titlePending: event.title_pending,
                                    agentType: event.agent_type,
                                    createdAt: event.created_at
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
                            case 'tool_progress': {
                                callbacks?.onToolProgress?.({
                                    tool_call_id: event.tool_call_id,
                                    name: event.name,
                                    output: event.output
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
                            case 'council_member': {
                                callbacks?.onCouncilMember?.({
                                    status: event.status,
                                    model_id: event.model_id,
                                    model_name: event.model_name,
                                    delta: event.delta,
                                    content: event.content,
                                    error: event.error
                                })
                                break
                            }
                            case 'council_synthesis': {
                                callbacks?.onCouncilSynthesis?.({
                                    status: event.status,
                                    model_id: event.model_id,
                                    delta: event.delta,
                                    content: event.content,
                                    error: event.error
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
                            callbacks?.onError?.(event.message, event.code)
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
                const errorStatus =
                    typeof error === 'object' &&
                    error !== null &&
                    'status' in error
                        ? (error as { status?: number }).status
                        : undefined
                const isInsufficientCredits =
                    error instanceof Error &&
                    errorStatus === 402
                callbacks?.onError?.(
                    error instanceof Error ? error.message : undefined,
                    isInsufficientCredits ? 'insufficient_credits' : undefined
                )
                if (!isInsufficientCredits) {
                    toast.error(
                        'Unable to submit your question right now. Please try again.'
                    )
                }
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
            chatToolSettings,
            selectedGitHubRepository,
            chatMediaPreference,
            councilPreference
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

    const resetSubmitting = useCallback(() => {
        setIsSubmitting(false)
    }, [])

    return { submitChatQuery, isSubmitting, stopActiveStream, resetSubmitting }
}
