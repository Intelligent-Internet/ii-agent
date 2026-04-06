import { useEffect, useMemo } from 'react'
import {
    setCurrentQuestion,
    setEditingMessage,
    setLoading,
    setMessages,
    setQuestionMode,
    setRunStatus,
    setWorkspaceInfo,
    useAppDispatch
} from '@/state'
import { QUESTION_MODE, type Message } from '@/typings/agent'
import type {
    CoworkChatSessionDetail,
    CoworkLiveSessionState
} from '@/typings/cowork'
import {
    buildCoworkTranscriptMessageId,
    resolveCoworkTranscriptAnchor
} from './cowork-chatmessage-contract'

const mapPersistedMessages = (
    activeSession: CoworkChatSessionDetail | null
): Message[] =>
    (activeSession?.messages ?? []).map((message) => ({
        id: message.id,
        role: message.role,
        content: message.content,
        timestamp: new Date(message.created_at).getTime(),
        isThinkMessage: message.is_think_message
    }))

const mapLiveMessages = (
    liveSession: CoworkLiveSessionState | null
): Message[] => {
    if (!liveSession) {
        return []
    }

    const nextMessages: Message[] = []

    if (liveSession.thinking.trim()) {
        nextMessages.push({
            id:
                liveSession.thinking_message_id ??
                buildCoworkTranscriptMessageId(
                    'thinking',
                    resolveCoworkTranscriptAnchor(
                        liveSession.thinking_started_at,
                        liveSession.session_id
                    ) ?? liveSession.session_id
                ),
            role: 'assistant',
            content: liveSession.thinking,
            timestamp: new Date(
                liveSession.thinking_started_at ?? Date.now()
            ).getTime(),
            isThinkMessage: true
        })
    }

    if (liveSession.response.trim()) {
        nextMessages.push({
            id:
                liveSession.response_message_id ??
                buildCoworkTranscriptMessageId(
                    'response',
                    resolveCoworkTranscriptAnchor(
                        liveSession.response_started_at,
                        liveSession.session_id
                    ) ?? liveSession.session_id
                ),
            role: 'assistant',
            content: liveSession.response,
            timestamp: new Date(
                liveSession.response_started_at ?? Date.now()
            ).getTime()
        })
    }

    return nextMessages
}

const sortTimelineMessages = (messages: Message[]) =>
    messages
        .map((message, index) => ({ message, index }))
        .sort((left, right) => {
            if (left.message.timestamp === right.message.timestamp) {
                return left.index - right.index
            }

            return left.message.timestamp - right.message.timestamp
        })
        .map(({ message }) => message)

const buildCoworkMessages = ({
    activeSession,
    liveSession
}: {
    activeSession: CoworkChatSessionDetail | null
    liveSession: CoworkLiveSessionState | null
}): Message[] => {
    const persistedMessages = mapPersistedMessages(activeSession)
    const eventMessages = liveSession?.event_messages ?? []
    const persistedMessageIds = new Set(
        persistedMessages.map((message) => message.id)
    )
    const liveMessages = mapLiveMessages(liveSession).filter(
        (message) => !persistedMessageIds.has(message.id)
    )
    const liveEventMessages = eventMessages.filter(
        (message) => !persistedMessageIds.has(message.id)
    )

    if (liveEventMessages.length === 0 && liveMessages.length === 0) {
        return persistedMessages
    }

    return sortTimelineMessages([
        ...persistedMessages,
        ...liveEventMessages,
        ...liveMessages
    ])
}

const mapCoworkRunStatus = ({
    activeSession,
    liveSession,
    isSending
}: {
    activeSession: CoworkChatSessionDetail | null
    liveSession: CoworkLiveSessionState | null
    isSending: boolean
}) => {
    if (activeSession?.run_status === 'completed') {
        return 'completed'
    }

    if (activeSession?.run_status === 'waiting_for_input') {
        return 'paused'
    }

    if (activeSession?.run_status === 'stopped') {
        return 'aborted'
    }

    if (
        isSending ||
        activeSession?.run_status === 'thinking' ||
        Boolean(
            liveSession?.thinking.trim() ||
                liveSession?.response.trim() ||
                liveSession?.event_messages.length ||
                liveSession?.tool_calls.length
        )
    ) {
        return 'running'
    }

    return null
}

interface UseCoworkChatMessageAdapterOptions {
    activeSession: CoworkChatSessionDetail | null
    liveSession?: CoworkLiveSessionState | null
    isLoading?: boolean
    isSending?: boolean
}

export const useCoworkChatMessageAdapter = ({
    activeSession,
    liveSession = null,
    isLoading = false,
    isSending = false
}: UseCoworkChatMessageAdapterOptions) => {
    const dispatch = useAppDispatch()

    const messages = useMemo(
        () => buildCoworkMessages({ activeSession, liveSession }),
        [activeSession, liveSession]
    )
    const runStatus = useMemo(
        () => mapCoworkRunStatus({ activeSession, liveSession, isSending }),
        [activeSession, liveSession, isSending]
    )
    const isChatLoading = Boolean(
        isLoading ||
            runStatus === 'running' ||
            activeSession?.run_status === 'thinking'
    )

    useEffect(() => {
        dispatch(setQuestionMode(QUESTION_MODE.COWORK))
        dispatch(setWorkspaceInfo(''))
    }, [dispatch])

    useEffect(() => {
        dispatch(setMessages(messages))
    }, [dispatch, messages])

    useEffect(() => {
        dispatch(setRunStatus(runStatus))
    }, [dispatch, runStatus])

    useEffect(() => {
        dispatch(setLoading(isChatLoading))
    }, [dispatch, isChatLoading])

    useEffect(() => {
        dispatch(setEditingMessage(undefined))
    }, [dispatch, activeSession?.id])

    useEffect(() => {
        return () => {
            dispatch(setMessages([]))
            dispatch(setRunStatus(null))
            dispatch(setLoading(false))
            dispatch(setCurrentQuestion(''))
            dispatch(setEditingMessage(undefined))
        }
    }, [dispatch])
}
