import { useEffect } from 'react'
import { useWebSocketContext } from '@/contexts/websocket-context'
import { ACCESS_TOKEN } from '@/constants/auth'
import {
    AUTH_TOKEN_CLEARED_EVENT,
    AUTH_TOKEN_SET_EVENT,
    getStoredAccessToken
} from '@/utils/auth-token'

/**
 * Hook that monitors auth token changes and reconnects the WebSocket
 * when a new token becomes available (e.g. login from another tab, token refresh).
 *
 * The initial connection is owned by SocketIOProvider on mount.
 * Auto-reconnection on disconnect is handled by Socket.IO's built-in reconnection.
 * This hook only covers the case where the token itself changes.
 */
export function useWebSocketAuthSync() {
    const { connectSocket, socket } = useWebSocketContext()

    useEffect(() => {
        // Detect token changes from other browser tabs
        const handleStorageChange = (e: StorageEvent) => {
            if (e.key === ACCESS_TOKEN && e.newValue && !socket?.connected) {
                console.log(
                    'WebSocket: Token changed via storage event, reconnecting...'
                )
                connectSocket()
                return
            }

            if (e.key === ACCESS_TOKEN && !e.newValue && socket?.connected) {
                console.log(
                    'WebSocket: Token cleared via storage event, disconnecting...'
                )
                socket.disconnect()
            }
        }

        // Detect token set in the same tab (e.g. after login or token refresh)
        const handleAuthTokenSet = () => {
            const token = getStoredAccessToken()
            if (token && !socket?.connected) {
                console.log('WebSocket: Auth token set event, reconnecting...')
                connectSocket()
            }
        }

        const handleAuthTokenCleared = () => {
            if (socket?.connected) {
                console.log('WebSocket: Auth token cleared, disconnecting...')
                socket.disconnect()
            }
        }

        window.addEventListener('storage', handleStorageChange)
        window.addEventListener(AUTH_TOKEN_SET_EVENT, handleAuthTokenSet)
        window.addEventListener(
            AUTH_TOKEN_CLEARED_EVENT,
            handleAuthTokenCleared
        )
        return () => {
            window.removeEventListener('storage', handleStorageChange)
            window.removeEventListener(AUTH_TOKEN_SET_EVENT, handleAuthTokenSet)
            window.removeEventListener(
                AUTH_TOKEN_CLEARED_EVENT,
                handleAuthTokenCleared
            )
        }
    }, [connectSocket, socket?.connected])
}
