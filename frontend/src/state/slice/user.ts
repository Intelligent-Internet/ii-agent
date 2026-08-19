import { createSlice, PayloadAction, createAsyncThunk } from '@reduxjs/toolkit'
import type { CreditUsageResponse } from '@/typings/user'
import { userService } from '@/services/user.service'
import { SubscriptionPlan, type BillingCycle } from '@/typings/subscription'

export interface UserPreferences {
    has_memory: boolean
}

export interface User {
    id: string
    first_name: string
    last_name: string
    email: string
    avatar?: string
    role?: string
    subscription_status?: string
    subscription_plan?: SubscriptionPlan
    subscription_billing_cycle?: BillingCycle
    subscription_current_period_end?: string
    language?: string
    preferences?: UserPreferences
}

interface UserState {
    user: User | null
    isLoading: boolean
    creditBalance: number
    bonusCreditBalance: number
    creditUsage: CreditUsageResponse | null
    creditsLoading: boolean
    creditsError: string | null
}

const initialState: UserState = {
    user: null,
    isLoading: true,
    creditBalance: 0,
    bonusCreditBalance: 0,
    creditUsage: null,
    creditsLoading: false,
    creditsError: null
}

export const getCreditBalance = createAsyncThunk(
    'user/getCreditBalance',
    async () => {
        return await userService.getCreditBalance()
    }
)

export const getCreditUsage = createAsyncThunk(
    'user/getCreditUsage',
    async ({ page, perPage }: { page: number; perPage: number }) => {
        return await userService.getCreditUsage({ page, perPage })
    }
)

const userSlice = createSlice({
    name: 'user',
    initialState,
    reducers: {
        setUser: (state, action: PayloadAction<User>) => {
            state.user = action.payload
            state.isLoading = false
        },
        clearUser: (state) => {
            state.user = null
            state.isLoading = false
        },
        setLoading: (state, action: PayloadAction<boolean>) => {
            state.isLoading = action.payload
        }
    },
    extraReducers: (builder) => {
        builder
            // getCreditBalance
            .addCase(getCreditBalance.pending, (state) => {
                state.creditsLoading = true
                state.creditsError = null
            })
            .addCase(getCreditBalance.fulfilled, (state, action) => {
                state.creditsLoading = false
                state.creditBalance = action.payload.credits || 0
                state.bonusCreditBalance = action.payload.bonus_credits || 0
            })
            .addCase(getCreditBalance.rejected, (state, action) => {
                state.creditsLoading = false
                state.creditsError =
                    action.error.message || 'Failed to load balance'
            })
            // getCreditUsage
            .addCase(getCreditUsage.pending, (state) => {
                state.creditsLoading = true
                state.creditsError = null
            })
            .addCase(getCreditUsage.fulfilled, (state, action) => {
                state.creditsLoading = false
                state.creditUsage = action.payload
            })
            .addCase(getCreditUsage.rejected, (state, action) => {
                state.creditsLoading = false
                state.creditsError =
                    action.error.message || 'Failed to load usage'
            })
    }
})

export const { setUser, clearUser, setLoading } = userSlice.actions
export const userReducer = userSlice.reducer

// Selectors
export const selectUser = (state: { user: UserState }) => state.user.user
export const selectCreditBalance = (state: { user: UserState }) =>
    state.user.creditBalance
export const selectBonusCreditBalance = (state: { user: UserState }) =>
    state.user.bonusCreditBalance
export const selectCreditUsage = (state: { user: UserState }) =>
    state.user.creditUsage
export const selectCreditsLoading = (state: { user: UserState }) =>
    state.user.creditsLoading
export const selectCreditsError = (state: { user: UserState }) =>
    state.user.creditsError
export const selectSubscriptionStatus = (state: { user: UserState }) =>
    state.user.user?.subscription_status
export const selectSubscriptionPlan = (state: { user: UserState }) =>
    state.user.user?.subscription_plan
export const selectSubscriptionCurrentPeriodEnd = (state: {
    user: UserState
}) => state.user.user?.subscription_current_period_end
export const selectSubscriptionBillingCycle = (state: { user: UserState }) =>
    state.user.user?.subscription_billing_cycle
export const selectUserLanguage = (state: { user: UserState }) =>
    state.user.user?.language || 'en'
export const selectUserPreferences = (state: { user: UserState }): UserPreferences =>
    state.user.user?.preferences ?? { has_memory: true }