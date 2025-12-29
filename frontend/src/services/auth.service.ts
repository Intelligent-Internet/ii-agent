import axiosInstance from '@/lib/axios'
import { User } from '@/state/slice/user'
import {
    GoogleAuthResponse,
    RefreshTokenResponse,
    GoogleAuthRequest,
    DevLoginResponse
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

    async devLogin(): Promise<DevLoginResponse> {
        const response = await axiosInstance.get<DevLoginResponse>(
            '/auth/dev/login'
        )
        return response.data
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
