import { useEffect, useRef } from 'react'
import { invoke } from '@tauri-apps/api/core'
import {
    AUTH_TOKEN_CLEARED_EVENT,
    AUTH_TOKEN_SET_EVENT,
    getStoredAccessToken
} from '@/utils/auth-token'

const isTauri =
    typeof window !== 'undefined' &&
    !!(window as unknown as { __TAURI_INTERNALS__?: unknown })
        .__TAURI_INTERNALS__

type SyncPayload = {
    accessToken: string | null
    apiBaseUrl: string
}

export function useCoworkAuthSync() {
    const lastPayloadRef = useRef<SyncPayload | null>(null)

    useEffect(() => {
        if (!isTauri) return undefined

        const apiBaseUrl =
            import.meta.env.VITE_API_URL || 'http://localhost:8000'

        const syncAuthContext = async () => {
            const payload: SyncPayload = {
                accessToken: getStoredAccessToken(),
                apiBaseUrl
            }

            if (
                lastPayloadRef.current?.accessToken === payload.accessToken &&
                lastPayloadRef.current?.apiBaseUrl === payload.apiBaseUrl
            ) {
                return
            }

            await invoke('sync_cowork_auth_context', payload)
            lastPayloadRef.current = payload
        }

        const syncSilently = () => {
            void syncAuthContext().catch((error) => {
                console.error('Failed to sync cowork auth context:', error)
            })
        }

        syncSilently()

        const handleStorageChange = (event: StorageEvent) => {
            if (event.key) {
                syncSilently()
            }
        }

        window.addEventListener('storage', handleStorageChange)
        window.addEventListener(AUTH_TOKEN_SET_EVENT, syncSilently)
        window.addEventListener(AUTH_TOKEN_CLEARED_EVENT, syncSilently)

        return () => {
            window.removeEventListener('storage', handleStorageChange)
            window.removeEventListener(AUTH_TOKEN_SET_EVENT, syncSilently)
            window.removeEventListener(AUTH_TOKEN_CLEARED_EVENT, syncSilently)
        }
    }, [])
}
