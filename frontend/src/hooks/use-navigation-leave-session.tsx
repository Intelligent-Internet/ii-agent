import { useEffect, useRef } from 'react'
import { useLocation, useParams } from 'react-router'
import { useSocketIOContext } from '@/contexts/websocket-context'
import {
    setActiveSessionId,
    setActiveTab,
    setIsMobileChatVisible,
    setLoading,
    setSandboxIframeAwake,
    setSandboxStatus,
    useAppDispatch,
    setMessages
} from '@/state'
import { TAB } from '@/typings'
import { useSessionStateManager } from './use-session-state-manager'
import { useChat } from './use-chat-query'

export function useNavigationLeaveSession() {
    const dispatch = useAppDispatch()
    const location = useLocation()
    const { sessionId } = useParams()
    const { socket } = useSocketIOContext()
    const previousSessionIdRef = useRef<string | undefined>(sessionId)
    const previousPathRef = useRef<string>(location.pathname)

    const { saveCurrentSessionState, resetSessionState } =
        useSessionStateManager()
    const { resetConversationState, setSessionId } = useChat()

    useEffect(() => {
        const currentPath = location.pathname
        const previousPath = previousPathRef.current
        const previousSessionId = previousSessionIdRef.current
        const currentSessionId = sessionId

        // Detect if we're switching from one session to another
        const isSwitchingSessions =
            previousSessionId &&
            currentSessionId &&
            previousSessionId !== currentSessionId

        const isLeavingAgentPage =
            previousSessionId &&
            !currentPath.includes(previousSessionId) &&
            previousPath.includes(previousSessionId) &&
            !previousPath.startsWith('/chat')

        const isLeavingChatPage =
            previousPath.startsWith('/chat') && !currentPath.startsWith('/chat')

        const isLeavingToHome =
            (isLeavingAgentPage || isLeavingChatPage) && !isSwitchingSessions

        // Always save state when leaving a session
        if (
            (isLeavingAgentPage || isLeavingChatPage || isSwitchingSessions) &&
            previousSessionId
        ) {
            saveCurrentSessionState(previousSessionId)
        }

        // Emit leave_session event for agent pages
        if (isLeavingAgentPage && socket?.connected && previousSessionId) {
            socket.emit('leave_session', {
                session_uuid: previousSessionId
            })
        }

        // Only reset state when going to home, not when switching sessions
        if (isLeavingToHome) {
            // Reset all session-related state
            resetSessionState()

            // Reset UI-specific state
            dispatch(setActiveTab(TAB.BUILD))
            dispatch(setIsMobileChatVisible(true))
            dispatch(setSandboxIframeAwake(false))
            dispatch(setSandboxStatus(''))
            dispatch(setActiveSessionId(null))
            dispatch(setMessages([]))
            resetConversationState()
            setSessionId(null)
        } else if (isSwitchingSessions) {
            // When switching sessions, just clear messages but keep other state
            // The new session's state will be restored by useSessionEnter
            // Clear transient loading state to prevent bleed-through between sessions.
            dispatch(setLoading(false))
            dispatch(setMessages([]))
        } else if (isLeavingChatPage) {
            resetConversationState()
            setSessionId(null)
        }

        previousPathRef.current = currentPath
        previousSessionIdRef.current = sessionId
    }, [
        location.pathname,
        sessionId,
        socket,
        dispatch,
        saveCurrentSessionState,
        resetSessionState,
        resetConversationState,
        setSessionId
    ])
}
