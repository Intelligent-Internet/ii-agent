'use client'

import { useEffect, useState, useRef, useCallback } from 'react'
import {
    Link,
    useLocation,
    useNavigate,
    useParams,
    useSearchParams
} from 'react-router'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import {
    Tooltip,
    TooltipContent,
    TooltipTrigger
} from '@/components/ui/tooltip'

import { Logo } from './logo'
import { Icon } from './ui/icon'
import {
    Sidebar as SidebarContainer,
    SidebarContent,
    SidebarHeader,
    SidebarMenu,
    SidebarMenuItem,
    useSidebar
} from './ui/sidebar'
import {
    setMessages,
    fetchChats,
    fetchProjects,
    fetchAllRemainingProjects,
    setActiveSessionId,
    selectChatsLoading,
    selectChatsHasMore,
    selectChatsPage,
    selectProjectsLoading,
    selectProjectsHasMore,
    selectProjectsPage,
    selectSessionsLimit,
    resetChatsPagination,
    resetProjectsPagination,
    useAppDispatch,
    useAppSelector,
    setCurrentActionData,
    setShouldFocusInput,
    setRequireClearFiles,
    setActiveTab,
    setIsMobileChatVisible,
    setQuestionMode,
    setChatMediaPreference,
    selectChatMediaPreference
} from '@/state'
import { getDefaultChatMediaPreference } from '@/utils/default-models'
import { useMediaModels } from '@/hooks/use-media-models'
import SearchHistory from './search-history'
import { QUESTION_MODE, TAB } from '@/typings/agent'
import { useSessionStateManager } from '@/hooks/use-session-state-manager'
import Credit from './credit'
import { useGetCreditBalanceQuery } from '@/state'
import { ENABLE_BETA } from '@/constants/features'
import ChatList from './chat-list'
import ProjectList from './project-list'
import UserProfileDropdown from './user-profile-dropdown'
import { useIsSageTheme } from '@/hooks/use-is-sage-theme'
import { useChat } from '@/hooks/use-chat-query'
import clsx from 'clsx'

interface SidebarButtonProps {
    className?: string
    workspaceInfo?: string
}

const Sidebar = ({ className, workspaceInfo }: SidebarButtonProps) => {
    const { t } = useTranslation()
    const navigate = useNavigate()
    const [searchParams] = useSearchParams()
    const location = useLocation()
    const { sessionId: sessionIdFromParams } = useParams()
    const isSage = useIsSageTheme()

    const dispatch = useAppDispatch()
    const { isMobile, toggleSidebar, state } = useSidebar()
    const { resetSessionState } = useSessionStateManager()
    const { resetConversationState, setSessionId } = useChat()
    const { imageModels, videoModels } = useMediaModels()

    const chatsLoading = useAppSelector(selectChatsLoading)
    const chatsHasMore = useAppSelector(selectChatsHasMore)
    const chatsPage = useAppSelector(selectChatsPage)
    const projectsLoading = useAppSelector(selectProjectsLoading)
    const projectsHasMore = useAppSelector(selectProjectsHasMore)
    const projectsPage = useAppSelector(selectProjectsPage)
    const limit = useAppSelector(selectSessionsLimit)
    const chatMediaPreference = useAppSelector(selectChatMediaPreference)

    // Use RTK Query hook to fetch credit balance
    useGetCreditBalanceQuery()

    // Get session ID from either URL params or query parameter
    const sessionId = sessionIdFromParams || searchParams.get('id') || ''
    const scrollContainerRef = useRef<HTMLDivElement>(null)
    const [loadingMoreChats, setLoadingMoreChats] = useState(false)
    const [loadingMoreProjects, setLoadingMoreProjects] = useState(false)

    const handleNewChat = () => {
        // Reset all session state
        resetSessionState()
        resetConversationState()
        setSessionId(null)

        // Reset messages and other chat-specific state
        dispatch(setMessages([]))
        dispatch(setActiveTab(TAB.BUILD))
        dispatch(setIsMobileChatVisible(true))
        dispatch(setShouldFocusInput(true))
        dispatch(setRequireClearFiles(true))
        dispatch(
            setChatMediaPreference(
                getDefaultChatMediaPreference(
                    imageModels,
                    videoModels,
                    chatMediaPreference
                )
            )
        )
        dispatch(setQuestionMode(QUESTION_MODE.CHAT))
        navigate('/')
        if (isMobile) {
            toggleSidebar()
        }
    }

    const handleNewProject = () => {
        // Reset all session state
        resetSessionState()
        resetConversationState()
        setSessionId(null)

        // Reset messages and other project-specific state
        dispatch(setMessages([]))
        dispatch(setActiveTab(TAB.BUILD))
        dispatch(setIsMobileChatVisible(true))
        dispatch(setShouldFocusInput(true))
        dispatch(setRequireClearFiles(true))
        dispatch(setQuestionMode(QUESTION_MODE.AGENT))
        navigate('/')
        if (isMobile) {
            toggleSidebar()
        }
    }

    const handleResetState = () => {
        // Reset all session state
        resetSessionState()
        resetConversationState()
        setSessionId(null)

        // Reset messages and other state
        dispatch(setMessages([]))
        dispatch(setCurrentActionData(undefined))
        if (isMobile) {
            toggleSidebar()
        }
    }

    const handleGotoSubscription = () => {
        navigate('/settings/subscription')
    }

    const handleScroll = useCallback(() => {
        if (!scrollContainerRef.current) {
            return
        }

        const { scrollTop, scrollHeight, clientHeight } =
            scrollContainerRef.current

        // Load more when user scrolls to within 100px of the bottom
        if (scrollHeight - scrollTop - clientHeight < 100) {
            // Load more chats if available
            if (!loadingMoreChats && chatsHasMore && !chatsLoading) {
                setLoadingMoreChats(true)
                dispatch(fetchChats({ page: chatsPage + 1, limit })).finally(
                    () => setLoadingMoreChats(false)
                )
            }
            // Load more projects if available
            if (!loadingMoreProjects && projectsHasMore && !projectsLoading) {
                setLoadingMoreProjects(true)
                dispatch(fetchProjects({ page: projectsPage + 1, limit })).finally(
                    () => setLoadingMoreProjects(false)
                )
            }
        }
    }, [
        dispatch,
        chatsPage,
        projectsPage,
        limit,
        chatsHasMore,
        chatsLoading,
        loadingMoreChats,
        projectsHasMore,
        projectsLoading,
        loadingMoreProjects
    ])

    const header = (
        <div className="flex items-center gap-4">
            <div className="flex w-full md:hidden items-center justify-between">
                <div className="flex gap-x-3 items-center">
                    <Tooltip>
                        <TooltipTrigger asChild>
                            <Button
                                className="!p-0"
                                onClick={toggleSidebar}
                                aria-label={t('common.close')}
                            >
                                <Icon
                                    name="arrow-circle-left"
                                    className="size-6 fill-black dark:fill-white"
                                />
                            </Button>
                        </TooltipTrigger>
                        <TooltipContent side="bottom">
                            {t('common.close')}
                        </TooltipContent>
                    </Tooltip>

                    <Logo
                        imageClassName={`${isSage ? '!h-6 md:!h-6' : 'size-8 md:size-10'} rounded-sm`}
                        label="II-Agent"
                        labelClassName="text-black dark:text-white text-lg font-semibold"
                        showBeta={ENABLE_BETA}
                    />
                </div>
                <div className="flex items-center gap-x-4">
                    {location.pathname !== '/' && (
                        <Link to="/">
                            <Icon
                                name="home"
                                className="size-6 fill-black dark:fill-white"
                            />
                        </Link>
                    )}
                    <Link to="/dashboard">
                        <Icon
                            name="dashboard"
                            className="size-6 fill-black dark:fill-white"
                        />
                    </Link>
                    <SearchHistory isMobile />
                </div>
            </div>
            <Logo
                className="hidden md:flex gap-x-3"
                imageClassName={clsx(
                    'rounded-sm',
                    isSage ? '!h-6 md:!h-10' : 'size-10'
                )}
                label="II-Agent"
                labelClassName="group-data-[collapsible=icon]:hidden text-black dark:text-white text-2xl font-semibold"
                showBeta={ENABLE_BETA}
                betaClassName="group-data-[collapsible=icon]:hidden"
                width={40}
                height={40}
                showIconWhenCollapsed
            />
        </div>
    )

    useEffect(() => {
        if (sessionId) {
            dispatch(setActiveSessionId(sessionId))
        }
    }, [sessionId, dispatch])

    useEffect(() => {
        dispatch(resetChatsPagination())
        dispatch(resetProjectsPagination())
        dispatch(fetchChats({ page: 1, limit }))
        dispatch(fetchProjects({ page: 1, limit }))
    }, [dispatch, limit])

    useEffect(() => {
        const scrollContainer = scrollContainerRef.current
        if (!scrollContainer) return

        scrollContainer.addEventListener('scroll', handleScroll)
        return () => scrollContainer.removeEventListener('scroll', handleScroll)
    }, [handleScroll])

    return (
        <SidebarContainer
            collapsible="icon"
            className={`bg-sidebar-bg dark:!bg-charcoal border-grey-2 dark:!border-grey/30 group-data-[collapsible=icon]:w-[88px] ${className}`}
        >
            <SidebarHeader>{header}</SidebarHeader>
            <SidebarContent ref={scrollContainerRef}>
                <SidebarMenu>
                    <div className="px-3 md:px-6 pb-6">
                        <div className="flex md:hidden mb-6 items-center justify-between">
                            <div className="flex items-center gap-2 flex-1">
                                <UserProfileDropdown showPlan />
                            </div>
                            <Tooltip>
                                <TooltipTrigger asChild>
                                    <Button
                                        size="xl"
                                        className="bg-firefly dark:bg-sky-blue-2 text-sky-blue-2 dark:text-black rounded-full text-sm font-semibold px-3 py-[6px] h-auto"
                                        onClick={handleGotoSubscription}
                                    >
                                        <span className="group-data-[collapsible=icon]:hidden text-sm">
                                            {t('upgrade.title')}
                                        </span>
                                    </Button>
                                </TooltipTrigger>
                                <TooltipContent side="bottom">
                                    {t('upgrade.title')}
                                </TooltipContent>
                            </Tooltip>
                        </div>
                        <Tooltip>
                            <TooltipTrigger asChild>
                                <Button
                                    className="!px-0 h-auto group-data-[collapsible=icon]:!w-10"
                                    size="xl"
                                    onClick={handleNewChat}
                                >
                                    <Icon
                                        name="edit"
                                        className="size-5 fill-black dark:fill-white"
                                    />{' '}
                                    <span className="group-data-[collapsible=icon]:hidden font-normal">
                                        {t('sidebar.newChat')}
                                    </span>
                                </Button>
                            </TooltipTrigger>
                            <TooltipContent
                                side="right"
                                align="center"
                                hidden={state !== 'collapsed' || isMobile}
                            >
                                {t('sidebar.newChat')}
                            </TooltipContent>
                        </Tooltip>
                        <SearchHistory className="mt-4 hidden md:block group-data-[collapsible=icon]:mt-6" />
                        <SidebarMenuItem className="hidden md:block mt-4 group-data-[collapsible=icon]:mt-6">
                            <Tooltip>
                                <TooltipTrigger asChild>
                                    <Link
                                        to="/dashboard"
                                        aria-label={t('dashboard.title')}
                                        className="flex items-center gap-x-2 group-data-[collapsible=icon]:px-0 group-data-[collapsible=icon]:justify-center"
                                    >
                                        <Icon
                                            name="dashboard"
                                            className="fill-black dark:fill-white"
                                        />
                                        <span className="group-data-[collapsible=icon]:hidden">
                                            {t('dashboard.title')}
                                        </span>
                                    </Link>
                                </TooltipTrigger>
                                <TooltipContent
                                    side="right"
                                    align="center"
                                    hidden={state !== 'collapsed' || isMobile}
                                >
                                    {t('dashboard.title')}
                                </TooltipContent>
                            </Tooltip>
                        </SidebarMenuItem>

                        <div className="mt-4 md:mt-8 space-y-8 group-data-[collapsible=icon]:mt-4">
                            <ProjectList
                                workspaceInfo={workspaceInfo}
                                isLoading={projectsLoading}
                                loadingMore={loadingMoreProjects}
                                hasMore={projectsHasMore}
                                onLoadMore={() => {
                                    if (!loadingMoreProjects && projectsHasMore && !projectsLoading) {
                                        setLoadingMoreProjects(true)
                                        dispatch(fetchAllRemainingProjects()).finally(
                                            () => setLoadingMoreProjects(false)
                                        )
                                    }
                                }}
                                handleResetState={handleResetState}
                                handleNewProject={handleNewProject}
                            />
                            <ChatList
                                workspaceInfo={workspaceInfo}
                                isLoading={chatsLoading}
                                loadingMore={loadingMoreChats}
                                handleResetState={handleResetState}
                            />
                        </div>
                    </div>
                </SidebarMenu>
            </SidebarContent>
            <Credit />
        </SidebarContainer>
    )
}

export default Sidebar
