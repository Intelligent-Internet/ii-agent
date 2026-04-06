import { createApi, fetchBaseQuery } from '@reduxjs/toolkit/query/react'
import type {
    BaseQueryFn,
    FetchArgs,
    FetchBaseQueryError
} from '@reduxjs/toolkit/query'
import type {
    CreditBalanceResponse,
    CreditUsageResponse,
    LedgerHistoryResponse,
    ReservationHistoryResponse,
    SessionUsageDetailResponse
} from '@/typings/user'
import { getStoredAccessToken, clearAccessToken } from '@/utils/auth-token'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

const baseQuery = fetchBaseQuery({
    baseUrl: `${API_URL}/v1`,
    prepareHeaders: (headers) => {
        const token = getStoredAccessToken()
        if (token) {
            headers.set('Authorization', `Bearer ${token}`)
        }
        headers.set('Content-Type', 'application/json')
        return headers
    }
})

const baseQueryWithReauth: BaseQueryFn<
    string | FetchArgs,
    unknown,
    FetchBaseQueryError
> = async (args, api, extraOptions) => {
    const result = await baseQuery(args, api, extraOptions)
    if (result.error && result.error.status === 401) {
        clearAccessToken()
        // Don't redirect to login if we're on a share route
        if (!window.location.pathname.startsWith('/share/')) {
            window.location.href = '/login'
        }
    }
    return result
}

export const userApi = createApi({
    reducerPath: 'userApi',
    baseQuery: baseQueryWithReauth,
    tagTypes: ['CreditBalance', 'CreditUsage', 'SessionUsageDetail', 'SessionLedger', 'SessionReservations'],
    endpoints: (builder) => ({
        getCreditBalance: builder.query<CreditBalanceResponse, void>({
            query: () => '/credits/balance',
            providesTags: ['CreditBalance']
        }),
        getCreditUsage: builder.query<
            CreditUsageResponse,
            { page: number; perPage: number }
        >({
            query: ({ page, perPage }) => ({
                url: '/credits/usage',
                params: { page, per_page: perPage }
            }),
            providesTags: ['CreditUsage']
        }),
        getSessionUsageDetail: builder.query<
            SessionUsageDetailResponse,
            { sessionId: string; page?: number; perPage?: number }
        >({
            query: ({ sessionId, page = 1, perPage = 50 }) => ({
                url: `/credits/usage/${sessionId}`,
                params: { page, per_page: perPage }
            }),
            providesTags: ['SessionUsageDetail']
        }),
        getSessionLedger: builder.query<
            LedgerHistoryResponse,
            { sessionId: string; page?: number; perPage?: number }
        >({
            query: ({ sessionId, page = 1, perPage = 50 }) => ({
                url: `/credits/ledger/${sessionId}`,
                params: { page, per_page: perPage }
            }),
            providesTags: ['SessionLedger']
        }),
        getSessionReservations: builder.query<
            ReservationHistoryResponse,
            { sessionId: string; page?: number; perPage?: number }
        >({
            query: ({ sessionId, page = 1, perPage = 50 }) => ({
                url: `/credits/reservations/${sessionId}`,
                params: { page, per_page: perPage }
            }),
            providesTags: ['SessionReservations']
        })
    })
})

export const {
    useGetCreditBalanceQuery,
    useGetCreditUsageQuery,
    useGetSessionUsageDetailQuery,
    useGetSessionLedgerQuery,
    useGetSessionReservationsQuery
} = userApi
