'use client'

import { cloneDeep, debounce, uniqBy } from 'lodash'
import { useCallback, useEffect, useRef } from 'react'
import { useLocation, useNavigate } from 'react-router'
import { toast } from 'sonner'

import { extractUrls, isE2bLink } from '@/lib/utils'
import {
    requestAction,
    setActiveFile,
    setAgentInitialized,
    setBuildStep,
    setCompleted,
    setSelectedBuildStep,
    userApi,
    sessionApi
} from '@/state'
import {
    setHarmonicMissStats,
    setContextUsage
} from '@/state/slice/context'
import {
    setResultUrl,
    setStopped,
    setSandboxIframeAwake,
    setFullstackProjectInitialized,
    setPublished
} from '@/state/slice/agent'
import { setIsUploading, setRequireClearFiles } from '@/state/slice/files'
import {
    addMessage,
    selectMessages,
    setMessages,
    updateMessage
} from '@/state/slice/messages'
import { setActiveSessionId } from '@/state/slice/sessions'
import {
    setActiveTab,
    setGeneratingPrompt,
    setIsCreatingSession,
    setIsFromNewQuestion,
    setIsMobileChatVisible,
    setLoading
} from '@/state/slice/ui'
import {
    selectWorkspaceInfo,
    setBrowserUrl,
    setCurrentQuestion,
    setVscodeUrl,
    setWorkspaceInfo
} from '@/state/slice/workspace'
import { useAppDispatch, useAppSelector } from '@/state/store'
import {
    ActionStep,
    AgentContext,
    AgentEvent,
    AttachmentMeta,
    BUILD_STEP,
    FileURLContent,
    Message,
    TAB,
    TOOL
} from '@/typings/agent'
import { normalizeAttachment } from '@/utils/attachments'

export function useAppEvents() {
    const navigate = useNavigate()

    const dispatch = useAppDispatch()
    const messages = useAppSelector(selectMessages)
    const workspaceInfo = useAppSelector(selectWorkspaceInfo)
    const messagesRef = useRef(messages)
    const workspaceInfoRef = useRef(workspaceInfo)
    const location = useLocation()

    // Track agent hierarchy
    const activeAgentsRef = useRef<Map<string, AgentContext>>(new Map())
    const mainAgentId = useRef<string>('main-agent')
    const agentStackRef = useRef<string[]>([mainAgentId.current])
    const hasResetForReplay = useRef<boolean>(false)

    useEffect(() => {
        messagesRef.current = messages
    }, [JSON.stringify(messages)])

    useEffect(() => {
        workspaceInfoRef.current = workspaceInfo
    }, [workspaceInfo])

    // Reset replay flag when location/session changes
    useEffect(() => {
        hasResetForReplay.current = false
    }, [location.pathname])

    // Create a custom dispatch function that updates messagesRef immediately
    const safeDispatch = useCallback(
        (
            action:
                | ReturnType<typeof addMessage>
                | ReturnType<typeof updateMessage>
                | ReturnType<typeof setMessages>
                | ReturnType<typeof setWorkspaceInfo>
                | { type: string; payload: unknown }
        ) => {
            // Handle different action types and update messagesRef immediately
            if (action.type === addMessage.type) {
                messagesRef.current = uniqBy(
                    [...messagesRef.current, action.payload as Message],
                    'id'
                )
            } else if (action.type === updateMessage.type) {
                messagesRef.current = messagesRef.current.map((msg) =>
                    msg.id === (action.payload as Message).id
                        ? (action.payload as Message)
                        : msg
                )
            } else if (action.type === setMessages.type) {
                messagesRef.current = action.payload as Message[]
            } else if (action.type === setWorkspaceInfo.type) {
                workspaceInfoRef.current = action.payload as string
            }

            // Call the actual dispatch
            dispatch(action)
        },
        [dispatch]
    )

    // Helper function to reset agent tracking state (useful for replay mode)
    const resetAgentTrackingState = useCallback(() => {
        activeAgentsRef.current.clear()
        agentStackRef.current = [mainAgentId.current]
        hasResetForReplay.current = false
        // Initialize main agent
        activeAgentsRef.current.set(mainAgentId.current, {
            agentId: mainAgentId.current,
            agentType: 'main',
            nestingLevel: 0
        })
    }, [])

    const handleEvent = useCallback(
        (
            data: {
                id: string
                type: AgentEvent
                content: Record<string, unknown>
            },
            ignoreClickAction?: boolean
        ) => {
            switch (data.type) {
                case AgentEvent.AGENT_INITIALIZED: {
                    // Reset agent tracking state once per replay session
                    if (ignoreClickAction && !hasResetForReplay.current) {
                        resetAgentTrackingState()
                        hasResetForReplay.current = true
                    }
                    dispatch(setFullstackProjectInitialized(false))
                    dispatch(setPublished(null))
                    if (!ignoreClickAction) {
                        dispatch(setAgentInitialized(true))
                        // Also reset in live mode to ensure clean state
                        resetAgentTrackingState()
                    }
                    const vscode_url = data.content.vscode_url as string
                    if (vscode_url) {
                        dispatch(setVscodeUrl(vscode_url))
                    }
                    break
                }

                case AgentEvent.AGENT_RESPONSE_INTERRUPTED: {
                    dispatch(setLoading(false))
                    dispatch(setStopped(true))

                    break
                }

                case AgentEvent.STATUS_UPDATE: {
                    const status = data.content.status as string | undefined
                    if (typeof status === 'string') {
                        dispatch(setLoading(status === 'running'))
                    }
                    const statusMessage = data.content.message as string | undefined
                    if (statusMessage) {
                        toast.info(statusMessage)
                    }
                    break
                }

                case AgentEvent.ERROR: {
                    const errorMessage =
                        (data.content.message as string) ||
                        'An unexpected error occurred.'
                    toast.error(errorMessage)
                    dispatch(setLoading(false))
                    dispatch(setPublished(null))
                    break
                }

                case AgentEvent.SANDBOX_STATUS: {
                    if (!ignoreClickAction) {
                        const isAwake = data.content.status === 'running'
                        dispatch(setSandboxIframeAwake(isAwake))
                    }
                    const vscode_url = data.content.vscode_url as string
                    if (vscode_url) {
                        dispatch(setVscodeUrl(vscode_url))
                    }
                    break
                }
                case AgentEvent.CHECKPOINT_CREATED: {
                    // Inform the user a checkpoint was created
                    const slabId = data.content?.slab_id as string | undefined
                    if (slabId) {
                        toast.success(`Checkpoint created: ${slabId}`)
                    }
                    break
                }
                case AgentEvent.TILE_GENERATED: {
                    // Notify when tiles are generated
                    toast.success('Context tiles generated')
                    break
                }
                case AgentEvent.SUMMARY_CREATED: {
                    // Attach summary to messages (best effort placeholder)
                    const summaryId = data.content?.summary_message_id as string | undefined
                    if (summaryId) {
                        safeDispatch(
                            setMessages([
                                ...(messagesRef.current ?? []),
                                {
                                    id: summaryId,
                                    role: 'assistant',
                                    content: data.content?.summary_preview as string ?? '[Summary created]',
                                    createdAt: Date.now(),
                                    model: '',
                                    parts: [],
                                    files: undefined,
                                    finish_reason: 'summary'
                                }
                            ])
                        )
                        toast.success('Summary created and injected into the thread')
                    }
                    break
                }
                case AgentEvent.PERFORMANCE_WARNING: {
                    const message = data.content?.message as string | undefined
                    const model = data.content?.model as string | undefined
                    toast.error(`Performance warning for ${model ?? 'model'}: ${message ?? 'approaching performance cliff'}`)
                    break
                }
                case AgentEvent.MONITORING: {
                    // Update harmonic miss stats and monitoring info
                    try {
                        const harmonicStats = data.content?.harmonic_miss_stats as Record<string, unknown> | undefined
                        if (harmonicStats) {
                            dispatch(setHarmonicMissStats(harmonicStats))
                        }
                    } catch (e) {
                        // ignore
                    }
                    break
                }

                case AgentEvent.SYSTEM: {
                    if (data.content.type === 'reviewer_agent') {
                        safeDispatch(
                            addMessage({
                                id: data.id,
                                role: 'assistant',
                                action: {
                                    type: TOOL.REVIEWER_AGENT,
                                    data: {
                                        content: data.content.message as string
                                    }
                                },
                                timestamp: Date.now()
                            })
                        )
                    } else if (data.content.session_id) {
                        dispatch(
                            setActiveSessionId(
                                data.content.session_id as string
                            )
                        )
                        dispatch(setIsCreatingSession(false))
                        // Invalidate sessions cache to refresh the session list
                        dispatch(
                            sessionApi.util.invalidateTags([
                                { type: 'Sessions', id: 'LIST' }
                            ])
                        )
                        setTimeout(() => {
                            dispatch(setCurrentQuestion(''))
                            dispatch(setRequireClearFiles(true))
                            const isShareMode =
                                location.pathname?.includes('/share/')
                            const isOnChatPage = location.pathname === '/chat'
                            if (!isShareMode && !isOnChatPage) {
                                dispatch(setIsFromNewQuestion(true))
                                navigate(`/${data.content.session_id}`)
                            }
                        }, 0)
                    } else {
                        const deployment = data.content
                            .deployment as
                            | { url?: unknown }
                            | undefined
                        const deploymentUrl = (deployment?.url ||
                            data.content.deployment_url) as
                            | string
                            | undefined
                        if (deploymentUrl) {
                            dispatch(setPublished(deploymentUrl))
                            toast.success(
                                (data.content.message as string) ||
                                    `Deployment live at ${deploymentUrl}`
                            )
                            break
                        }
                        safeDispatch(
                            addMessage({
                                id: data.id,
                                role: 'assistant',
                                content: data.content.message as string,
                                timestamp: Date.now()
                            })
                        )
                    }
                    break
                }

                case AgentEvent.USER_MESSAGE: {
                    const messageContent = data.content.text as string
                    const currentMessages = messagesRef.current
                    const isDuplicate = currentMessages.some(
                        (msg) =>
                            msg.role === 'user' &&
                            msg.content === messageContent
                    )

                    if (!isDuplicate) {
                        safeDispatch(
                            addMessage({
                                id: data.id,
                                role: 'user',
                                content: messageContent,
                                timestamp: Date.now()
                            })
                        )
                    }
                    dispatch(setCompleted(false))
                    break
                }

                case AgentEvent.PROMPT_GENERATED: {
                    dispatch(setGeneratingPrompt(false))
                    dispatch(setCurrentQuestion(data.content.result as string))
                    break
                }

                case AgentEvent.PROCESSING: {
                    const isShareMode = location.pathname?.includes('/share/')
                    if (isShareMode) {
                        dispatch(setLoading(true))
                    }
                    dispatch(setStopped(false))
                    break
                }

                case AgentEvent.AGENT_THINKING: {
                    const currentAgentId =
                        agentStackRef.current[
                            agentStackRef.current.length - 1
                        ] || mainAgentId.current
                    const agentContext =
                        activeAgentsRef.current.get(currentAgentId)

                    safeDispatch(
                        addMessage({
                            id: data.id,
                            role: 'assistant',
                            content: data.content.text as string,
                            timestamp: Date.now(),
                            isThinkMessage: true,
                            agentContext
                        })
                    )
                    break
                }

                case AgentEvent.TOOL_CALL: {
                    // Determine current agent context
                    const currentAgentId =
                        agentStackRef.current[
                            agentStackRef.current.length - 1
                        ] || mainAgentId.current
                    let agentContext =
                        activeAgentsRef.current.get(currentAgentId)

                    // Check if this is a subagent tool call
                    const isSubagentTool =
                        data.content.tool_name === TOOL.SUB_AGENT ||
                        data.content.tool_name === TOOL.SUB_AGENT_RESEARCHER ||
                        data.content.tool_name === TOOL.DESIGN_DOCUMENT_AGENT ||
                        data.content.tool_name === TOOL.TASK ||
                        data.content.tool_name === TOOL.CODEX_AGENT ||
                        (data.content.tool_name as string)
                            .toString()
                            .startsWith(TOOL.SUB_AGENT.toString())

                    // If it's a subagent tool, create or reuse agent context
                    // This needs to happen regardless of ignoreClickAction for proper replay
                    if (isSubagentTool) {
                        const agentName = (data.content.tool_display_name ||
                            data.content.tool_name) as string
                        const toolCallId = data.content.tool_call_id as
                            | string
                            | undefined
                        const parentContext = agentContext || {
                            agentId: mainAgentId.current,
                            agentType: 'main' as const,
                            nestingLevel: 0
                        }

                        const sanitizeIdPart = (value: string | undefined) =>
                            (value || '')
                                .toLowerCase()
                                .trim()
                                .replace(/[^a-z0-9]+/g, '-')
                                .replace(/^-+|-+$/g, '')

                        const baseAgentSlug =
                            sanitizeIdPart(parentContext.agentId) || 'agent'
                        const agentNameSlug =
                            sanitizeIdPart(String(agentName)) || 'sub-agent'
                        const baseId = `${baseAgentSlug}-${agentNameSlug}`

                        let subagentId = baseId

                        if (toolCallId) {
                            const toolCallSlug =
                                sanitizeIdPart(toolCallId) || 'call'
                            // Include tool call identifier to guarantee uniqueness across same-named delegates
                            subagentId = `${baseId}-${toolCallSlug}`
                        } else {
                            // Fallback to incrementing suffix if no call identifier is available
                            let counter = 1
                            while (activeAgentsRef.current.has(subagentId)) {
                                counter += 1
                                subagentId = `${baseId}-${counter}`
                            }
                        }

                        // Check if we already have this agent context
                        const existingContext =
                            activeAgentsRef.current.get(subagentId)

                        if (existingContext) {
                            // Reuse existing context but only update to running if not already completed
                            if (existingContext.status !== 'completed') {
                                existingContext.status = 'running'
                                existingContext.endTime = undefined
                            }
                            agentContext = existingContext
                            // Make sure it's on the stack if still running
                            if (
                                existingContext.status === 'running' &&
                                !agentStackRef.current.includes(subagentId)
                            ) {
                                agentStackRef.current.push(subagentId)
                            }
                        } else {
                            // Create new agent context
                            const newAgentContext: AgentContext = {
                                agentId: subagentId,
                                agentType: 'subagent',
                                agentName: String(agentName),
                                parentAgentId: parentContext.agentId,
                                nestingLevel: parentContext.nestingLevel + 1,
                                startTime: Date.now(),
                                status: 'running'
                            }

                            activeAgentsRef.current.set(
                                subagentId,
                                newAgentContext
                            )
                            agentStackRef.current.push(subagentId)
                            agentContext = newAgentContext
                        }
                    }

                    if (!agentContext) {
                        // Default to main agent context
                        agentContext = {
                            agentId: mainAgentId.current,
                            agentType: 'main',
                            nestingLevel: 0
                        }
                        activeAgentsRef.current.set(
                            mainAgentId.current,
                            agentContext
                        )
                    }

                    if (data.content.tool_name === TOOL.SEQUENTIAL_THINKING) {
                        safeDispatch(
                            addMessage({
                                id: data.id,
                                role: 'assistant',
                                content: (
                                    data.content.tool_input as {
                                        thought: string
                                    }
                                ).thought as string,
                                timestamp: Date.now(),
                                agentContext
                            })
                        )
                    } else if (data.content.tool_name === TOOL.MESSAGE_USER) {
                        // Message content is emitted on TOOL_RESULT; no-op here
                    } else {
                        const message: Message = {
                            id: data.id,
                            role: 'assistant',
                            action: {
                                type: data.content.tool_name as TOOL,
                                data: {
                                    ...data.content,
                                    agentContext
                                }
                            },
                            timestamp: Date.now(),
                            agentContext
                        }
                        const url = (data.content.tool_input as { url: string })
                            ?.url as string
                        if (url) {
                            dispatch(setBrowserUrl(url))
                        }
                        safeDispatch(addMessage(message))
                        if (
                            data.content.tool_name ===
                            TOOL.FULLSTACK_PROJECT_INIT
                        ) {
                            dispatch(setFullstackProjectInitialized(true))
                        }
                        if (!ignoreClickAction) {
                            handleClickAction(message.action)
                        }
                    }
                    break
                }

                case AgentEvent.BROWSER_USE:
                    // Commented out in original code
                    break

                case AgentEvent.TOOL_RESULT: {
                    // Get current agent context for tool results
                    const currentAgentId =
                        agentStackRef.current[
                            agentStackRef.current.length - 1
                        ] || mainAgentId.current
                    let agentContext =
                        activeAgentsRef.current.get(currentAgentId)

                    if (data.content.tool_name === TOOL.MESSAGE_USER) {
                        const resultPayload = data.content.result as
                            | {
                                  action?: Record<string, unknown>
                              }
                            | undefined
                        const action = (resultPayload?.action || {}) as Record<
                            string,
                            unknown
                        >
                        const messageText =
                            typeof action.text === 'string' ? action.text : ''

                        const attachmentsRaw = Array.isArray(action.attachments)
                            ? (action.attachments as unknown[])
                            : []

                        const attachments = attachmentsRaw
                            .map((item) => normalizeAttachment(item))
                            .filter(Boolean) as AttachmentMeta[]

                        const message: Message = {
                            id: data.id,
                            role: 'assistant',
                            timestamp: Date.now(),
                            agentContext
                        }

                        if (messageText) {
                            message.content = messageText
                        }

                        if (attachments.length > 0) {
                            message.attachments = attachments
                        }

                        safeDispatch(addMessage(message))
                    } else if (data.content.tool_name === TOOL.BROWSER_USE) {
                        safeDispatch(
                            addMessage({
                                id: data.id,
                                role: 'assistant',
                                content: data.content.result as string,
                                timestamp: Date.now(),
                                agentContext
                            })
                        )
                    } else {
                        if (
                            data.content.tool_name !==
                                TOOL.SEQUENTIAL_THINKING &&
                            data.content.tool_name !== TOOL.PRESENTATION &&
                            data.content.tool_name !== TOOL.MESSAGE_USER &&
                            data.content.tool_name !==
                                TOOL.RETURN_CONTROL_TO_USER
                        ) {
                            // Get the latest messages from our ref
                            const messages = [...messagesRef.current]

                            // Find the last message with a matching tool call
                            let lastToolCallMessageIndex = -1
                            for (let i = messages.length - 1; i >= 0; i--) {
                                if (
                                    messages[i].action?.type ===
                                        data.content.tool_name &&
                                    !messages[i].action?.data?.isResult
                                ) {
                                    lastToolCallMessageIndex = i
                                    break
                                }
                            }

                            // If we found a matching tool call message
                            if (lastToolCallMessageIndex !== -1) {
                                const lastToolCallMessage = cloneDeep(
                                    messages[lastToolCallMessageIndex]
                                )

                                if (lastToolCallMessage?.action) {
                                    // Store the raw result - could be string or object
                                    lastToolCallMessage.action.data.result =
                                        data.content.result as
                                            | string
                                            | Record<string, unknown>

                                    lastToolCallMessage.action.data.isResult =
                                        true

                                    // Check if this completes a subagent task
                                    const isSubagentCompletingTool =
                                        data.content.tool_name ===
                                            TOOL.SUB_AGENT ||
                                        data.content.tool_name ===
                                            TOOL.SUB_AGENT_RESEARCHER ||
                                        data.content.tool_name ===
                                            TOOL.DESIGN_DOCUMENT_AGENT ||
                                        data.content.tool_name === TOOL.TASK ||
                                        (data.content.tool_name as string)
                                            .toString()
                                            .startsWith(
                                                TOOL.SUB_AGENT.toString()
                                            )

                                    // Also check if the result contains completion indicators
                                    const resultText =
                                        typeof data.content.result === 'string'
                                            ? data.content.result
                                            : JSON.stringify(
                                                  data.content.result || ''
                                              )
                                    const hasCompletionIndicator =
                                        resultText.includes('Task completed') ||
                                        resultText.includes(
                                            'Sub agent completed'
                                        ) ||
                                        resultText.includes('task is complete')

                                    const messageAgentContext =
                                        lastToolCallMessage.agentContext

                                    const shouldCompleteSubagent =
                                        isSubagentCompletingTool &&
                                        (agentContext?.agentType ===
                                            'subagent' ||
                                            messageAgentContext?.agentType ===
                                                'subagent' ||
                                            hasCompletionIndicator)

                                    if (shouldCompleteSubagent) {
                                        // Find the appropriate subagent context to complete
                                        let subagentToComplete:
                                            | AgentContext
                                            | undefined =
                                            agentContext?.agentType ===
                                            'subagent'
                                                ? agentContext
                                                : undefined

                                        if (
                                            !subagentToComplete &&
                                            messageAgentContext?.agentType ===
                                                'subagent'
                                        ) {
                                            subagentToComplete =
                                                activeAgentsRef.current.get(
                                                    messageAgentContext.agentId
                                                ) || messageAgentContext
                                        }

                                        // If current context is not a subagent, find the relevant one
                                        if (
                                            !subagentToComplete ||
                                            subagentToComplete.agentType !==
                                                'subagent'
                                        ) {
                                            // Look for a running subagent that matches this tool
                                            for (const [
                                                ,
                                                context
                                            ] of activeAgentsRef.current.entries()) {
                                                if (
                                                    context.agentType ===
                                                        'subagent' &&
                                                    context.status === 'running'
                                                ) {
                                                    subagentToComplete = context
                                                    break
                                                }
                                            }
                                        }

                                        if (
                                            subagentToComplete?.agentType ===
                                                'subagent' &&
                                            subagentToComplete.status !==
                                                'completed'
                                        ) {
                                            // Create a new completed agent context (objects may be immutable)
                                            const completedAgentContext = {
                                                ...subagentToComplete,
                                                status: 'completed' as const,
                                                endTime: Date.now()
                                            }
                                            activeAgentsRef.current.set(
                                                subagentToComplete.agentId,
                                                completedAgentContext
                                            )
                                            subagentToComplete =
                                                completedAgentContext

                                            // Update all existing messages with this agent context to reflect completed status
                                            const updatedMessages =
                                                messagesRef.current.map(
                                                    (msg) => {
                                                        if (
                                                            msg.agentContext
                                                                ?.agentId ===
                                                            completedAgentContext.agentId
                                                        ) {
                                                            return {
                                                                ...msg,
                                                                agentContext: {
                                                                    ...completedAgentContext
                                                                }
                                                            }
                                                        }
                                                        return msg
                                                    }
                                                )

                                            // Update messages in store to trigger re-render
                                            safeDispatch(
                                                setMessages(updatedMessages)
                                            )

                                            // Pop from agent stack
                                            const agentIndex =
                                                agentStackRef.current.indexOf(
                                                    subagentToComplete.agentId
                                                )
                                            if (agentIndex >= 0) {
                                                agentStackRef.current.splice(
                                                    agentIndex,
                                                    1
                                                )
                                            }

                                            // Update agentContext to parent for the message
                                            const parentAgentId =
                                                agentStackRef.current[
                                                    agentStackRef.current
                                                        .length - 1
                                                ] || mainAgentId.current
                                            agentContext =
                                                activeAgentsRef.current.get(
                                                    parentAgentId
                                                ) || completedAgentContext
                                        }
                                    }

                                    // Update the message with the latest agent context
                                    if (
                                        agentContext &&
                                        lastToolCallMessage.agentContext
                                    ) {
                                        if (
                                            agentContext.agentId ===
                                            lastToolCallMessage.agentContext
                                                .agentId
                                        ) {
                                            lastToolCallMessage.agentContext =
                                                agentContext
                                        }
                                    } else if (
                                        !lastToolCallMessage.agentContext &&
                                        agentContext
                                    ) {
                                        lastToolCallMessage.agentContext =
                                            agentContext
                                    }

                                    if (!ignoreClickAction) {
                                        setTimeout(() => {
                                            handleClickAction(
                                                lastToolCallMessage.action
                                            )
                                        }, 50)
                                    }

                                    if (
                                        data.content.tool_name ===
                                        TOOL.REGISTER_DEPLOYMENT
                                    ) {
                                        const urls = extractUrls(
                                            lastToolCallMessage.action.data
                                                ?.result as string
                                        )

                                        for (const url of urls) {
                                            if (url) {
                                                dispatch(setResultUrl(url))
                                                break
                                            }
                                        }
                                    } else if (
                                        data.content.tool_name ===
                                            TOOL.IMAGE_GENERATE ||
                                        data.content.tool_name ===
                                            TOOL.VIDEO_GENERATE ||
                                        data.content.tool_name ===
                                            TOOL.READ_REMOTE_IMAGE
                                    ) {
                                        // Handle new dictionary format
                                        const result = lastToolCallMessage
                                            .action.data?.result as string
                                        if (
                                            typeof result === 'object' &&
                                            result !== null &&
                                            'url' in result
                                        ) {
                                            dispatch(
                                                setResultUrl(
                                                    (result as FileURLContent)
                                                        .url
                                                )
                                            )
                                        } else {
                                            // Fallback for old format
                                            dispatch(setResultUrl(result))
                                        }
                                    }

                                    safeDispatch(
                                        updateMessage(lastToolCallMessage)
                                    )
                                }
                            } else {
                                // If no matching tool call message was found, fall back to using the last message
                                const lastMessage = cloneDeep(
                                    messages[messages.length - 1]
                                )
                                safeDispatch(
                                    addMessage({
                                        ...lastMessage,
                                        action: data.content as ActionStep
                                    })
                                )
                            }
                        }
                    }
                    break
                }

                case AgentEvent.AGENT_RESPONSE: {
                    const text = data.content.text as string
                    const currentAgentId =
                        agentStackRef.current[
                            agentStackRef.current.length - 1
                        ] || mainAgentId.current
                    let agentContext =
                        activeAgentsRef.current.get(currentAgentId)

                    // Special handling for subagent completion messages
                    // Check for exact match or if it's contained in the message
                    // IMPORTANT: This should happen regardless of ignoreClickAction for proper replay
                    if (
                        text === 'Sub agent completed' ||
                        text.includes('Sub agent completed')
                    ) {
                        // Find the subagent to complete - prioritize the most recent subagent
                        let subagentToComplete: AgentContext | undefined =
                            undefined

                        // First, check if current context is a subagent
                        if (agentContext?.agentType === 'subagent') {
                            subagentToComplete = agentContext
                        }

                        // If not, try to find the most recent subagent from the stack (working backwards)
                        if (!subagentToComplete) {
                            for (
                                let i = agentStackRef.current.length - 1;
                                i >= 0;
                                i--
                            ) {
                                const agentId = agentStackRef.current[i]
                                const context =
                                    activeAgentsRef.current.get(agentId)
                                if (
                                    context?.agentType === 'subagent' &&
                                    context.status !== 'completed'
                                ) {
                                    subagentToComplete = context
                                    break
                                }
                            }
                        }

                        // If still not found, find ANY running subagent
                        if (!subagentToComplete) {
                            for (const [
                                ,
                                context
                            ] of activeAgentsRef.current.entries()) {
                                if (
                                    context.agentType === 'subagent' &&
                                    context.status === 'running'
                                ) {
                                    subagentToComplete = context
                                    break
                                }
                            }
                        }

                        // Last resort: find any non-completed subagent
                        if (!subagentToComplete) {
                            for (const [
                                ,
                                context
                            ] of activeAgentsRef.current.entries()) {
                                if (
                                    context.agentType === 'subagent' &&
                                    context.status !== 'completed'
                                ) {
                                    subagentToComplete = context
                                    break
                                }
                            }
                        }

                        if (
                            subagentToComplete?.agentType === 'subagent' &&
                            subagentToComplete.status !== 'completed'
                        ) {
                            // Create a new completed agent context (objects may be immutable)
                            const completedAgentContext = {
                                ...subagentToComplete,
                                status: 'completed' as const,
                                endTime: Date.now()
                            }
                            activeAgentsRef.current.set(
                                subagentToComplete.agentId,
                                completedAgentContext
                            )
                            subagentToComplete = completedAgentContext

                            // Update all existing messages with this agent context to reflect completed status
                            const updatedMessages = messagesRef.current.map(
                                (msg) => {
                                    if (
                                        msg.agentContext?.agentId ===
                                        completedAgentContext.agentId
                                    ) {
                                        return {
                                            ...msg,
                                            agentContext: {
                                                ...completedAgentContext
                                            }
                                        }
                                    }
                                    return msg
                                }
                            )

                            // Update messages in store to trigger re-render
                            safeDispatch(setMessages(updatedMessages))

                            // Pop from agent stack
                            const agentIndex = agentStackRef.current.indexOf(
                                subagentToComplete.agentId
                            )
                            if (agentIndex >= 0) {
                                agentStackRef.current.splice(agentIndex, 1)
                            }

                            // Get the parent agent context for this message
                            const parentAgentId =
                                agentStackRef.current[
                                    agentStackRef.current.length - 1
                                ] || mainAgentId.current
                            agentContext =
                                activeAgentsRef.current.get(parentAgentId) ||
                                agentContext
                        }
                    }

                    const urls = extractUrls(text)

                    for (const url of urls) {
                        if (url && isE2bLink(url)) {
                            dispatch(setResultUrl(url))
                            break
                        }
                    }

                    safeDispatch(
                        addMessage({
                            id: data.id,
                            role: 'assistant',
                            content: text,
                            timestamp: Date.now(),
                            agentContext
                        })
                    )
                    break
                }

                case AgentEvent.SUB_AGENT_COMPLETE: {
                    const content = data.content?.text as string
                    const currentAgentId =
                        agentStackRef.current[
                            agentStackRef.current.length - 1
                        ] || mainAgentId.current
                    let agentContext =
                        activeAgentsRef.current.get(currentAgentId)

                    // Find the subagent to complete - use same comprehensive logic as AGENT_RESPONSE
                    let subagentToComplete: AgentContext | undefined = undefined

                    // First, check if current context is a subagent
                    if (agentContext?.agentType === 'subagent') {
                        subagentToComplete = agentContext
                    }

                    // If not, try to find the most recent subagent from the stack (working backwards)
                    if (!subagentToComplete) {
                        for (
                            let i = agentStackRef.current.length - 1;
                            i >= 0;
                            i--
                        ) {
                            const agentId = agentStackRef.current[i]
                            const context = activeAgentsRef.current.get(agentId)
                            if (
                                context?.agentType === 'subagent' &&
                                context.status !== 'completed'
                            ) {
                                subagentToComplete = context
                                break
                            }
                        }
                    }

                    // If still not found, find ANY running subagent
                    if (!subagentToComplete) {
                        for (const [
                            ,
                            context
                        ] of activeAgentsRef.current.entries()) {
                            if (
                                context.agentType === 'subagent' &&
                                context.status === 'running'
                            ) {
                                subagentToComplete = context
                                break
                            }
                        }
                    }

                    // Last resort: find any non-completed subagent
                    if (!subagentToComplete) {
                        for (const [
                            ,
                            context
                        ] of activeAgentsRef.current.entries()) {
                            if (
                                context.agentType === 'subagent' &&
                                context.status !== 'completed'
                            ) {
                                subagentToComplete = context
                                break
                            }
                        }
                    }

                    // Mark current subagent as completed if it's a subagent and not already completed
                    // This should happen regardless of ignoreClickAction for proper replay
                    if (
                        subagentToComplete?.agentType === 'subagent' &&
                        subagentToComplete.status !== 'completed'
                    ) {
                        // Create a new completed agent context (objects may be immutable)
                        const completedAgentContext = {
                            ...subagentToComplete,
                            status: 'completed' as const,
                            endTime: Date.now()
                        }
                        activeAgentsRef.current.set(
                            subagentToComplete.agentId,
                            completedAgentContext
                        )
                        subagentToComplete = completedAgentContext

                        // Update all existing messages with this agent context to reflect completed status
                        const updatedMessages = messagesRef.current.map(
                            (msg) => {
                                if (
                                    msg.agentContext?.agentId ===
                                    completedAgentContext.agentId
                                ) {
                                    return {
                                        ...msg,
                                        agentContext: {
                                            ...completedAgentContext
                                        }
                                    }
                                }
                                return msg
                            }
                        )

                        // Update messages in store to trigger re-render (happens in both modes)
                        safeDispatch(setMessages(updatedMessages))

                        // Pop from agent stack
                        const agentIndex = agentStackRef.current.indexOf(
                            subagentToComplete.agentId
                        )
                        if (agentIndex >= 0) {
                            agentStackRef.current.splice(agentIndex, 1)
                        }

                        // Update agent context for message
                        const parentAgentId =
                            agentStackRef.current[
                                agentStackRef.current.length - 1
                            ] || mainAgentId.current
                        agentContext =
                            activeAgentsRef.current.get(parentAgentId) ||
                            completedAgentContext
                    }

                    // Get the current agent context after potentially popping the stack
                    const messageAgentContext =
                        agentStackRef.current.length > 1
                            ? activeAgentsRef.current.get(
                                  agentStackRef.current[
                                      agentStackRef.current.length - 1
                                  ]
                              )
                            : activeAgentsRef.current.get(mainAgentId.current)

                    // Add a message with the appropriate agent context (usually parent agent)
                    safeDispatch(
                        addMessage({
                            id: data.id,
                            role: 'assistant',
                            content: content,
                            timestamp: Date.now(),
                            agentContext: messageAgentContext
                        })
                    )
                    break
                }

                case AgentEvent.TOOL_PROGRESS: {
                    // Handle Codex tool progress updates
                    const progressData = data.content
                    const toolName = progressData?.tool_name
                    const message = progressData?.message
                    const status = progressData?.status

                    // Only handle Codex tool progress
                    if (
                        toolName === 'codex_execute' ||
                        toolName === 'codex_review'
                    ) {
                        console.log(`Codex Progress [${status}]: ${message}`)

                        // You can add UI updates here, such as:
                        // - Show progress toast notifications
                        // - Update a progress indicator
                        // - Display status in the chat

                        // For now, we'll log to console for visibility
                        // Future enhancement: Add progress UI components
                    }
                    break
                }

                case AgentEvent.COMPLETE: {
                    dispatch(setCompleted(true))
                    dispatch(setLoading(false))
                    // Invalidate credit cache to refresh balance and usage
                    dispatch(
                        userApi.util.invalidateTags([
                            'CreditBalance',
                            'CreditUsage'
                        ])
                    )
                    setTimeout(() => {
                        dispatch(setBuildStep(BUILD_STEP.BUILD))
                        dispatch(setActiveTab(TAB.RESULT))
                    }, 50)
                    break
                }

                case AgentEvent.MODEL_COMPACT: {
                    const summary = data.content.summary as string
                    // Add a system message to show compaction occurred
                    safeDispatch(
                        addMessage({
                            id: `compact-${data.id}`,
                            role: 'system',
                            content: `✨ Context compacted to manage conversation length. Your conversation history has been summarized to continue efficiently.`,
                            timestamp: Date.now()
                        })
                    )
                    // Optionally show the summary content in a collapsible section
                    if (summary) {
                        safeDispatch(
                            addMessage({
                                id: `compact-summary-${data.id}`,
                                role: 'system',
                                content: `<details><summary>View compacted context</summary>\n\n${summary}</details>`,
                                timestamp: Date.now()
                            })
                        )
                    }
                    break
                }

                case AgentEvent.UPLOAD_SUCCESS: {
                    safeDispatch(setIsUploading(false))

                    // Update the uploaded files state
                    const newFiles = data.content.files as {
                        path: string
                        saved_path: string
                    }[]

                    // Filter out files that are part of folders
                    const folderMetadataFiles = newFiles.filter((f) =>
                        f.path.startsWith('folder:')
                    )

                    const folderNames = folderMetadataFiles
                        .map((f) => {
                            const match = f.path.match(/^folder:(.+):\d+$/)
                            return match ? match[1] : null
                        })
                        .filter(Boolean) as string[]

                    // Only add files that are not part of folders or are folder metadata files
                    const filesToAdd = newFiles.filter((f) => {
                        // If it's a folder metadata file, include it
                        if (f.path.startsWith('folder:')) {
                            return true
                        }

                        // For regular files, exclude them if they might be part of a folder
                        return !folderNames.some((folderName) =>
                            f.path.includes(folderName)
                        )
                    })

                    const paths = filesToAdd.map((f) => f.path)
                    safeDispatch({ type: 'ADD_UPLOADED_FILES', payload: paths })
                    break
                }

                case 'error': {
                    toast.error(data.content.message as string)
                    safeDispatch(setIsUploading(false))
                    safeDispatch(setLoading(false))
                    safeDispatch(setGeneratingPrompt(false))
                    break
                }
            }
        },
        [safeDispatch]
    )

    const handleClickAction = useCallback(
        debounce((data: ActionStep | undefined, showTabOnly = false) => {
            if (!data) return

            switch (data.type) {
                case TOOL.WEB_SEARCH:
                case TOOL.WEB_BATCH_SEARCH:
                    if (showTabOnly) {
                        dispatch(requestAction(data))
                        dispatch(setSelectedBuildStep(BUILD_STEP.BUILD))
                        dispatch(setIsMobileChatVisible(false))
                    } else {
                        dispatch(setBuildStep(BUILD_STEP.BUILD))
                    }
                    break

                case TOOL.IMAGE_GENERATE:
                case TOOL.VIDEO_GENERATE:
                case TOOL.READ_REMOTE_IMAGE:
                case TOOL.IMAGE_SEARCH:
                case TOOL.BROWSER_USE:
                case TOOL.VISIT:
                case TOOL.VISIT_COMPRESS:
                    if (showTabOnly) {
                        dispatch(requestAction(data))
                        dispatch(setSelectedBuildStep(BUILD_STEP.BUILD))
                        dispatch(setIsMobileChatVisible(false))
                    } else {
                        dispatch(setBuildStep(BUILD_STEP.BUILD))
                    }
                    break

                case TOOL.BROWSER_CLICK:
                case TOOL.BROWSER_CLOSE:
                case TOOL.BROWSER_CONSOLE_MESSAGES:
                case TOOL.BROWSER_DRAG:
                case TOOL.BROWSER_EVALUATE:
                case TOOL.BROWSER_HANDLE_DIALOG:
                case TOOL.BROWSER_HOVER:
                case TOOL.BROWSER_NAVIGATE:
                case TOOL.BROWSER_NETWORK_REQUESTS:
                case TOOL.BROWSER_PRESS_KEY:
                case TOOL.BROWSER_SELECT_OPTION:
                case TOOL.BROWSER_SNAPSHOT:
                case TOOL.BROWSER_TAKE_SCREENSHOT:
                case TOOL.BROWSER_TYPE:
                case TOOL.BROWSER_WAIT_FOR:
                case TOOL.BROWSER_TAB_CLOSE:
                case TOOL.BROWSER_TAB_LIST:
                case TOOL.BROWSER_TAB_NEW:
                case TOOL.BROWSER_TAB_SELECT:
                case TOOL.BROWSER_MOUSE_CLICK_XY:
                case TOOL.BROWSER_MOUSE_DRAG_XY:
                case TOOL.BROWSER_MOUSE_MOVE_XY:
                case TOOL.BROWSER_NAVIGATION:
                case TOOL.BROWSER_WAIT:
                case TOOL.BROWSER_VIEW_INTERACTIVE_ELEMENTS:
                case TOOL.BROWSER_SCROLL_DOWN:
                case TOOL.BROWSER_SCROLL_UP:
                case TOOL.BROWSER_SWITCH_TAB:
                case TOOL.BROWSER_OPEN_NEW_TAB:
                case TOOL.BROWSER_GET_SELECT_OPTIONS:
                case TOOL.BROWSER_SELECT_DROPDOWN_OPTION:
                case TOOL.BROWSER_RESTART:
                case TOOL.BROWSER_ENTER_TEXT:
                case TOOL.BROWSER_ENTER_MULTI_TEXTS:
                    if (showTabOnly) {
                        dispatch(requestAction(data))
                        dispatch(setSelectedBuildStep(BUILD_STEP.BUILD))
                        dispatch(setIsMobileChatVisible(false))
                    } else {
                        dispatch(setBuildStep(BUILD_STEP.BUILD))
                    }
                    break

                case TOOL.LS:
                    if (showTabOnly) {
                        dispatch(requestAction(data))
                        dispatch(setSelectedBuildStep(BUILD_STEP.BUILD))
                        dispatch(setIsMobileChatVisible(false))
                    } else {
                        dispatch(setBuildStep(BUILD_STEP.BUILD))
                    }
                    break

                case TOOL.BASH:
                case TOOL.BASH_INIT:
                case TOOL.BASH_VIEW:
                case TOOL.BASH_STOP:
                case TOOL.BASH_KILL:
                case TOOL.GREP:
                case TOOL.GLOB:
                    if (showTabOnly) {
                        dispatch(requestAction(data))
                        dispatch(setSelectedBuildStep(BUILD_STEP.BUILD))
                        dispatch(setIsMobileChatVisible(false))
                    } else {
                        dispatch(setBuildStep(BUILD_STEP.BUILD))
                    }
                    break

                case TOOL.READ:
                case TOOL.WRITE:
                case TOOL.EDIT:
                case TOOL.MULTI_EDIT:
                case TOOL.APPLY_PATCH:
                case TOOL.CODEX_EXECUTE:
                case TOOL.CODEX_REVIEW:
                case TOOL.MCP_CODEX_EXECUTE:
                case TOOL.MCP_CODEX_REVIEW:
                case TOOL.CODEX_MCP_CODEX_EXECUTE:
                case TOOL.CODEX_MCP_CODEX_REVIEW:
                case TOOL.CLAUDE_CODE:
                case TOOL.STR_REPLACE_BASED_EDIT: {
                    if (showTabOnly) {
                        dispatch(requestAction(data))
                        dispatch(setSelectedBuildStep(BUILD_STEP.BUILD))
                        dispatch(setIsMobileChatVisible(false))
                    } else {
                        dispatch(setBuildStep(BUILD_STEP.BUILD))
                    }
                    const path =
                        data.data.tool_input?.file_path ||
                        data.data.tool_input?.file ||
                        data.data.tool_input?.path
                    if (path) {
                        dispatch(setActiveFile(path))
                    }

                    break
                }

                case TOOL.TODO_WRITE:
                    dispatch(setBuildStep(BUILD_STEP.PLAN))
                    break

                case TOOL.REGISTER_DEPLOYMENT: {
                    const urls = extractUrls(data.data?.result as string)
                    if (showTabOnly) {
                        dispatch(requestAction(data))
                        dispatch(setSelectedBuildStep(BUILD_STEP.BUILD))
                        dispatch(setIsMobileChatVisible(false))
                    } else {
                        dispatch(setBuildStep(BUILD_STEP.BUILD))
                    }

                    for (const url of urls) {
                        if (url) {
                            dispatch(setResultUrl(url))
                            break
                        }
                    }

                    break
                }

                case TOOL.SLIDE_EDIT:
                case TOOL.SLIDE_WRITE:
                case TOOL.SLIDE_APPLY_PATCH:
                    if (showTabOnly) {
                        dispatch(requestAction(data))
                        dispatch(setSelectedBuildStep(BUILD_STEP.BUILD))
                        dispatch(setIsMobileChatVisible(false))
                    } else {
                        dispatch(setBuildStep(BUILD_STEP.BUILD))
                    }
                    break

                default:
                    break
            }
        }, 50),
        [safeDispatch]
    )

    return { handleEvent, handleClickAction, resetAgentTrackingState }
}
