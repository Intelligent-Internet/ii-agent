import { useState, useCallback, useMemo } from 'react'
import isEmpty from 'lodash/isEmpty'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'

import SessionItem from './session-item'
import { Skeleton } from './ui/skeleton'
import {
    Collapsible,
    CollapsibleContent,
    CollapsibleTrigger
} from './ui/collapsible'
import {
    selectProjects,
    selectActiveSessionId,
    selectPinnedSessionIds,
    selectPinnedSessions,
    pinnedItemToSession,
    useAppSelector,
    useAppDispatch,
    bulkDeleteSessions
} from '@/state'
import { clearSessionState } from '@/state/slice/session-state'
import { removePin } from '@/state/slice/pins'
import { Icon } from './ui/icon'
import { Button } from './ui/button'
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
import {
    Tooltip,
    TooltipContent,
    TooltipTrigger
} from '@/components/ui/tooltip'
import { useSidebar } from '@/components/ui/sidebar'
import { hasSessionDisplayTitle } from '@/utils/session-title'

interface ProjectListProps {
    workspaceInfo?: string
    isLoading: boolean
    loadingMore: boolean
    hasMore: boolean
    onLoadMore: () => void
    handleResetState: () => void
    handleNewProject: () => void
}

const ProjectList = ({
    workspaceInfo,
    isLoading,
    loadingMore,
    hasMore,
    onLoadMore,
    handleResetState,
    handleNewProject
}: ProjectListProps) => {
    const { t } = useTranslation()
    const { isMobile, state } = useSidebar()
    const dispatch = useAppDispatch()
    const projects = useAppSelector(selectProjects)
    const activeSessionId = useAppSelector(selectActiveSessionId)
    const pinnedSessionIds = useAppSelector(selectPinnedSessionIds)
    const pinnedSessions = useAppSelector(selectPinnedSessions)

    const [isCollapsibleOpen, setIsCollapsibleOpen] = useState(true)
    const [showAllProjects, setShowAllProjects] = useState(false)
    const [selectionMode, setSelectionMode] = useState(false)
    const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
    const [isDeleteDialogOpen, setIsDeleteDialogOpen] = useState(false)
    const [isDeleting, setIsDeleting] = useState(false)

    const filteredProjects = useMemo(() => {
        const loaded = projects?.filter(hasSessionDisplayTitle) ?? []
        const loadedIds = new Set(loaded.map((s) => s.id))

        // Add pinned project sessions not yet loaded via pagination
        const missingPinned = pinnedSessions
            .filter(
                (p) =>
                    p.agent_type != null &&
                    p.agent_type !== 'chat' &&
                    p.session_name &&
                    !loadedIds.has(p.session_id)
            )
            .map(pinnedItemToSession)

        return [...missingPinned, ...loaded].sort((a, b) => {
            const aPinned = pinnedSessionIds.includes(a.id)
            const bPinned = pinnedSessionIds.includes(b.id)
            if (aPinned && !bPinned) return -1
            if (!aPinned && bPinned) return 1
            return 0
        })
    }, [projects, pinnedSessions, pinnedSessionIds])
    const hasMoreProjects = filteredProjects.length > 5
    const visibleProjects = showAllProjects
        ? filteredProjects
        : filteredProjects.slice(0, 5)

    const toggleSelectionMode = () => {
        if (selectionMode) {
            setSelectedIds(new Set())
        } else {
            // Auto-expand list so users can see all selectable items
            setShowAllProjects(true)
        }
        setSelectionMode(!selectionMode)
    }

    const handleSelectionChange = useCallback(
        (sessionId: string, selected: boolean) => {
            setSelectedIds((prev) => {
                const next = new Set(prev)
                if (selected) {
                    next.add(sessionId)
                } else {
                    next.delete(sessionId)
                }
                return next
            })
        },
        []
    )

    const handleSelectAll = () => {
        if (selectedIds.size === filteredProjects.length) {
            setSelectedIds(new Set())
        } else {
            setSelectedIds(new Set(filteredProjects.map((s) => s.id)))
        }
    }

    const handleBulkDelete = () => {
        if (selectedIds.size === 0) return
        setIsDeleteDialogOpen(true)
    }

    const confirmBulkDelete = async () => {
        setIsDeleting(true)
        try {
            const ids = Array.from(selectedIds)
            const result = await dispatch(bulkDeleteSessions(ids)).unwrap()

            for (const id of result.deleted_ids) {
                dispatch(clearSessionState(id))
                dispatch(removePin(id))
            }

            if (result.deleted_ids.length > 0) {
                toast.success(
                    t('sidebar.bulkDeleteSuccess', {
                        count: result.deleted_ids.length
                    })
                )
            }
            if (result.failed_ids.length > 0) {
                toast.error(
                    t('sidebar.bulkDeletePartialFailure', {
                        count: result.failed_ids.length
                    })
                )
            }

            setSelectedIds(new Set())
            setSelectionMode(false)
        } catch (error) {
            console.error('Failed to bulk delete projects:', error)
            toast.error(t('sidebar.bulkDeleteError'))
        } finally {
            setIsDeleting(false)
            setIsDeleteDialogOpen(false)
        }
    }

    return (
        <Collapsible
            open={isCollapsibleOpen}
            onOpenChange={setIsCollapsibleOpen}
        >
            <div className="flex items-center justify-between group-data-[collapsible=icon]:hidden">
                <CollapsibleTrigger className="flex-1">
                    <div className="w-full justify-start !text-[14px] rounded-xl cursor-pointer flex items-center gap-x-[6px]">
                        <span className="text-black/[0.56] dark:text-white/[0.56]">
                            {t('sidebar.projects')}
                        </span>
                        <Icon
                            name="arrow-down"
                            className={`size-[18px] fill-black/[0.56] dark:fill-white/[0.56] transition-transform duration-200 ${
                                isCollapsibleOpen ? 'rotate-180' : ''
                            }`}
                        />
                    </div>
                </CollapsibleTrigger>
                {isCollapsibleOpen && filteredProjects.length > 0 && (
                    <Tooltip>
                        <TooltipTrigger asChild>
                            <Button
                                variant="ghost"
                                size="sm"
                                className="!p-0 !h-auto z-10"
                                onClick={toggleSelectionMode}
                                aria-label={
                                    selectionMode
                                        ? t('common.cancel')
                                        : t('sidebar.selectProjects')
                                }
                            >
                                <Icon
                                    name={
                                        selectionMode
                                            ? 'close'
                                            : 'document-check'
                                    }
                                    className={`size-[18px] ${
                                        selectionMode
                                            ? 'fill-black dark:fill-white'
                                            : 'fill-black/[0.56] dark:fill-white/[0.56]'
                                    }`}
                                />
                            </Button>
                        </TooltipTrigger>
                        <TooltipContent side="bottom">
                            {selectionMode
                                ? t('common.cancel')
                                : t('sidebar.selectProjects')}
                        </TooltipContent>
                    </Tooltip>
                )}
            </div>
            <CollapsibleContent className="mt-3 group-data-[collapsible=icon]:mt-0">
                {!selectionMode && (
                    <Tooltip>
                        <TooltipTrigger asChild>
                            <Button
                                variant="secondary"
                                className="!px-0 text-sm !font-normal group-data-[collapsible=icon]:w-10 group-data-[collapsible=icon]:p-0 mb-2"
                                onClick={handleNewProject}
                                aria-label={t('project.newProject')}
                            >
                                <Icon
                                    name="folder-add"
                                    className="fill-black dark:fill-white size-5"
                                />
                                <span className="group-data-[collapsible=icon]:hidden">
                                    {t('project.newProject')}
                                </span>
                            </Button>
                        </TooltipTrigger>
                        <TooltipContent
                            side="right"
                            align="center"
                            hidden={state !== 'collapsed' || isMobile}
                        >
                            {t('project.newProject')}
                        </TooltipContent>
                    </Tooltip>
                )}
                {selectionMode && (
                    <div className="flex items-center gap-x-2 mb-2">
                        <Button
                            variant="ghost"
                            size="sm"
                            className="!px-0 !h-auto text-xs font-normal"
                            onClick={handleSelectAll}
                        >
                            {selectedIds.size === filteredProjects.length
                                ? t('sidebar.deselectAll')
                                : t('sidebar.selectAll')}
                        </Button>
                        {selectedIds.size > 0 && (
                            <Button
                                variant="ghost"
                                size="sm"
                                className="!px-0 !h-auto text-xs font-normal text-red-2"
                                onClick={handleBulkDelete}
                            >
                                <Icon
                                    name="trash"
                                    className="size-3.5 fill-red-2"
                                />
                                {t('sidebar.deleteSelected', {
                                    count: selectedIds.size
                                })}
                            </Button>
                        )}
                    </div>
                )}
                <div className="space-y-[6px] text-[14px] group-data-[collapsible=icon]:hidden">
                    {isLoading && isEmpty(projects) && (
                        <div className="px-2 space-y-4">
                            <Skeleton className="h-4 w-full !bg-black/10 dark:!bg-white/10" />
                            <Skeleton className="h-4 w-full !bg-black/10 dark:!bg-white/10" />
                            <Skeleton className="h-4 w-full !bg-black/10 dark:!bg-white/10" />
                        </div>
                    )}
                    {visibleProjects.map((session) => (
                        <SessionItem
                            key={session.id}
                            session={session}
                            isActive={
                                activeSessionId === session.id ||
                                (workspaceInfo?.includes(session.id) ?? false)
                            }
                            onClick={handleResetState}
                            selectionMode={selectionMode}
                            isSelected={selectedIds.has(session.id)}
                            onSelectionChange={handleSelectionChange}
                        />
                    ))}
                    {hasMoreProjects && !showAllProjects && !selectionMode && (
                        <Button
                            variant="ghost"
                            size="sm"
                            className="w-full justify-start !px-0 text-black dark:text-white font-normal"
                            onClick={() => setShowAllProjects(true)}
                        >
                            <Icon
                                name="more-2"
                                className="size-5 stroke-black dark:stroke-white"
                            />
                            {t('sidebar.seeMore')}
                        </Button>
                    )}
                    {loadingMore && (
                        <div className="text-center py-2 text-gray-500">
                            {t('common.loadingMore')}
                        </div>
                    )}
                    {!loadingMore && hasMore && showAllProjects && (
                        <Button
                            variant="ghost"
                            size="sm"
                            className="w-full justify-start !px-0 text-black dark:text-white font-normal"
                            onClick={onLoadMore}
                        >
                            <Icon
                                name="more-2"
                                className="size-5 stroke-black dark:stroke-white"
                            />
                            {t('sidebar.loadAll', 'Load all projects')}
                        </Button>
                    )}
                </div>
            </CollapsibleContent>
            <AlertDialog
                open={isDeleteDialogOpen}
                onOpenChange={setIsDeleteDialogOpen}
            >
                <AlertDialogContent>
                    <AlertDialogHeader>
                        <AlertDialogTitle>
                            {t('sidebar.bulkDeleteProjectsTitle')}
                        </AlertDialogTitle>
                        <AlertDialogDescription>
                            {t('sidebar.bulkDeleteProjectsConfirmation', {
                                count: selectedIds.size
                            })}
                        </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                        <AlertDialogCancel disabled={isDeleting}>
                            {t('common.cancel')}
                        </AlertDialogCancel>
                        <AlertDialogAction
                            onClick={confirmBulkDelete}
                            className="bg-red-2 hover:bg-red-2 text-white"
                            disabled={isDeleting}
                        >
                            {isDeleting
                                ? t('common.loading')
                                : t('common.delete')}
                        </AlertDialogAction>
                    </AlertDialogFooter>
                </AlertDialogContent>
            </AlertDialog>
        </Collapsible>
    )
}

export default ProjectList
