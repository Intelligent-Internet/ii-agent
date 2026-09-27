import { useMemo, useState } from 'react'
import {
    useLocation,
    useNavigate,
    useParams,
    useSearchParams
} from 'react-router'
import { useTranslation } from 'react-i18next'

import ButtonIcon from '@/components/button-icon'
import { Logo } from '@/components/logo'
import { Button } from '@/components/ui/button'
import { Icon } from '@/components/ui/icon'
import { ENABLE_BETA } from '@/constants/features'
import {
    selectIsFavorite,
    toggleFavoriteAsync,
    useAppDispatch,
    useAppSelector
} from '@/state'
import { deleteSession } from '@/state/slice/sessions'
import { clearSessionState } from '@/state/slice/session-state'
import { setRunStatus } from '@/state/slice/agent'
import { ISession } from '@/typings'
import {
    AlertDialog,
    AlertDialogAction,
    AlertDialogCancel,
    AlertDialogContent,
    AlertDialogDescription,
    AlertDialogFooter,
    AlertDialogHeader,
    AlertDialogTitle
} from './ui/alert-dialog'
import { SidebarTrigger } from './ui/sidebar'
import ShareConversation from './agent/share-conversation'
import HeaderDropdownMenu from './header-dropdown-menu'
import { useIsSageTheme } from '@/hooks/use-is-sage-theme'
import { useIsMobile } from '@/hooks/use-mobile'
import SessionTitle from './session-title'
import { getSessionDisplayName } from '@/utils/session-title'

interface AgentHeaderProps {
    sessionData?: ISession
    isChatPage?: boolean
}

const AgentHeader = ({ sessionData, isChatPage }: AgentHeaderProps) => {
    const { t } = useTranslation()
    const navigate = useNavigate()
    const dispatch = useAppDispatch()
    const { sessionId: sessionIdFromParams } = useParams()
    const [searchParams] = useSearchParams()
    const location = useLocation()
    const isSage = useIsSageTheme()
    const isMobile = useIsMobile()

    // Get session ID from either URL params or query parameter
    const sessionId = sessionIdFromParams || searchParams.get('id') || ''

    const isFavorite = useAppSelector(selectIsFavorite(sessionId || ''))
    const [isShareOpen, setIsShareOpen] = useState(false)
    const [isDeleteDialogOpen, setIsDeleteDialogOpen] = useState(false)

    const isShareMode = useMemo(
        () => location.pathname.includes('/share/'),
        [location.pathname]
    )

    const handleShare = () => {
        if (!sessionId) return
        setIsShareOpen(true)
    }

    const handleBack = () => {
        navigate('/')
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
            // Clear cached session state to free up localStorage
            dispatch(clearSessionState(sessionId))
            dispatch(setRunStatus(null))
            setIsDeleteDialogOpen(false)
            // Navigate to home page after deletion
            navigate('/')
        } catch (error) {
            console.error('Failed to delete session:', error)
        }
    }

    const cancelDelete = () => {
        setIsDeleteDialogOpen(false)
    }

    return (
        <div className="relative py-3 px-3 md:px-6 flex items-center gap-x-4 md:border-b border-neutral-200 dark:border-white/30">
            {isChatPage ? (
                <SidebarTrigger className="size-6 p-0" />
            ) : (
                <>
                    <SidebarTrigger className="block md:hidden size-6 p-0" />
                    <ButtonIcon
                        name="home"
                        className="bg-black hidden md:flex"
                        iconClassName="fill-sky-blue-2 dark:fill-black"
                        onClick={handleBack}
                    />
                </>
            )}
            {!isChatPage && (
                <Logo
                    className="hidden md:flex gap-x-[6px]"
                    imageClassName={`${isSage ? '!h-6 md:!h-6' : 'size-6'} inline`}
                    alt={t('publicHome.logoAlt')}
                    label={t('common.appName')}
                    labelClassName="text-black dark:text-white text-sm font-semibold"
                    showBeta={ENABLE_BETA}
                    betaLabel={t('common.beta')}
                />
            )}
            {sessionData && (
                <div className="flex-1 pr-3 md:pr-0 flex gap-x-4 items-center md:absolute md:left-1/2 md:-translate-x-1/2">
                    <div className="flex-1 flex items-center gap-x-2">
                        <div className="hidden border dark:border-white rounded-full size-6 md:flex items-center justify-center">
                            <Icon
                                name="lock"
                                className="fill-black dark:fill-white"
                            />
                        </div>
                        <span className="dark:text-white font-semibold text-sm flex-1 line-clamp-1 text-center">
                            <SessionTitle session={sessionData} />
                        </span>
                    </div>
                    {!isShareMode && (
                        <>
                            <Button
                                size="icon"
                                className="hidden md:inline w-auto"
                                onClick={handleShare}
                            >
                                <Icon
                                    name="share"
                                    className="stroke-black dark:stroke-white size-[18px]"
                                />
                            </Button>
                            <Button
                                size="icon"
                                className="hidden md:inline w-auto"
                                onClick={handleToggleFavorite}
                            >
                                {isFavorite ? (
                                    <Icon
                                        name="star-fill"
                                        className="fill-black dark:fill-white size-[18px]"
                                    />
                                ) : (
                                    <Icon
                                        name="star"
                                        className="fill-black dark:fill-white size-[18px]"
                                    />
                                )}
                            </Button>
                        </>
                    )}
                </div>
            )}
            {sessionData && isMobile && (
                <HeaderDropdownMenu
                    isFavorite={isFavorite}
                    onShare={handleShare}
                    onToggleFavorite={handleToggleFavorite}
                    onDelete={handleDelete}
                    session={sessionData}
                />
            )}
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

export default AgentHeader
