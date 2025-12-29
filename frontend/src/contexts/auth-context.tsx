import { ACCESS_TOKEN } from '@/constants/auth'
import { authService } from '@/services/auth.service'
import { settingsService } from '@/services/settings.service'
import {
    selectAvailableModels,
    selectSelectedModel,
    setAvailableModels,
    setSelectedModel,
    store,
    userApi,
    sessionApi
} from '@/state'
import { useAppDispatch, useAppSelector } from '@/state/store'
import { setUser, clearUser, setLoading } from '@/state/slice/user'
import type { User } from '@/state/slice/user'
import { fetchWishlist, clearFavorites } from '@/state/slice/favorites'
import { createContext, useContext, useEffect, ReactNode, useCallback } from 'react'

interface AuthContextType {
    user: User | null
    isAuthenticated: boolean
    loginWithAuthCode: (authCode: string) => Promise<void>
    loginWithDevAuth: () => Promise<void>
    logout: () => void
    isLoading: boolean
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

// Check if dev auth auto-login is enabled
const DEV_AUTH_AUTOLOGIN = import.meta.env.VITE_DEV_AUTH_AUTOLOGIN === 'true'

export function AuthProvider({ children }: { children: ReactNode }) {
    const dispatch = useAppDispatch()
    const { user, isLoading } = useAppSelector((state) => state.user)

    // Derive isAuthenticated from the presence of a valid access token
    const isAuthenticated = !!localStorage.getItem(ACCESS_TOKEN)

    const fetchAvailableModels = useCallback(async () => {
        try {
            const data = await settingsService.getAvailableModels()
            dispatch(setAvailableModels(data?.models || []))

            if (data?.models?.length) {
                const firstModel = data.models[0]

                const state = store.getState()
                const currentSelectedModel = selectSelectedModel(state)
                const currentAvailableModels = selectAvailableModels(state)

                const selectedModelStillAvailable = currentAvailableModels.find(
                    (model) => model.id === currentSelectedModel
                )

                if (!currentSelectedModel || !selectedModelStillAvailable) {
                    dispatch(setSelectedModel(firstModel.id))
                }
            }
        } catch (error) {
            console.log('Failed to fetch llm models', error)
        }
    }, [dispatch])

    useEffect(() => {
        const initializeAuth = async () => {
            try {
                const accessToken = localStorage.getItem(ACCESS_TOKEN)

                if (accessToken) {
                    try {
                        const userRes = await authService.getCurrentUser()
                        dispatch(setUser(userRes))
                        await fetchAvailableModels()
                        // Fetch user's wishlist after successful authentication
                        dispatch(fetchWishlist())
                    } catch (apiError) {
                        console.error(
                            'Failed to get current user from API:',
                            apiError
                        )
                        const storedUser = localStorage.getItem('user')
                        if (storedUser) {
                            const userData = JSON.parse(storedUser)
                            dispatch(setUser(userData))
                            // Try to fetch wishlist even with cached user data
                            dispatch(fetchWishlist())
                        } else {
                            dispatch(setLoading(false))
                        }
                    }
                } else if (DEV_AUTH_AUTOLOGIN) {
                    // Auto-login using dev auth endpoint when enabled and no token exists
                    try {
                        console.log('Dev auth auto-login enabled, attempting dev login...')
                        const res = await authService.devLogin()
                        localStorage.setItem(ACCESS_TOKEN, res.access_token)
                        window.dispatchEvent(new CustomEvent('auth-token-set'))

                        const userRes = await authService.getCurrentUser()
                        dispatch(setUser(userRes))
                        await fetchAvailableModels()
                        dispatch(fetchWishlist())
                        console.log('Dev auth auto-login successful')
                    } catch (devAuthError) {
                        console.error('Dev auth auto-login failed:', devAuthError)
                        dispatch(setLoading(false))
                    }
                } else {
                    dispatch(setLoading(false))
                }
            } catch (error) {
                console.error('Error initializing auth:', error)
                dispatch(setLoading(false))
            }
        }

        initializeAuth()
    }, [dispatch, fetchAvailableModels])

    const loginWithAuthCode = async (code: string) => {
        try {
            const res = await authService.googleAuth({
                code,
                redirect_uri: window.location.origin
            })

            // Store the access token immediately to trigger WebSocket connection
            localStorage.setItem(ACCESS_TOKEN, res.access_token)
            // Dispatch a custom event to notify WebSocket to connect immediately
            window.dispatchEvent(new CustomEvent('auth-token-set'))

            // Get user information using the access token (in parallel with WebSocket connection)
            const userRes = await authService.getCurrentUser()
            dispatch(setUser(userRes))
            await fetchAvailableModels()
            // Fetch user's wishlist after successful login
            dispatch(fetchWishlist())
        } catch (error) {
            console.error('Error handling auth code:', error)
            throw error
        }
    }

    const loginWithDevAuth = async () => {
        try {
            const res = await authService.devLogin()
            localStorage.setItem(ACCESS_TOKEN, res.access_token)
            window.dispatchEvent(new CustomEvent('auth-token-set'))

            const userRes = await authService.getCurrentUser()
            dispatch(setUser(userRes))
            await fetchAvailableModels()
            dispatch(fetchWishlist())
        } catch (error) {
            console.error('Error handling dev login:', error)
            throw error
        }
    }

    const logout = () => {
        localStorage.removeItem(ACCESS_TOKEN)
        dispatch(clearUser())
        dispatch(clearFavorites())
        // Reset all RTK Query cache to prevent data leakage between users
        dispatch(userApi.util.resetApiState())
        dispatch(sessionApi.util.resetApiState())
    }

    const value: AuthContextType = {
        user,
        isAuthenticated,
        loginWithAuthCode,
        loginWithDevAuth,
        logout,
        isLoading
    }

    return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
    const context = useContext(AuthContext)
    if (context === undefined) {
        throw new Error('useAuth must be used within an AuthProvider')
    }
    return context
}
