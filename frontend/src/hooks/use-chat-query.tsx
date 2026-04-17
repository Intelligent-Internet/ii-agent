import {
    createContext,
    useCallback,
    useContext,
    useEffect,
    useMemo,
    useRef,
    useState,
    type ReactNode
} from 'react'
import { toast } from 'sonner'
import { useTranslation } from 'react-i18next'

import { chatService } from '@/services/chat.service'
import {
    storybookService,
    type Storybook,
    type StorybookGenerationResponse
} from '@/services/storybook.service'
import {
    useAppSelector,
    useAppDispatch,
    selectSelectedChatModel,
    selectCurrentMessageFileIds,
    selectUploadedFiles,
    clearCurrentMessageFileIds,
    setChatMediaPreference,
    selectChatMediaPreference,
    upsertSession,
    userApi
} from '@/state'
import { isImageFile } from '@/lib/utils'
import {
    type ISession,
    type ImageAspectRatio,
    type ImageResolution,
    type PageCount,
    type TextPosition,
    type StorybookLanguage,
    type StorybookGenre,
    type VideoSettings,
    type VideoFrameReference
} from '@/typings/agent'
import { type AdvancedModeSettings, type ChatHistoryMessage } from '@/typings/chat'
import { sessionService } from '@/services/session.service'
import {
    type AgentStatusState,
    type ChatMessage,
    type ContentPart
} from '@/utils/chat-events'
import { useNavigate } from 'react-router'
import { useChatTransport } from './use-chat-transport'
import { type ChatMediaType } from '@/constants/media-type-config'
import { getDefaultChatMediaPreference } from '@/utils/default-models'
import { useMediaModels } from './use-media-models'
import {
    getEffectiveMediaFileIds,
    getMediaMetadata
} from '@/hooks/use-chat-media-preference'
import { getStorybookLanguageFromLocale } from '@/utils/storybook-language'

type UploadedFile = {
    id: string
    name: string
    path: string
    size: number
    folderName?: string
    fileCount?: number
    fileIds?: string[] // Individual file IDs for folders
}

type StorybookPollingEntry = {
    timerId: number
    toolCallId?: string
}

type ChatSharedState = {
    sessionId: string | null
    sessionData?: ISession
    sessionError: string | null
    messages: ChatMessage[]
    chatStatus: AgentStatusState
    inputValue: string
    isHistoryLoading: boolean
    isLoadingMore: boolean
    hasMoreMessages: boolean
    isWaitingForNextEvent: boolean
    showThinking: boolean
    advancedModeSettings: AdvancedModeSettings | null
    isStorybookPolling: boolean
    editingMessageId: string | null
}

type ChatContextValue = ChatSharedState & {
    isSubmitting: boolean
    sendMessage: (overrideQuestion?: string) => Promise<void>
    stopActiveStream: () => void
    cancelStorybookGeneration: () => Promise<void>
    resetSubmitting: () => void
    resetConversationState: () => void
    hydrateSessionHistory: (sessionId: string) => Promise<void>
    loadMoreMessages: () => Promise<void>
    setInputValue: (value: string) => void
    setSessionId: (sessionId: string | null) => void
    setAdvancedModeSettings: (settings: AdvancedModeSettings | null) => void
    setEditingMessageId: (messageId: string | null) => void
    editMessage: (messageId: string, newContent: string) => Promise<void>
}

const INITIAL_CHAT_STATE: ChatSharedState = {
    sessionId: null,
    sessionData: undefined,
    sessionError: null,
    messages: [],
    chatStatus: 'ready',
    inputValue: '',
    isHistoryLoading: false,
    isLoadingMore: false,
    hasMoreMessages: false,
    isWaitingForNextEvent: false,
    showThinking: false,
    advancedModeSettings: null,
    isStorybookPolling: false,
    editingMessageId: null
}

const ChatContext = createContext<ChatContextValue | undefined>(undefined)
const MAX_PENDING_TITLE_POLLS = 40

const parseStorybookPayload = (
    payload: unknown
): StorybookGenerationResponse | null => {
    if (!payload) return null
    if (typeof payload === 'string') {
        try {
            return JSON.parse(payload) as StorybookGenerationResponse
        } catch {
            return null
        }
    }
    if (typeof payload === 'object') {
        return payload as StorybookGenerationResponse
    }
    return null
}

const toToolResultOutput = (content: unknown): ContentPart['output'] => {
    const parsed =
        typeof content === 'string' ? parseStorybookPayload(content) : content

    if (
        parsed &&
        typeof parsed === 'object' &&
        'type' in parsed &&
        typeof (parsed as { type?: unknown }).type === 'string'
    ) {
        return parsed as ContentPart['output']
    }

    return undefined
}

const getStorybookProgressFlags = (response: StorybookGenerationResponse) => {
    if (response.type !== 'storybook_progress') {
        return {
            isFailed: false,
            isComplete: true,
            isGenerating: false
        }
    }

    const hasAllPages =
        response.total_pages > 0 &&
        response.completed_pages >= response.total_pages
    const isFailed = response.status === 'failed'
    const isComplete = response.status === 'completed' || hasAllPages
    const isGenerating =
        response.status === 'generating' && !isFailed && !isComplete

    return { isFailed, isComplete, isGenerating }
}

const parseStorybookTime = (value?: string | null) => {
    if (!value) return 0
    const parsed = Date.parse(value)
    return Number.isNaN(parsed) ? 0 : parsed
}

const pickLatestStorybook = (
    storybooks: Storybook[],
    filterIds?: Set<string>
) => {
    const candidates = filterIds
        ? storybooks.filter((storybook) => filterIds.has(storybook.id))
        : storybooks
    if (candidates.length === 0) return undefined

    return candidates.reduce((latest, current) => {
        const latestTime = Math.max(
            parseStorybookTime(latest.updated_at),
            parseStorybookTime(latest.created_at)
        )
        const currentTime = Math.max(
            parseStorybookTime(current.updated_at),
            parseStorybookTime(current.created_at)
        )

        if (currentTime > latestTime) return current
        if (currentTime < latestTime) return latest
        if ((current.version || 0) > (latest.version || 0)) {
            return current
        }
        return latest
    }, candidates[0])
}

function useChatProviderValue(): ChatContextValue {
    const { submitChatQuery, isSubmitting, stopActiveStream, resetSubmitting } =
        useChatTransport({ autoStopOnUnmount: false })
    const dispatch = useAppDispatch()
    const currentMessageFileIds = useAppSelector(selectCurrentMessageFileIds)
    const uploadedFiles = useAppSelector(selectUploadedFiles) as UploadedFile[]
    const selectedModelId = useAppSelector(selectSelectedChatModel)
    const chatMediaPreferenceFromStore = useAppSelector(selectChatMediaPreference)
    const { i18n } = useTranslation()
    const navigate = useNavigate()
    const { getModelsForMediaType } = useMediaModels()

    const [state, setState] = useState<ChatSharedState>(INITIAL_CHAT_STATE)
    const stateRef = useRef(state)

    const streamingMessageIdRef = useRef<string | null>(null)
    const activeSessionIdRef = useRef<string | null>(null)
    const hydratedSessionsRef = useRef<Set<string>>(new Set())
    const previousSessionIdRef = useRef<string | null>(null)
    const chatMediaPreferenceRef = useRef(chatMediaPreferenceFromStore)
    const pendingTitlePollCountsRef = useRef<Map<string, number>>(new Map())
    const storybookPollingRef = useRef<Map<string, StorybookPollingEntry>>(
        new Map()
    )
    const storybookProgressRefreshRef = useRef<Map<string, number>>(new Map())
    const storybookProgressCheckedRef = useRef<string | null>(null)
    const defaultStorybookLanguage = useMemo(
        () => getStorybookLanguageFromLocale(i18n.language),
        [i18n.language]
    )

    const setChatState = useCallback(
        (
            updater:
                | Partial<ChatSharedState>
                | ((prev: ChatSharedState) => ChatSharedState)
        ) => {
            setState((prev) => {
                const next =
                    typeof updater === 'function'
                        ? (
                              updater as (
                                  prevState: ChatSharedState
                              ) => ChatSharedState
                          )(prev)
                        : { ...prev, ...updater }
                stateRef.current = next
                return next
            })
        },
        []
    )

    useEffect(() => {
        stateRef.current = state
    }, [state])

    useEffect(() => {
        chatMediaPreferenceRef.current = chatMediaPreferenceFromStore
    }, [chatMediaPreferenceFromStore])

    useEffect(() => {
        const prevSessionId = previousSessionIdRef.current
        const nextSessionId = state.sessionId

        // Only clear file IDs when switching FROM one existing session TO another existing session
        // Don't clear when: no session (new chat), or transitioning to/from new chat
        if (
            prevSessionId !== null &&
            nextSessionId !== null &&
            nextSessionId !== prevSessionId &&
            currentMessageFileIds.length > 0
        ) {
            dispatch(clearCurrentMessageFileIds())
        }

        // Clear mini_tools when switching sessions to prevent reuse from old session
        if (
            prevSessionId !== null &&
            nextSessionId !== null &&
            nextSessionId !== prevSessionId &&
            chatMediaPreferenceFromStore.mini_tools
        ) {
            dispatch(
                setChatMediaPreference({
                    ...chatMediaPreferenceFromStore,
                    mini_tools: undefined
                })
            )
        }

        previousSessionIdRef.current = nextSessionId
    }, [currentMessageFileIds.length, dispatch, state.sessionId, chatMediaPreferenceFromStore])

    useEffect(() => {
        const currentSessionId = state.sessionId
        if (!currentSessionId) {
            return
        }
        if (!state.sessionData?.title_pending) {
            pendingTitlePollCountsRef.current.delete(currentSessionId)
            return
        }
        const pollCount =
            pendingTitlePollCountsRef.current.get(currentSessionId) ?? 0
        if (pollCount >= MAX_PENDING_TITLE_POLLS) {
            return
        }

        let cancelled = false
        const timerId = window.setTimeout(async () => {
            try {
                const session = await sessionService.getSession(currentSessionId)
                if (cancelled || activeSessionIdRef.current !== currentSessionId) {
                    return
                }

                if (session.title_pending) {
                    pendingTitlePollCountsRef.current.set(
                        currentSessionId,
                        pollCount + 1
                    )
                } else {
                    pendingTitlePollCountsRef.current.delete(currentSessionId)
                }
                dispatch(upsertSession(session))
                setChatState((prev) => {
                    if (prev.sessionId !== currentSessionId) {
                        return prev
                    }

                    return {
                        ...prev,
                        sessionData: session
                    }
                })
            } catch (error) {
                if (!cancelled) {
                    pendingTitlePollCountsRef.current.set(
                        currentSessionId,
                        pollCount + 1
                    )
                    console.error('Failed to refresh pending session title', error)
                }
            }
        }, 1500)

        return () => {
            cancelled = true
            window.clearTimeout(timerId)
        }
    }, [dispatch, setChatState, state.sessionData, state.sessionId])

    const updateMessagePartByToolCall = useCallback(
        (
            toolCallId: string,
            updater: (existing: ContentPart | undefined) => ContentPart | null
        ) => {
            setChatState((prev) => {
                const partId = `result-${toolCallId}`
                const resultIndexes: number[] = []
                prev.messages.forEach((message, index) => {
                    const parts = message.parts || []
                    if (
                        parts.some(
                            (part) =>
                                part.type === 'tool_result' &&
                                part.tool_call_id === toolCallId
                        )
                    ) {
                        resultIndexes.push(index)
                    }
                })

                let targetIndexes = resultIndexes
                if (targetIndexes.length === 0) {
                    const fallbackIndex = prev.messages.findIndex((message) => {
                        const parts = message.parts || []
                        return parts.some(
                            (part) =>
                                part.id === partId ||
                                (part.type === 'tool_call' &&
                                    part.id === toolCallId)
                        )
                    })
                    if (fallbackIndex === -1) return prev
                    targetIndexes = [fallbackIndex]
                }

                const targetSet = new Set(targetIndexes)
                const nextMessages = prev.messages.map((message, index) => {
                    if (!targetSet.has(index)) return message

                    const parts = message.parts || []
                    const existingIndex = parts.findIndex(
                        (part) =>
                            part.id === partId ||
                            (part.type === 'tool_result' &&
                                part.tool_call_id === toolCallId)
                    )

                    let updatedParts: ContentPart[]
                    if (existingIndex >= 0) {
                        const updated = updater(parts[existingIndex])
                        if (updated === null) {
                            updatedParts = [
                                ...parts.slice(0, existingIndex),
                                ...parts.slice(existingIndex + 1)
                            ]
                        } else {
                            updatedParts = [
                                ...parts.slice(0, existingIndex),
                                updated,
                                ...parts.slice(existingIndex + 1)
                            ]
                        }
                    } else {
                        const newPart = updater(undefined)
                        updatedParts = newPart ? [...parts, newPart] : parts
                    }

                    const aggregatedContent = updatedParts
                        .filter((part) => part.type === 'text')
                        .map((part) => part.text || '')
                        .join('')

                    return {
                        ...message,
                        parts: updatedParts,
                        content: aggregatedContent
                    }
                })

                return {
                    ...prev,
                    messages: nextMessages
                }
            })
        },
        [setChatState]
    )

    const updateToolResultContent = useCallback(
        (
            toolCallId: string,
            name: string,
            content: unknown,
            isError: boolean = false
        ) => {
            const payload =
                typeof content === 'string' ? content : JSON.stringify(content)
            const outputValue = toToolResultOutput(content)
            updateMessagePartByToolCall(toolCallId, () => ({
                type: 'tool_result',
                id: `result-${toolCallId}`,
                tool_call_id: toolCallId,
                name,
                content: payload,
                output: outputValue,
                metadata: '',
                is_error: isError
            }))
        },
        [updateMessagePartByToolCall]
    )

    const updateToolResultContentByStorybookId = useCallback(
        (storybookId: string, content: unknown, isError: boolean = false) => {
            if (!storybookId) return
            const payload =
                typeof content === 'string' ? content : JSON.stringify(content)
            const outputValue = toToolResultOutput(content)

            setChatState((prev) => {
                let didUpdate = false
                const nextMessages = prev.messages.map((message) => {
                    const parts = message.parts || []
                    let didUpdateMessage = false

                    const updatedParts = parts.map((part) => {
                        if (
                            part.type !== 'tool_result' ||
                            part.name !== 'generate_storybook'
                        ) {
                            return part
                        }

                        const parsed = parseStorybookPayload(
                            part.output ?? part.content
                        )
                        if (parsed?.storybook_id !== storybookId) {
                            return part
                        }

                        didUpdate = true
                        didUpdateMessage = true
                        return {
                            ...part,
                            content: payload,
                            output: outputValue,
                            is_error: isError
                        }
                    })

                    if (!didUpdateMessage) return message

                    const aggregatedContent = updatedParts
                        .filter((part) => part.type === 'text')
                        .map((part) => part.text || '')
                        .join('')

                    return {
                        ...message,
                        parts: updatedParts,
                        content: aggregatedContent
                    }
                })

                if (!didUpdate) return prev
                return {
                    ...prev,
                    messages: nextMessages
                }
            })
        },
        [setChatState]
    )

    const resetConversationState = useCallback(() => {
        streamingMessageIdRef.current = null
        storybookPollingRef.current.forEach((entry) =>
            window.clearInterval(entry.timerId)
        )
        storybookPollingRef.current.clear()
        setChatState((prev) => ({
            ...prev,
            messages: [],
            chatStatus: 'ready',
            advancedModeSettings: null,
            isStorybookPolling: false,
            hasMoreMessages: false,
            isLoadingMore: false
        }))
        if (currentMessageFileIds.length > 0) {
            dispatch(clearCurrentMessageFileIds())
        }
    }, [currentMessageFileIds.length, dispatch, setChatState])

    const stopStorybookPolling = useCallback((storybookId: string) => {
        const entry = storybookPollingRef.current.get(storybookId)
        if (entry) {
            window.clearInterval(entry.timerId)
            storybookPollingRef.current.delete(storybookId)
        }
        if (storybookPollingRef.current.size === 0) {
            setChatState((prev) =>
                prev.isStorybookPolling
                    ? { ...prev, isStorybookPolling: false }
                    : prev
            )
        }
    }, [setChatState])

    const stopOtherStorybookPolling = useCallback(
        (storybookId?: string) => {
            const ids = Array.from(storybookPollingRef.current.keys())
            ids.forEach((id) => {
                if (!storybookId || id !== storybookId) {
                    stopStorybookPolling(id)
                }
            })
        },
        [stopStorybookPolling]
    )

    const startStorybookPolling = useCallback(
        (
            storybookId: string,
            toolCallId?: string,
            options?: { skipImmediatePoll?: boolean }
        ) => {
            if (!storybookId) return

            const existing = storybookPollingRef.current.get(storybookId)
            if (existing) {
                if (!existing.toolCallId && toolCallId) {
                    storybookPollingRef.current.set(storybookId, {
                        ...existing,
                        toolCallId
                    })
                }
                return
            }

            const poll = async () => {
                if (!storybookPollingRef.current.has(storybookId)) return
                try {
                    const response =
                        await storybookService.getStorybookGenerationStatus(
                            storybookId
                        )
                    const { isFailed, isComplete } =
                        getStorybookProgressFlags(response)
                    const entry = storybookPollingRef.current.get(storybookId)
                    const currentToolCallId = entry?.toolCallId

                    if (currentToolCallId) {
                        updateToolResultContent(
                            currentToolCallId,
                            'generate_storybook',
                            response,
                            isFailed
                        )
                    } else {
                        updateToolResultContentByStorybookId(
                            storybookId,
                            response,
                            isFailed
                        )
                    }

                    if (isFailed || isComplete) {
                        stopStorybookPolling(storybookId)
                        // Invalidate credit cache to refresh balance and usage
                        dispatch(
                            userApi.util.invalidateTags([
                                'CreditBalance',
                                'CreditUsage'
                            ])
                        )
                    }
                } catch (error) {
                    console.error(
                        'Failed to poll storybook progress',
                        error
                    )
                }
            }

            const timerId = window.setInterval(poll, 10000)
            storybookPollingRef.current.set(storybookId, {
                timerId,
                toolCallId
            })
            setChatState((prev) =>
                prev.isStorybookPolling
                    ? prev
                    : { ...prev, isStorybookPolling: true }
            )
            if (!options?.skipImmediatePoll) {
                void poll()
            }
        },
        [
            setChatState,
            stopStorybookPolling,
            updateToolResultContent,
            updateToolResultContentByStorybookId,
            dispatch
        ]
    )

    const maybeStartStorybookPolling = useCallback(
        (toolCallId: string, name: string, output?: string | null) => {
            if (name !== 'generate_storybook' || !output) return

            const parsed = parseStorybookPayload(output)
            if (!parsed || parsed.type !== 'storybook_progress') return
            const polling = (parsed as { polling?: boolean }).polling
            if (polling !== true) return
            if (parsed.status && parsed.status !== 'generating') return
            if (!parsed.storybook_id) return

            stopOtherStorybookPolling(parsed.storybook_id)
            startStorybookPolling(parsed.storybook_id, toolCallId)
        },
        [startStorybookPolling, stopOtherStorybookPolling]
    )

    const cancelStorybookGeneration = useCallback(async () => {
        const entries = Array.from(storybookPollingRef.current.entries())
        if (entries.length === 0) return
        await Promise.all(
            entries.map(async ([storybookId, entry]) => {
                try {
                    await storybookService.cancelStorybookGeneration(storybookId)
                    // Fetch final cancelled status and update the UI before
                    // stopping the polling so the error message is displayed.
                    const response =
                        await storybookService.getStorybookGenerationStatus(
                            storybookId
                        )
                    const cancelledPayload: StorybookGenerationResponse =
                        response && response.type === 'storybook_progress'
                            ? {
                                  ...response,
                                  status: 'failed',
                                  error_message: 'storybook_cancelled',
                                  generating_pages: []
                              }
                            : response || {
                                  type: 'storybook_progress',
                                  storybook_id: storybookId,
                                  storybook_name: 'Storybook',
                                  total_pages: 0,
                                  completed_pages: 0,
                                  current_page: 0,
                                  status: 'failed',
                                  pages: [],
                                  error_message: 'storybook_cancelled',
                                  generating_pages: []
                              }
                    const { isFailed } =
                        getStorybookProgressFlags(cancelledPayload)
                    if (entry.toolCallId) {
                        updateToolResultContent(
                            entry.toolCallId,
                            'generate_storybook',
                            cancelledPayload,
                            isFailed
                        )
                    } else {
                        updateToolResultContentByStorybookId(
                            storybookId,
                            cancelledPayload,
                            isFailed
                        )
                    }
                } catch (error) {
                    console.error(
                        'Failed to cancel storybook generation',
                        error
                    )
                }
                // Stop polling immediately so old storybooks don't keep
                // progressing when a new generation starts.
                stopStorybookPolling(storybookId)
            })
        )
    }, [stopStorybookPolling, updateToolResultContent, updateToolResultContentByStorybookId])

    const findToolCallIdForStorybook = useCallback(
        (messages: ChatMessage[], storybookId: string) => {
            for (let i = messages.length - 1; i >= 0; i--) {
                const parts = messages[i].parts ?? []
                for (let j = parts.length - 1; j >= 0; j--) {
                    const part = parts[j]
                    if (
                        part.type !== 'tool_result' ||
                        part.name !== 'generate_storybook'
                    ) {
                        continue
                    }

                    const parsed = parseStorybookPayload(
                        part.output ?? part.content
                    )
                    if (parsed?.storybook_id === storybookId) {
                        return part.tool_call_id || undefined
                    }
                }
            }
            return undefined
        },
        []
    )

    const checkSessionStorybookProgress = useCallback(
        async (
            sessionId: string,
            messages: ChatMessage[],
            options?: { forceSync?: boolean }
        ) => {
            try {
                const toolCallIds = new Set<string>()
                const storybookTargets = new Map<
                    string,
                    {
                        storybookId: string
                        toolCallId?: string
                        statusHint?: 'generating' | 'completed' | 'failed'
                    }
                >()

                messages.forEach((message) => {
                    const parts = message.parts ?? []
                    parts.forEach((part) => {
                        if (
                            part.type === 'tool_call' &&
                            part.name === 'generate_storybook' &&
                            part.id
                        ) {
                            toolCallIds.add(part.id)
                            return
                        }

                        if (
                            part.type !== 'tool_result' ||
                            part.name !== 'generate_storybook'
                        ) {
                            return
                        }

                        if (part.tool_call_id) {
                            toolCallIds.add(part.tool_call_id)
                        }

                        const parsed = parseStorybookPayload(
                            part.output ?? part.content
                        ) as { storybook_id?: string } | null
                        const storybookId =
                            typeof parsed?.storybook_id === 'string'
                                ? parsed.storybook_id
                                : ''
                        if (!storybookId) return

                        const existing = storybookTargets.get(storybookId)
                        if (existing) {
                            if (!existing.toolCallId && part.tool_call_id) {
                                existing.toolCallId = part.tool_call_id
                            }
                            return
                        }

                        storybookTargets.set(storybookId, {
                            storybookId,
                            toolCallId: part.tool_call_id,
                            statusHint:
                                parsed &&
                                typeof parsed === 'object' &&
                                'status' in parsed
                                    ? (parsed.status as
                                          | 'generating'
                                          | 'completed'
                                          | 'failed'
                                          | undefined)
                                    : part.is_error
                                      ? 'failed'
                                      : undefined
                        })
                    })
                })

                if (toolCallIds.size === 0 && storybookTargets.size === 0) {
                    return
                }

                const response =
                    await storybookService.getSessionStorybooks(sessionId)
                if (activeSessionIdRef.current !== sessionId) return

                const storybookIdByToolCallId = new Map<string, string>()
                ;(response.storybooks || []).forEach((storybook) => {
                    const styleJson = storybook.style_json as
                        | Record<string, unknown>
                        | null
                    const generation =
                        styleJson && typeof styleJson === 'object'
                            ? (styleJson.generation as
                                  | Record<string, unknown>
                                  | undefined)
                            : undefined
                    const toolCallId =
                        generation && typeof generation === 'object'
                            ? (generation.tool_call_id as string | undefined)
                            : undefined
                    if (toolCallId && storybook.id) {
                        storybookIdByToolCallId.set(toolCallId, storybook.id)
                    }
                })

                toolCallIds.forEach((toolCallId) => {
                    const storybookId =
                        storybookIdByToolCallId.get(toolCallId)
                    if (!storybookId) return

                    const existing = storybookTargets.get(storybookId)
                    if (existing) {
                        if (!existing.toolCallId) {
                            existing.toolCallId = toolCallId
                        }
                        return
                    }

                    storybookTargets.set(storybookId, {
                        storybookId,
                        toolCallId,
                        statusHint: 'generating'
                    })
                })

                const targets = Array.from(storybookTargets.values())
                if (targets.length === 0) return

                const targetIds = new Set<string>(
                    targets.map((target) => target.storybookId)
                )
                const latestStorybook = pickLatestStorybook(
                    response.storybooks || [],
                    targetIds
                )
                const latestStorybookId = latestStorybook?.id

                stopOtherStorybookPolling(latestStorybookId)

                await Promise.allSettled(
                    targets.map(async (target) => {
                        const shouldFetch =
                            options?.forceSync ||
                            target.statusHint === 'generating' ||
                            !target.statusHint
                        if (!shouldFetch) return

                        const lastRefresh =
                            storybookProgressRefreshRef.current.get(
                                target.storybookId
                            ) || 0
                        if (!options?.forceSync && Date.now() - lastRefresh < 3000) {
                            return
                        }
                        storybookProgressRefreshRef.current.set(
                            target.storybookId,
                            Date.now()
                        )

                        const progress =
                            await storybookService.getStorybookGenerationStatus(
                                target.storybookId
                            )
                        if (activeSessionIdRef.current !== sessionId) return

                        const { isFailed, isGenerating } =
                            getStorybookProgressFlags(progress)

                        const resolvedToolCallId =
                            target.toolCallId ||
                            findToolCallIdForStorybook(
                                messages,
                                target.storybookId
                            )

                        if (resolvedToolCallId) {
                            updateToolResultContent(
                                resolvedToolCallId,
                                'generate_storybook',
                                progress,
                                isFailed
                            )
                        } else {
                            updateToolResultContentByStorybookId(
                                target.storybookId,
                                progress,
                                isFailed
                            )
                        }

                        if (
                            latestStorybookId &&
                            target.storybookId === latestStorybookId &&
                            isGenerating
                        ) {
                            startStorybookPolling(
                                target.storybookId,
                                resolvedToolCallId,
                                { skipImmediatePoll: true }
                            )
                            return
                        }

                        stopStorybookPolling(target.storybookId)
                    })
                )
            } catch (error) {
                console.error(
                    'Failed to check storybook progress',
                    error
                )
            }
        },
        [
            findToolCallIdForStorybook,
            startStorybookPolling,
            stopOtherStorybookPolling,
            stopStorybookPolling,
            updateToolResultContent,
            updateToolResultContentByStorybookId
        ]
    )

    const hydrateSessionHistory = useCallback(
        async (activeSessionId: string, silent = false) => {
            // Check if we've already hydrated this session
            const alreadyHydrated =
                hydratedSessionsRef.current.has(activeSessionId)

            // Only show loading if not silent and not already hydrated
            if (!silent && !alreadyHydrated) {
                setChatState((prev) => ({
                    ...prev,
                    isHistoryLoading: true
                }))
            }

            try {
                const [session, chatHistory, advancedModeSettings] =
                    await Promise.all([
                        sessionService.getSession(activeSessionId),
                        chatService.getChatHistory(activeSessionId),
                        chatService
                            .getAdvancedModeSettings(activeSessionId)
                            .catch(() => null)
                    ])

                // IMPORTANT: Check if the session is still active after async fetch
                // This prevents race conditions where an old hydration request
                // completes after navigating to a different session
                if (activeSessionIdRef.current !== activeSessionId) {
                    console.log(
                        `Discarding stale hydration for session ${activeSessionId}, current session is ${activeSessionIdRef.current}`
                    )
                    return
                }

                const historyMessages = chatHistory.messages ?? []

                // Convert ChatHistoryMessage[] to ChatMessage[] directly
                const messages: ChatMessage[] = historyMessages.map((historyMsg) => {
                    // Extract text content from parts
                    const textContent = historyMsg.content
                        .filter(
                            (
                                part
                            ): part is Extract<typeof part, { type: 'text' }> =>
                                part.type === 'text'
                        )
                        .map((part) => part.text)
                        .join('')

                    // Restore video frames from metadata if available
                    const mediaVideoFrames = historyMsg.metadata?.media?.video_frames
                    const videoFrames = Array.isArray(mediaVideoFrames) && mediaVideoFrames.length > 0
                        ? mediaVideoFrames as VideoFrameReference[]
                        : undefined

                    return {
                        id: historyMsg.id,
                        role: historyMsg.role,
                        content: textContent,
                        createdAt: historyMsg.created_at,
                        model: historyMsg.model,
                        parts: historyMsg.content,
                        files: historyMsg.files,
                        finish_reason: historyMsg.finish_reason,
                        metadata: historyMsg.metadata,
                        ...(videoFrames ? { videoFrames } : {})
                    }
                })

                streamingMessageIdRef.current = null
                activeSessionIdRef.current = activeSessionId
                dispatch(upsertSession(session))

                // Mark this session as hydrated
                hydratedSessionsRef.current.add(activeSessionId)

                // Load media preferences from the most recent USER message that includes media metadata.
                const lastUserMediaMessage =
                    historyMessages.reduce<ChatHistoryMessage | null>(
                        (latest, message) => {
                            if (
                                message.role !== 'user' ||
                                !message.metadata?.media
                            ) {
                                return latest
                            }

                            if (!latest) return message

                            return new Date(message.created_at).getTime() >
                                new Date(latest.created_at).getTime()
                                ? message
                                : latest
                        },
                        null
                    )
                const historyMediaPrefs =
                    lastUserMediaMessage?.metadata?.media || null

                let mediaPrefsToApply = getDefaultChatMediaPreference(
                    getModelsForMediaType('image'),
                    getModelsForMediaType('video'),
                    chatMediaPreferenceRef.current
                )

                if (historyMediaPrefs) {
                    const mediaPrefs = historyMediaPrefs as Record<
                        string,
                        unknown
                    >
                    const preferredType =
                        (mediaPrefs.type as ChatMediaType) ?? 'image'

                    // Select the appropriate models array based on preferred type
                    const mediaModelsArray = getModelsForMediaType(preferredType)

                    const matchedModel = mediaModelsArray.find(
                        (model) =>
                            model.model_name ===
                            (mediaPrefs.model_name as string)
                    )
                    const defaultMediaModel =
                        mediaModelsArray.find(
                            (model) => model.type === preferredType
                        ) || mediaModelsArray[0]
                    const resolvedModelName =
                        matchedModel?.model_name ??
                        (mediaPrefs.model_name as string) ??
                        defaultMediaModel?.model_name ??
                        ''
                    const resolvedProvider =
                        (mediaPrefs.provider as string) ??
                        matchedModel?.provider ??
                        defaultMediaModel?.provider ??
                        ''
                    const historyLanguage = mediaPrefs.language as
                        | StorybookLanguage
                        | undefined
                    const historyLanguageSource = mediaPrefs.language_source as
                        | 'system'
                        | 'user'
                        | undefined
                    const inferredLanguageSource =
                        historyLanguageSource ??
                        (preferredType === 'storybook' && historyLanguage
                            ? historyLanguage === defaultStorybookLanguage
                                ? 'system'
                                : 'user'
                            : undefined)

                    mediaPrefsToApply = {
                        enabled: (mediaPrefs.enabled as boolean) ?? true,
                        type: preferredType,
                        model_name: resolvedModelName,
                        provider: resolvedProvider,
                        template_id: mediaPrefs.template_id as
                            | string
                            | undefined,
                        template_name: mediaPrefs.template_name as
                            | string
                            | undefined,
                        template_prompt: mediaPrefs.template_prompt as
                            | string
                            | undefined,
                        aspect_ratio: mediaPrefs.aspect_ratio as
                            | ImageAspectRatio
                            | undefined,
                        resolution: mediaPrefs.resolution as
                            | ImageResolution
                            | undefined,
                        page_count: mediaPrefs.page_count as
                            | PageCount
                            | undefined,
                        text_position: mediaPrefs.text_position as
                            | TextPosition
                            | undefined,
                        language: historyLanguage,
                        language_source: inferredLanguageSource,
                        genre: mediaPrefs.genre as
                            | StorybookGenre
                            | undefined,
                        manga_layout: mediaPrefs.manga_layout as
                            | boolean
                            | undefined,
                        rich_dialogue: mediaPrefs.rich_dialogue as
                            | boolean
                            | undefined,
                        voice_enabled: mediaPrefs.voice_enabled as
                            | boolean
                            | undefined,
                        video_settings: mediaPrefs.video_settings as
                            | VideoSettings
                            | undefined,
                        // DO NOT load mini_tools from history - it should only apply to that specific message
                        // Loading it would cause the old mini tool to be reused in new messages
                        mini_tools: undefined
                    }
                }

                if (advancedModeSettings?.enabled && mediaPrefsToApply.type === 'image') {
                    mediaPrefsToApply = {
                        ...mediaPrefsToApply,
                        enabled: true,
                        type: 'image',
                        advanced_mode: true,
                        references: advancedModeSettings.references?.map(
                            (ref) => ({
                                file_id: ref.file_id,
                                type: ref.type
                            })
                        )
                    }
                }

                // Don't override a fresh mini tool selection if hydration finishes after the user picked files
                const hasActiveMiniToolSelection =
                    Boolean(chatMediaPreferenceRef.current?.mini_tools)
                if (!hasActiveMiniToolSelection) {
                    dispatch(setChatMediaPreference(mediaPrefsToApply))
                }

                // Only update state, don't update sessionId to prevent circular updates
                // sessionId should only be set via setSessionId from URL changes
                setChatState((prev) => ({
                    ...prev,
                    // Don't update sessionId here - it's already set from the URL
                    sessionData: session,
                    sessionError: null,
                    messages,
                    chatStatus: 'ready',
                    advancedModeSettings: advancedModeSettings ?? null,
                    hasMoreMessages: chatHistory.has_more,
                    isLoadingMore: false
                }))
            } catch (error) {
                console.error('Failed to load session history', error)
                setChatState((prev) => ({
                    ...prev,
                    advancedModeSettings: null
                }))
                // setChatState((prev) => ({
                //     ...prev,
                //     sessionData: undefined,
                //     sessionError:
                //         'We could not load this chat session. It may have been deleted or you might not have access.',
                //     messages: [],
                //     agentStatus: 'ready'
                // }))
                // resetConversationState()
            } finally {
                // Always clear loading state if it was set
                // Only skip if silent AND already hydrated (meaning loading was never set)
                if (!alreadyHydrated || !silent) {
                    setChatState((prev) => ({
                        ...prev,
                        isHistoryLoading: false
                    }))
                }
            }
        },
        [dispatch, getModelsForMediaType, resetConversationState, setChatState]
    )

    const loadMoreMessages = useCallback(async () => {
        const currentSessionId = activeSessionIdRef.current
        if (!currentSessionId) return
        if (stateRef.current.isLoadingMore || !stateRef.current.hasMoreMessages) return

        const currentMessages = stateRef.current.messages
        if (currentMessages.length === 0) return

        // Use the oldest message ID as cursor
        const oldestMessageId = currentMessages[0].id

        setChatState((prev) => ({ ...prev, isLoadingMore: true }))

        try {
            const chatHistory = await chatService.getChatHistory(currentSessionId, {
                before: oldestMessageId,
                limit: 50
            })

            // Discard if session changed during fetch
            if (activeSessionIdRef.current !== currentSessionId) return

            const olderMessages: ChatMessage[] = (chatHistory.messages ?? []).map(
                (historyMsg) => {
                    const textContent = historyMsg.content
                        .filter(
                            (
                                part
                            ): part is Extract<typeof part, { type: 'text' }> =>
                                part.type === 'text'
                        )
                        .map((part) => part.text)
                        .join('')

                    const mediaVideoFrames = historyMsg.metadata?.media?.video_frames
                    const videoFrames =
                        Array.isArray(mediaVideoFrames) && mediaVideoFrames.length > 0
                            ? (mediaVideoFrames as VideoFrameReference[])
                            : undefined

                    return {
                        id: historyMsg.id,
                        role: historyMsg.role,
                        content: textContent,
                        createdAt: historyMsg.created_at,
                        model: historyMsg.model,
                        parts: historyMsg.content,
                        files: historyMsg.files,
                        finish_reason: historyMsg.finish_reason,
                        metadata: historyMsg.metadata,
                        ...(videoFrames ? { videoFrames } : {})
                    }
                }
            )

            setChatState((prev) => ({
                ...prev,
                messages: [...olderMessages, ...prev.messages],
                hasMoreMessages: chatHistory.has_more,
                isLoadingMore: false
            }))
        } catch (error) {
            console.error('Failed to load more messages', error)
            setChatState((prev) => ({ ...prev, isLoadingMore: false }))
        }
    }, [setChatState])

    useEffect(() => {
        storybookPollingRef.current.forEach((entry) =>
            window.clearInterval(entry.timerId)
        )
        storybookPollingRef.current.clear()
        storybookProgressRefreshRef.current.clear()
        storybookProgressCheckedRef.current = null
        setChatState((prev) =>
            prev.isStorybookPolling
                ? { ...prev, isStorybookPolling: false }
                : prev
        )
    }, [setChatState, state.sessionId])

    useEffect(() => {
        return () => {
            storybookPollingRef.current.forEach((entry) =>
                window.clearInterval(entry.timerId)
            )
            storybookPollingRef.current.clear()
        }
    }, [])

    useEffect(() => {
        if (!state.sessionId) {
            storybookProgressCheckedRef.current = null
            return
        }
        if (!state.sessionData || state.isHistoryLoading) return
        if (state.messages.length === 0) return

        if (storybookProgressCheckedRef.current !== state.sessionId) {
            storybookProgressCheckedRef.current = state.sessionId
            void checkSessionStorybookProgress(state.sessionId, state.messages, {
                forceSync: true
            })
        }
    }, [
        checkSessionStorybookProgress,
        state.isHistoryLoading,
        state.messages,
        state.sessionData,
        state.sessionId
    ])

    useEffect(() => {
        if (!state.sessionId) return
        if (!state.sessionData || state.isHistoryLoading) return
        if (state.messages.length === 0) return

        let hasStorybook = false
        let hasGenerating = false

        for (let i = state.messages.length - 1; i >= 0; i--) {
            const parts = state.messages[i].parts ?? []
            for (let j = parts.length - 1; j >= 0; j--) {
                const part = parts[j]
                if (part.type === 'tool_call' && part.name === 'generate_storybook') {
                    hasStorybook = true
                    hasGenerating = true
                    break
                }
                if (part.type !== 'tool_result' || part.name !== 'generate_storybook') {
                    continue
                }
                hasStorybook = true
                const parsed = parseStorybookPayload(part.output ?? part.content)
                if (parsed?.type === 'storybook_progress') {
                    if (!parsed.status || parsed.status === 'generating') {
                        hasGenerating = true
                        break
                    }
                }
            }
            if (hasGenerating) break
        }

        if (!hasStorybook || !hasGenerating) return
        void checkSessionStorybookProgress(state.sessionId, state.messages)
    }, [
        checkSessionStorybookProgress,
        state.isHistoryLoading,
        state.messages,
        state.sessionData,
        state.sessionId
    ])

    useEffect(() => {
        let latest: { storybookId: string; toolCallId: string } | null = null

        for (let i = state.messages.length - 1; i >= 0; i--) {
            const parts = state.messages[i].parts ?? []
            for (let j = parts.length - 1; j >= 0; j--) {
                const part = parts[j]
                if (
                    part.type !== 'tool_result' ||
                    part.name !== 'generate_storybook' ||
                    !part.tool_call_id
                ) {
                    continue
                }

                const rawPayload = part.output ?? part.content
                if (!rawPayload) continue

                const parsed = parseStorybookPayload(rawPayload)
                if (!parsed || parsed.type !== 'storybook_progress') continue
                const polling = (parsed as { polling?: boolean }).polling
                if (polling !== true) continue
                if (parsed.status && parsed.status !== 'generating') continue
                if (!parsed.storybook_id) continue

                latest = {
                    storybookId: parsed.storybook_id,
                    toolCallId: part.tool_call_id
                }
                break
            }
            if (latest) break
        }

        if (!latest) return

        stopOtherStorybookPolling(latest.storybookId)
        startStorybookPolling(latest.storybookId, latest.toolCallId)
    }, [startStorybookPolling, stopOtherStorybookPolling, state.messages])

    const setSessionId = useCallback(
        (sessionId: string | null) => {
            // If switching to a different session, clear messages immediately
            const isDifferentSession = sessionId !== activeSessionIdRef.current
            const shouldPreserveAdvancedMode =
                sessionId === null &&
                chatMediaPreferenceRef.current?.advanced_mode &&
                chatMediaPreferenceRef.current?.type === 'image'

            // Clear hydrated sessions when switching to a different session
            if (isDifferentSession && sessionId !== null) {
                hydratedSessionsRef.current.clear()
            }

            activeSessionIdRef.current = sessionId
            setChatState((prev) => ({
                ...prev,
                sessionId,
                ...(sessionId === null
                    ? {
                          sessionData: undefined,
                          sessionError: null,
                          messages: [],
                          chatStatus: 'ready' as const,
                          advancedModeSettings: shouldPreserveAdvancedMode
                              ? prev.advancedModeSettings
                              : null,
                          hasMoreMessages: false,
                          isLoadingMore: false
                      }
                    : isDifferentSession
                      ? {
                            // Clear messages when switching to a different session
                            messages: [],
                            sessionData: undefined,
                            sessionError: null,
                            isHistoryLoading: false,
                            advancedModeSettings: null,
                            hasMoreMessages: false,
                            isLoadingMore: false
                        }
                      : {})
            }))
        },
        [setChatState]
    )

    const setInputValue = useCallback(
        (value: string) => {
            setChatState((prev) => ({
                ...prev,
                inputValue: value
            }))
        },
        [setChatState]
    )

    const setAdvancedModeSettings = useCallback(
        (settings: AdvancedModeSettings | null) => {
            setChatState((prev) => ({
                ...prev,
                advancedModeSettings: settings
            }))
        },
        [setChatState]
    )

    const setEditingMessageId = useCallback(
        (messageId: string | null) => {
            setChatState((prev) => ({
                ...prev,
                editingMessageId: messageId
            }))
        },
        [setChatState]
    )

    const sendMessage = useCallback(
        async (
            overrideQuestion?: string,
            overrideFileIds?: string[]
        ) => {
            const rawQuestion =
                typeof overrideQuestion === 'string'
                    ? overrideQuestion
                    : stateRef.current.inputValue
            const trimmed = rawQuestion.trim()
            if (!trimmed) return

            const createdAt = new Date().toISOString()
            const timestamp = Date.now()
            const userMessageId = `user-${timestamp}`
            const assistantMessageId = `assistant-${timestamp}`

            streamingMessageIdRef.current = assistantMessageId
            activeSessionIdRef.current = stateRef.current.sessionId

            // Track counters for unique IDs
            let reasoningCounter = 0
            let textCounter = 0

            // For mini_tools, get files from preference.mini_tools.reference_file_ids
            // For normal messages, get files from currentMessageFileIds
            // Use overrideFileIds if provided (e.g., empty array for text-only edit)
            const effectiveFileIds = getEffectiveMediaFileIds(
                chatMediaPreferenceRef.current,
                overrideFileIds !== undefined
                    ? overrideFileIds
                    : currentMessageFileIds
            )

            // Build a map to track which folders contain which files
            const processedFolderIds = new Set<string>()
            const attachments: UploadedFile[] = []
            const mediaMetadata = getMediaMetadata(
                chatMediaPreferenceRef.current
            )

            effectiveFileIds.forEach((fileId) => {
                // First, check if this ID matches a file directly
                const directMatch = uploadedFiles.find(
                    (file) => file.id === fileId
                )
                if (directMatch) {
                    attachments.push(directMatch)
                    return
                }

                // Otherwise, check if this file ID is part of a folder
                const folderMatch = uploadedFiles.find((file) => {
                    if (file.fileCount && file.fileCount > 0 && file.id) {
                        return true
                    }
                    return false
                })

                if (folderMatch && !processedFolderIds.has(folderMatch.id)) {
                    attachments.push(folderMatch)
                    processedFolderIds.add(folderMatch.id)
                }
            })

            // Also add folders that should be included
            // A folder should be added if we haven't seen it yet but it's in uploadedFiles
            // and has a fileCount > 0
            uploadedFiles.forEach((file) => {
                if (
                    file.fileCount &&
                    file.fileCount > 0 &&
                    !processedFolderIds.has(file.id)
                ) {
                    // Check if this folder's ID exists in effectiveFileIds
                    // Since folders store their ID directly and effectiveFileIds contains individual file IDs,
                    // we need different logic
                    // Actually, let's just check if any of the effectiveFileIds match this file
                    const shouldInclude = effectiveFileIds.includes(
                        file.id
                    )
                    if (shouldInclude) {
                        attachments.push(file)
                        processedFolderIds.add(file.id)
                    }
                }
            })

            const userMessageFiles =
                attachments.length > 0
                    ? attachments.map((file) => {
                          // If it's a folder, format the name to include file count
                          const fileName =
                              file.fileCount && file.fileCount > 0
                                  ? `${file.folderName || file.name.split(' (')[0]} (${file.fileCount} file${file.fileCount === 1 ? '' : 's'})`
                                  : file.name

                          return {
                              id: file.id,
                              file_name: fileName,
                              file_size: file.size,
                              content_type: file.path.startsWith('data:')
                                  ? file.path.split(';')[0].replace('data:', '')
                                  : 'application/octet-stream',
                              created_at: new Date().toISOString()
                          }
                      })
                    : undefined

            const userMessageFileContents = attachments.reduce<
                Record<string, string>
            >((acc, file) => {
                // Use the formatted file name for consistency with userMessageFiles
                const fileName =
                    file.fileCount && file.fileCount > 0
                        ? `${file.folderName || file.name.split(' (')[0]} (${file.fileCount} file${file.fileCount === 1 ? '' : 's'})`
                        : file.name

                if (isImageFile(file.name)) {
                    acc[fileName] = file.path
                }
                return acc
            }, {})

            // Capture video frames before they get cleared (for display in chat)
            const currentVideoFrames =
                chatMediaPreferenceRef.current?.video_frames ?? []
            const videoFrames =
                chatMediaPreferenceRef.current?.type === 'video' &&
                currentVideoFrames.length > 0
                    ? [...currentVideoFrames]
                    : undefined

            const userMessage: ChatMessage = {
                id: userMessageId,
                role: 'user',
                content: trimmed,
                createdAt,
                model: selectedModelId || '',
                ...(mediaMetadata ? { metadata: mediaMetadata } : {}),
                ...(userMessageFiles ? { files: userMessageFiles } : {}),
                ...(Object.keys(userMessageFileContents).length
                    ? { fileContents: userMessageFileContents }
                    : {}),
                ...(videoFrames ? { videoFrames } : {})
            }

            setChatState((prev) => {
                const base = prev.sessionId ? [...prev.messages] : []
                return {
                    ...prev,
                    inputValue: '',
                    messages: [
                        ...base,
                        userMessage,
                        {
                            id: assistantMessageId,
                            role: 'assistant',
                            content: '',
                            createdAt,
                            model: selectedModelId || '',
                            parts: [],
                            ...(mediaMetadata ? { metadata: mediaMetadata } : {})
                        }
                    ],
                    chatStatus: 'running',
                    sessionError: null,
                    showThinking: true
                }
            })

            const updateMessagePart = (
                partId: string,
                updater: (
                    existing: ContentPart | undefined
                ) => ContentPart | null
            ) => {
                const targetId = streamingMessageIdRef.current
                if (!targetId) return

                setChatState((prev) => ({
                    ...prev,
                    messages: prev.messages.map((message) => {
                        if (message.id !== targetId) return message

                        const parts = message.parts || []
                        const existingIndex = parts.findIndex(
                            (p) => p.id === partId
                        )

                        let updatedParts: ContentPart[]
                        if (existingIndex >= 0) {
                            const updated = updater(parts[existingIndex])
                            if (updated === null) {
                                // Remove part
                                updatedParts = [
                                    ...parts.slice(0, existingIndex),
                                    ...parts.slice(existingIndex + 1)
                                ]
                            } else {
                                // Update part
                                updatedParts = [
                                    ...parts.slice(0, existingIndex),
                                    updated,
                                    ...parts.slice(existingIndex + 1)
                                ]
                            }
                        } else {
                            const newPart = updater(undefined)
                            if (newPart) {
                                updatedParts = [...parts, newPart]
                            } else {
                                updatedParts = parts
                            }
                        }

                        // Aggregate content from text parts for backward compatibility
                        const aggregatedContent = updatedParts
                            .filter((p) => p.type === 'text')
                            .map((p) => p.text || '')
                            .join('')

                        return {
                            ...message,
                            parts: updatedParts,
                            content: aggregatedContent
                        }
                    })
                }))
            }

            try {
                await submitChatQuery(trimmed, {
                    sessionId: stateRef.current.sessionId ?? undefined,
                    files: effectiveFileIds,
                    callbacks: {
                        onSession: ({
                            sessionId: newSessionId,
                            name,
                            titlePending,
                            agentType,
                            createdAt
                        }) => {
                            if (!newSessionId) return
                            const provisionalSession: ISession = {
                                id: newSessionId,
                                workspace_dir: `/workspace/${newSessionId}`,
                                created_at:
                                    createdAt ?? new Date().toISOString(),
                                updated_at:
                                    createdAt ?? new Date().toISOString(),
                                name,
                                title_pending: titlePending,
                                status: 'active',
                                agent_type: agentType ?? 'chat'
                            }
                            activeSessionIdRef.current = newSessionId
                            dispatch(upsertSession(provisionalSession))
                            setChatState((prev) => ({
                                ...prev,
                                sessionId: newSessionId,
                                sessionData: provisionalSession
                            }))
                        },
                        onThinking: ({ delta, signature }) => {
                            const timestamp = Date.now()
                            const targetId = streamingMessageIdRef.current
                            if (!targetId) return

                            // Clear waiting state and hide thinking message when thinking starts
                            setChatState((prev) => ({
                                ...prev,
                                isWaitingForNextEvent: false,
                                showThinking: false
                            }))

                            updateMessagePart(
                                `reasoning-active`,
                                (existing) => {
                                    // Only update if it's actively streaming
                                    if (existing && existing.stream_active) {
                                        return {
                                            ...existing,
                                            thinking:
                                                (existing.thinking || '') +
                                                delta,
                                            signature:
                                                signature || existing.signature
                                        }
                                    }
                                    // If existing is finalized or doesn't exist, create new one
                                    reasoningCounter++
                                    return {
                                        type: 'reasoning',
                                        id: `reasoning-active`,
                                        thinking: delta,
                                        signature,
                                        started_at: timestamp,
                                        finished_at: null,
                                        stream_active: true
                                    }
                                }
                            )
                        },
                        onContentStart: () => {
                            const targetId = streamingMessageIdRef.current
                            if (!targetId) return

                            // Finalize any active text part by giving it a unique ID
                            const existingText = stateRef.current.messages
                                .find((m) => m.id === targetId)
                                ?.parts?.find((p) => p.id === 'text-active')

                            if (existingText) {
                                textCounter++
                                // Remove the active placeholder
                                updateMessagePart(`text-active`, () => null)

                                // Add the finalized version with unique ID
                                updateMessagePart(
                                    `text-${targetId}-${textCounter}`,
                                    () => ({
                                        ...existingText,
                                        id: `text-${targetId}-${textCounter}`
                                    })
                                )
                            }
                        },
                        onToken: (token) => {
                            const timestamp = Date.now()
                            const targetId = streamingMessageIdRef.current
                            if (!targetId) return

                            // Clear waiting state and hide thinking message when text content starts
                            setChatState((prev) => ({
                                ...prev,
                                isWaitingForNextEvent: false,
                                showThinking: false
                            }))

                            // Finalize any active reasoning part by giving it a unique ID
                            const existingReasoning = stateRef.current.messages
                                .find((m) => m.id === targetId)
                                ?.parts?.find(
                                    (p) => p.id === 'reasoning-active'
                                )

                            if (existingReasoning?.stream_active) {
                                // Remove the active placeholder
                                updateMessagePart(
                                    `reasoning-active`,
                                    () => null
                                )

                                // Add the finalized version with unique ID
                                updateMessagePart(
                                    `reasoning-${targetId}-${reasoningCounter}`,
                                    () => ({
                                        ...existingReasoning,
                                        id: `reasoning-${targetId}-${reasoningCounter}`,
                                        stream_active: false,
                                        finished_at: timestamp
                                    })
                                )
                            }

                            // Add or update text content
                            updateMessagePart(`text-active`, (existing) => {
                                if (existing) {
                                    return {
                                        ...existing,
                                        text: (existing.text || '') + token
                                    }
                                }
                                return {
                                    type: 'text',
                                    id: `text-active`,
                                    text: token
                                }
                            })
                        },
                        onToolCallStart: ({ id, name }) => {
                            const timestamp = Date.now()
                            const targetId = streamingMessageIdRef.current
                            if (!targetId) return

                            setChatState((prev) => ({
                                ...prev,
                                isWaitingForNextEvent: false,
                                showThinking: false
                            }))

                            // Finalize any active reasoning by giving it a unique ID
                            const existingReasoning = stateRef.current.messages
                                .find((m) => m.id === targetId)
                                ?.parts?.find(
                                    (p) => p.id === 'reasoning-active'
                                )

                            if (existingReasoning?.stream_active) {
                                // Remove the active placeholder
                                updateMessagePart(
                                    `reasoning-active`,
                                    () => null
                                )

                                // Add the finalized version with unique ID
                                updateMessagePart(
                                    `reasoning-${targetId}-${reasoningCounter}`,
                                    () => ({
                                        ...existingReasoning,
                                        id: `reasoning-${targetId}-${reasoningCounter}`,
                                        stream_active: false,
                                        finished_at: timestamp
                                    })
                                )
                            }

                            // Add tool call
                            updateMessagePart(id, () => ({
                                type: 'tool_call',
                                id,
                                name,
                                input: '',
                                finished: false
                            }))
                        },
                        onToolCallDelta: ({ id, delta }) => {
                            updateMessagePart(id, (existing) => {
                                if (existing) {
                                    return {
                                        ...existing,
                                        input: (existing.input || '') + delta
                                    }
                                }
                                return null
                            })
                        },
                        onToolCallStop: ({ id, name, input }) => {
                            updateMessagePart(id, () => ({
                                type: 'tool_call',
                                id,
                                name,
                                input,
                                finished: true
                            }))
                        },
                        onToolResult: ({
                            tool_call_id,
                            name,
                            output,
                            is_error
                        }) => {
                            updateMessagePart(`result-${tool_call_id}`, () => ({
                                type: 'tool_result',
                                id: `result-${tool_call_id}`,
                                tool_call_id,
                                name,
                                content: output,
                                metadata: '',
                                is_error
                            }))

                            if (output && name) {
                                maybeStartStorybookPolling(
                                    tool_call_id,
                                    name,
                                    output
                                )
                            }

                            // Set waiting state after tool result
                            setChatState((prev) => ({
                                ...prev,
                                isWaitingForNextEvent: true
                            }))
                        },
                        onToolProgress: ({
                            tool_call_id,
                            name,
                            output
                        }) => {
                            // Update the tool result part with progress data
                            // This allows the UI to show storybook pages as they are generated
                            updateMessagePart(`result-${tool_call_id}`, () => ({
                                type: 'tool_result',
                                id: `result-${tool_call_id}`,
                                tool_call_id,
                                name,
                                content: output,
                                metadata: '',
                                is_error: false
                            }))

                            if (output && name) {
                                maybeStartStorybookPolling(
                                    tool_call_id,
                                    name,
                                    output
                                )
                            }
                        },
                        onUsage: ({
                            input_tokens,
                            output_tokens,
                            total_tokens
                        }) => {
                            console.log('Token usage:', {
                                input_tokens,
                                output_tokens,
                                total_tokens
                            })
                        },
                        onCouncilMember: ({
                            status,
                            model_id,
                            model_name,
                            delta,
                            content,
                            error
                        }) => {
                            // Hide thinking indicator when council starts
                            setChatState((prev) => ({
                                ...prev,
                                isWaitingForNextEvent: false,
                                showThinking: false
                            }))

                            const partId = `council-member-${model_id}`

                            if (status === 'start') {
                                updateMessagePart(partId, () => ({
                                    type: 'council_member_output',
                                    id: partId,
                                    model_id,
                                    model_name: model_name || model_id,
                                    content: '',
                                    status: 'streaming'
                                }))
                            } else if (status === 'delta' && delta) {
                                updateMessagePart(partId, (existing) => ({
                                    ...(existing || {}),
                                    type: 'council_member_output',
                                    id: partId,
                                    model_id,
                                    model_name:
                                        model_name ||
                                        existing?.model_name ||
                                        model_id,
                                    content:
                                        (existing?.content || '') + delta,
                                    status: 'streaming'
                                }))
                            } else if (status === 'complete') {
                                updateMessagePart(partId, (existing) => ({
                                    ...(existing || {}),
                                    type: 'council_member_output',
                                    id: partId,
                                    model_id,
                                    model_name:
                                        model_name ||
                                        existing?.model_name ||
                                        model_id,
                                    content:
                                        existing?.content || content || '',
                                    status: 'completed'
                                }))
                            } else if (status === 'error') {
                                updateMessagePart(partId, (existing) => ({
                                    ...(existing || {}),
                                    type: 'council_member_output',
                                    id: partId,
                                    model_id,
                                    model_name:
                                        model_name ||
                                        existing?.model_name ||
                                        model_id,
                                    content: existing?.content || '',
                                    status: 'error',
                                    error_message:
                                        error || 'Unknown error'
                                }))
                            }
                        },
                        onCouncilSynthesis: ({
                            status,
                            model_id,
                            delta,
                            content,
                            error
                        }) => {
                            const partId = 'council-synthesis'

                            if (status === 'start') {
                                updateMessagePart(partId, () => ({
                                    type: 'council_synthesis',
                                    id: partId,
                                    synthesis_model_id: model_id || '',
                                    content: ''
                                }))
                            } else if (status === 'delta' && delta) {
                                updateMessagePart(partId, (existing) => ({
                                    ...(existing || {}),
                                    type: 'council_synthesis',
                                    id: partId,
                                    synthesis_model_id:
                                        model_id ||
                                        existing?.synthesis_model_id ||
                                        '',
                                    content:
                                        (existing?.content || '') + delta
                                }))
                            } else if (status === 'complete') {
                                updateMessagePart(partId, (existing) => ({
                                    ...(existing || {}),
                                    type: 'council_synthesis',
                                    id: partId,
                                    synthesis_model_id:
                                        model_id ||
                                        existing?.synthesis_model_id ||
                                        '',
                                    content:
                                        existing?.content || content || ''
                                }))
                            } else if (status === 'error') {
                                updateMessagePart(partId, () => ({
                                    type: 'council_synthesis',
                                    id: partId,
                                    synthesis_model_id: model_id || '',
                                    content: '',
                                    error_message:
                                        error || 'Synthesis failed'
                                }))
                            }
                        },
                        onDone: () => {
                            const timestamp = Date.now()
                            const targetId = streamingMessageIdRef.current
                            streamingMessageIdRef.current = null

                            if (targetId) {
                                // Finalize any active reasoning by giving it a unique ID
                                const existingReasoning =
                                    stateRef.current.messages
                                        .find((m) => m.id === targetId)
                                        ?.parts?.find(
                                            (p) => p.id === 'reasoning-active'
                                        )

                                if (existingReasoning?.stream_active) {
                                    // Remove the active placeholder
                                    updateMessagePart(
                                        `reasoning-active`,
                                        () => null
                                    )

                                    // Add the finalized version with unique ID
                                    updateMessagePart(
                                        `reasoning-${targetId}-${reasoningCounter}`,
                                        () => ({
                                            ...existingReasoning,
                                            id: `reasoning-${targetId}-${reasoningCounter}`,
                                            stream_active: false,
                                            finished_at: timestamp
                                        })
                                    )
                                }
                            }

                            setChatState((prev) => ({
                                ...prev,
                                chatStatus: 'ready',
                                isWaitingForNextEvent: false,
                                showThinking: false
                            }))

                            // Clear mini_tools after submission to prevent reuse in next message
                            if (chatMediaPreferenceRef.current?.mini_tools) {
                                dispatch(
                                    setChatMediaPreference({
                                        ...chatMediaPreferenceRef.current,
                                        mini_tools: undefined
                                    })
                                )
                            }

                            const targetSessionId = stateRef.current.sessionId
                            if (targetSessionId) {
                                void hydrateSessionHistory(
                                    targetSessionId,
                                    true
                                )
                            }
                        },
                        onError: (message, code) => {
                            if (code === 'insufficient_credits') {
                                toast.warning(
                                    'You have run out of credits. Redirecting to upgrade your plan...'
                                )
                                navigate('/settings/subscription')
                            } else if (code === 'anthropic_image_too_large') {
                                toast.error(
                                    'Anthropic models cannot process images over 5 MB. Please switch to a different model (e.g. OpenAI) or upload a smaller image.'
                                )
                            } else if (message) {
                                toast.error(message)
                            } else {
                                toast.error(
                                    'Something went wrong while processing your request.'
                                )
                            }

                            const timestamp = Date.now()
                            const targetId = streamingMessageIdRef.current

                            if (targetId) {
                                // Finalize any active reasoning by giving it a unique ID
                                const existingReasoning =
                                    stateRef.current.messages
                                        .find((m) => m.id === targetId)
                                        ?.parts?.find(
                                            (p) => p.id === 'reasoning-active'
                                        )

                                if (existingReasoning?.stream_active) {
                                    // Remove the active placeholder
                                    updateMessagePart(
                                        `reasoning-active`,
                                        () => null
                                    )

                                    // Add the finalized version with unique ID
                                    updateMessagePart(
                                        `reasoning-${targetId}-${reasoningCounter}`,
                                        () => ({
                                            ...existingReasoning,
                                            id: `reasoning-${targetId}-${reasoningCounter}`,
                                            stream_active: false,
                                            finished_at: timestamp
                                        })
                                    )
                                }

                                // Add error text to the message so it's not blank
                                const errorText =
                                    message ||
                                    'Something went wrong while processing your request.'
                                const currentParts =
                                    stateRef.current.messages.find(
                                        (m) => m.id === targetId
                                    )?.parts || []
                                const hasTextContent = currentParts.some(
                                    (p) =>
                                        p.type === 'text' &&
                                        'text' in p &&
                                        (p.text ?? '').trim().length > 0
                                )
                                if (!hasTextContent) {
                                    updateMessagePart(
                                        `error-${targetId}`,
                                        () => ({
                                            type: 'text' as const,
                                            id: `error-${targetId}`,
                                            text: `⚠️ ${errorText}`
                                        })
                                    )
                                }
                            }

                            streamingMessageIdRef.current = null

                            setChatState((prev) => ({
                                ...prev,
                                chatStatus: 'ready',
                                isWaitingForNextEvent: false,
                                showThinking: false
                            }))

                            // Clear mini_tools after error to prevent reuse in next message
                            if (chatMediaPreferenceRef.current?.mini_tools) {
                                dispatch(
                                    setChatMediaPreference({
                                        ...chatMediaPreferenceRef.current,
                                        mini_tools: undefined
                                    })
                                )
                            }
                        }
                    }
                })
            } catch {
                streamingMessageIdRef.current = null
                setChatState((prev) => ({
                    ...prev,
                    chatStatus: 'ready'
                }))
            }
        },
        [
            currentMessageFileIds,
            hydrateSessionHistory,
            setChatState,
            submitChatQuery,
            uploadedFiles
        ]
    )

    const editMessage = useCallback(
        async (messageId: string, newContent: string) => {
            const sessionId = stateRef.current.sessionId
            if (!sessionId) return

            const trimmed = newContent.trim()
            if (!trimmed) return

            let deletionSucceeded = false

            try {
                // 1. Stop any active stream
                stopActiveStream()

                // 2. Verify the original message exists before proceeding
                const originalMessage = stateRef.current.messages.find(
                    (m) => m.id === messageId
                )
                if (!originalMessage) return

                // 3. Clear any pending file uploads from the Redux store
                //    for UI consistency (file picker will be cleared).
                dispatch(clearCurrentMessageFileIds())

                // 4. Call backend to delete the edited message and all subsequent messages
                await chatService.deleteMessagesFrom(sessionId, messageId)
                deletionSucceeded = true

                // 5. Truncate local messages: keep only messages before the edited one
                setChatState((prev) => {
                    const editIndex = prev.messages.findIndex(
                        (m) => m.id === messageId
                    )
                    if (editIndex === -1) return prev
                    return {
                        ...prev,
                        messages: prev.messages.slice(0, editIndex),
                        editingMessageId: null
                    }
                })

                // 6. Re-submit the edited content as a new text-only message.
                //    Pass empty array for overrideFileIds to bypass the closure
                //    issue where sendMessage's captured currentMessageFileIds
                //    might still hold stale file IDs.
                await sendMessage(trimmed, [])
            } catch (error) {
                console.error('Failed to edit message:', error)

                if (deletionSucceeded) {
                    // Messages were deleted but re-submit failed - reload from backend
                    toast.error(
                        'Failed to submit edited message. Reloading conversation...'
                    )
                    // Reload the session to sync with backend state
                    await hydrateSessionHistory(sessionId, true)
                } else {
                    // Deletion failed, nothing changed on backend
                    toast.error('Failed to edit message. Please try again.')
                }

                setChatState((prev) => ({
                    ...prev,
                    editingMessageId: null,
                    chatStatus: 'ready'
                }))
            }
        },
        [dispatch, stopActiveStream, setChatState, sendMessage, hydrateSessionHistory]
    )

    useEffect(() => {
        return () => {
            stopActiveStream()
        }
    }, [stopActiveStream])

    const value = useMemo<ChatContextValue>(
        () => ({
            ...state,
            isSubmitting,
            sendMessage,
            stopActiveStream,
            cancelStorybookGeneration,
            resetSubmitting,
            resetConversationState,
            hydrateSessionHistory,
            loadMoreMessages,
            setInputValue,
            setSessionId,
            setAdvancedModeSettings,
            setEditingMessageId,
            editMessage
        }),
        [
            hydrateSessionHistory,
            isSubmitting,
            loadMoreMessages,
            resetConversationState,
            resetSubmitting,
            sendMessage,
            setInputValue,
            setSessionId,
            state,
            stopActiveStream,
            cancelStorybookGeneration,
            setAdvancedModeSettings,
            setEditingMessageId,
            editMessage
        ]
    )

    return value
}

export function ChatProvider({ children }: { children: ReactNode }) {
    const value = useChatProviderValue()
    return <ChatContext.Provider value={value}>{children}</ChatContext.Provider>
}

export function useChat() {
    const context = useContext(ChatContext)
    if (!context) {
        throw new Error('useChat must be used within a ChatProvider')
    }
    return context
}

export function useChatQuery() {
    return useChat()
}
