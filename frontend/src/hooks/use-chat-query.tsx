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

import { chatService } from '@/services/chat.service'
import {
    useAppSelector,
    selectSelectedModel,
    selectCurrentMessageFileIds,
    selectUploadedFiles
} from '@/state'
import { isImageFile } from '@/lib/utils'
import { type ISession } from '@/typings/agent'
import { sessionService } from '@/services/session.service'
import {
    type AgentStatusState,
    type ChatMessage,
    type ContentPart
} from '@/utils/chat-events'
import { useChatTransport } from './use-chat-transport'

type UploadedFile = {
    id: string
    name: string
    path: string
    size: number
    folderName?: string
    fileCount?: number
    fileIds?: string[] // Individual file IDs for folders
}

type ChatSharedState = {
    sessionId: string | null
    sessionData?: ISession
    sessionError: string | null
    messages: ChatMessage[]
    chatStatus: AgentStatusState
    inputValue: string
    isHistoryLoading: boolean
    isWaitingForNextEvent: boolean
    showThinking: boolean
}

type ChatContextValue = ChatSharedState & {
    isSubmitting: boolean
    sendMessage: (overrideQuestion?: string) => Promise<void>
    stopActiveStream: () => void
    resetConversationState: () => void
    hydrateSessionHistory: (sessionId: string) => Promise<void>
    setInputValue: (value: string) => void
    setSessionId: (sessionId: string | null) => void
}

const INITIAL_CHAT_STATE: ChatSharedState = {
    sessionId: null,
    sessionData: undefined,
    sessionError: null,
    messages: [],
    chatStatus: 'ready',
    inputValue: '',
    isHistoryLoading: false,
    isWaitingForNextEvent: false,
    showThinking: false
}

const ChatContext = createContext<ChatContextValue | undefined>(undefined)

function useChatProviderValue(): ChatContextValue {
    const { submitChatQuery, isSubmitting, stopActiveStream } =
        useChatTransport({ autoStopOnUnmount: false })
    const currentMessageFileIds = useAppSelector(selectCurrentMessageFileIds)
    const uploadedFiles = useAppSelector(selectUploadedFiles) as UploadedFile[]
    const selectedModelId = useAppSelector(selectSelectedModel)

    const [state, setState] = useState<ChatSharedState>(INITIAL_CHAT_STATE)
    const stateRef = useRef(state)

    const streamingMessageIdRef = useRef<string | null>(null)
    const activeSessionIdRef = useRef<string | null>(null)
    const hydratedSessionsRef = useRef<Set<string>>(new Set())

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
        // Update maxTokens based on selected model heuristics
        const mapModelToWindow = (model?: string) => {
            if (!model) return 128000
            model = model.toLowerCase()
            if (model.includes('gpt-4.1')) return 1000000
            if (model.includes('gpt-4-turbo')) return 128000
            if (model.includes('claude')) return 200000
            if (model.includes('gemini')) return 1000000
            if (model.includes('llama')) return 128000
            return 128000
        }
        dispatch(
            setContextUsage({
                usedTokens: stateRef.current?.messages?.reduce(
                    (acc, m) =>
                        acc +
                        (m?.parts?.reduce(
                            (subAcc, p) => subAcc + ((p as any).text?.length || 0),
                            0
                        ) || 0),
                    0
                ),
                modelId: selectedModelId,
                maxTokens: mapModelToWindow(selectedModelId)
            })
        )
    }, [selectedModelId, dispatch])

    const resetConversationState = useCallback(() => {
        streamingMessageIdRef.current = null
        setChatState((prev) => ({
            ...prev,
            messages: [],
            chatStatus: 'ready'
        }))
    }, [setChatState])

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
                const [session, chatHistory] = await Promise.all([
                    sessionService.getSession(activeSessionId),
                    chatService.getChatHistory(activeSessionId)
                ])

                // Convert ChatHistoryMessage[] to ChatMessage[] directly
                const messages: ChatMessage[] = (
                    chatHistory.messages ?? []
                ).map((historyMsg) => {
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

                    return {
                        id: historyMsg.id,
                        role: historyMsg.role,
                        content: textContent,
                        createdAt: historyMsg.created_at,
                        model: historyMsg.model,
                        parts: historyMsg.content,
                        files: historyMsg.files,
                        finish_reason: historyMsg.finish_reason
                    }
                })

                streamingMessageIdRef.current = null
                activeSessionIdRef.current = activeSessionId

                // Mark this session as hydrated
                hydratedSessionsRef.current.add(activeSessionId)

                // Only update state, don't update sessionId to prevent circular updates
                // sessionId should only be set via setSessionId from URL changes
                setChatState((prev) => ({
                    ...prev,
                    // Don't update sessionId here - it's already set from the URL
                    sessionData: session,
                    sessionError: null,
                    messages,
                    chatStatus: 'ready'
                }))
            } catch (error) {
                console.error('Failed to load session history', error)
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
        [resetConversationState, setChatState]
    )

    const setSessionId = useCallback(
        (sessionId: string | null) => {
            // If switching to a different session, clear messages immediately
            const isDifferentSession = sessionId !== activeSessionIdRef.current

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
                          chatStatus: 'ready' as const
                      }
                    : isDifferentSession
                      ? {
                            // Clear messages when switching to a different session
                            messages: [],
                            sessionData: undefined,
                            sessionError: null,
                            isHistoryLoading: false
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

    const sendMessage = useCallback(
        async (overrideQuestion?: string) => {
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

            // Build a map to track which folders contain which files
            const processedFolderIds = new Set<string>()
            const attachments: UploadedFile[] = []

            currentMessageFileIds.forEach((fileId) => {
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
                    // Check if this folder's ID exists in currentMessageFileIds
                    // Since folders store their ID directly and currentMessageFileIds contains individual file IDs,
                    // we need different logic
                    // Actually, let's just check if any of the currentMessageFileIds match this file
                    const shouldInclude = currentMessageFileIds.includes(
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

            const userMessage: ChatMessage = {
                id: userMessageId,
                role: 'user',
                content: trimmed,
                createdAt,
                model: selectedModelId || '',
                ...(userMessageFiles ? { files: userMessageFiles } : {}),
                ...(Object.keys(userMessageFileContents).length
                    ? { fileContents: userMessageFileContents }
                    : {})
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
                            parts: []
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
                    callbacks: {
                        onSession: ({ sessionId: newSessionId }) => {
                            if (!newSessionId) return
                            activeSessionIdRef.current = newSessionId
                            setChatState((prev) => ({
                                ...prev,
                                sessionId: newSessionId
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

                            // Set waiting state after tool result
                            setChatState((prev) => ({
                                ...prev,
                                isWaitingForNextEvent: true
                            }))
                        },
                        onUsage: ({
                            input_tokens,
                            output_tokens,
                            total_tokens
                        }) => {
                            // Dispatch usage into global state for UI
                            dispatch(
                                setContextUsage({
                                    usedTokens: total_tokens,
                                    usage: { inputTokens: input_tokens, outputTokens: output_tokens, totalTokens: total_tokens },
                                    modelId: selectedModelId,
                                    maxTokens: 128000 // Default, will be updated by model change hook
                                })
                            )
                            console.log('Token usage:', {
                                input_tokens,
                                output_tokens,
                                total_tokens
                            })
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

                            const targetSessionId = stateRef.current.sessionId
                            if (targetSessionId) {
                                void hydrateSessionHistory(
                                    targetSessionId,
                                    true
                                )
                            }
                        },
                        onError: () => {
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
                        }
                    }
                })
            } catch {
                streamingMessageIdRef.current = null
                setChatState((prev) => ({
                    ...prev,
                    agentStatus: 'ready'
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
            resetConversationState,
            hydrateSessionHistory,
            setInputValue,
            setSessionId
        }),
        [
            hydrateSessionHistory,
            isSubmitting,
            resetConversationState,
            sendMessage,
            setInputValue,
            setSessionId,
            state,
            stopActiveStream
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
