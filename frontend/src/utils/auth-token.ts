import { ACCESS_TOKEN } from '@/constants/auth'

export const AUTH_TOKEN_SET_EVENT = 'auth-token-set'
export const AUTH_TOKEN_CLEARED_EVENT = 'auth-token-cleared'

function dispatchAuthEvent(eventName: string) {
    if (typeof window === 'undefined') return
    window.dispatchEvent(new CustomEvent(eventName))
}

export function getStoredAccessToken(): string | null {
    if (typeof window === 'undefined') return null
    return localStorage.getItem(ACCESS_TOKEN)
}

export function storeAccessToken(token: string): void {
    localStorage.setItem(ACCESS_TOKEN, token)
    dispatchAuthEvent(AUTH_TOKEN_SET_EVENT)
}

export function clearAccessToken(): void {
    localStorage.removeItem(ACCESS_TOKEN)
    dispatchAuthEvent(AUTH_TOKEN_CLEARED_EVENT)
}
