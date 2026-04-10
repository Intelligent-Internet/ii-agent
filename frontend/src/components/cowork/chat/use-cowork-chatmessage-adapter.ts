import { useEffect, useMemo, useRef, useState } from 'react'
import {
    setQuestionMode,
    useAppDispatch
} from '@/state'
import { QUESTION_MODE, type Message } from '@/typings/agent'
import { useChatMessageAdapterState } from '@/components/agent/use-chat-message-adapter-state'
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

const STREAM_REVEAL_TICK_MS = 24
const STREAM_REVEAL_MAX_STEP = 12

const useAnimatedStreamText = (
    targetText: string,
    streamKey: string | null
) => {
    const [renderedText, setRenderedText] = useState(targetText)
    const previousStreamKeyRef = useRef<string | null>(streamKey)

    useEffect(() => {
        if (!targetText) {
            setRenderedText('')
            previousStreamKeyRef.current = streamKey
            return
        }

        if (previousStreamKeyRef.current !== streamKey) {
            previousStreamKeyRef.current = streamKey
            setRenderedText('')
            return
        }

        setRenderedText((currentText) => {
            if (!currentText) {
                return currentText
            }

            if (
                currentText.length > targetText.length ||
                !targetText.startsWith(currentText)
            ) {
                return targetText
            }

            return currentText
        })
    }, [streamKey, targetText])

    useEffect(() => {
        if (!targetText || renderedText === targetText) {
            return
        }

        if (
            renderedText.length > targetText.length ||
            !targetText.startsWith(renderedText)
        ) {
            setRenderedText(targetText)
            return
        }

        const timeoutId = window.setTimeout(() => {
            setRenderedText((currentText) => {
                if (
                    currentText.length >= targetText.length ||
                    !targetText.startsWith(currentText)
                ) {
                    return targetText
                }

                const remainingLength = targetText.length - currentText.length
                const nextStep = Math.max(
                    1,
                    Math.min(
                        STREAM_REVEAL_MAX_STEP,
                        Math.ceil(remainingLength / 6)
                    )
                )

                return targetText.slice(0, currentText.length + nextStep)
            })
        }, STREAM_REVEAL_TICK_MS)

        return () => {
            window.clearTimeout(timeoutId)
        }
    }, [renderedText, targetText])

    return renderedText
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

const buildTranscriptSignature = (message: Message) =>
    message.action
        ? null
        : `${message.role}:${message.isThinkMessage ? 'think' : 'text'}:${
              message.content?.trim() ?? ''
          }`

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
    const persistedTranscriptSignatures = new Set(
        persistedMessages
            .map(buildTranscriptSignature)
            .filter((signature): signature is string => Boolean(signature))
    )
    const liveEventMessages = eventMessages.filter(
        (message) =>
            !persistedMessageIds.has(message.id) &&
            (message.action ||
                !persistedTranscriptSignatures.has(
                    buildTranscriptSignature(message) ?? ''
                ))
    )
    const liveEventMessageIds = new Set(
        liveEventMessages.map((message) => message.id)
    )
    const liveMessages = mapLiveMessages(liveSession).filter(
        (message) =>
            !persistedMessageIds.has(message.id) &&
            !liveEventMessageIds.has(message.id)
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
    const animatedThinking = useAnimatedStreamText(
        liveSession?.thinking ?? '',
        liveSession?.thinking_message_id ?? null
    )
    const animatedResponse = useAnimatedStreamText(
        liveSession?.response ?? '',
        liveSession?.response_message_id ?? null
    )
    const animatedLiveSession = useMemo(() => {
        if (!liveSession) {
            return null
        }

        return {
            ...liveSession,
            thinking: animatedThinking,
            response: animatedResponse
        }
    }, [animatedResponse, animatedThinking, liveSession])

    const messages = useMemo(
        () =>
            buildCoworkMessages({
                activeSession,
                liveSession: animatedLiveSession
            }),
        [activeSession, animatedLiveSession]
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

    useChatMessageAdapterState({
        messages,
        runStatus,
        isLoading: isChatLoading,
        workspaceInfo: '',
        resetEditingOnKey: activeSession?.id ?? 'cowork-empty'
    })

    useEffect(() => {
        dispatch(setQuestionMode(QUESTION_MODE.COWORK))
    }, [dispatch])
}
