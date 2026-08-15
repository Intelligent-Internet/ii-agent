import { useTheme } from 'next-themes'
import {
    useCallback,
    useEffect,
    useMemo,
    useState,
    type KeyboardEvent as ReactKeyboardEvent
} from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate } from 'react-router'

import AgentSetting from '@/components/agent-setting'
import ChatHeader from '@/components/chat-header'
import GoogleDrivePicker from '@/components/google-drive-picker'
import HomeMobile from '@/components/home-mobile'
import LearnMore from '@/components/learn-more'
import { Logo } from '@/components/logo'
import PublicHomePage from '@/components/public-home-page'
import QuestionInput from '@/components/question-input'
import Sidebar from '@/components/sidebar'
import { Button } from '@/components/ui/button'
import { Icon } from '@/components/ui/icon'
import { SidebarProvider, SidebarTrigger } from '@/components/ui/sidebar'
import UserProfileDropdown from '@/components/user-profile-dropdown'
import { ENABLE_BETA } from '@/constants/features'
import { useAuth } from '@/contexts/auth-context'
import { useAppEventsContext } from '@/contexts/app-events-context'
import { useChat } from '@/hooks/use-chat-query'
import { useGitHub } from '@/hooks/use-github'
import { useGoogleDrive } from '@/hooks/use-google-drive'
import { useIsSageTheme } from '@/hooks/use-is-sage-theme'
import { useIsMobile } from '@/hooks/use-mobile'
import { useQuestionHandlers } from '@/hooks/use-question-handlers'
import { useSessionManager } from '@/hooks/use-session-manager'
import type { GitHubRepository } from '@/services/connector.service'
import {
    selectCurrentQuestion,
    selectQuestionMode,
    setCurrentQuestion,
    setQuestionMode,
    setSelectedGitHubRepository,
    useAppDispatch,
    useAppSelector
} from '@/state'
import { WebSocketConnectionState } from '@/typings'
import { QUESTION_MODE } from '@/typings/agent'

function HomePageContent() {
    const { t } = useTranslation()
    const dispatch = useAppDispatch()
    const { handleEvent } = useAppEventsContext()
    const { user, isLoading } = useAuth()
    const { theme, setTheme } = useTheme()
    const navigate = useNavigate()
    const [isOpenSetting, setIsOpenSetting] = useState(false)
    const isMobile = useIsMobile()
    const isSage = useIsSageTheme()

    const wsConnectionState = useAppSelector(
        (state) => state.agent.wsConnectionState
    )
    const questionMode = useAppSelector(selectQuestionMode)
    const isChatMode = questionMode === QUESTION_MODE.CHAT

    useEffect(() => {
        if (questionMode === QUESTION_MODE.COWORK) {
            dispatch(setQuestionMode(QUESTION_MODE.AGENT))
        }
    }, [dispatch, questionMode])

    const toggleTheme = () => {
        setTheme(theme === 'dark' ? 'light' : 'dark')
    }

    useSessionManager({
        handleEvent
    })

    const { handleEnhancePrompt, handleQuestionSubmit, handleKeyDown } =
        useQuestionHandlers()

    const {
        sessionId,
        sendMessage,
        isSubmitting,
        setSessionId,
        resetSubmitting,
        advancedModeSettings,
        setAdvancedModeSettings
    } = useChat()
    const [isStartingChat, setIsStartingChat] = useState(false)

    const {
        isConnected: isGoogleDriveConnected,
        isAuthLoading: isGoogleDriveAuthLoading,
        isPickerOpen,
        pickerConfig,
        handlePickerClose,
        handleGoogleDriveClick,
        handleFilesPicked,
        downloadedFiles: downloadedGoogleDriveFiles,
        clearDownloadedFiles
    } = useGoogleDrive()

    const [isConnectorDropdownOpen, setIsConnectorDropdownOpen] =
        useState(false)

    const { isConnected: isGitHubConnected, handleGitHubClick } = useGitHub({
        onConnectionSuccess: () => {
            // Auto-open dropdown after successful GitHub connection
            setIsConnectorDropdownOpen(true)
        }
    })

    const handleRepositorySelect = useCallback(
        (repository: GitHubRepository | undefined) => {
            dispatch(
                setSelectedGitHubRepository(
                    repository
                        ? {
                              owner: repository.owner,
                              name: repository.name,
                              full_name: repository.full_name,
                              default_branch: repository.default_branch
                          }
                        : undefined
                )
            )
        },
        [dispatch]
    )

    const handleChatModeSubmit = useCallback(
        (value: string) => {
            const trimmed = value.trim()
            if (!trimmed) return

            // Reset submitting state to allow new chat submission
            // This handles the case where user clicks "New chat" while a previous chat is still processing
            resetSubmitting()
            dispatch(setCurrentQuestion(''))
            setIsStartingChat(true)
            setSessionId(null)
            sendMessage(trimmed)
        },
        [
            dispatch,
            sendMessage,
            setSessionId,
            setIsStartingChat,
            resetSubmitting
        ]
    )

    const handleChatKeyDown = useCallback(
        (event: ReactKeyboardEvent<HTMLTextAreaElement>) => {
            if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault()
                handleChatModeSubmit(event.currentTarget.value)
            }
        },
        [handleChatModeSubmit]
    )

    const isInputDisabled = useMemo(() => {
        if (isChatMode) {
            return isSubmitting
        }
        return wsConnectionState !== WebSocketConnectionState.CONNECTED
    }, [isChatMode, isSubmitting, wsConnectionState])

    const currentQuestion = useAppSelector(selectCurrentQuestion)

    useEffect(() => {
        if (!isStartingChat || !sessionId) return

        navigate(`/chat?id=${sessionId}`)
        setIsStartingChat(false)
    }, [isStartingChat, navigate, sessionId])

    useEffect(() => {
        if (!isStartingChat) return
        if (isSubmitting) return
        if (sessionId) return

        setIsStartingChat(false)
    }, [isStartingChat, isSubmitting, sessionId])

    if (isLoading) return null

    if (!user) return <PublicHomePage />

    if (isMobile) {
        return (
            <SidebarProvider>
                <Sidebar />
                <HomeMobile
                    currentQuestion={currentQuestion}
                    onQuestionChange={(val) => {
                        dispatch(setCurrentQuestion(val))
                    }}
                    onKeyDown={isChatMode ? handleChatKeyDown : handleKeyDown}
                    onSubmit={(val) => {
                        if (isChatMode) {
                            handleChatModeSubmit(val)
                        } else {
                            handleQuestionSubmit(val, true)
                        }
                    }}
                    isInputDisabled={isInputDisabled}
                    onOpenSetting={() => setIsOpenSetting(true)}
                    handleEnhancePrompt={handleEnhancePrompt}
                    onGoogleDriveClick={handleGoogleDriveClick}
                    isGoogleDriveConnected={isGoogleDriveConnected}
                    isGoogleDriveAuthLoading={isGoogleDriveAuthLoading}
                    googleDriveFiles={downloadedGoogleDriveFiles}
                    onGoogleDriveFilesHandled={clearDownloadedFiles}
                    onGitHubConnect={handleGitHubClick}
                    isGitHubConnected={isGitHubConnected}
                    onRepositorySelect={handleRepositorySelect}
                    isConnectorDropdownOpen={isConnectorDropdownOpen}
                    onConnectorDropdownOpenChange={setIsConnectorDropdownOpen}
                />
                <AgentSetting
                    isOpen={isOpenSetting}
                    onOpenChange={setIsOpenSetting}
                />
                <GoogleDrivePicker
                    isOpen={isPickerOpen}
                    onClose={handlePickerClose}
                    onFilesPicked={handleFilesPicked}
                    config={pickerConfig}
                />
            </SidebarProvider>
        )
    }

    return (
        <>
            <div className="flex h-screen">
                <SidebarProvider>
                    <div>
                        <div className="absolute w-full top-1 left-0 md:hidden p-3 flex justify-between">
                            <div className="flex items-center gap-x-3">
                                <SidebarTrigger className="size-6 p-0" />
                                <Logo
                                    className="gap-x-[6px]"
                                    imageClassName="size-6 inline"
                                    label="II-Agent"
                                    labelClassName="text-black dark:text-white text-sm font-semibold"
                                    showBeta={ENABLE_BETA}
                                />
                            </div>
                            <div className="flex items-center gap-x-4">
                                <Button
                                    className="!p-0 size-6"
                                    onClick={toggleTheme}
                                >
                                    <Icon
                                        name={theme === 'dark' ? 'sun' : 'moon'}
                                        className="size-6 stroke-black dark:stroke-white"
                                    />
                                </Button>
                                <Link to="/settings/usage">
                                    <Icon
                                        name="coin"
                                        className="size-6 fill-firefly dark:fill-white"
                                    />
                                </Link>
                                <UserProfileDropdown avatarClassName="size-8" />
                            </div>
                        </div>
                        <Sidebar />
                        <div className="sidebar-home absolute z-20 ml-6 bottom-8 hidden md:block">
                            <SidebarTrigger className="size-6 p-0" />
                        </div>
                    </div>
                    <div id="home-container" className="flex flex-col w-full">
                        <ChatHeader
                            onOpenSetting={() => setIsOpenSetting(true)}
                        />
                        <div className="relative flex-1 py-12 px-3 md:px-10 lg:px-[126px] flex md:items-center justify-center">
                            <div className="w-full max-w-[888px]">
                                <div className='-mt-16 mb-16'>
                                    {isSage && (
                                        <img
                                            src="/images/sage-3d.svg"
                                            alt="SAGE"
                                            className="md:w-[160px] m-auto"
                                        />
                                    )}
                                    <div className="flex items-end gap-4">
                                        <div className="text-center md:text-left">
                                            <p className="text-[25px] md:text-[32px] font-semibold dark:text-white">
                                                {t('home.greeting')}
                                                {user?.first_name
                                                    ? `, ${user?.first_name}`
                                                    : ''}
                                                !
                                            </p>
                                            <p className="text-[20px] md:text-2xl dark:text-white">
                                                {t('home.whatCanIDo')}
                                            </p>
                                        </div>
                                        <LearnMore />
                                    </div>
                                </div>

                                <QuestionInput
                                    value={currentQuestion}
                                    setValue={(val) => {
                                        dispatch(setCurrentQuestion(val))
                                    }}
                                    handleKeyDown={
                                        isChatMode
                                            ? handleChatKeyDown
                                            : handleKeyDown
                                    }
                                    handleSubmit={(val: string) => {
                                        if (isChatMode) {
                                            handleChatModeSubmit(val)
                                        } else {
                                            handleQuestionSubmit(val, true)
                                        }
                                    }}
                                    isDisabled={isInputDisabled}
                                    textareaClassName="min-h-[150px] w-full !border"
                                    handleEnhancePrompt={handleEnhancePrompt}
                                    onGoogleDriveClick={handleGoogleDriveClick}
                                    isGoogleDriveConnected={
                                        isGoogleDriveConnected
                                    }
                                    isGoogleDriveAuthLoading={
                                        isGoogleDriveAuthLoading
                                    }
                                    googleDriveFiles={
                                        downloadedGoogleDriveFiles
                                    }
                                    onGoogleDriveFilesHandled={
                                        clearDownloadedFiles
                                    }
                                    onGitHubConnect={handleGitHubClick}
                                    isGitHubConnected={isGitHubConnected}
                                    onRepositorySelect={handleRepositorySelect}
                                    isConnectorDropdownOpen={
                                        isConnectorDropdownOpen
                                    }
                                    onConnectorDropdownOpenChange={
                                        setIsConnectorDropdownOpen
                                    }
                                    advancedModeSettings={advancedModeSettings}
                                    onAdvancedModeSettingsChange={
                                        setAdvancedModeSettings
                                    }
                                    hideBuildModeSelector={isChatMode}
                                />
                                <p className="hidden md:block absolute w-full text-center bottom-2 left-1/2 -translate-x-1/2 mt-6 text-[10px] leading-snug text-black dark:text-white">
                                    {t('home.disclaimer', {
                                        appName: isSage
                                            ? 'SAGE'
                                            : t('common.appName')
                                    })}
                                </p>
                            </div>
                        </div>
                    </div>
                </SidebarProvider>
            </div>
            <AgentSetting
                isOpen={isOpenSetting}
                onOpenChange={setIsOpenSetting}
            />

            <GoogleDrivePicker
                isOpen={isPickerOpen}
                onClose={handlePickerClose}
                onFilesPicked={handleFilesPicked}
                config={pickerConfig}
            />
        </>
    )
}

export function HomePage() {
    return <HomePageContent />
}

export const Component = HomePage
