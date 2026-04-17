import { useMemo, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router'
import { useTranslation } from 'react-i18next'

import { Icon } from '@/components/ui/icon'
import { SidebarTrigger } from '@/components/ui/sidebar'
import {
    selectIsFavorite,
    selectAvailableModels,
    selectSelectedChatModel,
    selectSelectedAgentModel,
    selectQuestionMode,
    toggleFavoriteAsync,
    useAppDispatch,
    useAppSelector
} from '@/state'
import { deleteSession } from '@/state/slice/sessions'
import { clearSessionState } from '@/state/slice/session-state'
import { setRunStatus } from '@/state/slice/agent'
import { type ISession } from '@/typings/agent'
import { QUESTION_MODE } from '@/typings'
import HeaderDropdownMenu from '@/components/header-dropdown-menu'
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
import SessionTitle from '@/components/session-title'
import { getSessionDisplayName } from '@/utils/session-title'

interface ChatHeaderMobileProps {
    sessionData?: ISession
    onOpenSetting?: () => void
}

const ChatHeaderMobile = ({
    sessionData,
    onOpenSetting
}: ChatHeaderMobileProps) => {
    const { t } = useTranslation()
    const navigate = useNavigate()
    const dispatch = useAppDispatch()
    const [searchParams] = useSearchParams()
    const selectedChatModel = useAppSelector(selectSelectedChatModel)
    const selectedAgentModel = useAppSelector(selectSelectedAgentModel)
    const questionMode = useAppSelector(selectQuestionMode)
    const availableModels = useAppSelector(selectAvailableModels)
    const sessionId = searchParams.get('id') || ''
    const isFavorite = useAppSelector(selectIsFavorite(sessionId || ''))
    const [isShareOpen, setIsShareOpen] = useState(false)
    const [isDeleteDialogOpen, setIsDeleteDialogOpen] = useState(false)

    const selectedModel = questionMode === QUESTION_MODE.CHAT
        ? selectedChatModel
        : selectedAgentModel

    const model = useMemo(
        () => availableModels.find((item) => item.id === selectedModel),
        [selectedModel, availableModels]
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

    const confirmDelete = async () => {
        try {
            await dispatch(deleteSession(sessionId)).unwrap()
            dispatch(clearSessionState(sessionId))
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
        <div className="px-3 pt-3">
            <div className="flex items-center justify-between">
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
                <div className="flex items-center gap-4">
                    {sessionData && (
                        <HeaderDropdownMenu
                            isFavorite={isFavorite}
                            onShare={handleShare}
                            onToggleFavorite={handleToggleFavorite}
                            onDelete={handleDelete}
                            session={sessionData}
                        />
                    )}
                    <button
                        type="button"
                        className=""
                        aria-label={t('tooltips.agentSettings')}
                        onClick={onOpenSetting}
                    >
                        <Icon name="setting-3" className="size-6" />
                    </button>
                </div>
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

export default ChatHeaderMobile
