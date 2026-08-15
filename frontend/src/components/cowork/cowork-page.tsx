import { listen } from '@tauri-apps/api/event'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { DesignModeProvider } from '@/components/design-mode'
import RightSidebar from '@/components/right-sidebar'
import { coworkService } from '@/services/cowork.service'
import Sidebar from '@/components/sidebar'
import {
    AlertDialog,
    AlertDialogCancel,
    AlertDialogContent,
    AlertDialogDescription,
    AlertDialogFooter,
    AlertDialogHeader,
    AlertDialogTitle
} from '@/components/ui/alert-dialog'
import { Button } from '@/components/ui/button'
import { SidebarProvider } from '@/components/ui/sidebar'
import {
    useAppSelector,
    selectAvailableModels,
    selectSelectedModel,
    selectChatToolSettings,
    selectSelectedGitHubRepository
} from '@/state'
import { toast } from 'sonner'
import type { ActionStep, Message } from '@/typings/agent'
import { TOOL } from '@/typings/agent'
import type {
    CoworkChatLiveEvent,
    CoworkChatMessage,
    CoworkChatScope,
    CoworkChatSessionDetail,
    CoworkChatSessionSummary,
    CoworkLiveActivity,
    CoworkLiveActivityStatus,
    CoworkLiveSessionState,
    CoworkLiveToolCall
} from '@/typings/cowork'
import CoworkChatBox from './chat/cowork-chat-box'
import {
    buildCoworkTranscriptMessageId,
    resolveCoworkTranscriptAnchor
} from './chat/cowork-chatmessage-contract'
import {
    inferCoworkToolDisplayName,
    isCoworkBuildPanelActionVisible,
    normalizeCoworkToolNameForUi,
    readCoworkRecord,
    readCoworkString
} from './cowork-action-utils'
import CoworkHeader from './cowork-header'
import CoworkMain from './cowork-main'
import { type CoworkModeId } from './cowork.constants'
import CoworkSidebar from './cowork-sidebar'
import CoworkTabs from './cowork-tabs'

const HOMEPAGE_SCOPE: CoworkChatScope = 'homepage'
const FOLDER_SCOPE: CoworkChatScope = 'intelligent-folder'

const createScopeRecord = <T,>(
    initialValue: T
): Record<CoworkChatScope, T> => ({
    homepage: initialValue,
    'intelligent-folder': initialValue
})

const upsertChatSessionSummary = (
    sessions: CoworkChatSessionSummary[],
    nextSession: CoworkChatSessionSummary
) =>
    [
        ...sessions.filter((session) => session.id !== nextSession.id),
        nextSession
    ].sort(
        (left, right) =>
            new Date(right.updated_at).getTime() -
            new Date(left.updated_at).getTime()
    )

const buildChatSessionSummary = (
    session: CoworkChatSessionDetail
): CoworkChatSessionSummary => ({
    id: session.id,
    scope: session.scope,
    title: session.title,
    preview: session.preview,
    updated_at: session.updated_at,
    message_count: session.messages.length
})

const MAX_LIVE_ACTIVITIES = 40

const buildSessionDetailFromSummary = (
    summary: CoworkChatSessionSummary,
    current?: CoworkChatSessionDetail | null
): CoworkChatSessionDetail => ({
    id: summary.id,
    scope: summary.scope,
    title: summary.title,
    preview: summary.preview,
    updated_at: summary.updated_at,
    message_count: summary.message_count,
    runtime_kind: current?.runtime_kind,
    runtime_session_id: current?.runtime_session_id,
    messages: current?.messages ?? [],
    runtime_events: current?.runtime_events ?? [],
    files: current?.files ?? [],
    run_status: current?.run_status ?? 'idle',
    folder_tree_pair: current?.folder_tree_pair
})

const appendMessageIfMissing = (
    messages: CoworkChatMessage[],
    nextMessage: CoworkChatMessage
) => {
    if (messages.some((message) => message.id === nextMessage.id)) {
        return messages
    }
    return [...messages, nextMessage]
}

const stringifyLiveValue = (value: unknown) => {
    if (typeof value === 'string') {
        return value.trim() || undefined
    }

    if (value === null || value === undefined) {
        return undefined
    }

    try {
        const serialized = JSON.stringify(value, null, 2)
        return serialized === '{}' || serialized === '[]'
            ? undefined
            : serialized
    } catch {
        return String(value)
    }
}

const readString = (record: Record<string, unknown>, key: string) =>
    readCoworkString(record, key)

const readEventText = (record: Record<string, unknown>) =>
    readString(record, 'text') ??
    readString(record, 'message') ??
    readString(record, 'content') ??
    readString(record, 'delta')

const mergeStreamingText = (current: string, incoming: string) => {
    if (!incoming) {
        return current
    }

    if (!current) {
        return incoming
    }

    if (incoming === current) {
        return current
    }

    if (incoming.startsWith(current)) {
        return incoming
    }

    if (current.endsWith(incoming)) {
        return current
    }

    const maxOverlap = Math.min(current.length, incoming.length)

    for (let size = maxOverlap; size > 0; size -= 1) {
        if (current.slice(-size) === incoming.slice(0, size)) {
            return `${current}${incoming.slice(size)}`
        }
    }

    return `${current}${incoming}`
}

const readRecord = (value: unknown): Record<string, unknown> | undefined =>
    readCoworkRecord(value)

const toTimestamp = (value?: string) => {
    if (!value) {
        return Date.now()
    }

    const timestamp = new Date(value).getTime()
    return Number.isNaN(timestamp) ? Date.now() : timestamp
}

const inferToolDisplayName = (content: Record<string, unknown>) =>
    inferCoworkToolDisplayName({
        toolName: readString(content, 'tool_name'),
        displayName:
            readString(content, 'display_name') ??
            readString(content, 'tool_display_name'),
        toolInput: readRecord(content.tool_input)
    })

const HIDDEN_TOOL_MESSAGE_TYPES = new Set<string>([
    TOOL.SEQUENTIAL_THINKING,
    TOOL.MESSAGE_USER,
    TOOL.SUBMIT_PLAN,
    TOOL.SUBMIT_PLAN_MODIFICATION_SUGGESTIONS,
    TOOL.RETURN_CONTROL_TO_USER
])

const buildCoworkActionStep = (
    content: Record<string, unknown>,
    overrides?: Partial<ActionStep['data']>
): ActionStep | undefined => {
    const rawToolName = readString(content, 'tool_name')
    const toolName = normalizeCoworkToolNameForUi(rawToolName)

    if (!toolName) {
        return undefined
    }

    return {
        type: toolName as TOOL,
        data: {
            ...(content as Record<string, unknown>),
            ...overrides,
            tool_name: toolName,
            tool_display_name:
                readString(content, 'display_name') ??
                readString(content, 'tool_display_name') ??
                inferToolDisplayName(content),
            raw_tool_name: rawToolName,
            tool_logo: readString(content, 'tool_logo'),
            tool_input: readRecord(content.tool_input) as
                | ActionStep['data']['tool_input']
                | undefined
        } as ActionStep['data']
    }
}

const upsertEventMessage = (messages: Message[], nextMessage: Message) => {
    const existingIndex = messages.findIndex(
        (message) => message.id === nextMessage.id
    )

    if (existingIndex === -1) {
        return [...messages, nextMessage]
    }

    const nextMessages = [...messages]
    nextMessages[existingIndex] = {
        ...nextMessages[existingIndex],
        ...nextMessage
    }
    return nextMessages
}

const retainCoworkActionMessages = (messages: Message[]) =>
    messages.filter((message) => Boolean(message.action))

const buildTranscriptEventMessage = ({
    kind,
    content,
    sessionId,
    emittedAt,
    messageId
}: {
    kind: 'thinking' | 'response'
    content: string
    sessionId: string
    emittedAt: string
    messageId?: string
}): Message => ({
    id:
        messageId ??
        buildCoworkTranscriptMessageId(
            kind,
            resolveCoworkTranscriptAnchor(emittedAt, sessionId) ?? sessionId
        ),
    role: 'assistant',
    content,
    timestamp: toTimestamp(emittedAt),
    ...(kind === 'thinking' ? { isThinkMessage: true } : {})
})

const flushTranscriptBuffer = ({
    messages,
    kind,
    content,
    sessionId,
    emittedAt,
    messageId
}: {
    messages: Message[]
    kind: 'thinking' | 'response'
    content?: string
    sessionId: string
    emittedAt: string
    messageId?: string
}) => {
    const normalizedContent = content?.trim()

    if (!normalizedContent) {
        return messages
    }

    return upsertEventMessage(
        messages,
        buildTranscriptEventMessage({
            kind,
            content: normalizedContent,
            sessionId,
            emittedAt,
            messageId
        })
    )
}

const buildToolEventMessageId = (
    sessionId: string,
    toolCallId: string | undefined,
    toolName: string,
    emittedAt: string
) =>
    toolCallId
        ? `${sessionId}:tool:${toolCallId}`
        : `${sessionId}:tool:${toolName}:${emittedAt}`

const syncActionEventMessage = (
    messages: Message[],
    action: ActionStep,
    sessionId: string,
    emittedAt: string
) => {
    const toolCallId = action.data.tool_call_id
    const nextMessageId = buildToolEventMessageId(
        sessionId,
        toolCallId,
        action.type,
        emittedAt
    )

    let matchIndex = -1

    for (let index = messages.length - 1; index >= 0; index -= 1) {
        const message = messages[index]
        if (!message.action) {
            continue
        }

        if (
            toolCallId &&
            message.action.data.tool_call_id &&
            message.action.data.tool_call_id === toolCallId
        ) {
            matchIndex = index
            break
        }

        if (
            !toolCallId &&
            message.action.type === action.type &&
            !message.action.data.isResult
        ) {
            matchIndex = index
            break
        }
    }

    if (matchIndex === -1) {
        return {
            messages: upsertEventMessage(messages, {
                id: nextMessageId,
                role: 'assistant',
                action,
                timestamp: toTimestamp(emittedAt)
            }),
            currentAction: action
        }
    }

    const nextMessages = [...messages]
    nextMessages[matchIndex] = {
        ...nextMessages[matchIndex],
        action
    }

    return {
        messages: nextMessages,
        currentAction: action
    }
}

const inferToolStatus = (
    remoteEventType: string,
    isError = false
): CoworkLiveActivityStatus => {
    if (isError || remoteEventType === 'error') {
        return 'error'
    }
    if (
        remoteEventType === 'tool_confirmation' ||
        remoteEventType === 'waiting_for_user_input'
    ) {
        return 'waiting'
    }
    if (
        remoteEventType === 'tool_result' ||
        remoteEventType === 'complete' ||
        remoteEventType === 'stream_complete' ||
        remoteEventType === 'sub_agent_complete'
    ) {
        return 'completed'
    }
    return 'running'
}

const appendActivity = (
    activities: CoworkLiveActivity[],
    activity: CoworkLiveActivity
) => [...activities, activity].slice(-MAX_LIVE_ACTIVITIES)

const appendRuntimeEventIfMissing = (
    events: CoworkChatSessionDetail['runtime_events'],
    nextEvent: CoworkChatSessionDetail['runtime_events'][number]
) => {
    const alreadyExists = events.some((event) => {
        if (event.runtime_event_id && nextEvent.runtime_event_id) {
            return (
                event.runtime_event_type === nextEvent.runtime_event_type &&
                event.runtime_event_id === nextEvent.runtime_event_id
            )
        }

        return (
            event.runtime_event_type === nextEvent.runtime_event_type &&
            event.runtime_created_at === nextEvent.runtime_created_at &&
            event.emitted_at === nextEvent.emitted_at
        )
    })

    if (alreadyExists) {
        return events
    }

    return [...events, nextEvent].sort((left, right) => {
        const leftTime = left.runtime_created_at ?? left.emitted_at
        const rightTime = right.runtime_created_at ?? right.emitted_at

        if (leftTime === rightTime) {
            return `${left.runtime_event_type}:${left.runtime_event_id ?? ''}`.localeCompare(
                `${right.runtime_event_type}:${right.runtime_event_id ?? ''}`
            )
        }

        return leftTime.localeCompare(rightTime)
    })
}

const reduceCoworkLiveEvent = (
    current: CoworkLiveSessionState | undefined,
    event: CoworkChatLiveEvent
): CoworkLiveSessionState | undefined => {
    if (event.type !== 'runtime.event') {
        return current
    }

    const content = event.content ?? {}
    const nextState: CoworkLiveSessionState = current ?? {
        session_id: event.session_id,
        scope: event.scope,
        thinking: '',
        response: '',
        is_awaiting_turn_action: false,
        tool_calls: [],
        activities: [],
        event_messages: []
    }

    const toolCallId = readString(content, 'tool_call_id')
    const toolDisplayName = inferToolDisplayName(content)
    const skillName =
        typeof content.tool_input === 'object' &&
        content.tool_input !== null &&
        'skill' in content.tool_input &&
        typeof content.tool_input.skill === 'string'
            ? content.tool_input.skill
            : undefined
    const agentName = readString(content, 'agent_name')
    const emittedAt = event.emitted_at
    const resolveTranscriptId = (
        kind: 'thinking' | 'response',
        currentMessageId: string | undefined
    ) =>
        currentMessageId ??
        buildCoworkTranscriptMessageId(
            kind,
            resolveCoworkTranscriptAnchor(
                event.runtime_event_id,
                event.runtime_created_at,
                emittedAt
            ) ?? emittedAt
        )
    const resolveFinalTranscriptId = (kind: 'thinking' | 'response') =>
        buildCoworkTranscriptMessageId(
            kind,
            resolveCoworkTranscriptAnchor(
                event.runtime_event_id,
                event.runtime_created_at,
                emittedAt
            ) ?? emittedAt
        )

    switch (event.runtime_event_type) {
        case 'reasoning_delta':
        case 'agent_thinking_delta': {
            const delta = readEventText(content)
            if (!delta) return nextState
            return {
                ...nextState,
                thinking: mergeStreamingText(nextState.thinking, delta),
                thinking_message_id: resolveTranscriptId(
                    'thinking',
                    nextState.thinking_message_id
                ),
                thinking_started_at: nextState.thinking_started_at ?? emittedAt,
                latest_runtime_event_type: event.runtime_event_type,
                last_event_at: emittedAt
            }
        }
        case 'reasoning':
        case 'agent_thinking': {
            const text = readEventText(content)
            const finalizedThinking = text
                ? mergeStreamingText(nextState.thinking, text)
                : nextState.thinking
            const finalizedThinkingId = text
                ? resolveFinalTranscriptId('thinking')
                : nextState.thinking_message_id
            return {
                ...nextState,
                thinking: finalizedThinking,
                thinking_message_id: finalizedThinkingId,
                thinking_started_at: nextState.thinking_started_at ?? emittedAt,
                latest_runtime_event_type: event.runtime_event_type,
                last_event_at: emittedAt
            }
        }
        case 'agent_response_delta': {
            const delta = readEventText(content)
            if (!delta) return nextState
            const flushedThinkingMessages = flushTranscriptBuffer({
                messages: nextState.event_messages,
                kind: 'thinking',
                content: nextState.thinking,
                sessionId: event.session_id,
                emittedAt,
                messageId: nextState.thinking_message_id
            })
            return {
                ...nextState,
                thinking: '',
                thinking_message_id: undefined,
                thinking_started_at: undefined,
                event_messages: flushedThinkingMessages,
                response: mergeStreamingText(nextState.response, delta),
                response_message_id: resolveTranscriptId(
                    'response',
                    nextState.response_message_id
                ),
                response_started_at: nextState.response_started_at ?? emittedAt,
                latest_runtime_event_type: event.runtime_event_type,
                last_event_at: emittedAt
            }
        }
        case 'agent_response': {
            const text = readEventText(content)
            const finalizedResponse = text
                ? mergeStreamingText(nextState.response, text)
                : nextState.response
            const finalizedResponseId = text
                ? resolveFinalTranscriptId('response')
                : nextState.response_message_id
            return {
                ...nextState,
                response: finalizedResponse,
                response_message_id: finalizedResponseId,
                response_started_at: nextState.response_started_at ?? emittedAt,
                latest_runtime_event_type: event.runtime_event_type,
                last_event_at: emittedAt
            }
        }
        case 'tool_call': {
            const input = stringifyLiveValue(content.tool_input)
            const nextToolCall: CoworkLiveToolCall = {
                id: toolCallId ?? `${event.session_id}:${toolDisplayName}`,
                name: readString(content, 'tool_name') ?? toolDisplayName,
                display_name: toolDisplayName,
                input,
                status: 'running',
                logo: readString(content, 'tool_logo'),
                skill_name: skillName,
                agent_name: agentName
            }

            const toolCalls = [
                ...nextState.tool_calls.filter(
                    (tool) => tool.id !== nextToolCall.id
                ),
                nextToolCall
            ]
            const baseEventMessages = flushTranscriptBuffer({
                messages: nextState.event_messages,
                kind: 'thinking',
                content: nextState.thinking,
                sessionId: event.session_id,
                emittedAt,
                messageId: nextState.thinking_message_id
            })
            const action = buildCoworkActionStep(content)
            const actionSync =
                action && !HIDDEN_TOOL_MESSAGE_TYPES.has(action.type)
                    ? syncActionEventMessage(
                          baseEventMessages,
                          action,
                          event.session_id,
                          emittedAt
                      )
                    : null

            return {
                ...nextState,
                tool_calls: toolCalls,
                thinking: '',
                thinking_message_id: undefined,
                thinking_started_at: undefined,
                is_awaiting_turn_action: actionSync
                    ? false
                    : nextState.is_awaiting_turn_action,
                event_messages: actionSync?.messages ?? baseEventMessages,
                current_action:
                    actionSync?.currentAction ?? nextState.current_action,
                activities: appendActivity(nextState.activities, {
                    id: `${event.session_id}:${emittedAt}:tool-call:${nextToolCall.id}`,
                    runtime_event_type: event.runtime_event_type,
                    title: toolDisplayName,
                    detail: input,
                    timestamp: emittedAt,
                    status: 'running',
                    tool_call_id: nextToolCall.id,
                    tool_name: nextToolCall.name,
                    skill_name: skillName,
                    agent_name: agentName
                }),
                latest_runtime_event_type: event.runtime_event_type,
                last_event_at: emittedAt
            }
        }
        case 'tool_result': {
            const result = stringifyLiveValue(content.result)
            const status = inferToolStatus(
                event.runtime_event_type,
                content.is_error === true
            )
            const nextToolId =
                toolCallId ?? `${event.session_id}:${toolDisplayName}`
            const existingToolCall = nextState.tool_calls.find(
                (tool) => tool.id === nextToolId
            )

            const toolCalls = [
                ...nextState.tool_calls.filter(
                    (tool) => tool.id !== nextToolId
                ),
                {
                    id: nextToolId,
                    name:
                        readString(content, 'tool_name') ??
                        existingToolCall?.name ??
                        toolDisplayName,
                    display_name: toolDisplayName,
                    input:
                        existingToolCall?.input ??
                        stringifyLiveValue(content.tool_input),
                    result,
                    status,
                    logo:
                        readString(content, 'tool_logo') ??
                        existingToolCall?.logo,
                    skill_name: skillName ?? existingToolCall?.skill_name,
                    agent_name: agentName ?? existingToolCall?.agent_name
                }
            ]
            const action = buildCoworkActionStep(content, {
                result: content.result as ActionStep['data']['result'],
                isResult: true
            })
            const actionSync =
                action && !HIDDEN_TOOL_MESSAGE_TYPES.has(action.type)
                    ? syncActionEventMessage(
                          nextState.event_messages,
                          action,
                          event.session_id,
                          emittedAt
                      )
                    : null

            return {
                ...nextState,
                tool_calls: toolCalls,
                is_awaiting_turn_action: actionSync
                    ? false
                    : nextState.is_awaiting_turn_action,
                event_messages:
                    actionSync?.messages ?? nextState.event_messages,
                current_action:
                    actionSync?.currentAction ?? nextState.current_action,
                activities: appendActivity(nextState.activities, {
                    id: `${event.session_id}:${emittedAt}:tool-result:${nextToolId}`,
                    runtime_event_type: event.runtime_event_type,
                    title: `${toolDisplayName} finished`,
                    detail: result,
                    timestamp: emittedAt,
                    status,
                    tool_call_id: nextToolId,
                    tool_name:
                        readString(content, 'tool_name') ?? toolDisplayName,
                    skill_name: skillName,
                    agent_name: agentName
                }),
                latest_runtime_event_type: event.runtime_event_type,
                last_event_at: emittedAt
            }
        }
        case 'tool_confirmation':
        case 'waiting_for_user_input':
        case 'reasoning_start':
        case 'agent_thinking_start':
        case 'sub_agent_complete':
        case 'processing':
        case 'complete':
        case 'stream_complete':
        case 'system':
        case 'error':
        case 'agent_response_interrupted':
        case 'model_compact': {
            const flushedThinkingMessages = flushTranscriptBuffer({
                messages: nextState.event_messages,
                kind: 'thinking',
                content: nextState.thinking,
                sessionId: event.session_id,
                emittedAt,
                messageId: nextState.thinking_message_id
            })
            const finalizedResponseContent =
                event.runtime_event_type === 'complete' ||
                event.runtime_event_type === 'stream_complete' ||
                event.runtime_event_type === 'sub_agent_complete'
                    ? (readEventText(content) ?? nextState.response)
                    : nextState.response
            const flushedTranscriptMessages = flushTranscriptBuffer({
                messages: flushedThinkingMessages,
                kind: 'response',
                content: finalizedResponseContent,
                sessionId: event.session_id,
                emittedAt,
                messageId: nextState.response_message_id
            })
            const detail =
                readEventText(content) ??
                stringifyLiveValue(content.result) ??
                stringifyLiveValue(content.summary)
            const titleMap: Record<string, string> = {
                tool_confirmation: 'Waiting for confirmation',
                waiting_for_user_input: 'Waiting for input',
                reasoning_start: 'Thinking',
                agent_thinking_start: 'Thinking',
                sub_agent_complete: agentName
                    ? `Sub-agent finished: ${agentName}`
                    : 'Sub-agent finished',
                processing: 'Processing',
                complete: 'Run completed',
                stream_complete: 'Stream completed',
                system: 'System event',
                error: 'Run error',
                agent_response_interrupted: 'Run interrupted',
                model_compact: 'Session compacted'
            }

            return {
                ...nextState,
                thinking: '',
                response: '',
                thinking_message_id: undefined,
                response_message_id: undefined,
                thinking_started_at: undefined,
                response_started_at: undefined,
                event_messages: flushedTranscriptMessages,
                activities: appendActivity(nextState.activities, {
                    id: `${event.session_id}:${emittedAt}:${event.runtime_event_type}`,
                    runtime_event_type: event.runtime_event_type,
                    title: titleMap[event.runtime_event_type] ?? 'Activity',
                    detail,
                    timestamp: emittedAt,
                    status: inferToolStatus(
                        event.runtime_event_type,
                        event.runtime_event_type === 'error'
                    ),
                    agent_name: agentName
                }),
                latest_runtime_event_type: event.runtime_event_type,
                last_event_at: emittedAt
            }
        }
        default:
            return {
                ...nextState,
                latest_runtime_event_type: event.runtime_event_type,
                last_event_at: emittedAt
            }
    }
}

const replayPersistedLiveSession = (
    session: CoworkChatSessionDetail | null | undefined
): CoworkLiveSessionState | null => {
    if (!session || session.runtime_events.length === 0) {
        return null
    }

    const replayedState = session.runtime_events.reduce<
        CoworkLiveSessionState | undefined
    >((state, event) => reduceCoworkLiveEvent(state, event), undefined)

    if (!replayedState) {
        return null
    }

    return {
        ...replayedState,
        event_messages:
            session.messages.length > 0
                ? retainCoworkActionMessages(replayedState.event_messages)
                : replayedState.event_messages,
        thinking: '',
        response: '',
        thinking_message_id: undefined,
        response_message_id: undefined,
        thinking_started_at: undefined,
        response_started_at: undefined
    }
}

const CoworkPage = () => {
    const [activeMode, setActiveMode] = useState<CoworkModeId | null>(null)
    const [isSidebarOpen, setIsSidebarOpen] = useState(false)
    const [isChatSessionsBoardOpen, setIsChatSessionsBoardOpen] =
        useState(false)
    const [folderModeResetVersion, setFolderModeResetVersion] = useState(0)
    const [isSessionsBoardOpen, setIsSessionsBoardOpen] = useState(false)
    const [isFolderWorkflowActive, setIsFolderWorkflowActive] = useState(false)
    const [pendingDeleteSession, setPendingDeleteSession] =
        useState<CoworkChatSessionSummary | null>(null)
    const [isDeletingSession, setIsDeletingSession] = useState(false)
    const [chatSessionsByScope, setChatSessionsByScope] = useState<
        Record<CoworkChatScope, CoworkChatSessionSummary[]>
    >(() => createScopeRecord([]))
    const [activeChatSessionIds, setActiveChatSessionIds] = useState<
        Record<CoworkChatScope, string | null>
    >(() => createScopeRecord<string | null>(null))
    const [activeChatSessionsByScope, setActiveChatSessionsByScope] = useState<
        Record<CoworkChatScope, CoworkChatSessionDetail | null>
    >(() => createScopeRecord<CoworkChatSessionDetail | null>(null))
    const [isChatSessionsLoadingByScope, setIsChatSessionsLoadingByScope] =
        useState<Record<CoworkChatScope, boolean>>(() =>
            createScopeRecord(true)
        )
    const [isChatSessionLoadingByScope, setIsChatSessionLoadingByScope] =
        useState<Record<CoworkChatScope, boolean>>(() =>
            createScopeRecord(false)
        )
    const [isChatSendingByScope, setIsChatSendingByScope] = useState<
        Record<CoworkChatScope, boolean>
    >(() => createScopeRecord(false))
    const [liveSessionsById, setLiveSessionsById] = useState<
        Record<string, CoworkLiveSessionState>
    >({})
    const [requestedFolderAction, setRequestedFolderAction] =
        useState<ActionStep | null>(null)
    const [requestedFolderActionToken, setRequestedFolderActionToken] =
        useState(0)
    const recoveringSessionIdsRef = useRef<Set<string>>(new Set())
    const suppressedStreamingSessionIdsRef = useRef<Set<string>>(new Set())
    const availableModels = useAppSelector(selectAvailableModels)
    const selectedModelId = useAppSelector(selectSelectedModel)
    const chatToolSettings = useAppSelector(selectChatToolSettings)
    const selectedGitHubRepository = useAppSelector(
        selectSelectedGitHubRepository
    )

    const currentChatScope: CoworkChatScope =
        activeMode === 'intelligent-folder' ? FOLDER_SCOPE : HOMEPAGE_SCOPE

    const currentActiveChatSession = activeChatSessionsByScope[currentChatScope]
    const replayedCurrentLiveSession = useMemo(
        () => replayPersistedLiveSession(currentActiveChatSession),
        [currentActiveChatSession]
    )
    const currentLiveSession = currentActiveChatSession
        ? (liveSessionsById[currentActiveChatSession.id] ??
          replayedCurrentLiveSession ??
          null)
        : null
    const isCurrentChatSessionLoading =
        isChatSessionLoadingByScope[currentChatScope]
    const isCurrentChatSending = isChatSendingByScope[currentChatScope]
    const isCurrentChatInputLocked =
        activeMode === 'intelligent-folder' && !isFolderWorkflowActive

    const homepageChatSessions = chatSessionsByScope[HOMEPAGE_SCOPE]
    const homepageActiveChatSessionId = activeChatSessionIds[HOMEPAGE_SCOPE]
    const folderChatSessions = chatSessionsByScope[FOLDER_SCOPE]
    const folderActiveChatSessionId = activeChatSessionIds[FOLDER_SCOPE]
    const folderActiveChatSession = activeChatSessionsByScope[FOLDER_SCOPE]
    const replayedFolderLiveSession = useMemo(
        () => replayPersistedLiveSession(folderActiveChatSession),
        [folderActiveChatSession]
    )
    const folderLiveSession = folderActiveChatSession
        ? (liveSessionsById[folderActiveChatSession.id] ??
          replayedFolderLiveSession ??
          null)
        : null
    const isFolderSessionLoading = isChatSessionLoadingByScope[FOLDER_SCOPE]

    const resetFolderSessionState = useCallback(() => {
        setActiveChatSessionIds((prev) => ({
            ...prev,
            [FOLDER_SCOPE]: null
        }))
        setActiveChatSessionsByScope((prev) => ({
            ...prev,
            [FOLDER_SCOPE]: null
        }))
        setRequestedFolderAction(null)
        setRequestedFolderActionToken(0)
    }, [])

    const setScopeLoading = useCallback(
        (scope: CoworkChatScope, isLoading: boolean) => {
            setIsChatSessionsLoadingByScope((prev) => ({
                ...prev,
                [scope]: isLoading
            }))
        },
        []
    )

    const setScopeSessionLoading = useCallback(
        (scope: CoworkChatScope, isLoading: boolean) => {
            setIsChatSessionLoadingByScope((prev) => ({
                ...prev,
                [scope]: isLoading
            }))
        },
        []
    )

    const setScopeSending = useCallback(
        (scope: CoworkChatScope, isSending: boolean) => {
            setIsChatSendingByScope((prev) => ({
                ...prev,
                [scope]: isSending
            }))
        },
        []
    )

    const prepareLiveRunState = useCallback(
        (
            sessionId: string | null | undefined,
            session?: CoworkChatSessionDetail | null
        ) => {
            if (!sessionId) {
                return
            }

            setLiveSessionsById((prev) => {
                const current = prev[sessionId]
                const replayed = current
                    ? null
                    : replayPersistedLiveSession(session)
                const baseline: CoworkLiveSessionState = current ??
                    replayed ?? {
                        session_id: sessionId,
                        scope: session?.scope ?? currentChatScope,
                        thinking: '',
                        response: '',
                        is_awaiting_turn_action: false,
                        tool_calls: [],
                        activities: [],
                        event_messages: []
                    }

                return {
                    ...prev,
                    [sessionId]: {
                        ...baseline,
                        thinking: '',
                        response: '',
                        is_awaiting_turn_action: true,
                        event_messages: retainCoworkActionMessages(
                            baseline.event_messages
                        ),
                        thinking_message_id: undefined,
                        response_message_id: undefined,
                        thinking_started_at: undefined,
                        response_started_at: undefined,
                        tool_calls: [],
                        current_action: undefined
                    }
                }
            })
        },
        [currentChatScope]
    )

    const finalizeLiveRunState = useCallback(
        (sessionId: string | null | undefined) => {
            if (!sessionId) {
                return
            }

            setLiveSessionsById((prev) => {
                const current = prev[sessionId]
                if (!current) {
                    return prev
                }

                return {
                    ...prev,
                    [sessionId]: {
                        ...current,
                        thinking: '',
                        response: '',
                        event_messages: retainCoworkActionMessages(
                            current.event_messages
                        ),
                        is_awaiting_turn_action: false,
                        thinking_message_id: undefined,
                        response_message_id: undefined,
                        thinking_started_at: undefined,
                        response_started_at: undefined
                    }
                }
            })
        },
        []
    )

    const removeLiveSessionState = useCallback(
        (sessionId: string | null | undefined) => {
            if (!sessionId) {
                return
            }

            setLiveSessionsById((prev) => {
                if (!prev[sessionId]) {
                    return prev
                }

                const next = { ...prev }
                delete next[sessionId]
                return next
            })
        },
        []
    )

    const handleStopCurrentChatSession = useCallback(async () => {
        const activeSession = currentActiveChatSession

        if (!activeSession) {
            return
        }

        if (
            activeSession.run_status !== 'thinking' &&
            activeSession.run_status !== 'waiting_for_input'
        ) {
            return
        }

        try {
            suppressedStreamingSessionIdsRef.current.add(activeSession.id)
            const stoppedSession = await coworkService.stopChatSession(
                activeSession.id,
                activeSession.scope
            )
            recoveringSessionIdsRef.current.delete(stoppedSession.id)
            removeLiveSessionState(stoppedSession.id)
            setActiveChatSessionsByScope((prev) => ({
                ...prev,
                [stoppedSession.scope]: stoppedSession
            }))
            setChatSessionsByScope((prev) => ({
                ...prev,
                [stoppedSession.scope]: upsertChatSessionSummary(
                    prev[stoppedSession.scope],
                    buildChatSessionSummary(stoppedSession)
                )
            }))
        } catch (error) {
            console.error('Failed to stop Cowork session', error)
            suppressedStreamingSessionIdsRef.current.delete(activeSession.id)
            toast.error(
                error instanceof Error
                    ? error.message
                    : 'Unable to stop the Cowork session right now.'
            )
        }
    }, [currentActiveChatSession, removeLiveSessionState])

    useEffect(() => {
        const session = currentActiveChatSession
        if (!session) {
            return
        }

        const hasActiveLiveStream = Boolean(liveSessionsById[session.id])

        if (
            hasActiveLiveStream ||
            isCurrentChatSending ||
            (session.run_status !== 'thinking' &&
                session.run_status !== 'waiting_for_input')
        ) {
            recoveringSessionIdsRef.current.delete(session.id)
            return
        }

        if (recoveringSessionIdsRef.current.has(session.id)) {
            return
        }

        recoveringSessionIdsRef.current.add(session.id)
        void handleStopCurrentChatSession()
    }, [
        currentActiveChatSession,
        handleStopCurrentChatSession,
        isCurrentChatSending,
        liveSessionsById
    ])

    useEffect(() => {
        let unlisten: (() => void) | undefined

        void listen<CoworkChatLiveEvent>('cowork://stream', ({ payload }) => {
            if (!payload) {
                return
            }

            const eventSessionId =
                payload.type === 'session.created' ||
                payload.type === 'session.updated'
                    ? payload.session.id
                    : 'session_id' in payload
                      ? payload.session_id
                      : undefined

            if (
                eventSessionId &&
                suppressedStreamingSessionIdsRef.current.has(eventSessionId)
            ) {
                return
            }

            if (
                payload.type === 'session.created' ||
                payload.type === 'session.updated'
            ) {
                const session = payload.session
                const shouldActivateSession = payload.type === 'session.created'
                setChatSessionsByScope((prev) => ({
                    ...prev,
                    [session.scope]: upsertChatSessionSummary(
                        prev[session.scope],
                        session
                    )
                }))
                if (shouldActivateSession) {
                    setActiveChatSessionIds((prev) => ({
                        ...prev,
                        [session.scope]: session.id
                    }))
                }
                setActiveChatSessionsByScope((prev) => {
                    const currentSession = prev[session.scope]
                    const shouldMerge =
                        shouldActivateSession ||
                        currentSession?.id === session.id

                    if (!shouldMerge) {
                        return prev
                    }

                    return {
                        ...prev,
                        [session.scope]: buildSessionDetailFromSummary(
                            session,
                            currentSession
                        )
                    }
                })
                return
            }

            if (payload.type === 'message.created') {
                setActiveChatSessionsByScope((prev) => {
                    const currentSession = prev[payload.scope]
                    if (
                        !currentSession ||
                        currentSession.id !== payload.session_id
                    ) {
                        return prev
                    }

                    const nextSession = {
                        ...currentSession,
                        messages: appendMessageIfMissing(
                            currentSession.messages,
                            payload.message
                        ),
                        message_count:
                            currentSession.messages.length +
                            (currentSession.messages.some(
                                (message) => message.id === payload.message.id
                            )
                                ? 0
                                : 1),
                        updated_at: payload.message.created_at,
                        preview:
                            payload.message.role === 'assistant'
                                ? payload.message.content
                                : currentSession.preview
                    }

                    return {
                        ...prev,
                        [payload.scope]: nextSession
                    }
                })
                return
            }

            if (payload.type === 'files.updated') {
                setActiveChatSessionsByScope((prev) => {
                    const currentSession = prev[payload.scope]
                    if (
                        !currentSession ||
                        currentSession.id !== payload.session_id
                    ) {
                        return prev
                    }

                    return {
                        ...prev,
                        [payload.scope]: {
                            ...currentSession,
                            files: payload.files
                        }
                    }
                })
                return
            }

            if (payload.type === 'status.updated') {
                setActiveChatSessionsByScope((prev) => {
                    const currentSession = prev[payload.scope]
                    if (
                        !currentSession ||
                        currentSession.id !== payload.session_id
                    ) {
                        return prev
                    }

                    return {
                        ...prev,
                        [payload.scope]: {
                            ...currentSession,
                            run_status: payload.status
                        }
                    }
                })
            }

            if (payload.type === 'runtime.event') {
                setActiveChatSessionsByScope((prev) => {
                    const currentSession = prev[payload.scope]
                    if (
                        !currentSession ||
                        currentSession.id !== payload.session_id
                    ) {
                        return prev
                    }

                    return {
                        ...prev,
                        [payload.scope]: {
                            ...currentSession,
                            runtime_events: appendRuntimeEventIfMissing(
                                currentSession.runtime_events,
                                payload
                            ),
                            updated_at: payload.emitted_at
                        }
                    }
                })
                setLiveSessionsById((prev) => {
                    const nextState = reduceCoworkLiveEvent(
                        prev[payload.session_id],
                        payload
                    )
                    if (!nextState) {
                        return prev
                    }

                    return {
                        ...prev,
                        [payload.session_id]: nextState
                    }
                })
            }
        }).then((dispose) => {
            unlisten = dispose
        })

        return () => {
            unlisten?.()
        }
    }, [])

    const refreshChatSessions = useCallback(
        async (scope: CoworkChatScope) => {
            setScopeLoading(scope, true)
            try {
                const sessions = await coworkService.getChatSessions(scope)
                setChatSessionsByScope((prev) => ({
                    ...prev,
                    [scope]: sessions
                }))
            } finally {
                setScopeLoading(scope, false)
            }
        },
        [setScopeLoading]
    )

    const loadChatSession = useCallback(
        async (sessionId: string, scope: CoworkChatScope) => {
            setScopeSessionLoading(scope, true)

            try {
                let session = await coworkService.getChatSession(
                    sessionId,
                    scope
                )
                if (
                    session.run_status === 'thinking' ||
                    session.run_status === 'waiting_for_input'
                ) {
                    session = await coworkService.stopChatSession(
                        session.id,
                        session.scope
                    )
                }
                setActiveChatSessionIds((prev) => ({
                    ...prev,
                    [session.scope]: session.id
                }))
                setActiveChatSessionsByScope((prev) => ({
                    ...prev,
                    [session.scope]: session
                }))
                setChatSessionsByScope((prev) => ({
                    ...prev,
                    [session.scope]: upsertChatSessionSummary(
                        prev[session.scope],
                        {
                            id: session.id,
                            scope: session.scope,
                            title: session.title,
                            preview: session.preview,
                            updated_at: session.updated_at,
                            message_count: session.messages.length
                        }
                    )
                }))
            } finally {
                setScopeSessionLoading(scope, false)
            }
        },
        [setScopeSessionLoading]
    )

    useEffect(() => {
        void Promise.all([
            refreshChatSessions(HOMEPAGE_SCOPE),
            refreshChatSessions(FOLDER_SCOPE)
        ])
    }, [refreshChatSessions])

    const handleGoHomepage = () => {
        setActiveMode(null)
        setIsSidebarOpen(false)
        setIsChatSessionsBoardOpen(false)
        setIsSessionsBoardOpen(false)
        setIsFolderWorkflowActive(false)
    }

    const handleSelectMode = (mode: CoworkModeId) => {
        setActiveMode(mode)
        setIsChatSessionsBoardOpen(false)
        setIsSessionsBoardOpen(false)

        if (mode === 'intelligent-folder') {
            resetFolderSessionState()
            setFolderModeResetVersion((prev) => prev + 1)
            setIsFolderWorkflowActive(false)
            setRequestedFolderAction(null)
            setRequestedFolderActionToken(0)
        }
    }

    const handleChatSessionsBoardOpenChange = (open: boolean) => {
        setIsChatSessionsBoardOpen(open)
        if (open) {
            setIsSessionsBoardOpen(false)
        }
    }

    const handleSessionsBoardOpenChange = (open: boolean) => {
        setIsSessionsBoardOpen(open)
    }

    const handleFolderWorkflowActiveChange = (active: boolean) => {
        setIsFolderWorkflowActive(active)
    }

    const handleOpenModeFirstPage = () => {
        if (activeMode === 'intelligent-folder') {
            resetFolderSessionState()
            setFolderModeResetVersion((prev) => prev + 1)
            setIsFolderWorkflowActive(false)
        }

        setIsChatSessionsBoardOpen(false)
        setIsSessionsBoardOpen(false)
    }

    const handleSelectSession = async (sessionId: string) => {
        setIsChatSessionsBoardOpen(false)
        setIsSessionsBoardOpen(false)

        if (sessionId !== activeChatSessionIds[FOLDER_SCOPE]) {
            await loadChatSession(sessionId, FOLDER_SCOPE)
        }
    }

    const handleRenameSession = useCallback(
        async (sessionId: string) => {
            const currentSummary = chatSessionsByScope[FOLDER_SCOPE].find(
                (session) => session.id === sessionId
            )
            const nextTitle = window.prompt(
                'Rename session',
                currentSummary?.title ?? ''
            )

            if (!nextTitle || !nextTitle.trim()) {
                return
            }

            const renamedSession = await coworkService.renameFolderSession(
                sessionId,
                nextTitle
            )

            setChatSessionsByScope((prev) => ({
                ...prev,
                [FOLDER_SCOPE]: upsertChatSessionSummary(
                    prev[FOLDER_SCOPE],
                    buildChatSessionSummary(renamedSession)
                )
            }))
            setActiveChatSessionsByScope((prev) => ({
                ...prev,
                [FOLDER_SCOPE]:
                    prev[FOLDER_SCOPE]?.id === renamedSession.id
                        ? renamedSession
                        : prev[FOLDER_SCOPE]
            }))
        },
        [chatSessionsByScope]
    )

    const handleRenameChatSession = useCallback(
        async (sessionId: string) => {
            const currentSummary = chatSessionsByScope[HOMEPAGE_SCOPE].find(
                (session) => session.id === sessionId
            )
            const nextTitle = window.prompt(
                'Rename chat session',
                currentSummary?.title ?? ''
            )

            if (!nextTitle || !nextTitle.trim()) {
                return
            }

            const renamedSession =
                await coworkService.renameHomepageChatSession(
                    sessionId,
                    nextTitle
                )

            setChatSessionsByScope((prev) => ({
                ...prev,
                [HOMEPAGE_SCOPE]: upsertChatSessionSummary(
                    prev[HOMEPAGE_SCOPE],
                    buildChatSessionSummary(renamedSession)
                )
            }))
            setActiveChatSessionsByScope((prev) => ({
                ...prev,
                [HOMEPAGE_SCOPE]:
                    prev[HOMEPAGE_SCOPE]?.id === renamedSession.id
                        ? renamedSession
                        : prev[HOMEPAGE_SCOPE]
            }))
        },
        [chatSessionsByScope]
    )

    const handleDeleteSession = useCallback(
        (sessionId: string) => {
            const currentSummary = chatSessionsByScope[FOLDER_SCOPE].find(
                (session) => session.id === sessionId
            )

            setPendingDeleteSession(
                currentSummary ?? {
                    id: sessionId,
                    scope: FOLDER_SCOPE,
                    title: sessionId,
                    preview: '',
                    updated_at: '',
                    message_count: 0
                }
            )
        },
        [chatSessionsByScope]
    )

    const handleDeleteChatSession = useCallback(
        (sessionId: string) => {
            const currentSummary = chatSessionsByScope[HOMEPAGE_SCOPE].find(
                (session) => session.id === sessionId
            )

            setPendingDeleteSession(
                currentSummary ?? {
                    id: sessionId,
                    scope: HOMEPAGE_SCOPE,
                    title: sessionId,
                    preview: '',
                    updated_at: '',
                    message_count: 0
                }
            )
        },
        [chatSessionsByScope]
    )

    const handleConfirmDeleteSession = useCallback(async () => {
        if (!pendingDeleteSession || isDeletingSession) {
            return
        }

        const sessionId = pendingDeleteSession.id
        const sessionScope = pendingDeleteSession.scope
        setIsDeletingSession(true)

        try {
            if (sessionScope === HOMEPAGE_SCOPE) {
                await coworkService.deleteHomepageChatSession(sessionId)
            } else {
                await coworkService.deleteFolderSession(sessionId)
            }

            setChatSessionsByScope((prev) => ({
                ...prev,
                [sessionScope]: prev[sessionScope].filter(
                    (session) => session.id !== sessionId
                )
            }))

            if (sessionScope === HOMEPAGE_SCOPE) {
                if (activeChatSessionIds[HOMEPAGE_SCOPE] === sessionId) {
                    setActiveChatSessionIds((prev) => ({
                        ...prev,
                        [HOMEPAGE_SCOPE]: null
                    }))
                    setActiveChatSessionsByScope((prev) => ({
                        ...prev,
                        [HOMEPAGE_SCOPE]: null
                    }))
                }
            } else if (activeChatSessionIds[FOLDER_SCOPE] === sessionId) {
                resetFolderSessionState()
                setFolderModeResetVersion((prev) => prev + 1)
                setIsFolderWorkflowActive(false)
            }

            removeLiveSessionState(sessionId)
            setPendingDeleteSession(null)
        } finally {
            setIsDeletingSession(false)
        }
    }, [
        activeChatSessionIds,
        isDeletingSession,
        pendingDeleteSession,
        removeLiveSessionState,
        resetFolderSessionState
    ])

    const handleDeleteDialogOpenChange = useCallback(
        (open: boolean) => {
            if (!open && !isDeletingSession) {
                setPendingDeleteSession(null)
            }
        },
        [isDeletingSession]
    )

    const handleFolderSessionCreated = useCallback(
        (session: CoworkChatSessionDetail) => {
            setRequestedFolderAction(null)
            setRequestedFolderActionToken((prev) => prev + 1)
            setChatSessionsByScope((prev) => ({
                ...prev,
                [FOLDER_SCOPE]: upsertChatSessionSummary(
                    prev[FOLDER_SCOPE],
                    buildChatSessionSummary(session)
                )
            }))
            setActiveChatSessionIds((prev) => ({
                ...prev,
                [FOLDER_SCOPE]: session.id
            }))
            setActiveChatSessionsByScope((prev) => ({
                ...prev,
                [FOLDER_SCOPE]: session
            }))
        },
        []
    )

    const handleSelectCoworkAction = useCallback(
        (action: ActionStep) => {
            if (currentChatScope !== FOLDER_SCOPE) {
                return
            }

            if (!isCoworkBuildPanelActionVisible(action)) {
                return
            }

            setRequestedFolderAction(action)
            setRequestedFolderActionToken((prev) => prev + 1)
        },
        [currentChatScope]
    )

    const handleSelectChatSession = async (sessionId: string) => {
        setActiveMode(null)
        setIsChatSessionsBoardOpen(false)
        setIsSessionsBoardOpen(false)

        if (sessionId !== homepageActiveChatSessionId) {
            await loadChatSession(sessionId, HOMEPAGE_SCOPE)
        }
    }

    const handleNewChatSession = () => {
        setActiveMode(null)
        setIsChatSessionsBoardOpen(false)
        setIsSessionsBoardOpen(false)
        setActiveChatSessionIds((prev) => ({
            ...prev,
            [HOMEPAGE_SCOPE]: null
        }))
        setActiveChatSessionsByScope((prev) => ({
            ...prev,
            [HOMEPAGE_SCOPE]: null
        }))
    }

    const handleSendChatMessage = useCallback(
        async (content: string) => {
            const scope = currentChatScope
            const currentSessionId = activeChatSessionIds[scope]
            const currentSession = activeChatSessionsByScope[scope]
            const selectedModel =
                availableModels.find((model) => model.id === selectedModelId) ??
                availableModels[0]

            if (!selectedModel) {
                toast.error(
                    'No AI model is configured. Please add a model in settings first.'
                )
                return
            }

            if (scope === FOLDER_SCOPE) {
                setRequestedFolderAction(null)
                setRequestedFolderActionToken((prev) => prev + 1)
            }

            setScopeSending(scope, true)
            prepareLiveRunState(currentSessionId, currentSession)

            try {
                const response = await coworkService.sendChatMessage({
                    session_id: currentSessionId,
                    runtime_kind: currentSession?.runtime_kind ?? 'remote',
                    scope,
                    content,
                    model_id: selectedModel.id,
                    tools: chatToolSettings,
                    github_repository: selectedGitHubRepository
                })

                let latestSummary: CoworkChatSessionSummary | null = null

                for (const event of response.events) {
                    if (
                        event.type === 'session.created' ||
                        event.type === 'session.updated'
                    ) {
                        latestSummary = event.session
                    }
                }

                const hydratedSession = await coworkService.getChatSession(
                    response.session_id,
                    scope
                )
                const isSuppressed =
                    suppressedStreamingSessionIdsRef.current.has(
                        hydratedSession.id
                    )
                let resolvedSession = isSuppressed
                    ? await coworkService.stopChatSession(
                          hydratedSession.id,
                          scope
                      )
                    : hydratedSession

                if (
                    scope === FOLDER_SCOPE &&
                    resolvedSession.folder_tree_pair?.source_root
                ) {
                    resolvedSession = await coworkService.getChatSession(
                        resolvedSession.id,
                        scope
                    )
                }

                const sessionSummary =
                    latestSummary ?? buildChatSessionSummary(resolvedSession)

                setChatSessionsByScope((prev) => ({
                    ...prev,
                    [scope]: upsertChatSessionSummary(
                        prev[scope],
                        sessionSummary
                    )
                }))
                setActiveChatSessionIds((prev) => ({
                    ...prev,
                    [scope]: resolvedSession.id
                }))
                setActiveChatSessionsByScope((prev) => ({
                    ...prev,
                    [scope]: resolvedSession
                }))
                finalizeLiveRunState(resolvedSession.id)
                suppressedStreamingSessionIdsRef.current.delete(
                    resolvedSession.id
                )
            } catch (error) {
                console.error('Failed to send Cowork chat message', error)
                toast.error(
                    error instanceof Error
                        ? error.message
                        : 'Unable to send the Cowork message right now.'
                )
            } finally {
                if (currentSessionId) {
                    suppressedStreamingSessionIdsRef.current.delete(
                        currentSessionId
                    )
                }
                setScopeSending(scope, false)
            }
        },
        [
            activeChatSessionIds,
            activeChatSessionsByScope,
            availableModels,
            chatToolSettings,
            finalizeLiveRunState,
            currentChatScope,
            prepareLiveRunState,
            selectedGitHubRepository,
            selectedModelId,
            setScopeSending
        ]
    )

    return (
        <DesignModeProvider>
            <div className="flex h-screen">
                <SidebarProvider className="!w-auto flex-1 min-w-0">
                    <div className="flex-1 min-w-0 overflow-hidden">
                        <CoworkHeader />
                        <Sidebar className="block md:hidden" />
                        <div className="flex h-[calc(100vh-86px)] flex-col md:h-[calc(100vh-53px)] md:flex-row">
                            <div className="flex h-full min-w-0 flex-1 flex-col overflow-hidden">
                                <CoworkTabs
                                    activeMode={activeMode}
                                    onOpenSidebar={() => setIsSidebarOpen(true)}
                                    onGoHomepage={handleGoHomepage}
                                    onOpenModeFirstPage={
                                        handleOpenModeFirstPage
                                    }
                                    isChatSessionsBoardOpen={
                                        isChatSessionsBoardOpen
                                    }
                                    onChatSessionsBoardOpenChange={
                                        handleChatSessionsBoardOpenChange
                                    }
                                    chatSessions={homepageChatSessions}
                                    activeChatSessionId={
                                        homepageActiveChatSessionId
                                    }
                                    isChatSessionsLoading={
                                        isChatSessionsLoadingByScope[
                                            HOMEPAGE_SCOPE
                                        ]
                                    }
                                    onNewChatSession={handleNewChatSession}
                                    onSelectChatSession={
                                        handleSelectChatSession
                                    }
                                    onRenameChatSession={
                                        handleRenameChatSession
                                    }
                                    onDeleteChatSession={
                                        handleDeleteChatSession
                                    }
                                    isSessionsBoardOpen={isSessionsBoardOpen}
                                    onSessionsBoardOpenChange={
                                        handleSessionsBoardOpenChange
                                    }
                                    modeSessions={folderChatSessions}
                                    activeModeSessionId={
                                        folderActiveChatSessionId
                                    }
                                    isModeSessionsLoading={
                                        isChatSessionsLoadingByScope[
                                            FOLDER_SCOPE
                                        ]
                                    }
                                    onSelectSession={handleSelectSession}
                                    onRenameSession={handleRenameSession}
                                    onDeleteSession={handleDeleteSession}
                                />
                                <div className="min-h-0 flex-1 overflow-hidden">
                                    <CoworkMain
                                        activeMode={activeMode}
                                        folderSession={folderActiveChatSession}
                                        folderLiveSession={folderLiveSession}
                                        isFolderSessionLoading={
                                            isFolderSessionLoading
                                        }
                                        isFolderChatSending={
                                            isChatSendingByScope[FOLDER_SCOPE]
                                        }
                                        onSelectMode={handleSelectMode}
                                        folderModeResetVersion={
                                            folderModeResetVersion
                                        }
                                        onFolderWorkflowActiveChange={
                                            handleFolderWorkflowActiveChange
                                        }
                                        onFolderSessionCreated={
                                            handleFolderSessionCreated
                                        }
                                        requestedFolderAction={
                                            requestedFolderAction
                                        }
                                        requestedFolderActionToken={
                                            requestedFolderActionToken
                                        }
                                    />
                                </div>
                            </div>
                            <CoworkChatBox
                                isVisible={true}
                                scope={currentChatScope}
                                activeSession={currentActiveChatSession}
                                liveSession={currentLiveSession}
                                isLoading={isCurrentChatSessionLoading}
                                isSending={isCurrentChatSending}
                                isInputLocked={isCurrentChatInputLocked}
                                onSendMessage={handleSendChatMessage}
                                onStopSession={handleStopCurrentChatSession}
                                onSelectAction={handleSelectCoworkAction}
                            />
                        </div>
                    </div>
                </SidebarProvider>
                <RightSidebar />
                <CoworkSidebar
                    open={isSidebarOpen}
                    activeMode={activeMode}
                    onOpenChange={setIsSidebarOpen}
                    onGoHomepage={handleGoHomepage}
                    onSelectMode={handleSelectMode}
                />
                <AlertDialog
                    open={pendingDeleteSession !== null}
                    onOpenChange={handleDeleteDialogOpenChange}
                >
                    <AlertDialogContent>
                        <AlertDialogHeader>
                            <AlertDialogTitle>
                                {pendingDeleteSession?.scope === HOMEPAGE_SCOPE
                                    ? 'Delete chat session?'
                                    : 'Delete folder session?'}
                            </AlertDialogTitle>
                            <AlertDialogDescription>
                                {`Session "${pendingDeleteSession?.title ?? ''}" will be removed from this device.`}
                            </AlertDialogDescription>
                        </AlertDialogHeader>
                        <AlertDialogFooter>
                            <AlertDialogCancel disabled={isDeletingSession}>
                                Cancel
                            </AlertDialogCancel>
                            <Button
                                type="button"
                                className="bg-red-600 text-white hover:bg-red-700 dark:bg-red-500 dark:text-white dark:hover:bg-red-400"
                                onClick={handleConfirmDeleteSession}
                                disabled={isDeletingSession}
                            >
                                {isDeletingSession ? 'Deleting...' : 'Delete'}
                            </Button>
                        </AlertDialogFooter>
                    </AlertDialogContent>
                </AlertDialog>
            </div>
        </DesignModeProvider>
    )
}

export default CoworkPage
