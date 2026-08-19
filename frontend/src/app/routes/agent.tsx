import Lottie from 'lottie-react'
import clsx from 'clsx'
import { useEffect, useMemo, useRef, useState } from 'react'
import { useLocation, useNavigate, useParams } from 'react-router'
import { useTheme } from 'next-themes'

import ThinkingLottie from '@/assets/thinking_2.json'
import ThinkingDarkMode from '@/assets/thinking_dark_mode.json'
import AgentBuild from '@/components/agent/agent-build'
import AgentSteps from '@/components/agent/agent-step'
import AgentTabs from '@/components/agent/agent-tab'
import AgentTasks from '@/components/agent/agent-task'
import ChatBox from '@/components/agent/chat-box'
import AgentHeader from '@/components/header'
import RightSidebar from '@/components/right-sidebar'
import { rewriteLocalhostUrl } from '@/lib/utils'
import { sessionService } from '@/services/session.service'
import {
    selectActiveTab,
    selectSelectedBuildStep,
    selectIsMobileChatVisible,
    selectPreviewUrl,
    selectMobileWebPreviewUrl,
    selectHasMobileAppTools,
    selectHasSlideTools,
    selectProjectId,
    selectWsConnectionState,
    setSelectedFeature,
    setIsMobileChatVisible,
    setProjectId,
    useAppDispatch,
    useAppSelector,
    selectIsLoading,
    setQuestionMode
} from '@/state'
import {
    BUILD_STEP,
    CommandType,
    ISession,
    QUESTION_MODE,
    TAB,
    WebSocketConnectionState
} from '@/typings/agent'
import AgentResult from '@/components/agent/agent-result'
import PiPPreview from '@/components/agent/pip-preview'
import AgentPopoverDone from '@/components/agent/agent-popover-done'
import { useSocketIOContext } from '@/contexts/websocket-context'
import { SidebarProvider } from '@/components/ui/sidebar'
import Sidebar from '@/components/sidebar'
import AgentTabMobile, {
    type ChatOption as MobileChatOption
} from '@/components/agent-tab-mobile'
import ProjectPanel from '@/components/project/project-panel'
import { useIsMobile } from '@/hooks/use-mobile'
import { useSessionEnter } from '@/hooks/use-session-enter'
import { DesignModeProvider } from '@/components/design-mode'
import { useTranslation } from 'react-i18next'

function AgentPageContent() {
    const { sessionId } = useParams()
    const dispatch = useAppDispatch()
    const navigate = useNavigate()
    const theme = useTheme()
    const location = useLocation()
    const { t } = useTranslation()

    // Restore session state when entering a session
    useSessionEnter()

    const activeTab = useAppSelector(selectActiveTab)
    const selectedBuildStep = useAppSelector(selectSelectedBuildStep)
    const [sessionData, setSessionData] = useState<ISession>()
    const [sessionError, setSessionError] = useState<string | null>(null)
    const [mobileChatTab, setMobileChatTab] = useState<MobileChatOption>('chat')
    const { socket, sendMessage } = useSocketIOContext()
    const isRunning = useAppSelector(selectIsLoading)
    const isMobileChatVisible = useAppSelector(selectIsMobileChatVisible)
    // Use memoized selector for previewUrl to avoid subscribing to full messages array
    const previewUrl = useAppSelector(selectPreviewUrl)
    const mobileWebPreviewUrl = useAppSelector(selectMobileWebPreviewUrl)
    const hasMobileAppTools = useAppSelector(selectHasMobileAppTools)
    const hasSlideTools = useAppSelector(selectHasSlideTools)
    const projectId = useAppSelector(selectProjectId)
    const [isPiPDismissed, setIsPiPDismissed] = useState(false)
    const wsConnectionState = useAppSelector(selectWsConnectionState)
    const previousResultUrlRef = useRef<string>('')
    const isMobile = useIsMobile()

    const isShareMode = useMemo(
        () => location.pathname.includes('/share/'),
        [location.pathname]
    )

    // PiP preview URL (mobile takes priority over fullstack)
    const pipUrl = rewriteLocalhostUrl(mobileWebPreviewUrl || previewUrl)
    const showPiP =
        !isMobile &&
        activeTab !== TAB.RESULT &&
        !!pipUrl &&
        !isPiPDismissed &&
        !hasSlideTools &&
        !isShareMode

    // Reset PiP dismissed state when switching to RESULT tab or when URL changes
    useEffect(() => {
        if (activeTab === TAB.RESULT) {
            setIsPiPDismissed(false)
        }
    }, [activeTab])

    useEffect(() => {
        setIsPiPDismissed(false)
    }, [pipUrl])

    const isChatBoxVisible = useMemo(
        () => !isMobile || (isMobile && isMobileChatVisible),
        [isMobile, isMobileChatVisible]
    )

    useEffect(() => {
        const previousResultUrl = previousResultUrlRef.current
        const hasNewResult = !!previewUrl && !previousResultUrl

        if (isMobile && hasNewResult && isMobileChatVisible) {
            dispatch(setIsMobileChatVisible(false))
        }

        previousResultUrlRef.current = previewUrl ?? ''
    }, [dispatch, isMobile, previewUrl, isMobileChatVisible])

    // Single sandbox_status request for both PROJECT and RESULT tabs.
    useEffect(() => {
        if (
            (activeTab === TAB.PROJECT || activeTab === TAB.RESULT) &&
            wsConnectionState === WebSocketConnectionState.CONNECTED &&
            socket
        ) {
            sendMessage({
                session_uuid: sessionId || '',
                content: { command: CommandType.SANDBOX_STATUS }
            })
        }
    }, [activeTab, sessionId, socket, sendMessage, wsConnectionState])

    useEffect(() => {
        dispatch(setQuestionMode(QUESTION_MODE.AGENT))
    }, [dispatch])

    useEffect(() => {
        let timeoutId: NodeJS.Timeout | undefined

        const fetchSession = async () => {
            if (sessionId) {
                dispatch(setProjectId(null))
                try {
                    const data = await sessionService.getSession(sessionId)

                    if (!data?.name || data.name.trim() === '') {
                        // Retry after 5 seconds if name is null or empty
                        timeoutId = setTimeout(() => {
                            fetchSession()
                        }, 5000)
                    } else {
                        // Redirect chat sessions to the chat page
                        if (data.agent_type === 'chat') {
                            navigate(`/chat?id=${sessionId}`, { replace: true })
                            return
                        }
                        dispatch(setSelectedFeature(data.agent_type ?? null))
                        dispatch(setProjectId(data.project_id ?? null))
                        setSessionData(data)
                        setSessionError(null) // Clear any previous errors
                    }
                } catch (error: unknown) {
                    // Handle 404 errors specifically
                    if (
                        error &&
                        typeof error === 'object' &&
                        'response' in error
                    ) {
                        const axiosError = error as {
                            response: { status: number }
                        }
                        if (axiosError.response?.status === 404) {
                            setSessionError('404 - Session not found')
                        } else {
                            setSessionError('Failed to load session')
                        }
                    } else {
                        setSessionError('Failed to load session')
                    }
                    console.error('Error fetching session:', error)
                }
            } else {
                dispatch(setProjectId(null))
            }
        }

        fetchSession()

        return () => {
            if (timeoutId) {
                clearTimeout(timeoutId)
            }
        }
    }, [sessionId, dispatch])

    const isThinkingView = useMemo(() => {
        return (
            activeTab === TAB.BUILD && selectedBuildStep === BUILD_STEP.THINKING
        )
    }, [activeTab, selectedBuildStep])

    // Show error page if there's a session error
    if (sessionError) {
        return (
            <div className="flex h-screen items-center justify-center">
                <div className="text-center">
                    <h1 className="text-4xl font-semibold text-black dark:text-white mb-4">
                        {sessionError}
                    </h1>
                    <p className="text-lg text-gray-600 dark:text-gray-400 mb-6">
                        The session you&apos;re looking for doesn&apos;t exist
                        or has been deleted.
                    </p>
                    <button
                        onClick={() => navigate(-1)}
                        className="px-6 py-3 bg-firefly dark:bg-sky-blue text-sky-blue dark:text-black rounded-lg font-medium hover:opacity-80 transition-opacity"
                    >
                        Go Back
                    </button>
                </div>
            </div>
        )
    }

    return (
        <DesignModeProvider sessionId={sessionId}>
            <div className="flex h-screen">
                <SidebarProvider className="!w-auto flex-1 min-w-0">
                    <div className="flex-1 min-w-0 overflow-hidden">
                        <AgentHeader sessionData={sessionData} />
                        <Sidebar className="block md:hidden" />
                        <AgentTabMobile
                            isShowChat={isMobileChatVisible}
                            onToggleChat={(value) =>
                                dispatch(setIsMobileChatVisible(value))
                            }
                            activeChatOption={mobileChatTab}
                            onChatOptionChange={(option) =>
                                setMobileChatTab(option)
                            }
                            sessionId={sessionData?.id}
                            projectId={projectId ?? sessionData?.project_id}
                        />
                        <div className="flex flex-col md:flex-row !h-[calc(100vh-86px)] md:!h-[calc(100vh-53px)]">
                            <div
                                className={clsx(
                                    'flex-1 flex items-center justify-center',
                                    {
                                        hidden:
                                            !isThinkingView ||
                                            (isMobile && isMobileChatVisible)
                                    }
                                )}
                            >
                                {isRunning ? (
                                    <div className="flex flex-col items-center justify-center">
                                        <Lottie
                                            className="w-40"
                                            animationData={
                                                theme.theme === 'dark'
                                                    ? ThinkingDarkMode
                                                    : ThinkingLottie
                                            }
                                            loop={true}
                                        />
                                        <p className="text-[24px] md:text-[32px] pl-6 font-semibold  text-black dark:text-sky-blue">
                                            {t('chat.thinking')}
                                        </p>
                                    </div>
                                ) : (
                                    <div className="flex-1" />
                                )}
                            </div>
                            <div
                                className={clsx(
                                    'flex-1 flex flex-col h-full relative min-w-0 overflow-hidden',
                                    isThinkingView && 'hidden',
                                    isMobile &&
                                    isMobileChatVisible &&
                                    'hidden md:flex'
                                )}
                            >
                                <AgentTabs
                                    sessionId={sessionData?.id}
                                    projectId={
                                        projectId ?? sessionData?.project_id
                                    }
                                    agentType={sessionData?.agent_type}
                                />
                                <div className="flex-1 min-w-0 overflow-hidden">
                                    {!isMobile && (
                                        <div
                                            className={
                                                activeTab === TAB.BUILD
                                                    ? 'h-full'
                                                    : 'hidden h-full'
                                            }
                                        >
                                            <div
                                                className={`flex flex-col items-center justify-between px-3 pt-8 md:p-6 pb-8 h-full`}
                                            >
                                                <AgentSteps />
                                                <div
                                                    className={`flex flex-1 flex-col justify-between w-full ${selectedBuildStep === BUILD_STEP.PLAN ? '' : 'hidden'}`}
                                                >
                                                    <AgentTasks className="flex-1" />
                                                    <div />
                                                </div>
                                                <AgentBuild
                                                    className={
                                                        selectedBuildStep ===
                                                            BUILD_STEP.BUILD
                                                            ? ''
                                                            : 'hidden'
                                                    }
                                                />
                                            </div>
                                        </div>
                                    )}

                                    <div
                                        className={`h-full relative ${activeTab === TAB.RESULT ? '' : 'hidden'}`}
                                    >
                                        <AgentResult />
                                        <div className="absolute bottom-8 right-4">
                                            <AgentPopoverDone />
                                        </div>
                                    </div>
                                </div>
                                <div
                                    className={`h-full overflow-y-auto ${activeTab === TAB.PROJECT ? '' : 'hidden'}`}
                                >
                                    <div className="px-3 md:px-6 py-4 h-full">
                                        <ProjectPanel
                                            sessionId={sessionData?.id}
                                            projectId={
                                                projectId ??
                                                sessionData?.project_id
                                            }
                                            agentType={sessionData?.agent_type}
                                            visible={activeTab === TAB.PROJECT}
                                            className="h-full !mt-0"
                                        />
                                    </div>
                                </div>
                            </div>
                            {showPiP && (
                                <PiPPreview
                                    url={pipUrl}
                                    isMobile={hasMobileAppTools}
                                    onClose={() => setIsPiPDismissed(true)}
                                />
                            )}
                            <ChatBox
                                activeTab={mobileChatTab}
                                onTabChange={(tab) => setMobileChatTab(tab)}
                                isVisible={isChatBoxVisible}
                                className={`${isMobileChatVisible ? 'block' : 'hidden'} md:block md:flex-shrink-0`}
                                sessionData={sessionData}
                            />
                        </div>
                    </div>
                </SidebarProvider>
                <RightSidebar />
            </div>
        </DesignModeProvider>
    )
}

export function AgentPage() {
    return <AgentPageContent />
}

export const Component = AgentPage
