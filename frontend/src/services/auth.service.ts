import axiosInstance from '@/lib/axios'
import { User } from '@/state/slice/user'
import {
    GoogleAuthResponse,
    RefreshTokenResponse,
    GoogleAuthRequest
} from '@/typings/auth'

class AuthService {
    async googleAuth(params: GoogleAuthRequest): Promise<GoogleAuthResponse> {
        const response = await axiosInstance.get<GoogleAuthResponse>(
            '/auth/oauth/google/callback',
            {
                params
            }
        )
        return response.data
    }

    /** Fetch the Google OAuth URL for desktop login (no browser redirect to backend). */
    async getDesktopGoogleLoginUrl(
        desktopState: string
    ): Promise<string> {
        const response = await axiosInstance.get<{ url: string }>(
            '/auth/oauth/google/desktop/login-url',
            { params: { desktop_state: desktopState } }
        )
        return response.data.url
    }

    /** Poll for a desktop auth token stored by the backend after Google login. */
    async pollDesktopToken(
        state: string
    ): Promise<GoogleAuthResponse | null> {
        const response = await axiosInstance.get<
            { status: 'pending' } | GoogleAuthResponse
        >('/auth/oauth/google/poll', { params: { state } })
        if ('status' in response.data && response.data.status === 'pending') {
            return null
        }
        return response.data as GoogleAuthResponse
    }

    async logout(): Promise<void> {
        await axiosInstance.post('/api/auth/logout')
    }

    async getCurrentUser(): Promise<User> {
        const response = await axiosInstance.get<User>('/auth/me')
        return response.data
    }

    async refreshToken(): Promise<RefreshTokenResponse> {
        const response =
            await axiosInstance.post<RefreshTokenResponse>('/auth/refresh')
        return response.data
    }
}

export const authService = new AuthService()
