import { useMemo, useState } from 'react'
import { useAppDispatch, useAppSelector } from '@/state/store'
import { useTranslation } from 'react-i18next'
import { Icon } from '@/components/ui/icon'
import {
    Tooltip,
    TooltipContent,
    TooltipTrigger
} from '@/components/ui/tooltip'
import { ISession, QUESTION_MODE, TAB } from '@/typings/agent'
import {
    selectAvailableModels,
    selectIsFavorite,
    selectSelectedChatModel,
    toggleFavoriteAsync,
    setMessages,
    setActiveTab,
    setIsMobileChatVisible,
    setShouldFocusInput,
    setRequireClearFiles,
    setChatMediaPreference,
    setQuestionMode,
    selectQuestionMode,
    selectChatMediaPreference
} from '@/state'
import HeaderDropdownMenu from './header-dropdown-menu'
import { useSearchParams } from 'react-router'
import { useNavigate } from 'react-router'
import { deleteSession } from '@/state/slice/sessions'
import { clearSessionState } from '@/state/slice/session-state'
import { setRunStatus } from '@/state/slice/agent'
import ShareConversation from '@/components/agent/share-conversation'
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
import { SidebarTrigger } from './ui/sidebar'
import { useIsMobile } from '@/hooks/use-mobile'
import { Button } from './ui/button'
import { useSessionStateManager } from '@/hooks/use-session-state-manager'
import { getDefaultChatMediaPreference } from '@/utils/default-models'
import SwitchLanguage from './switch-language'
import { useMediaModels } from '@/hooks/use-media-models'
import { useChat } from '@/hooks/use-chat-query'
import SessionTitle from './session-title'
import { getSessionDisplayName } from '@/utils/session-title'

interface ChatHeaderProps {
    sessionData?: ISession
    onOpenSetting?: () => void
    className?: string
}

const ChatHeader = ({
    sessionData,
    onOpenSetting,
    className = ''
}: ChatHeaderProps) => {
    const { t } = useTranslation()
    const navigate = useNavigate()
    const dispatch = useAppDispatch()
    const [searchParams] = useSearchParams()
    const isMobile = useIsMobile()
    const sessionId = searchParams.get('id') || ''

    const selectedChatModel = useAppSelector(selectSelectedChatModel)
    const availableModels = useAppSelector(selectAvailableModels)
    const isFavorite = useAppSelector(selectIsFavorite(sessionId || ''))
    const questionMode = useAppSelector(selectQuestionMode)
    const chatMediaPreference = useAppSelector(selectChatMediaPreference)

    const [isShareOpen, setIsShareOpen] = useState(false)
    const [isDeleteDialogOpen, setIsDeleteDialogOpen] = useState(false)
    const { resetSessionState } = useSessionStateManager()
    const { resetConversationState, setSessionId } = useChat()
    const { imageModels, videoModels } = useMediaModels()

    const model = useMemo(
        () => availableModels.find((m) => m.id === selectedChatModel),
        [selectedChatModel, availableModels]
    )

    const handleShare = () => {
        if (!sessionId) return
        setIsShareOpen(true)
    }

    const handleToggleFavorite = () => {
        if (sessionId) {
            dispatch(toggleFavoriteAsync(sessionId))
        }
    }

    const handleDelete = () => {
        setIsDeleteDialogOpen(true)
    }

    const handleNewChat = () => {
        resetSessionState()
        resetConversationState()
        setSessionId(null)
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
    }

    const confirmDelete = async () => {
        try {
            await dispatch(deleteSession(sessionId)).unwrap()
            dispatch(clearSessionState(sessionId))
            resetSessionState()
            resetConversationState()
            setSessionId(null)
            dispatch(setRunStatus(null))
            setIsDeleteDialogOpen(false)
            navigate('/')
        } catch (error) {
            console.error('Failed to delete session:', error)
        }
    }

    const cancelDelete = () => {
        setIsDeleteDialogOpen(false)
    }

    return (
        <div
            className={`flex items-center justify-between w-full gap-x-2 pt-3 md:pt-6 px-3 md:px-6 ${className}`}
        >
            {isMobile ? (
                <div className="flex items-center gap-3">
                    <SidebarTrigger className="size-6 p-0" />
                    <div className="leading-tight">
                        <p className="text-lg line-clamp-1">
                            <SessionTitle
                                session={sessionData}
                                dotClassName="size-[5px]"
                            />
                        </p>
                        <p className="text-[10px] leading-tight">
                            {model?.model}
                        </p>
                    </div>
                </div>
            ) : (
                <div className="leading-tight">
                    <p className="text-[10px]">{t('home.thinkingWith')}</p>
                    <p className="text-lg leading-tight">
                        {model?.model?.split('@')[0]}
                    </p>
                </div>
            )}
            <div className="flex gap-4">
                {sessionData && (
                    <>
                        {!isMobile && (
                            <Button
                                variant="outline"
                                className="h-8 border border-black dark:border-sky-blue-2 text-black dark:text-sky-blue-2 rounded-full px-3 py-[6px]"
                                onClick={handleNewChat}
                            >
                                <Icon
                                    name="plus"
                                    className="size-5 fill-black dark:fill-sky-blue-2"
                                />
                                {t('sidebar.newChat')}
                            </Button>
                        )}

                        <HeaderDropdownMenu
                            isFavorite={isFavorite}
                            onShare={handleShare}
                            onToggleFavorite={handleToggleFavorite}
                            onDelete={handleDelete}
                            session={sessionData}
                        />
                    </>
                )}
                <SwitchLanguage />
                <Tooltip>
                    <TooltipTrigger asChild>
                        <button
                            type="button"
                            className="cursor-pointer"
                            aria-label={t('tooltips.agentSettings')}
                            onClick={onOpenSetting}
                        >
                            <Icon name="setting-3" className="size-6" />
                        </button>
                    </TooltipTrigger>
                    <TooltipContent>
                        {questionMode === QUESTION_MODE.AGENT
                            ? t('agent.settings')
                            : t('agent.chatSettings')}
                    </TooltipContent>
                </Tooltip>
            </div>
            <ShareConversation
                open={isShareOpen}
                onOpenChange={setIsShareOpen}
                sessionId={sessionId}
                sessionData={sessionData}
            />
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
                            {t('dashboard.deleteConfirmationNamed', {
                                sessionName: getSessionDisplayName(
                                    sessionData,
                                    t('common.untitled')
                                )
                            })}
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

export default ChatHeader
