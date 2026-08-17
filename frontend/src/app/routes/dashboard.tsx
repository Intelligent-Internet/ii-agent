import clsx from 'clsx'
import SessionTitle from '@/components/session-title'
import { hasSessionDisplayTitle } from '@/utils/session-title'
import { useMemo, useState, useRef, useCallback, useEffect } from 'react'
import { Link, useNavigate } from 'react-router'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { Icon } from '@/components/ui/icon'
import Sidebar from '@/components/sidebar'
import { SidebarProvider } from '@/components/ui/sidebar'
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuSeparator,
    DropdownMenuTrigger
} from '@/components/ui/dropdown-menu'
import {
    AlertDialog,
    AlertDialogAction,
    AlertDialogCancel,
    AlertDialogContent,
    AlertDialogDescription,
    AlertDialogFooter,
    AlertDialogHeader,
    AlertDialogTitle
} from '@/components/ui/alert-dialog'
import ShareConversation from '@/components/agent/share-conversation'
import {
    selectSessions,
    selectSessionsLoading,
    selectSessionsHasMore,
    selectSessionsPage,
    selectSessionsLimit,
    fetchSessions,
    resetPagination,
    useAppSelector,
    useAppDispatch,
    toggleFavoriteAsync,
    selectFavoriteSessionIds,
    fetchWishlist,
    fetchPins
} from '@/state'
import { wishlistService } from '@/services/wishlist.service'
import { sessionService } from '@/services/session.service'
import { ISession } from '@/typings/agent'
import { deleteSession, selectActiveSessionId } from '@/state/slice/sessions'
import { clearSessionState } from '@/state/slice/session-state'
import { removePin } from '@/state/slice/pins'
import { setRunStatus } from '@/state/slice/agent'
import { setLoading } from '@/state'

enum TAB {
    ALL = 'all',
    RECENT = 'recent',
    FAVORITE = 'favorite'
}

export function DashboardPage() {
    const { t } = useTranslation()
    const navigate = useNavigate()
    const dispatch = useAppDispatch()
    const [activeTab, setActiveTab] = useState(TAB.ALL)
    const [loadingMore, setLoadingMore] = useState(false)
    const [shareSessionId, setShareSessionId] = useState<string | null>(null)
    const [deleteSessionId, setDeleteSessionId] = useState<string | null>(null)
    const [isDeleteDialogOpen, setIsDeleteDialogOpen] = useState(false)
    const [favoriteSessions, setFavoriteSessions] = useState<ISession[]>([])
    const [loadingFavorites, setLoadingFavorites] = useState(false)
    const scrollContainerRef = useRef<HTMLDivElement>(null)

    const sessions = useAppSelector(selectSessions)
    const isLoading = useAppSelector(selectSessionsLoading)
    const hasMore = useAppSelector(selectSessionsHasMore)
    const currentPage = useAppSelector(selectSessionsPage)
    const limit = useAppSelector(selectSessionsLimit)
    const favoriteSessionIds = useAppSelector(selectFavoriteSessionIds)
    const activeSessionId = useAppSelector(selectActiveSessionId)

    const handleBack = () => {
        navigate(-1)
    }

    const toggleFavorite = async (id: string) => {
        await dispatch(toggleFavoriteAsync(id))

        // If we're on the Favorite tab, update the favorite sessions list
        if (activeTab === TAB.FAVORITE) {
            // Remove the session from favorites list if it was unfavorited
            if (isFavorite(id)) {
                setFavoriteSessions((prev) =>
                    prev.filter((session) => session.id !== id)
                )
            }
        }
    }

    const isFavorite = (id: string) => {
        return favoriteSessionIds.includes(id)
    }

    const handleShare = (sessionId: string) => {
        setShareSessionId(sessionId)
    }

    // const handleRename = (sessionId: string) => {
    //     console.log('Rename session:', sessionId)
    // }

    const handleDelete = (sessionId: string) => {
        setDeleteSessionId(sessionId)
        setIsDeleteDialogOpen(true)
    }

    const confirmDelete = async () => {
        if (!deleteSessionId) return

        try {
            await dispatch(deleteSession(deleteSessionId)).unwrap()
            dispatch(clearSessionState(deleteSessionId))
            dispatch(removePin(deleteSessionId))
            if (deleteSessionId === activeSessionId) {
                dispatch(setRunStatus(null))
                dispatch(setLoading(false))
            }
            setIsDeleteDialogOpen(false)
            setDeleteSessionId(null)
        } catch (error) {
            console.error('Failed to delete session:', error)
            // You might want to show a toast notification here
        }
    }

    const cancelDelete = () => {
        setIsDeleteDialogOpen(false)
        setDeleteSessionId(null)
    }

    const sessionsByTab = useMemo(() => {
        const filteredSessions = sessions?.filter(hasSessionDisplayTitle)
        switch (activeTab) {
            case TAB.ALL:
                return filteredSessions
            case TAB.RECENT:
                return filteredSessions?.slice(0, 10)
            case TAB.FAVORITE:
                // Use the fetched favorite sessions from API
                return favoriteSessions.filter(hasSessionDisplayTitle)
            default:
                return filteredSessions
        }
    }, [activeTab, sessions, favoriteSessions])

    // Initialize sessions on mount and fetch wishlist
    useEffect(() => {
        dispatch(resetPagination())
        dispatch(fetchSessions({ page: 1, limit }))
        dispatch(fetchWishlist())
        dispatch(fetchPins())
    }, [dispatch, limit])

    // Fetch favorite sessions when Favorite tab is selected or favoriteSessionIds changes
    useEffect(() => {
        const loadFavoriteSessions = async () => {
            if (activeTab === TAB.FAVORITE) {
                setLoadingFavorites(true)
                try {
                    const wishlistResponse =
                        await wishlistService.getWishlistSessions()

                    // Fetch full session details for each wishlist item
                    const sessionPromises = wishlistResponse.sessions.map(
                        (item) => sessionService.getSession(item.session_id)
                    )

                    const sessionDetails = await Promise.all(sessionPromises)
                    setFavoriteSessions(sessionDetails)
                } catch (error) {
                    console.error('Failed to load favorite sessions:', error)
                    setFavoriteSessions([])
                } finally {
                    setLoadingFavorites(false)
                }
            }
        }

        loadFavoriteSessions()
    }, [activeTab, favoriteSessionIds])

    // Handle infinite scroll
    const handleScroll = useCallback(() => {
        if (
            !scrollContainerRef.current ||
            loadingMore ||
            !hasMore ||
            isLoading
        ) {
            return
        }

        const { scrollTop, scrollHeight, clientHeight } =
            scrollContainerRef.current

        // Load more when user scrolls to within 100px of the bottom
        if (scrollHeight - scrollTop - clientHeight < 100) {
            setLoadingMore(true)
            dispatch(fetchSessions({ page: currentPage + 1, limit })).finally(
                () => setLoadingMore(false)
            )
        }
    }, [dispatch, currentPage, limit, hasMore, isLoading, loadingMore])

    useEffect(() => {
        const scrollContainer = scrollContainerRef.current
        if (!scrollContainer) return

        scrollContainer.addEventListener('scroll', handleScroll)
        return () => scrollContainer.removeEventListener('scroll', handleScroll)
    }, [handleScroll])

    return (
        <div className="flex h-screen">
            <div>
                <SidebarProvider>
                    <Sidebar />
                </SidebarProvider>
            </div>
            <div className="flex justify-center px-3 md:px-0 pt-3 md:pt-[96px] flex-1">
                <div className="flex flex-col gap-y-4 md:gap-y-10 w-full md:max-w-[768px]">
                    <div className="flex flex-col md:flex-row md:items-center justify-between gap-8 md:gap-3">
                        <div className="flex items-center gap-x-3 md:gap-x-4">
                            <button
                                className="cursor-pointer"
                                onClick={handleBack}
                            >
                                <Icon
                                    name="arrow-left"
                                    className="size-6 md:size-8 hidden dark:inline"
                                />
                                <Icon
                                    name="arrow-left-dark"
                                    className="size-6 md:size-8 inline dark:hidden"
                                />
                            </button>
                            <span className="text-black dark:text-sky-blue text-2xl md:text-[32px] font-semibold">
                                {t('dashboard.title')}
                            </span>
                        </div>
                        <div className="flex items-center gap-x-2">
                            <Button
                                className={clsx(
                                    'h-7 text-xs font-semibold px-4 rounded-full border border-firefly dark:border-sky-blue',
                                    {
                                        'bg-firefly dark:bg-sky-blue text-sky-blue-2 dark:text-black':
                                            activeTab === TAB.ALL,
                                        'text-firefly dark:text-sky-blue':
                                            activeTab !== TAB.ALL
                                    }
                                )}
                                onClick={() => setActiveTab(TAB.ALL)}
                            >
                                {t('dashboard.tabs.all')}
                            </Button>
                            <Button
                                className={clsx(
                                    'h-7 text-xs font-semibold px-4 rounded-full border border-firefly dark:border-sky-blue',
                                    {
                                        'bg-firefly dark:bg-sky-blue text-sky-blue-2 dark:text-black':
                                            activeTab === TAB.RECENT,
                                        'text-firefly dark:text-sky-blue':
                                            activeTab !== TAB.RECENT
                                    }
                                )}
                                onClick={() => setActiveTab(TAB.RECENT)}
                            >
                                {t('dashboard.tabs.recent')}
                            </Button>
                            <Button
                                className={clsx(
                                    'h-7 text-xs font-semibold px-4 rounded-full border border-firefly dark:border-sky-blue',
                                    {
                                        'bg-firefly dark:bg-sky-blue text-sky-blue-2 dark:text-black':
                                            activeTab === TAB.FAVORITE,
                                        'text-firefly dark:text-sky-blue':
                                            activeTab !== TAB.FAVORITE
                                    }
                                )}
                                onClick={() => setActiveTab(TAB.FAVORITE)}
                            >
                                {t('dashboard.tabs.favorite')}
                            </Button>
                        </div>
                    </div>
                    <div
                        ref={scrollContainerRef}
                        className="flex-1 divide-y divide-black/30 dark:divide-white/30 overflow-auto pb-8"
                    >
                        {loadingFavorites && activeTab === TAB.FAVORITE ? (
                            <div className="text-center py-8 text-gray-500">
                                {t('dashboard.loadingFavorites')}
                            </div>
                        ) : sessionsByTab?.length === 0 &&
                          activeTab === TAB.FAVORITE ? (
                            <div className="text-center py-8 text-gray-500">
                                {t('dashboard.noFavorites')}
                            </div>
                        ) : (
                            sessionsByTab?.map((session) => (
                                <Link
                                    to={
                                        session.agent_type === 'chat'
                                            ? `/chat?id=${session.id}`
                                            : `/${session.id}`
                                    }
                                    key={session.id}
                                    className="flex items-center justify-between gap-4 md:gap-6 md:px-4 py-3"
                                >
                                    <div className="flex items-center gap-3 md:gap-4">
                                        <Icon
                                            name={
                                                session.agent_type === 'chat'
                                                    ? 'chat'
                                                    : 'folder-3'
                                            }
                                            className="size-8 md:size-10 fill-black dark:fill-white"
                                        />
                                        <div className="flex flex-col gap-1 text-sm flex-1">
                                            <p className="font-semibold">
                                                <SessionTitle session={session} />
                                            </p>
                                        </div>
                                    </div>
                                    <div className="flex items-center gap-4">
                                        <Button
                                            size="icon"
                                            className="w-auto"
                                            onClick={(e) => {
                                                e.preventDefault()
                                                e.stopPropagation()
                                                toggleFavorite(session.id)
                                            }}
                                        >
                                            {isFavorite(session.id) ? (
                                                <Icon
                                                    name="star-fill"
                                                    className="fill-black dark:fill-white size-6"
                                                />
                                            ) : (
                                                <Icon
                                                    name="star"
                                                    className="fill-black dark:fill-white size-6"
                                                />
                                            )}
                                        </Button>
                                        <DropdownMenu>
                                            <DropdownMenuTrigger className="cursor-pointer">
                                                <Icon
                                                    name="more"
                                                    className="size-6 fill-black dark:fill-white"
                                                />
                                            </DropdownMenuTrigger>
                                            <DropdownMenuContent
                                                align="end"
                                                className="w-[185px] px-4 py-2"
                                            >
                                                <DropdownMenuItem
                                                    className="py-2"
                                                    onClick={(e) => {
                                                        e.preventDefault()
                                                        e.stopPropagation()
                                                        handleShare(session.id)
                                                    }}
                                                >
                                                    <Icon
                                                        name="share"
                                                        className="size-5 stroke-black"
                                                    />
                                                    {t('common.share')}
                                                </DropdownMenuItem>
                                                {/* <DropdownMenuItem
                                                    className="py-2"
                                                    onClick={() =>
                                                        handleRename(session.id)
                                                    }
                                                >
                                                    <Icon
                                                        name="edit"
                                                        className="size-5 fill-black"
                                                    />
                                                    Rename
                                                </DropdownMenuItem> */}
                                                <DropdownMenuSeparator className="my-1" />
                                                <DropdownMenuItem
                                                    onClick={(e) => {
                                                        e.preventDefault()
                                                        e.stopPropagation()
                                                        handleDelete(session.id)
                                                    }}
                                                    variant="destructive"
                                                    className="text-red-2 py-2"
                                                >
                                                    <Icon
                                                        name="trash"
                                                        className="size-5"
                                                    />
                                                    {t('common.delete')}
                                                </DropdownMenuItem>
                                            </DropdownMenuContent>
                                        </DropdownMenu>
                                    </div>
                                </Link>
                            ))
                        )}
                        {loadingMore && (
                            <div className="text-center py-4 text-gray-500">
                                {t('common.loadingMore')}
                            </div>
                        )}
                    </div>
                </div>
            </div>
            {shareSessionId && (
                <ShareConversation
                    open={!!shareSessionId}
                    onOpenChange={(open) => !open && setShareSessionId(null)}
                    sessionId={shareSessionId}
                />
            )}
            <AlertDialog
                open={isDeleteDialogOpen}
                onOpenChange={setIsDeleteDialogOpen}
            >
                <AlertDialogContent>
                    <AlertDialogHeader>
                        <AlertDialogTitle>
                            {t('dashboard.deleteSession')}
                        </AlertDialogTitle>
                        <AlertDialogDescription>
                            {t('dashboard.deleteConfirmation')}
                        </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                        <AlertDialogCancel onClick={cancelDelete}>
                            {t('common.cancel')}
                        </AlertDialogCancel>
                        <AlertDialogAction
                            onClick={confirmDelete}
                            className="bg-red-2 hover:bg-red-2 text-white"
                        >
                            {t('common.delete')}
                        </AlertDialogAction>
                    </AlertDialogFooter>
                </AlertDialogContent>
            </AlertDialog>
        </div>
    )
}

export const Component = DashboardPage
