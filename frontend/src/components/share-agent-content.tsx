import Lottie from 'lottie-react'
import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router'
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
import { sessionService } from '@/services/session.service'
import {
    selectActiveTab,
    selectSelectedBuildStep,
    selectVscodeUrl,
    selectIsSandboxIframeAwake,
    setSelectedFeature,
    useAppDispatch,
    useAppSelector,
    selectIsLoading,
    selectIsMobileChatVisible,
    setIsMobileChatVisible
} from '@/state'
import { BUILD_STEP, ISession, TAB } from '@/typings/agent'
import AgentResult from '@/components/agent/agent-result'
import AgentPopoverDone from '@/components/agent/agent-popover-done'
import { isE2bLink } from '@/lib/utils'
import { SidebarProvider } from '@/components/ui/sidebar'
import AgentTabMobile, {
    type ChatOption as MobileChatOption
} from '@/components/agent-tab-mobile'
import { useIsMobile } from '@/hooks/use-mobile'
import clsx from 'clsx'
import Sidebar from '@/components/sidebar'

export function ShareAgentContent() {
    const { sessionId } = useParams()
    const dispatch = useAppDispatch()
    const navigate = useNavigate()
    const theme = useTheme()

    const activeTab = useAppSelector(selectActiveTab)
    const vscodeUrl = useAppSelector(selectVscodeUrl)
    const selectedBuildStep = useAppSelector(selectSelectedBuildStep)
    const isSandboxIframeAwake = useAppSelector(selectIsSandboxIframeAwake)
    const [sessionData, setSessionData] = useState<ISession>()
    const [sessionError, setSessionError] = useState<string | null>(null)
    const [iframeKey, setIframeKey] = useState(0)
    const isRunning = useAppSelector(selectIsLoading)
    const isMobileChatVisible = useAppSelector(selectIsMobileChatVisible)
    const [mobileChatTab, setMobileChatTab] = useState<MobileChatOption>('chat')
    const isMobile = useIsMobile()

    const isChatBoxVisible = useMemo(
        () => !isMobile || (isMobile && isMobileChatVisible),
        [isMobile, isMobileChatVisible]
    )

    useEffect(() => {
        let timeoutId: NodeJS.Timeout | undefined

        const fetchSession = async () => {
            if (sessionId) {
                try {
                    const data =
                        await sessionService.getPublicSession(sessionId)

                    if (!data?.name || data.name.trim() === '') {
                        // Retry after 5 seconds if name is null or empty
                        timeoutId = setTimeout(() => {
                            fetchSession()
                        }, 5000)
                    } else {
                        // Normalize chat sessions to 'general' to prevent invalid agent_type
                        // (ShareAgentContent should not receive chat sessions, but be defensive)
                        const agentType = data.agent_type === 'chat' ? 'general' : data.agent_type
                        dispatch(setSelectedFeature(agentType))
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
            }
        }

        fetchSession()

        return () => {
            if (timeoutId) {
                clearTimeout(timeoutId)
            }
        }
    }, [sessionId, dispatch])

    useEffect(() => {
        if (isSandboxIframeAwake) {
            setIframeKey((prev) => prev + 1)
        }
    }, [isSandboxIframeAwake])

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
        <div className="flex h-screen">
            <SidebarProvider>
                <div className="flex-1">
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
                    />
                    <div className="flex flex-col md:flex-row !h-[calc(100vh-86px)] md:!h-[calc(100vh-53px)]">
                        <div
                            className={clsx(
                                'flex-1 flex items-center justify-center',
                                {
                                    hidden:
                                        !isThinkingView || isMobileChatVisible
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
                                    <p className="text-[32px] pl-6 font-semibold  text-black dark:text-sky-blue">
                                        {`I'm thinking...`}
                                    </p>
                                </div>
                            ) : (
                                <div className="flex-1" />
                            )}
                        </div>
                        <div
                            className={clsx(
                                'flex-1 flex flex-col h-full relative',
                                isThinkingView && 'hidden',
                                isMobileChatVisible && 'hidden md:flex'
                            )}
                        >
                            <AgentTabs />
                            <div className="flex-1">
                                <div
                                    className={
                                        activeTab === TAB.BUILD
                                            ? 'h-full'
                                            : 'hidden h-full'
                                    }
                                >
                                    <div
                                        className={`flex flex-col items-center justify-between p-6 pb-8 h-full`}
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

                                <div
                                    className={`h-full ${activeTab === TAB.CODE ? '' : 'hidden'}`}
                                >
                                    {vscodeUrl && isE2bLink(vscodeUrl) && (
                                        <iframe
                                            key={iframeKey}
                                            src={vscodeUrl}
                                            className="w-full h-full"
                                        />
                                    )}
                                </div>

                                <div
                                    className={`h-full relative ${activeTab === TAB.RESULT ? '' : 'hidden'}`}
                                >
                                    <AgentResult />
                                    <div className="absolute bottom-8 right-4">
                                        <AgentPopoverDone />
                                    </div>
                                </div>
                            </div>
                        </div>
                        <ChatBox
                            isShareMode={true}
                            activeTab={mobileChatTab}
                            onTabChange={(tab) => setMobileChatTab(tab)}
                            isVisible={isChatBoxVisible}
                            className={`${isMobileChatVisible ? 'block' : 'hidden'} md:block`}
                        />
                    </div>
                </div>
            </SidebarProvider>
            <RightSidebar />
        </div>
    )
}
