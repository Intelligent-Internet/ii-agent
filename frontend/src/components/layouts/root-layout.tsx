import { Outlet } from 'react-router'
import { WebSocketProvider } from '@/contexts/websocket-context'
import {
    AppEventsProvider,
    useAppEventsContext
} from '@/contexts/app-events-context'
import { useNavigationLeaveSession } from '@/hooks/use-navigation-leave-session'
import { useWebSocketAuthSync } from '@/hooks/use-websocket-auth-sync'
import { ChatProvider } from '@/hooks/use-chat-query'
import { useCoworkAuthSync } from '@/hooks/use-cowork-auth-sync'

function RootLayoutContent() {
    useNavigationLeaveSession()
    // Establish WebSocket connection immediately when auth token is available
    useWebSocketAuthSync()
    useCoworkAuthSync()
    
    return <Outlet />
}

function WebSocketBridge({ children }: { children: React.ReactNode }) {
    const { handleEvent } = useAppEventsContext()

    return (
        <WebSocketProvider handleEvent={handleEvent}>
            {children}
        </WebSocketProvider>
    )
}

export function RootLayout() {
    return (
        <AppEventsProvider>
            <WebSocketBridge>
                <ChatProvider>
                    <RootLayoutContent />
                </ChatProvider>
            </WebSocketBridge>
        </AppEventsProvider>
    )
}
