import { createSlice, createAsyncThunk, PayloadAction } from '@reduxjs/toolkit'
import { ISession } from '@/typings/agent'
import store from '../store'
import { sessionApi } from '../api/session.api'

interface PaginatedSessionState {
    sessions: ISession[]
    isLoading: boolean
    page: number
    hasMore: boolean
}

interface SessionsState {
    sessions: ISession[]
    chats: PaginatedSessionState
    projects: PaginatedSessionState
    activeSessionId: string | null
    isLoading: boolean
    error: string | null
    page: number
    hasMore: boolean
    limit: number
}

const initialPaginatedState: PaginatedSessionState = {
    sessions: [],
    isLoading: false,
    page: 1,
    hasMore: true
}

const initialState: SessionsState = {
    sessions: [],
    chats: { ...initialPaginatedState },
    projects: { ...initialPaginatedState },
    activeSessionId: null,
    isLoading: false,
    error: null,
    page: 1,
    hasMore: true,
    limit: 20
}

const isChatSession = (session: ISession) =>
    session.agent_type === 'chat' || session.agent_type == null

const upsertSessionInList = (sessions: ISession[], session: ISession) => {
    const existingIndex = sessions.findIndex((item) => item.id === session.id)
    if (existingIndex === -1) {
        sessions.unshift(session)
        return
    }

    sessions[existingIndex] = {
        ...sessions[existingIndex],
        ...session
    }
}

export const fetchSessions = createAsyncThunk(
    'sessions/fetchSessions',
    async ({
        page = 1,
        limit = 20
    }: { page?: number; limit?: number } = {}) => {
        const result = await store.dispatch(
            sessionApi.endpoints.getSessions.initiate(
                { page, limit },
                { forceRefetch: true, subscribe: false }
            )
        )
        return result.data || []
    }
)

export const fetchChats = createAsyncThunk(
    'sessions/fetchChats',
    async ({
        page = 1,
        limit = 20
    }: { page?: number; limit?: number } = {}) => {
        const result = await store.dispatch(
            sessionApi.endpoints.getSessions.initiate(
                {
                    page,
                    limit,
                    session_type: 'chat'
                },
                { forceRefetch: true, subscribe: false }
            )
        )
        return result.data || []
    }
)

export const fetchProjects = createAsyncThunk(
    'sessions/fetchProjects',
    async ({
        page = 1,
        limit = 20
    }: { page?: number; limit?: number } = {}) => {
        const result = await store.dispatch(
            sessionApi.endpoints.getSessions.initiate(
                {
                    page,
                    limit,
                    session_type: 'agent'
                },
                { forceRefetch: true, subscribe: false }
            )
        )
        return result.data || []
    }
)

// Fetch ALL remaining project pages in one go.
//
// IMPORTANT: the backend computes offset = (page - 1) * per_page, so the
// `limit` used here MUST match the `limit` used by the initial fetch and the
// infinite-scroll loader (both use state.sessions.limit, default 20).
// Using a larger batchLimit here would jump the offset past already-loaded
// rows and silently skip every session beyond the first page. (Bug history:
// hardcoding batchLimit=100 caused all sessions past position 20 to vanish
// from the sidebar after clicking "Load all projects".)
export const fetchAllRemainingProjects = createAsyncThunk(
    'sessions/fetchAllRemainingProjects',
    async (_, { getState }) => {
        const state = getState() as { sessions: SessionsState }
        const batchLimit = state.sessions.limit
        let currentPage = state.sessions.projects.page
        const allSessions: ISession[] = []

        // eslint-disable-next-line no-constant-condition
        while (true) {
            currentPage += 1
            const result = await store.dispatch(
                sessionApi.endpoints.getSessions.initiate(
                    {
                        page: currentPage,
                        limit: batchLimit,
                        session_type: 'agent'
                    },
                    { forceRefetch: true, subscribe: false }
                )
            )
            const batch = result.data || []
            allSessions.push(...batch)
            if (batch.length < batchLimit) break
        }

        return { sessions: allSessions, lastPage: currentPage }
    }
)

export const deleteSession = createAsyncThunk(
    'sessions/deleteSession',
    async (sessionId: string) => {
        // Use RTK Query mutation to delete session
        await store.dispatch(
            sessionApi.endpoints.deleteSession.initiate(sessionId)
        ).unwrap()
        return sessionId
    }
)

const BULK_DELETE_BATCH_SIZE = 50

export const bulkDeleteSessions = createAsyncThunk(
    'sessions/bulkDeleteSessions',
    async (sessionIds: string[]) => {
        const allDeletedIds: string[] = []
        const allFailedIds: string[] = []

        // Batch into chunks to respect the API's max 50 IDs per request
        for (let i = 0; i < sessionIds.length; i += BULK_DELETE_BATCH_SIZE) {
            const chunk = sessionIds.slice(i, i + BULK_DELETE_BATCH_SIZE)
            const result = await store.dispatch(
                sessionApi.endpoints.bulkDeleteSessions.initiate(chunk)
            ).unwrap()
            allDeletedIds.push(...result.deleted_ids)
            allFailedIds.push(...result.failed_ids)
        }

        return { deleted_ids: allDeletedIds, failed_ids: allFailedIds }
    }
)

export const updateSession = createAsyncThunk(
    'sessions/updateSession',
    async ({ sessionId, name }: { sessionId: string; name: string }) => {
        // Use RTK Query mutation to update session
        const result = await store.dispatch(
            sessionApi.endpoints.updateSession.initiate({
                sessionId,
                data: { name }
            })
        ).unwrap()
        return result
    }
)

const sessionsSlice = createSlice({
    name: 'sessions',
    initialState,
    reducers: {
        setActiveSessionId: (state, action: PayloadAction<string | null>) => {
            state.activeSessionId = action.payload
        },
        clearSessions: (state) => {
            state.sessions = []
            state.activeSessionId = null
            state.error = null
            state.page = 1
            state.hasMore = true
        },
        clearError: (state) => {
            state.error = null
        },
        resetPagination: (state) => {
            state.page = 1
            state.hasMore = true
            state.sessions = []
        },
        resetChatsPagination: (state) => {
            state.chats = { ...initialPaginatedState }
        },
        resetProjectsPagination: (state) => {
            state.projects = { ...initialPaginatedState }
        },
        moveSessionToTop: (
            state,
            action: PayloadAction<{ sessionId: string; sessionType: 'chat' | 'agent' }>
        ) => {
            const { sessionId, sessionType } = action.payload

            // Move session to top in chats or projects based on session type
            if (sessionType === 'chat') {
                const sessionIndex = state.chats.sessions.findIndex(
                    (s) => s.id === sessionId
                )
                if (sessionIndex > 0) {
                    const [session] = state.chats.sessions.splice(sessionIndex, 1)
                    state.chats.sessions.unshift(session)
                }
            } else {
                const sessionIndex = state.projects.sessions.findIndex(
                    (s) => s.id === sessionId
                )
                if (sessionIndex > 0) {
                    const [session] = state.projects.sessions.splice(sessionIndex, 1)
                    state.projects.sessions.unshift(session)
                }
            }

            // Also update in the general sessions list
            const generalIndex = state.sessions.findIndex((s) => s.id === sessionId)
            if (generalIndex > 0) {
                const [session] = state.sessions.splice(generalIndex, 1)
                state.sessions.unshift(session)
            }
        },
        upsertSession: (state, action: PayloadAction<ISession>) => {
            const session = action.payload

            upsertSessionInList(state.sessions, session)

            if (isChatSession(session)) {
                upsertSessionInList(state.chats.sessions, session)
                state.projects.sessions = state.projects.sessions.filter(
                    (item) => item.id !== session.id
                )
                return
            }

            upsertSessionInList(state.projects.sessions, session)
            state.chats.sessions = state.chats.sessions.filter(
                (item) => item.id !== session.id
            )
        }
    },
    extraReducers: (builder) => {
        builder
            .addCase(fetchSessions.pending, (state) => {
                state.isLoading = true
                state.error = null
            })
            .addCase(fetchSessions.fulfilled, (state, action) => {
                state.isLoading = false
                const newSessions = action.payload

                // For first page, replace sessions
                if (action.meta.arg?.page === 1) {
                    state.sessions = newSessions
                } else {
                    // For subsequent pages, append sessions
                    state.sessions = [...state.sessions, ...newSessions]
                }

                // Update pagination state
                state.page = action.meta.arg?.page || 1
                state.hasMore =
                    newSessions.length === (action.meta.arg?.limit || 20)
            })
            .addCase(fetchSessions.rejected, (state, action) => {
                state.isLoading = false
                state.error = action.error.message || 'Failed to fetch sessions'
            })
            .addCase(deleteSession.pending, (state) => {
                state.error = null
            })
            .addCase(deleteSession.fulfilled, (state, action) => {
                // Remove the deleted session from all lists
                state.sessions = state.sessions.filter(
                    (session) => session.id !== action.payload
                )
                state.chats.sessions = state.chats.sessions.filter(
                    (session) => session.id !== action.payload
                )
                state.projects.sessions = state.projects.sessions.filter(
                    (session) => session.id !== action.payload
                )
                // Clear active session if it was deleted
                if (state.activeSessionId === action.payload) {
                    state.activeSessionId = null
                }
            })
            .addCase(deleteSession.rejected, (state, action) => {
                state.error = action.error.message || 'Failed to delete session'
            })
            .addCase(bulkDeleteSessions.fulfilled, (state, action) => {
                const deletedIds = new Set(action.payload.deleted_ids)
                state.sessions = state.sessions.filter(
                    (s) => !deletedIds.has(s.id)
                )
                state.chats.sessions = state.chats.sessions.filter(
                    (s) => !deletedIds.has(s.id)
                )
                state.projects.sessions = state.projects.sessions.filter(
                    (s) => !deletedIds.has(s.id)
                )
                if (
                    state.activeSessionId &&
                    deletedIds.has(state.activeSessionId)
                ) {
                    state.activeSessionId = null
                }
            })
            .addCase(updateSession.pending, (state) => {
                state.error = null
            })
            .addCase(updateSession.fulfilled, (state, action) => {
                const updatedSession = action.payload
                // Update the session in all lists
                state.sessions = state.sessions.map((session) =>
                    session.id === updatedSession.id ? updatedSession : session
                )
                state.chats.sessions = state.chats.sessions.map((session) =>
                    session.id === updatedSession.id ? updatedSession : session
                )
                state.projects.sessions = state.projects.sessions.map(
                    (session) =>
                        session.id === updatedSession.id
                            ? updatedSession
                            : session
                )
            })
            .addCase(updateSession.rejected, (state, action) => {
                state.error = action.error.message || 'Failed to update session'
            })
            // Chats
            .addCase(fetchChats.pending, (state) => {
                state.chats.isLoading = true
            })
            .addCase(fetchChats.fulfilled, (state, action) => {
                state.chats.isLoading = false
                const newSessions = action.payload

                if (action.meta.arg?.page === 1) {
                    state.chats.sessions = newSessions
                } else {
                    state.chats.sessions = [
                        ...state.chats.sessions,
                        ...newSessions
                    ]
                }

                state.chats.page = action.meta.arg?.page || 1
                state.chats.hasMore =
                    newSessions.length === (action.meta.arg?.limit || 20)
            })
            .addCase(fetchChats.rejected, (state) => {
                state.chats.isLoading = false
            })
            // Projects
            .addCase(fetchProjects.pending, (state) => {
                state.projects.isLoading = true
            })
            .addCase(fetchProjects.fulfilled, (state, action) => {
                state.projects.isLoading = false
                const newSessions = action.payload

                if (action.meta.arg?.page === 1) {
                    state.projects.sessions = newSessions
                } else {
                    state.projects.sessions = [
                        ...state.projects.sessions,
                        ...newSessions
                    ]
                }

                state.projects.page = action.meta.arg?.page || 1
                state.projects.hasMore =
                    newSessions.length === (action.meta.arg?.limit || 20)
            })
            .addCase(fetchProjects.rejected, (state) => {
                state.projects.isLoading = false
            })
            // Fetch all remaining projects
            .addCase(fetchAllRemainingProjects.pending, (state) => {
                state.projects.isLoading = true
            })
            .addCase(fetchAllRemainingProjects.fulfilled, (state, action) => {
                state.projects.isLoading = false
                state.projects.sessions = [
                    ...state.projects.sessions,
                    ...action.payload.sessions
                ]
                state.projects.page = action.payload.lastPage
                state.projects.hasMore = false
            })
            .addCase(fetchAllRemainingProjects.rejected, (state) => {
                state.projects.isLoading = false
            })
    }
})

export const {
    setActiveSessionId,
    clearSessions,
    clearError,
    resetPagination,
    resetChatsPagination,
    resetProjectsPagination,
    moveSessionToTop,
    upsertSession
} = sessionsSlice.actions
export const sessionsReducer = sessionsSlice.reducer

export const selectSessions = (state: { sessions: SessionsState }) =>
    state.sessions.sessions
export const selectActiveSessionId = (state: { sessions: SessionsState }) =>
    state.sessions.activeSessionId
export const selectSessionsLoading = (state: { sessions: SessionsState }) =>
    state.sessions.isLoading
export const selectSessionsError = (state: { sessions: SessionsState }) =>
    state.sessions.error
export const selectSessionsPage = (state: { sessions: SessionsState }) =>
    state.sessions.page
export const selectSessionsHasMore = (state: { sessions: SessionsState }) =>
    state.sessions.hasMore
export const selectSessionsLimit = (state: { sessions: SessionsState }) =>
    state.sessions.limit

// Chats selectors
export const selectChats = (state: { sessions: SessionsState }) =>
    state.sessions.chats.sessions
export const selectChatsLoading = (state: { sessions: SessionsState }) =>
    state.sessions.chats.isLoading
export const selectChatsPage = (state: { sessions: SessionsState }) =>
    state.sessions.chats.page
export const selectChatsHasMore = (state: { sessions: SessionsState }) =>
    state.sessions.chats.hasMore

// Projects selectors
export const selectProjects = (state: { sessions: SessionsState }) =>
    state.sessions.projects.sessions
export const selectProjectsLoading = (state: { sessions: SessionsState }) =>
    state.sessions.projects.isLoading
export const selectProjectsPage = (state: { sessions: SessionsState }) =>
    state.sessions.projects.page
export const selectProjectsHasMore = (state: { sessions: SessionsState }) =>
    state.sessions.projects.hasMore
