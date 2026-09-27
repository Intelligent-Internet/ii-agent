// Export store and hooks
export {
    default as store,
    useAppDispatch,
    useAppSelector,
    persistor
} from './store'
export type { RootState, AppDispatch } from './store'

// Export all action creators
export * from './slice/messages'
export * from './slice/ui'
export * from './slice/editor'
export * from './slice/agent'
export * from './slice/files'
export * from './slice/workspace'
export * from './slice/settings'

// Export user slice with explicit re-exports to avoid naming conflicts with ui slice
export {
    setUser,
    clearUser,
    setLoading as setUserLoading,
    getCreditBalance,
    getCreditUsage,
    userReducer,
    selectUser,
    selectCreditBalance,
    selectBonusCreditBalance,
    selectCreditUsage,
    selectCreditsLoading,
    selectCreditsError,
    selectSubscriptionStatus,
    selectSubscriptionPlan,
    selectSubscriptionCurrentPeriodEnd,
    selectSubscriptionBillingCycle,
    selectUserLanguage
} from './slice/user'

// Export sessions slice with explicit re-exports to avoid naming conflicts
export {
    fetchSessions,
    fetchChats,
    fetchProjects,
    fetchAllRemainingProjects,
    bulkDeleteSessions,
    setActiveSessionId,
    clearSessions,
    resetPagination,
    resetChatsPagination,
    resetProjectsPagination,
    moveSessionToTop,
    upsertSession,
    sessionsReducer,
    selectSessions,
    selectActiveSessionId,
    selectSessionsLoading,
    selectSessionsError,
    selectSessionsPage,
    selectSessionsHasMore,
    selectSessionsLimit,
    selectChats,
    selectChatsLoading,
    selectChatsPage,
    selectChatsHasMore,
    selectProjects,
    selectProjectsLoading,
    selectProjectsPage,
    selectProjectsHasMore,
    clearError as clearSessionsError
} from './slice/sessions'

// Export favorites slice with explicit re-exports to avoid naming conflicts
export {
    fetchWishlist,
    addToWishlistAsync,
    removeFromWishlistAsync,
    toggleFavoriteAsync,
    toggleFavorite,
    addFavorite,
    removeFavorite,
    clearFavorites,
    setFavorites,
    selectFavoriteSessionIds,
    selectIsFavorite,
    selectFavoritesLoading,
    selectFavoritesError,
    selectFavoritesInitialized,
    favoritesReducer,
    clearError as clearFavoritesError
} from './slice/favorites'

// Export pins slice with explicit re-exports to avoid naming conflicts
export {
    fetchPins,
    pinSessionAsync,
    unpinSessionAsync,
    togglePinAsync,
    togglePin,
    addPin,
    removePin,
    clearPins,
    setPins,
    selectPinnedSessionIds,
    selectPinnedSessions,
    selectIsPinned,
    selectPinsLoading,
    selectPinsError,
    selectPinsInitialized,
    pinnedItemToSession,
    pinsReducer,
    clearPinsError
} from './slice/pins'

// Export session state slice
export * from './slice/session-state'

// Export file explorer slice
export * from './slice/file-explorer'

// Export RTK Query API
export {
    userApi,
    useGetCreditBalanceQuery,
    useGetCreditUsageQuery,
    useGetSessionUsageDetailQuery,
    useGetSessionLedgerQuery,
    useGetSessionReservationsQuery
} from './api/user.api'
export {
    sessionApi,
    useGetSessionsQuery,
    useDeleteSessionMutation
} from './api/session.api'
export {
    connectorApi,
    useGetGoogleDriveStatusQuery,
    useGetGitHubStatusQuery,
    useGetRevenueCatStatusQuery,
    useDisconnectGoogleDriveMutation,
    useDisconnectGitHubMutation,
    useDisconnectRevenueCatMutation
} from './api/connector.api'
