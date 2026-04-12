'use client'

import { cloneDeep, debounce, uniqBy } from 'lodash'
import { useCallback, useEffect, useRef } from 'react'
import { useLocation, useNavigate } from 'react-router'
import { toast } from 'sonner'

import { rewriteLocalhostUrl } from '@/lib/utils'

import {
    requestAction,
    setActiveFile,
    setAgentInitialized,
    setBuildStep,
    setCurrentActionData,
    setSelectedBuildStep,
    userApi,
    sessionApi
} from '@/state'
import {
    setCancelling,
    setRunStatus,
    setSandboxIframeAwake,
    setSandboxStatus,
    setFullstackProjectInitialized,
    setProjectId,
    setPublished,
    setLatestCheckpoint
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
    clearPlanModificationOptions,
    selectPlanModificationOptions,
    setActiveTab,
    setBuildMode,
    setIsCreatingSession,
    setIsFromNewQuestion,
    setIsMobileChatVisible,
    setLoading,
    setPlanData,
    setPlanModificationOptions,
    updateMilestoneStatus
} from '@/state/slice/ui'
import {
    selectWorkspaceInfo,
    setBrowserUrl,
    setCurrentQuestion,
    setMobileAppUrl,
    setVscodeUrl,
    setVncUrl,
    setWorkspaceInfo
} from '@/state/slice/workspace'
import {
    type CachedContent,
    type FileTreeNode,
    markFilesChanged,
    setFileTree,
    setTreeError,
    setFileContent,
    setFileLoading,
    updateCachedContents
} from '@/state/slice/file-explorer'
import { useAppDispatch, useAppSelector } from '@/state/store'
import {
    ActionStep,
    AgentContext,
    AgentEvent,
    AttachmentMeta,
    BUILD_MODE,
    BUILD_STEP,
    ErrorCode,
    Message,
    Milestone,
    PlanModificationSuggestion,
    RunStatus,
    TAB,
    TOOL,
    ToolConfirmationData,
    isActiveRunStatus,
    isTerminalRunStatus
} from '@/typings/agent'
import { normalizeAttachment } from '@/utils/attachments'

export function useAppEvents() {
    const navigate = useNavigate()

    const dispatch = useAppDispatch()
    const messages = useAppSelector(selectMessages)
    const workspaceInfo = useAppSelector(selectWorkspaceInfo)
    const planModificationOptions = useAppSelector(
        selectPlanModificationOptions
    )
    const messagesRef = useRef(messages)
    const workspaceInfoRef = useRef(workspaceInfo)
    const planModificationOptionsRef = useRef(planModificationOptions)
    const location = useLocation()
    const extractProjectIdFromResult = useCallback((result: unknown) => {
        const coerceId = (value: unknown) =>
            typeof value === 'string' && value.trim().length > 0 ? value : null

        if (Array.isArray(result)) {
            for (const item of result) {
                if (item && typeof item === 'object') {
                    const nestedId = coerceId(
                        (item as { project_id?: string }).project_id
                    )
                    if (nestedId) {
                        return nestedId
                    }

                    const project = (item as { project?: { id?: string } })
                        .project
                    const projectId = coerceId(project?.id)
                    if (projectId) {
                        return projectId
                    }
                }
            }
        } else if (result && typeof result === 'object') {
            const nestedId = coerceId(
                (result as { project_id?: string }).project_id
            )
            if (nestedId) {
                return nestedId
            }

            const project = (result as { project?: { id?: string } }).project
            const projectId = coerceId(project?.id)
            if (projectId) {
                return projectId
            }
        }

        return null
    }, [])

    // Track agent hierarchy
    const activeAgentsRef = useRef<Map<string, AgentContext>>(new Map())
    const mainAgentId = useRef<string>('main-agent')
    const agentStackRef = useRef<string[]>([mainAgentId.current])
    const hasResetForReplay = useRef<boolean>(false)
    const streamingMessageIdsRef = useRef<{
        thinking: Map<string, string>
        response: Map<string, string>
    }>({
        thinking: new Map(),
        response: new Map()
    })
    // Track if we just generated a plan per session (to skip redirect on COMPLETE)
    // Keyed by session_id to avoid cross-session interference
    const justGeneratedPlanBySessionRef = useRef<Map<string, boolean>>(
        new Map()
    )

    useEffect(() => {
        messagesRef.current = messages
    }, [JSON.stringify(messages)])

    useEffect(() => {
        workspaceInfoRef.current = workspaceInfo
    }, [workspaceInfo])

    useEffect(() => {
        planModificationOptionsRef.current = planModificationOptions
    }, [planModificationOptions])

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
        streamingMessageIdsRef.current.thinking.clear()
        streamingMessageIdsRef.current.response.clear()
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
                name: AgentEvent
                content: Record<string, unknown>
                run_id?: string
                session_id?: string
                run_status?: string | null
            },
            ignoreClickAction?: boolean
        ) => {
            // Reconcile run_status from BE — single dispatch, selectors derive isCompleted/isStopped/isWaitingForInput
            const runStatus =
                data.run_status ??
                (data.content?.run_status as string | undefined)
            if (runStatus && !ignoreClickAction) {
                dispatch(setRunStatus(runStatus))
                dispatch(setLoading(isActiveRunStatus(runStatus)))
                if (runStatus !== RunStatus.ABORTING) {
                   dispatch(setCancelling(false))
                }
                if (isTerminalRunStatus(runStatus)) {
                    dispatch(setLoading(false))
                } else if (runStatus === RunStatus.PAUSED) {
                    dispatch(setLoading(false))
                }
            }

            // ── Helpers (close over stable refs — no dependency concerns) ──

            /** Get the AgentContext for the agent currently at the top of the stack. */
            const getActiveAgent = (): AgentContext | undefined => {
                const id =
                    agentStackRef.current[agentStackRef.current.length - 1] ||
                    mainAgentId.current
                return activeAgentsRef.current.get(id)
            }

            const resolveToolConfirmationsForRun = (runId?: string): void => {
                if (!runId) return

                let changed = false
                const updatedMessages = messagesRef.current.map((msg) => {
                    if (
                        !msg.toolConfirmation ||
                        msg.toolConfirmation.run_id !== runId ||
                        msg.toolConfirmation.resolved
                    ) {
                        return msg
                    }

                    changed = true
                    return {
                        ...msg,
                        toolConfirmation: {
                            ...msg.toolConfirmation,
                            resolved: true
                        }
                    }
                })

                if (changed) {
                    safeDispatch(setMessages(updatedMessages))
                }
            }

            /** Search for a non-completed subagent to finalize (complete/fail).
             *  Priority: preferred → stack (newest first) → any running → any non-completed. */
            const findSubagentToComplete = (
                preferred?: AgentContext
            ): AgentContext | undefined => {
                if (
                    preferred?.agentType === 'subagent' &&
                    preferred.status !== 'completed'
                )
                    return preferred

                for (let i = agentStackRef.current.length - 1; i >= 0; i--) {
                    const ctx = activeAgentsRef.current.get(
                        agentStackRef.current[i]
                    )
                    if (
                        ctx?.agentType === 'subagent' &&
                        ctx.status !== 'completed'
                    )
                        return ctx
                }

                for (const [, ctx] of activeAgentsRef.current.entries()) {
                    if (
                        ctx.agentType === 'subagent' &&
                        ctx.status === 'running'
                    )
                        return ctx
                }
                for (const [, ctx] of activeAgentsRef.current.entries()) {
                    if (
                        ctx.agentType === 'subagent' &&
                        ctx.status !== 'completed'
                    )
                        return ctx
                }
                return undefined
            }

            /** Mark a subagent as completed or failed, update all its messages, and pop it from the stack. */
            const finalizeSubagent = (
                subagent: AgentContext,
                status: 'completed' | 'failed'
            ): AgentContext => {
                const updated: AgentContext = {
                    ...subagent,
                    status,
                    endTime: Date.now()
                }
                activeAgentsRef.current.set(subagent.agentId, updated)

                const updatedMessages = messagesRef.current.map((msg) =>
                    msg.agentContext?.agentId === subagent.agentId
                        ? { ...msg, agentContext: { ...updated } }
                        : msg
                )
                safeDispatch(setMessages(updatedMessages))

                const idx = agentStackRef.current.indexOf(subagent.agentId)
                if (idx >= 0) agentStackRef.current.splice(idx, 1)

                return updated
            }

            /** Fail all currently-running subagents (used on main interrupt & new user message). */
            const failAllRunningSubagents = (): void => {
                const msgs = [...messagesRef.current]
                let changed = false

                for (const [
                    agentId,
                    ctx
                ] of activeAgentsRef.current.entries()) {
                    if (
                        ctx.agentType !== 'subagent' ||
                        ctx.status !== 'running'
                    )
                        continue
                    const failed: AgentContext = {
                        ...ctx,
                        status: 'failed',
                        endTime: Date.now()
                    }
                    activeAgentsRef.current.set(agentId, failed)
                    for (let i = 0; i < msgs.length; i++) {
                        if (msgs[i].agentContext?.agentId === agentId) {
                            msgs[i] = {
                                ...msgs[i],
                                agentContext: { ...failed }
                            }
                            changed = true
                        }
                    }
                }
                if (changed) safeDispatch(setMessages(msgs))
            }

            /** Append a delta chunk to an existing streaming message, or create one.
             *  Works for both thinking and response streams. */
            const handleStreamingDelta = (
                stream: 'thinking' | 'response',
                dataId: string,
                deltaText: string,
                agentContext: AgentContext | undefined,
                isThinkMessage = false
            ): void => {
                const map = streamingMessageIdsRef.current[stream]
                const agentId = agentContext?.agentId || mainAgentId.current
                const existingId = map.get(agentId)

                if (existingId) {
                    const existing = messagesRef.current.find(
                        (m) => m.id === existingId
                    )
                    if (existing) {
                        safeDispatch(
                            updateMessage({
                                ...existing,
                                content: `${existing.content || ''}${deltaText}`,
                                ...(isThinkMessage && { isThinkMessage: true }),
                                agentContext
                            })
                        )
                        return
                    }
                    map.delete(agentId)
                }

                map.set(agentId, dataId)
                safeDispatch(
                    addMessage({
                        id: dataId,
                        role: 'assistant',
                        content: deltaText,
                        timestamp: Date.now(),
                        ...(isThinkMessage && { isThinkMessage: true }),
                        agentContext
                    })
                )
            }

            /** Finalize a stream with the full text. Returns true if an existing message was updated. */
            const finalizeStream = (
                stream: 'thinking' | 'response',
                fullText: string,
                agentContext: AgentContext | undefined,
                isThinkMessage = false
            ): boolean => {
                const map = streamingMessageIdsRef.current[stream]
                const agentId = agentContext?.agentId || mainAgentId.current
                const streamingId = map.get(agentId)

                if (streamingId) {
                    const existing = messagesRef.current.find(
                        (m) => m.id === streamingId
                    )
                    if (existing) {
                        map.delete(agentId)
                        safeDispatch(
                            updateMessage({
                                ...existing,
                                content: fullText,
                                ...(isThinkMessage && { isThinkMessage: true }),
                                agentContext
                            })
                        )
                        return true
                    }
                    map.delete(agentId)
                }
                return false
            }

            // ── Event switch ──

            switch (data.name) {
                case AgentEvent.AGENT_INITIALIZED: {
                    // Reset agent tracking state once per replay session
                    if (ignoreClickAction && !hasResetForReplay.current) {
                        resetAgentTrackingState()
                        hasResetForReplay.current = true
                    }
                    dispatch(setFullstackProjectInitialized(false))
                    dispatch(setProjectId(null))
                    dispatch(setPublished(null))
                    dispatch(setLatestCheckpoint(null))
                    if (!ignoreClickAction) {
                        dispatch(setAgentInitialized(true))
                        // Also reset in live mode to ensure clean state
                        resetAgentTrackingState()
                    }
                    const vscode_url = data.content.vscode_url as string
                    if (vscode_url) {
                        dispatch(setVscodeUrl(rewriteLocalhostUrl(vscode_url)))
                    }
                    break
                }

                case AgentEvent.AGENT_RESPONSE_INTERRUPTED: {
                    const isSubAgentInterrupt =
                        data.content?.is_sub_agent_event ||
                        data.content?.delegated_from ||
                        data.content?.parent_run_id

                    if (isSubAgentInterrupt) {
                        // Only fail the specific interrupted subagent
                        const sub = findSubagentToComplete(getActiveAgent())
                        if (
                            sub?.agentType === 'subagent' &&
                            sub.status !== 'completed'
                        ) {
                            finalizeSubagent(sub, 'failed')
                        }
                    } else {
                        // Main agent interrupted — fail all running subagents and reset stack
                        failAllRunningSubagents()
                        agentStackRef.current = [mainAgentId.current]
                    }

                    // Status (loading/stopped) handled by run_status reconciliation above
                    streamingMessageIdsRef.current.thinking.clear()
                    streamingMessageIdsRef.current.response.clear()
                    break
                }

                case AgentEvent.STATUS_UPDATE: {
                    const operation = data.content.operation as
                        | string
                        | undefined
                    if (operation === 'design_mode_sync') {
                        const progress = data.content.progress as
                            | Record<string, unknown>
                            | undefined

                        if (progress && typeof progress === 'object') {
                            const sessionIdFromEvent =
                                (data.session_id as string | undefined) ??
                                (data.content.session_id as string | undefined)

                            window.dispatchEvent(
                                new CustomEvent('design-mode-sync-progress', {
                                    detail: {
                                        ...progress,
                                        session_id: sessionIdFromEvent
                                    }
                                })
                            )
                        }
                        break
                    }

                    // Loading state is handled by run_status reconciliation above
                    const statusMessage = data.content.message as
                        | string
                        | undefined
                    if (statusMessage) {
                        toast.info(statusMessage)
                    }
                    break
                }

                case AgentEvent.ERROR: {
                    const errorMessage =
                        (data.content.message as string) ||
                        'An unexpected error occurred.'
                    const errorCode = (data.content.error_code ?? (data as Record<string, unknown>).error_code) as ErrorCode | undefined
                    const sessionIdFromEvent =
                        (data.session_id as string | undefined) ??
                        (data.content.session_id as string | undefined)

                    if (errorCode === ErrorCode.INSUFFICIENT_CREDITS) {
                        if (!ignoreClickAction) {
                            toast.error(
                                'You have run out of credits. Redirecting to upgrade your plan...'
                            )
                            navigate('/settings/subscription')
                        }
                        streamingMessageIdsRef.current.thinking.clear()
                        streamingMessageIdsRef.current.response.clear()
                        break
                    }

                    if (
                        errorCode === ErrorCode.DESIGN_SYNC_STATE_ERROR ||
                        errorCode === ErrorCode.SLIDE_DECK_SYNC_STATE_ERROR
                    ) {
                        const operation =
                            errorCode === 'design_sync_state_error'
                                ? 'design_sync_state_complete'
                                : 'slide_deck_sync_state_complete'

                        window.dispatchEvent(
                            new CustomEvent('design-mode-sync-response', {
                                detail: {
                                    operation,
                                    error_code: errorCode,
                                    message: errorMessage,
                                    session_id: sessionIdFromEvent
                                }
                            })
                        )
                    }

                    // Only show toast for live events, not during replay
                    if (!ignoreClickAction) {
                        toast.error(errorMessage)
                        // setLoading(false) handled by run_status reconciliation above
                        dispatch(setPublished(null))
                    }
                    streamingMessageIdsRef.current.thinking.clear()
                    streamingMessageIdsRef.current.response.clear()
                    break
                }

                case AgentEvent.SANDBOX_STATUS: {
                    if (!ignoreClickAction) {
                        const isAwake = data.content.status === 'running'
                        dispatch(setSandboxIframeAwake(isAwake))
                        dispatch(setSandboxStatus((data.content.status as string) ?? ''))
                    }
                    const vscode_url = data.content.vscode_url as string
                    // Always update vscode_url, even if null/empty (to clear stale URLs from previous sessions)
                    dispatch(setVscodeUrl(rewriteLocalhostUrl(vscode_url || '')))
                    const vnc_url = data.content.vnc_url as string
                    dispatch(setVncUrl(rewriteLocalhostUrl(vnc_url || '')))
                    break
                }

                case AgentEvent.CONNECTION_ESTABLISHED: {
                    // join_session acknowledgment — the BE sends this with
                    // session_id in content after a successful join.
                    if (data.content.session_id) {
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
                            // Only navigate from the home page — chat and agent pages
                            // manage their own session URLs. This prevents stale
                            // join_session events from overwriting the URL
                            // when switching between sessions.
                            const isOnHomePage = location.pathname === '/'
                            if (isOnHomePage) {
                                dispatch(setIsFromNewQuestion(true))
                                navigate(`/${data.content.session_id}`)
                            }
                        }, 0)

                        const deployment = data.content.deployment as
                            | { url?: unknown }
                            | undefined
                        const deploymentUrl = (deployment?.url ||
                            data.content.deployment_url) as string | undefined
                        if (deploymentUrl) {
                            dispatch(setPublished(deploymentUrl))
                            toast.success(
                                (data.content.message as string) ||
                                    `Deployment live at ${deploymentUrl}`
                            )
                        }
                    }
                    break
                }

                case AgentEvent.SYSTEM: {
                    // Design mode sync completion events
                    const systemOperation = data.content.operation as string | undefined
                    if (
                        systemOperation === 'design_sync_complete' ||
                        systemOperation === 'design_sync_state_complete' ||
                        systemOperation === 'slide_deck_sync_state_complete'
                    ) {
                        const sessionIdFromEvent =
                            (data.session_id as string | undefined) ??
                            (data.content.session_id as string | undefined)

                        window.dispatchEvent(
                            new CustomEvent('design-mode-sync-response', {
                                detail: {
                                    operation: systemOperation,
                                    session_id: sessionIdFromEvent,
                                    ...data.content
                                }
                            })
                        )

                        window.dispatchEvent(
                            new CustomEvent('design-mode-sync-complete', {
                                detail: {
                                    operation: systemOperation,
                                    session_id: sessionIdFromEvent,
                                    ...data.content,
                                }
                            })
                        )
                        break
                    }

                    if (
                        systemOperation === 'design_state_loaded' ||
                        systemOperation === 'design_state_saved'
                    ) {
                        window.dispatchEvent(
                            new CustomEvent('design-mode-state-response', {
                                detail: {
                                    operation: systemOperation,
                                    ...data.content
                                }
                            })
                        )
                        break
                    }

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
                    } else {
                        const deployment = data.content.deployment as
                            | { url?: unknown }
                            | undefined
                        const deploymentUrl = (deployment?.url ||
                            data.content.deployment_url) as string | undefined
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
                    // Clean up stale running subagents from previous cancelled runs
                    failAllRunningSubagents()
                    agentStackRef.current = [mainAgentId.current]

                    const messageContent = data.content.text as string
                    const currentMessages = messagesRef.current
                    const isDuplicate = currentMessages.some(
                        (msg) =>
                            msg.role === 'user' &&
                            msg.content === messageContent
                    )

                    if (!isDuplicate) {
                        // Extract file metadata if available
                        const filesMetadata = data.content.files_metadata as
                            | Array<{
                                  id: string
                                  file_name: string
                                  file_size: number
                                  content_type: string
                                  signed_url?: string
                              }>
                            | undefined

                        // Build files array for display
                        const files = filesMetadata?.map((f) => ({
                            id: f.id,
                            file_name: f.file_name,
                            file_size: f.file_size,
                            content_type: f.content_type,
                            created_at: new Date().toISOString()
                        }))

                        // Build fileContents from signed URLs returned by events API
                        // so uploaded-files-display can render images directly
                        const fileContents: Record<string, string> = {}
                        if (filesMetadata) {
                            for (const f of filesMetadata) {
                                if (f.signed_url) {
                                    fileContents[f.file_name] = f.signed_url
                                }
                            }
                        }

                        safeDispatch(
                            addMessage({
                                id: data.id,
                                role: 'user',
                                content: messageContent,
                                timestamp: Date.now(),
                                ...(files && files.length > 0 ? { files } : {}),
                                ...(Object.keys(fileContents).length > 0 ? { fileContents } : {})
                            })
                        )
                    }
                    // Status derived from runStatus via selectors — no explicit dispatch needed
                    break
                }

                case AgentEvent.PROCESSING: {
                    resolveToolConfirmationsForRun(
                        (
                            data.run_id ??
                            (data.content.run_id as string | undefined)
                        )?.toString()
                    )

                    // Transient event — setCancelling handled by run_status reconciliation above.
                    // Only share/replay mode needs explicit loading since it lacks the normal submit flow.
                    if (
                        !ignoreClickAction &&
                        location.pathname?.includes('/share/')
                    ) {
                        dispatch(setLoading(true))
                    }
                    break
                }
                case AgentEvent.AGENT_REASONING: {
                    if (!planModificationOptionsRef.current) {
                        dispatch(clearPlanModificationOptions())
                    }
                    const thinkingText = (data.content.text as string) || ''
                    const agentContext = getActiveAgent()

                    if (
                        !finalizeStream(
                            'thinking',
                            thinkingText,
                            agentContext,
                            true
                        )
                    ) {
                        safeDispatch(
                            addMessage({
                                id: data.id,
                                role: 'assistant',
                                content: thinkingText,
                                timestamp: Date.now(),
                                isThinkMessage: true,
                                agentContext
                            })
                        )
                    }
                    break
                }

                case AgentEvent.AGENT_REASONING_DELTA: {
                    const deltaText = data.content.text as string
                    if (!deltaText) break
                    handleStreamingDelta(
                        'thinking',
                        data.id,
                        deltaText,
                        getActiveAgent(),
                        true
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
                    } else if (
                        data.content.tool_name === TOOL.MESSAGE_USER ||
                        data.content.tool_name === TOOL.SUBMIT_PLAN ||
                        data.content.tool_name ===
                            TOOL.SUBMIT_PLAN_MODIFICATION_SUGGESTIONS
                    ) {
                        // These tools emit their own events (PLAN_GENERATED, PLAN_MODIFICATION_OPTIONS)
                        // Don't show tool call in chatbox
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
                            dispatch(setBrowserUrl(rewriteLocalhostUrl(url)))
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

                case AgentEvent.TOOL_CONFIRMATION: {
                    // Human-in-the-Loop: run_id/session_id from event top-level, fallback to content
                    const runId =
                        data.run_id ??
                        (data.content as { run_id?: string }).run_id
                    const sessionId =
                        data.session_id ??
                        (data.content as { session_id?: string }).session_id

                    safeDispatch(
                        addMessage({
                            id: data.id,
                            role: 'assistant',
                            content: '',
                            timestamp: Date.now(),
                            agentContext: getActiveAgent(),
                            toolConfirmation: {
                                run_id: runId as string,
                                session_id: sessionId as string,
                                message: data.content.message as string,
                                active_requirements: data.content
                                    .active_requirements as ToolConfirmationData['active_requirements']
                            }
                        })
                    )
                    // isWaitingForInput / setLoading handled by run_status reconciliation above
                    break
                }

                case AgentEvent.TOOL_RESULT: {
                    const agentContext = getActiveAgent()
                    const toolName = data.content.tool_name as string
                    resolveToolConfirmationsForRun(
                        (
                            data.run_id ??
                            (data.content.run_id as string | undefined)
                        )?.toString()
                    )

                    // ── Tool-specific side effects ──

                    if (toolName === TOOL.FULLSTACK_PROJECT_INIT) {
                        const projectId = extractProjectIdFromResult(
                            data.content.result
                        )
                        if (projectId) dispatch(setProjectId(projectId))
                        dispatch(setFullstackProjectInitialized(true))
                        dispatch(
                            setBrowserUrl(
                                rewriteLocalhostUrl(
                                    (
                                        data.content.result as {
                                            preview_url?: string
                                        }
                                    )?.preview_url || ''
                                )
                            )
                        )
                        dispatch(
                            setMobileAppUrl(
                                (
                                    data.content.result as {
                                        mobile_app_url?: string
                                    }
                                )?.mobile_app_url || ''
                            )
                        )
                        dispatch(setActiveTab(TAB.RESULT))
                    }

                    if (data.content.tool_name === TOOL.MOBILE_APP_INIT) {
                        const web_preview_url = (
                            data.content.result as {
                                web_preview_url?: string
                            }
                        )?.web_preview_url
                        if (web_preview_url) {
                            dispatch(setBrowserUrl(rewriteLocalhostUrl(web_preview_url)))
                            dispatch(setActiveTab(TAB.RESULT))
                        }
                    }

                    if (data.content.tool_name === TOOL.RESTART_MOBILE_SERVER) {
                        const result = data.content.result as {
                            web_preview_url?: string
                            qr_code_value?: string
                        }
                        if (result?.web_preview_url) {
                            dispatch(setBrowserUrl(rewriteLocalhostUrl(result.web_preview_url)))
                        }
                        if (result?.qr_code_value) {
                            dispatch(setMobileAppUrl(result.qr_code_value))
                        }
                    }

                    if (
                        data.content.tool_name ===
                        TOOL.RESTART_FULLSTACK_SERVERS
                    ) {
                        const previewUrl = (
                            data.content.result as {
                                preview_url?: string
                            }
                        )?.preview_url
                        if (previewUrl) {
                            dispatch(setBrowserUrl(rewriteLocalhostUrl(previewUrl)))
                        }
                    }

                    if (toolName === TOOL.SAVE_CHECKPOINT) {
                        const result = data.content.result as {
                            project_directory?: string
                            revision?: string
                        } | null
                        if (
                            result &&
                            typeof result.project_directory === 'string' &&
                            typeof result.revision === 'string'
                        ) {
                            dispatch(
                                setLatestCheckpoint({
                                    projectDirectory: result.project_directory,
                                    revision: result.revision
                                })
                            )
                        }
                    }

                    // ── Message handling by tool type ──

                    if (toolName === TOOL.MESSAGE_USER) {
                        const resultPayload = data.content.result as
                            | { action?: Record<string, unknown> }
                            | undefined
                        const action = (resultPayload?.action || {}) as Record<
                            string,
                            unknown
                        >
                        const messageText =
                            typeof action.text === 'string' ? action.text : ''
                        const attachments = (
                            Array.isArray(action.attachments)
                                ? (action.attachments as unknown[])
                                : []
                        )
                            .map((item) => normalizeAttachment(item))
                            .filter(Boolean) as AttachmentMeta[]

                        const message: Message = {
                            id: data.id,
                            role: 'assistant',
                            timestamp: Date.now(),
                            agentContext
                        }
                        if (messageText) message.content = messageText
                        if (attachments.length > 0)
                            message.attachments = attachments
                        safeDispatch(addMessage(message))
                    } else if (toolName === TOOL.SEND_USER_FILES) {
                        const resultPayload = data.content.result as
                            | { action?: Record<string, unknown> }
                            | undefined
                        const action = (resultPayload?.action || {}) as Record<
                            string,
                            unknown
                        >
                        const messageText =
                            typeof action.text === 'string' ? action.text : ''
                        const attachments = (
                            Array.isArray(action.attachments)
                                ? (action.attachments as unknown[])
                                : []
                        )
                            .map((item) => normalizeAttachment(item))
                            .filter(Boolean) as AttachmentMeta[]

                        // Find and update the matching TOOL_CALL message
                        for (
                            let i = messagesRef.current.length - 1;
                            i >= 0;
                            i--
                        ) {
                            const msg = messagesRef.current[i]
                            if (
                                msg.action?.type === TOOL.SEND_USER_FILES &&
                                !msg.action?.data?.isResult
                            ) {
                                safeDispatch(
                                    updateMessage({
                                        ...msg,
                                        content: messageText || undefined,
                                        attachments:
                                            attachments.length > 0
                                                ? attachments
                                                : undefined,
                                        action: {
                                            ...msg.action,
                                            data: {
                                                ...msg.action.data,
                                                isResult: true
                                            }
                                        }
                                    })
                                )
                                break
                            }
                        }
                    } else if (toolName === TOOL.BROWSER_USE) {
                        safeDispatch(
                            addMessage({
                                id: data.id,
                                role: 'assistant',
                                content: data.content.result as string,
                                timestamp: Date.now(),
                                agentContext
                            })
                        )
                    } else if (
                        toolName !== TOOL.SEQUENTIAL_THINKING &&
                        toolName !== TOOL.PRESENTATION &&
                        toolName !== TOOL.MESSAGE_USER &&
                        toolName !== TOOL.SEND_USER_FILES &&
                        toolName !== TOOL.RETURN_CONTROL_TO_USER
                    ) {
                        // Default: find matching TOOL_CALL and attach result
                        const messages = messagesRef.current
                        let matchIdx = -1
                        for (let i = messages.length - 1; i >= 0; i--) {
                            if (
                                messages[i].action?.type === toolName &&
                                !messages[i].action?.data?.isResult
                            ) {
                                matchIdx = i
                                break
                            }
                        }

                        if (matchIdx !== -1) {
                            const toolCallMsg = cloneDeep(messages[matchIdx])
                            if (toolCallMsg?.action) {
                                toolCallMsg.action.data.result = data.content
                                    .result as string | Record<string, unknown>
                                toolCallMsg.action.data.isResult = true

                                // Subagent finalization: rely on is_sub_agent_event flag from converter,
                                // NOT text-based detection. SUB_AGENT_COMPLETE is the canonical event,
                                // but this acts as a safety net for edge-case ordering.
                                const isSubagentTool =
                                    toolName === TOOL.SUB_AGENT ||
                                    toolName === TOOL.SUB_AGENT_RESEARCHER ||
                                    toolName === TOOL.DESIGN_DOCUMENT_AGENT ||
                                    toolName === TOOL.TASK ||
                                    toolName === TOOL.CODEX_AGENT ||
                                    toolName.startsWith(
                                        TOOL.SUB_AGENT.toString()
                                    )
                                const hasSubAgentFlag =
                                    data.content.is_sub_agent_event ||
                                    agentContext?.agentType === 'subagent' ||
                                    toolCallMsg.agentContext?.agentType ===
                                        'subagent'

                                if (isSubagentTool && hasSubAgentFlag) {
                                    const sub =
                                        findSubagentToComplete(agentContext)
                                    if (sub) {
                                        finalizeSubagent(sub, 'completed')
                                        // Update message context to parent
                                        const parent = getActiveAgent()
                                        if (
                                            parent &&
                                            toolCallMsg.agentContext
                                                ?.agentId === sub.agentId
                                        ) {
                                            toolCallMsg.agentContext = parent
                                        }
                                    }
                                }

                                if (!ignoreClickAction) {
                                    setTimeout(
                                        () =>
                                            handleClickAction(
                                                toolCallMsg.action
                                            ),
                                        50
                                    )
                                }
                                safeDispatch(updateMessage(toolCallMsg))
                            }
                        } else {
                            // Fallback: no matching tool call found
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
                    break
                }

                case AgentEvent.AGENT_RESPONSE: {
                    const text = data.content.text as string
                    const agentContext = getActiveAgent()

                    // Finalize streaming response, or add new message
                    // Note: subagent completion is handled by SUB_AGENT_COMPLETE event (not text matching)
                    if (!finalizeStream('response', text, agentContext)) {
                        safeDispatch(
                            addMessage({
                                id: data.id,
                                role: 'assistant',
                                content: text,
                                timestamp: Date.now(),
                                agentContext
                            })
                        )
                    }
                    break
                }

                case AgentEvent.AGENT_RESPONSE_DELTA: {
                    const deltaText = data.content.text as string
                    if (!deltaText) break
                    handleStreamingDelta(
                        'response',
                        data.id,
                        deltaText,
                        getActiveAgent()
                    )
                    break
                }

                case AgentEvent.SUB_AGENT_COMPLETE: {
                    const text = data.content?.text as string

                    // SUB_AGENT_COMPLETE is the canonical event for subagent completion
                    // (produced by converter.py from RunCompletedEvent/RunOutput with is_sub_agent flag)
                    const sub = findSubagentToComplete(getActiveAgent())
                    if (sub) {
                        finalizeSubagent(sub, 'completed')
                    }

                    // Message belongs to the parent agent context
                    safeDispatch(
                        addMessage({
                            id: data.id,
                            role: 'assistant',
                            content: text,
                            timestamp: Date.now(),
                            agentContext: getActiveAgent()
                        })
                    )
                    break
                }

                case AgentEvent.COMPLETE: {
                    const sessionId = data.content.session_id as
                        | string
                        | undefined
                    // Display completion message if text content is present
                    const text = data.content.text as string | undefined

                    if (text) {
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
                                content: text,
                                timestamp: Date.now(),
                                agentContext
                            })
                        )
                    }
                    streamingMessageIdsRef.current.thinking.clear()
                    streamingMessageIdsRef.current.response.clear()
                    // isCompleted / setLoading handled by run_status reconciliation above
                    // Invalidate credit cache to refresh balance and usage
                    dispatch(
                        userApi.util.invalidateTags([
                            'CreditBalance',
                            'CreditUsage'
                        ])
                    )
                    // Skip redirect if we just generated a plan for THIS session - stay on plan view
                    const justGeneratedPlan = sessionId
                        ? (justGeneratedPlanBySessionRef.current.get(
                              sessionId
                          ) ?? false)
                        : false
                    if (!justGeneratedPlan) {
                        setTimeout(() => {
                            dispatch(setBuildStep(BUILD_STEP.BUILD))
                            dispatch(setActiveTab(TAB.RESULT))
                        }, 50)
                    }
                    // Reset the flag for this session after handling
                    if (sessionId) {
                        justGeneratedPlanBySessionRef.current.delete(sessionId)
                    }
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

                case AgentEvent.PLAN_GENERATED: {
                    const summary = data.content.summary as string
                    const milestones = data.content.milestones as Milestone[]
                    const sessionId = data.content.session_id as
                        | string
                        | undefined

                    // Mark that we just generated a plan to skip redirect on COMPLETE
                    // Track per session to avoid cross-session interference
                    if (sessionId) {
                        justGeneratedPlanBySessionRef.current.set(
                            sessionId,
                            true
                        )
                    }

                    // Set plan data in the store
                    dispatch(
                        setPlanData({
                            summary,
                            milestones
                        })
                    )

                    // Add a message to show the plan was generated
                    safeDispatch(
                        addMessage({
                            id: `plan-${data.id}`,
                            role: 'assistant',
                            content: `**Project Plan Generated**\n\n${summary}\n\n**Milestones:**\n${milestones.map((m, i) => `${i + 1}. ${m.content}`).join('\n')}`,
                            timestamp: Date.now()
                        })
                    )

                    // Exit thinking state and show the plan UI
                    dispatch(setBuildMode(BUILD_MODE.PLAN))
                    dispatch(setBuildStep(BUILD_STEP.PLAN))
                    dispatch(setSelectedBuildStep(BUILD_STEP.PLAN))
                    break
                }

                case AgentEvent.MILESTONE_UPDATE: {
                    const milestoneId = data.content.milestone_id as string
                    const status = data.content.status as Milestone['status']

                    dispatch(
                        updateMilestoneStatus({
                            id: milestoneId,
                            status
                        })
                    )
                    break
                }

                case AgentEvent.PLAN_MODIFICATION_OPTIONS: {
                    const message = data.content.message as string
                    const suggestions = data.content
                        .suggestions as PlanModificationSuggestion[]

                    dispatch(
                        setPlanModificationOptions({
                            message,
                            suggestions
                        })
                    )

                    // Add a message to show the options
                    safeDispatch(
                        addMessage({
                            id: `plan-mod-options-${data.id}`,
                            role: 'assistant',
                            content: message,
                            timestamp: Date.now()
                        })
                    )

                    // setLoading(false) handled by run_status reconciliation above
                    break
                }

                case AgentEvent.UPLOAD_SUCCESS: {
                    // Files are already in Redux state via use-upload-files.tsx.
                    // UPLOAD_SUCCESS confirms the BE received them — just clear the uploading flag.
                    safeDispatch(setIsUploading(false))
                    break
                }

                // Note: raw 'error' === AgentEvent.ERROR, handled above

                case AgentEvent.TESTFLIGHT_LOG: {
                    const message = data.content.message as string
                    const status = data.content.status as string
                    const isError = data.content.is_error as boolean

                    // Display log as a message in the chat
                    safeDispatch(
                        addMessage({
                            id: data.id,
                            role: 'system',
                            content: message,
                            timestamp: Date.now(),
                            isHidden: false
                        })
                    )

                    // Show toast for status changes
                    if (status === 'completed') {
                        toast.success('TestFlight submission completed!')
                    } else if (status === 'failed') {
                        toast.error(
                            isError ? message : 'TestFlight submission failed'
                        )
                    }
                    break
                }

                case AgentEvent.FILE_TREE: {
                    const tree = data.content.tree as FileTreeNode | null
                    const rootPath = data.content.root_path as string | undefined
                    const contents = data.content.contents as
                        | Record<string, CachedContent>
                        | undefined
                    const error = data.content.error as string | undefined
                    if (error && !tree) {
                        dispatch(setTreeError(error))
                        if (!ignoreClickAction) {
                            toast.error(error)
                        }
                    } else {
                        dispatch(setFileTree({ tree, rootPath, contents }))
                    }
                    break
                }

                case AgentEvent.FILE_CONTENT: {
                    const filePath = data.content.path as string
                    const content = data.content.content as string | undefined
                    const language = data.content.language as string | undefined
                    const fileKind = data.content.file_kind as
                        | 'text'
                        | 'image'
                        | 'binary'
                        | undefined
                    const mimeType = data.content.mime_type as string | undefined
                    const message = data.content.message as string | undefined
                    const tooBig = Boolean(data.content.too_big)
                    const error = data.content.error as string | undefined
                    if (!error && filePath) {
                        dispatch(
                            setFileContent({
                                path: filePath,
                                content,
                                language: language || 'plaintext',
                                fileKind,
                                mimeType,
                                message,
                                tooBig
                            })
                        )
                    } else {
                        dispatch(setFileLoading(false))
                    }
                    break
                }

                case AgentEvent.DELEGATION_FALLBACK: {
                    const reason = data.content.reason as string
                    const failureCount = data.content.failure_count as number
                    const circuitState = data.content.circuit_state as string
                    console.warn(
                        '[A2A] Delegation fallback:',
                        reason,
                        `failures=${failureCount}`,
                        `circuit=${circuitState}`
                    )
                    toast.warning(
                        'Switching to built-in mode due to connectivity issue.'
                    )
                    break
                }

                case AgentEvent.COMPACTION_AUTHORITY: {
                    const authority = data.content.authority as string
                    const locked = data.content.compaction_locked as boolean
                    console.debug(
                        '[A2A] Compaction authority:',
                        authority,
                        locked ? '(locked)' : '(unlocked)'
                    )
                    break
                }

                case AgentEvent.FILE_TREE_UPDATE: {
                    const tree = data.content.tree as FileTreeNode | null
                    const rootPath = data.content.root_path as string | undefined
                    const contents = data.content.contents as
                        | Record<string, CachedContent>
                        | undefined
                    const updatedContents = data.content.updated_contents as
                        | Record<string, CachedContent>
                        | undefined
                    const changes = data.content.changes as
                        | Array<{ path?: string; type?: string }>
                        | undefined
                    if (tree) {
                        dispatch(
                            setFileTree({
                                tree,
                                rootPath,
                                contents
                            })
                        )
                    }
                    if (updatedContents && Object.keys(updatedContents).length > 0) {
                        dispatch(updateCachedContents(updatedContents))
                    }
                    if (changes && changes.length > 0) {
                        dispatch(
                            markFilesChanged(
                                changes
                                    .filter((change) => change.type === 'write')
                                    .map((change) => change.path)
                                    .filter(
                                        (path): path is string =>
                                            typeof path === 'string' &&
                                            path.length > 0
                                    )
                            )
                        )
                    }
                    break
                }

            }
        },
        [
            safeDispatch,
            dispatch,
            navigate,
            location.pathname,
            extractProjectIdFromResult
        ]
    )

    /** Tools that set the active file path in addition to showing the build tab. */
    const FILE_TOOLS: ReadonlySet<TOOL> = new Set([
        TOOL.READ,
        TOOL.WRITE,
        TOOL.EDIT,
        TOOL.MULTI_EDIT,
        TOOL.APPLY_PATCH,
        TOOL.CODEX_EXECUTE,
        TOOL.CODEX_REVIEW,
        TOOL.MCP_CODEX_EXECUTE,
        TOOL.MCP_CODEX_REVIEW,
        TOOL.CODEX_MCP_CODEX_EXECUTE,
        TOOL.CODEX_MCP_CODEX_REVIEW,
        TOOL.CLAUDE_CODE,
        TOOL.STR_REPLACE_BASED_EDIT
    ])

    /** Tools that show the build step (the vast majority of actionable tools). */
    const BUILD_TOOLS: ReadonlySet<TOOL> = new Set([
        // Search & browse
        TOOL.WEB_SEARCH,
        TOOL.WEB_BATCH_SEARCH,
        TOOL.IMAGE_GENERATE,
        TOOL.VIDEO_GENERATE,
        TOOL.READ_REMOTE_IMAGE,
        TOOL.IMAGE_SEARCH,
        TOOL.BROWSER_USE,
        TOOL.VISIT,
        TOOL.VISIT_COMPRESS,
        // Browser automation
        TOOL.BROWSER_CLICK,
        TOOL.BROWSER_CLOSE,
        TOOL.BROWSER_CONSOLE_MESSAGES,
        TOOL.BROWSER_DRAG,
        TOOL.BROWSER_EVALUATE,
        TOOL.BROWSER_HANDLE_DIALOG,
        TOOL.BROWSER_HOVER,
        TOOL.BROWSER_NAVIGATE,
        TOOL.BROWSER_NETWORK_REQUESTS,
        TOOL.BROWSER_PRESS_KEY,
        TOOL.BROWSER_SELECT_OPTION,
        TOOL.BROWSER_SNAPSHOT,
        TOOL.BROWSER_TAKE_SCREENSHOT,
        TOOL.BROWSER_TYPE,
        TOOL.BROWSER_WAIT_FOR,
        TOOL.BROWSER_TAB_CLOSE,
        TOOL.BROWSER_TAB_LIST,
        TOOL.BROWSER_TAB_NEW,
        TOOL.BROWSER_TAB_SELECT,
        TOOL.BROWSER_MOUSE_CLICK_XY,
        TOOL.BROWSER_MOUSE_DRAG_XY,
        TOOL.BROWSER_MOUSE_MOVE_XY,
        TOOL.BROWSER_NAVIGATION,
        TOOL.BROWSER_WAIT,
        TOOL.BROWSER_VIEW_INTERACTIVE_ELEMENTS,
        TOOL.BROWSER_SCROLL_DOWN,
        TOOL.BROWSER_SCROLL_UP,
        TOOL.BROWSER_SWITCH_TAB,
        TOOL.BROWSER_ENTER_TEXT,
        TOOL.BROWSER_ENTER_MULTI_TEXTS,
        // Shell & FS
        TOOL.LS,
        TOOL.BASH,
        TOOL.BASH_INIT,
        TOOL.BASH_VIEW,
        TOOL.BASH_STOP,
        TOOL.BASH_KILL,
        TOOL.GREP,
        TOOL.GLOB,
        TOOL.FULLSTACK_PROJECT_INIT,
        TOOL.RESTART_FULLSTACK_SERVERS,
        TOOL.GET_SERVER_STATUS,
        // File editing (also in FILE_TOOLS)
        ...FILE_TOOLS,
        // Deployment & slides
        TOOL.REGISTER_PORT,
        TOOL.SLIDE_EDIT,
        TOOL.SLIDE_WRITE,
        TOOL.SLIDE_APPLY_PATCH,
        TOOL.SLIDE_GENERATE,
        TOOL.GITHUB
    ])

    const handleClickAction = useCallback(
        debounce((data: ActionStep | undefined, showTabOnly = false) => {
            if (!data) return

            if (data.type === TOOL.TODO_WRITE) {
                dispatch(setBuildStep(BUILD_STEP.PLAN))
            } else if (BUILD_TOOLS.has(data.type)) {
                if (showTabOnly) {
                    dispatch(requestAction(data))
                    dispatch(setSelectedBuildStep(BUILD_STEP.BUILD))
                    dispatch(setIsMobileChatVisible(false))
                } else {
                    dispatch(setBuildStep(BUILD_STEP.BUILD))
                }

                // File tools also set the active file path
                if (FILE_TOOLS.has(data.type)) {
                    const path =
                        data.data.tool_input?.file_path ||
                        data.data.tool_input?.file ||
                        data.data.tool_input?.path
                    if (path) dispatch(setActiveFile(path))
                }
            }

            if (showTabOnly) {
                dispatch(setCurrentActionData(data))
            }
        }, 50),
        [safeDispatch]
    )

    return { handleEvent, handleClickAction, resetAgentTrackingState }
}
