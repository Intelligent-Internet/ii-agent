import { createApi, fetchBaseQuery } from '@reduxjs/toolkit/query/react'
import type {
    BaseQueryFn,
    FetchArgs,
    FetchBaseQueryError
} from '@reduxjs/toolkit/query'
import type { ISession } from '@/typings/agent'
import type {
    UpdateSessionRequest,
    ForkSessionRequest,
    ForkSessionResponse
} from '@/typings/session'
import { getStoredAccessToken, clearAccessToken } from '@/utils/auth-token'
import { normalizeSession, normalizeSessions } from '@/services/session-normalizer'

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

export const sessionApi = createApi({
    reducerPath: 'sessionApi',
    baseQuery: baseQueryWithReauth,
    tagTypes: ['Sessions'],
    endpoints: (builder) => ({
        getSessions: builder.query<
            ISession[],
            {
                page?: number
                limit?: number
                public_only?: boolean
                session_type?: 'agent' | 'chat'
            }
        >({
            query: ({
                page = 1,
                limit = 20,
                public_only = false,
                session_type
            }) => ({
                url: '/sessions',
                params: { page, per_page: limit, public_only, session_type }
            }),
            transformResponse: (response: { sessions: ISession[] }) =>
                normalizeSessions(response.sessions || []),
            providesTags: (result) =>
                result
                    ? [
                          ...result.map(({ id }) => ({
                              type: 'Sessions' as const,
                              id
                          })),
                          { type: 'Sessions', id: 'LIST' }
                      ]
                    : [{ type: 'Sessions', id: 'LIST' }]
        }),
        deleteSession: builder.mutation<void, string>({
            query: (sessionId) => ({
                url: `/sessions/${sessionId}`,
                method: 'DELETE'
            }),
            invalidatesTags: (_result, _error, sessionId) => [
                { type: 'Sessions', id: sessionId },
                { type: 'Sessions', id: 'LIST' }
            ]
        }),
        bulkDeleteSessions: builder.mutation<
            { deleted_ids: string[]; failed_ids: string[] },
            string[]
        >({
            query: (sessionIds) => ({
                url: '/sessions/bulk-delete',
                method: 'POST',
                body: { session_ids: sessionIds }
            }),
            invalidatesTags: [{ type: 'Sessions', id: 'LIST' }]
        }),
        updateSession: builder.mutation<
            ISession,
            { sessionId: string; data: UpdateSessionRequest }
        >({
            query: ({ sessionId, data }) => ({
                url: `/sessions/${sessionId}`,
                method: 'PATCH',
                body: data
            }),
            transformResponse: (response: ISession) => normalizeSession(response),
            invalidatesTags: (_result, _error, { sessionId }) => [
                { type: 'Sessions', id: sessionId },
                { type: 'Sessions', id: 'LIST' }
            ],
        }),
        forkSession: builder.mutation<
            ForkSessionResponse,
            { sessionId: string; data: ForkSessionRequest }
        >({
            query: ({ sessionId, data }) => ({
                url: `/sessions/${sessionId}/fork`,
                method: 'POST',
                body: data
            }),
            invalidatesTags: [{ type: 'Sessions', id: 'LIST' }]
        })
    })
})

export const {
    useGetSessionsQuery,
    useDeleteSessionMutation,
    useUpdateSessionMutation,
    useForkSessionMutation
} = sessionApi
