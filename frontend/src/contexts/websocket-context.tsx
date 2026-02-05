import {
    createContext,
    useContext,
    useEffect,
    ReactNode,
    useCallback,
    useRef,
    useState
} from 'react'
import { useParams } from 'react-router'
import { toast } from 'sonner'
import { io, Socket, ManagerOptions, SocketOptions } from 'socket.io-client'
import { AgentEvent, WebSocketConnectionState } from '@/typings/agent'
import { useAppDispatch, useAppSelector } from '@/state/store'
import {
    selectIsFromNewQuestion,
    selectActiveSessionId,
    setAgentInitialized,
    setWsConnectionState
} from '@/state'
import { ACCESS_TOKEN } from '@/constants/auth'

interface WebSocketMessageContent {
    [key: string]: unknown
}

interface SocketIOContextType {
    socket: Socket | null
    connectSocket: () => void
    sendMessage: (payload: {
        type: string
        content: WebSocketMessageContent
    }) => boolean
    joinSession: () => void
}

const SocketIOContext = createContext<SocketIOContextType | null>(null)

interface SocketIOProviderProps {
    children: ReactNode
    handleEvent: (data: {
        id: string
        type: AgentEvent
        content: Record<string, unknown>
    }) => void
}

export function SocketIOProvider({
    children,
    handleEvent
}: SocketIOProviderProps) {
    const { sessionId } = useParams()
    const isFromNewQuestion = useAppSelector(selectIsFromNewQuestion)
    const activeSessionId = useAppSelector(selectActiveSessionId)
    const [socket, setSocket] = useState<Socket | null>(null)
    const connectionRef = useRef<Socket | null>(null)
    const handleEventRef = useRef(handleEvent)
    const sessionIdRef = useRef(sessionId)
    const isFromNewQuestionRef = useRef(isFromNewQuestion)
    const dispatch = useAppDispatch()
    const sessionInitializedRef = useRef(false)

    // Update the refs when values change
    handleEventRef.current = handleEvent
    isFromNewQuestionRef.current = isFromNewQuestion

    // Keep sessionIdRef in sync with sessionId (from URL params) or activeSessionId (from Redux)
    // Priority: sessionId (from URL) > activeSessionId (for newly created sessions before URL updates)
    // This ensures that when navigating directly to a session URL, it takes precedence over stale Redux state
    const currentSessionId = sessionId || activeSessionId

    // Reset session initialization flag when sessionId changes or on initial load
    if (sessionIdRef.current !== currentSessionId) {
        sessionInitializedRef.current = false
        sessionIdRef.current = currentSessionId
        // Reset agent initialization whenever we have a sessionId (including initial load)
        if (currentSessionId) {
            console.log(
                'WebSocket: Resetting isAgentInitialized for session change:',
                currentSessionId
            )
            dispatch(setAgentInitialized(false))
        }
    }

    // Also reset on initial mount if sessionId is present
    useEffect(() => {
        if (sessionId && sessionIdRef.current === sessionId) {
            dispatch(setAgentInitialized(false))
        }
    }, [sessionId, dispatch]) // Run on mount and when sessionId changes

    const connectSocket = useCallback(() => {
        // Prevent duplicate connections - check if already connected
        if (connectionRef.current?.connected) {
            console.log(
                'Socket.IO already connected, socket ID:',
                connectionRef.current.id
            )
            return
        }

        // Clean up any existing connection first - be more thorough
        if (connectionRef.current) {
            console.log(
                'Cleaning up existing connection:',
                connectionRef.current.id
            )
            connectionRef.current.removeAllListeners()
            connectionRef.current.disconnect()
            connectionRef.current = null
            setSocket(null)
        }

        // Reset session initialization flag when reconnecting
        sessionInitializedRef.current = false

        dispatch(setWsConnectionState(WebSocketConnectionState.CONNECTING))
        const token = localStorage.getItem(ACCESS_TOKEN)
        if (!token) {
            console.log('WebSocket: No token available, skipping connection')
            dispatch(
                setWsConnectionState(WebSocketConnectionState.DISCONNECTED)
            )
            return
        }

        console.log(
            'WebSocket: Token found, establishing connection immediately'
        )
        // Reset agent initialization state when connecting
        dispatch(setAgentInitialized(false))

        const socketOptions: Partial<ManagerOptions & SocketOptions> = {
            auth: { token },
            transports: ['websocket', 'polling'],
            timeout: 15000, // Initial connection timeout: 15 seconds
            reconnection: false // Disable automatic reconnection
        }

        if (sessionIdRef.current && !isFromNewQuestionRef.current) {
            ;(socketOptions.auth as Record<string, unknown>).session_uuid =
                sessionIdRef.current
        }

        const socketInstance = io(import.meta.env.VITE_API_URL, socketOptions)

        socketInstance.on('connect', () => {
            console.log('Socket.IO connection established')
            dispatch(setWsConnectionState(WebSocketConnectionState.CONNECTED))

            // Only auto-initialize session for new questions, not when accessing existing sessions
            if (
                sessionIdRef.current &&
                !sessionInitializedRef.current &&
                isFromNewQuestionRef.current
            ) {
                console.log(
                    'Auto-initializing session for new question:',
                    sessionIdRef.current
                )
                setTimeout(() => {
                    console.log(
                        'Emitting join_session for:',
                        sessionIdRef.current
                    )
                    socketInstance.emit('join_session', {
                        session_uuid: sessionIdRef.current
                    })
                    sessionInitializedRef.current = true
                }, 100) // Small delay to ensure connection is fully established
            }
        })

        socketInstance.on('chat_event', (data) => {
            try {
                handleEventRef.current({ ...data, id: Date.now().toString() })
            } catch (error) {
                console.error('Error handling Socket.IO event:', error)
            }
        })

        socketInstance.on('connect_error', (error) => {
            console.log('Socket.IO connection error:', error)
            dispatch(
                setWsConnectionState(WebSocketConnectionState.DISCONNECTED)
            )
            // Clean up references on connection error
            setSocket(null)
            connectionRef.current = null
        })

        socketInstance.on('disconnect', (reason) => {
            console.log(
                'Socket.IO connection closed:',
                reason,
                'Socket ID:',
                socketInstance.id
            )
            dispatch(
                setWsConnectionState(WebSocketConnectionState.DISCONNECTED)
            )

            // Clean up session initialization flag on disconnect
            sessionInitializedRef.current = false

            // Always clean up on disconnect (no reconnection)
            console.log('Cleaning up socket due to disconnect reason:', reason)
            setSocket(null)
            connectionRef.current = null
        })

        setSocket(socketInstance)
        connectionRef.current = socketInstance
    }, [dispatch]) // Only dispatch as dependency - other values are accessed via refs

    const joinSession = useCallback(() => {
        if (!socket || !socket.connected) {
            console.error('Cannot initialize session: Socket not connected')
            return
        }

        // Always emit initialize_session to ensure server-side session is ready
        // The server should handle duplicate initializations gracefully
        console.log('Joining session...')
        socket.emit('join_session', {
            session_uuid: sessionIdRef.current
        })
        sessionInitializedRef.current = true
    }, [socket])

    const sendMessage = useCallback(
        (payload: { type: string; content: WebSocketMessageContent }) => {
            if (!socket || !socket.connected) {
                toast.error(
                    'Socket.IO connection is not open. Please try again.'
                )
                return false
            }

            // Include session_uuid in the payload if available (for reconnection handling)
            const messageWithSession = sessionIdRef.current
                ? { ...payload, session_uuid: sessionIdRef.current }
                : payload

            socket.emit('chat_message', messageWithSession)
            return true
        },
        [socket]
    )

    // Only connect once on mount
    useEffect(() => {
        connectSocket()

        // Cleanup on unmount
        return () => {
            if (connectionRef.current) {
                connectionRef.current.disconnect()
                connectionRef.current = null
                setSocket(null)
            }
        }
    }, [connectSocket]) // connectSocket is stable now since it only depends on dispatch

    // Initialize session when sessionId changes and socket is connected (only for new questions)
    useEffect(() => {
        if (socket?.connected && sessionId && !sessionInitializedRef.current) {
            console.log(
                'Initializing session due to sessionId change for new question:',
                sessionId
            )
            joinSession()
        }
    }, [sessionId, socket?.connected, joinSession])

    return (
        <SocketIOContext.Provider
            value={{ socket, connectSocket, sendMessage, joinSession }}
        >
            {children}
        </SocketIOContext.Provider>
    )
}

export function useSocketIOContext() {
    const context = useContext(SocketIOContext)
    if (!context) {
        throw new Error(
            'useSocketIOContext must be used within a SocketIOProvider'
        )
    }
    return context
}

// Backward compatibility alias
export const useWebSocketContext = useSocketIOContext
export const WebSocketProvider = SocketIOProvider
