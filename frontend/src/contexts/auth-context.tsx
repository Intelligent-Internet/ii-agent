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
import { fetchPins, clearPins } from '@/state/slice/pins'
import { createContext, useContext, useEffect, ReactNode, useCallback } from 'react'
import {
    clearAccessToken,
    getStoredAccessToken,
    storeAccessToken
} from '@/utils/auth-token'

interface AuthContextType {
    user: User | null
    isAuthenticated: boolean
    loginWithAuthCode: (authCode: string) => Promise<void>
    logout: () => void
    isLoading: boolean
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

export function AuthProvider({ children }: { children: ReactNode }) {
    const dispatch = useAppDispatch()
    const { user, isLoading } = useAppSelector((state) => state.user)

    // Derive isAuthenticated from the presence of a valid access token
    const isAuthenticated = !!getStoredAccessToken()

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
                const accessToken = getStoredAccessToken()

                if (accessToken) {
                    try {
                        const userRes = await authService.getCurrentUser()
                        dispatch(setUser(userRes))
                        await fetchAvailableModels()
                        // Fetch user's wishlist and pins after successful authentication
                        dispatch(fetchWishlist())
                        dispatch(fetchPins())
                    } catch (apiError) {
                        console.error(
                            'Failed to get current user from API:',
                            apiError
                        )
                        const storedUser = localStorage.getItem('user')
                        if (storedUser) {
                            const userData = JSON.parse(storedUser)
                            dispatch(setUser(userData))
                            // Try to fetch wishlist and pins even with cached user data
                            dispatch(fetchWishlist())
                            dispatch(fetchPins())
                        } else {
                            dispatch(setLoading(false))
                        }
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
            storeAccessToken(res.access_token)

            // Get user information using the access token (in parallel with WebSocket connection)
            const userRes = await authService.getCurrentUser()
            dispatch(setUser(userRes))
            await fetchAvailableModels()
            // Fetch user's wishlist and pins after successful login
            dispatch(fetchWishlist())
            dispatch(fetchPins())
        } catch (error) {
            console.error('Error handling auth code:', error)
            throw error
        }
    }

    const logout = () => {
        clearAccessToken()
        dispatch(clearUser())
        dispatch(clearFavorites())
        dispatch(clearPins())
        // Reset all RTK Query cache to prevent data leakage between users
        dispatch(userApi.util.resetApiState())
        dispatch(sessionApi.util.resetApiState())
    }

    const value: AuthContextType = {
        user,
        isAuthenticated,
        loginWithAuthCode,
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
