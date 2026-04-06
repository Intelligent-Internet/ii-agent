import axiosInstance from '@/lib/axios'
import { CreditBalanceResponse, CreditUsageResponse } from '@/typings/user'

class UserService {
    async getCreditBalance(): Promise<CreditBalanceResponse> {
        const response =
            await axiosInstance.get<CreditBalanceResponse>('/v1/credits/balance')
        return response.data
    }
    async getCreditUsage({
        page,
        perPage
    }: {
        page: number
        perPage: number
    }): Promise<CreditUsageResponse> {
        const response = await axiosInstance.get<CreditUsageResponse>(
            '/v1/credits/usage',
            {
                params: { page, per_page: perPage }
            }
        )
        return response.data
    }
    async deleteAccount(): Promise<{ message: string }> {
        const response = await axiosInstance.delete<{ message: string }>(
            '/auth/me'
        )
        return response.data
    }
    async updateLanguage(
        language: string
    ): Promise<{ message: string; language: string }> {
        const response = await axiosInstance.patch<{
            message: string
            language: string
        }>('/auth/me/language', null, {
            params: { language }
        })
        return response.data
    }
    async updatePreferences(body: {
        has_memory?: boolean
    }): Promise<{ message: string; preferences: { has_memory: boolean } }> {
        const response = await axiosInstance.patch<{
            message: string
            preferences: { has_memory: boolean }
        }>('/auth/me/preferences', body)
        return response.data
    }
}

export const userService = new UserService()
