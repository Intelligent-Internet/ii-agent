import { useEffect, useRef } from 'react'
import { useLocation, useParams } from 'react-router'
import { useSocketIOContext } from '@/contexts/websocket-context'
import {
    setActiveSessionId,
    setActiveTab,
    setIsMobileChatVisible,
    setResultUrl,
    setSandboxIframeAwake,
    setSandboxStatus,
    setSelectedFeature,
    useAppDispatch
} from '@/state'
import { AGENT_TYPE, TAB } from '@/typings'

export function useNavigationLeaveSession() {
    const dispatch = useAppDispatch()
    const location = useLocation()
    const { sessionId } = useParams()
    const { socket } = useSocketIOContext()
    const previousSessionIdRef = useRef<string | undefined>(sessionId)
    const previousPathRef = useRef<string>(location.pathname)

    useEffect(() => {
        const currentPath = location.pathname
        const previousPath = previousPathRef.current
        const previousSessionId = previousSessionIdRef.current

        const isLeavingAgentPage =
            previousSessionId &&
            !currentPath.includes(previousSessionId) &&
            previousPath.includes(previousSessionId)

        const isLeavingChatPage =
            previousPath.startsWith('/chat') && !currentPath.startsWith('/chat')

        if (isLeavingAgentPage) {
            if (socket?.connected) {
                socket.emit('leave_session', {
                    session_uuid: previousSessionId
                })
            }
            dispatch(setResultUrl(''))
            dispatch(setActiveTab(TAB.BUILD))
            dispatch(setIsMobileChatVisible(true))
            dispatch(setSandboxIframeAwake(false))
            dispatch(setSandboxStatus(''))
            dispatch(setActiveSessionId(null))
            dispatch(setSelectedFeature(AGENT_TYPE.GENERAL))
        } else if (isLeavingChatPage) {
            dispatch(setActiveSessionId(null))
        }

        previousPathRef.current = currentPath
        previousSessionIdRef.current = sessionId
    }, [location.pathname, sessionId, socket])
}
