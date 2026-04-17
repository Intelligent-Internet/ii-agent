import { useRef, useState, useEffect, useMemo } from 'react'
import clsx from 'clsx'
import { toast } from 'sonner'

import { Button } from '../ui/button'
import { Icon } from '../ui/icon'
import ChatMessage from './chat-message'
import { useWebSocketContext } from '@/contexts/websocket-context'
import {
    selectActiveTab,
    selectBuildMode,
    selectEditingMessage,
    selectIsAgentInitialized,
    selectMessages,
    selectLastUserMessageContent,
    selectSelectedAgentModel,
    selectToolSettings,
    selectUploadedFiles,
    setBuildMode,
    setCancelling,
    setEditingMessage,
    setLoading,
    setMessages,
    setRunStatus,
    useAppDispatch,
    useAppSelector
} from '@/state'
import { setCurrentQuestion } from '@/state/slice/workspace'
import { BUILD_MODE, AGENT_TYPE, CommandType, ChatMessagePayload } from '@/typings/agent'
import { useSessionManager } from '@/hooks/use-session-manager'
import { useParams } from 'react-router'
import { useAppEventsContext } from '@/contexts/app-events-context'
import { useQuestionHandlers } from '@/hooks/use-question-handlers'
import AgentFiles from './agent-files'
import { useIsMobile } from '@/hooks/use-mobile'
import { DesignPanel, useDesignModeContext } from '@/components/design-mode'
import { useTranslation } from 'react-i18next'
import type { ISession } from '@/typings/agent'
import { SyncConfirmDialog } from '@/components/design-mode/sync-confirm-dialog'
import {
    AlertDialog,
    AlertDialogAction,
    AlertDialogCancel,
    AlertDialogContent,
    AlertDialogDescription,
    AlertDialogTitle
} from '@/components/ui/alert-dialog'
import {
    Popover,
    PopoverContent,
    PopoverTrigger
} from '@/components/ui/popover'
import type { DesignChange } from '@/components/design-mode/types'
import { buildDesignChangeKeyWithTimestamp } from '@/components/design-mode/change-keys'

type ChatTab = 'chat' | 'design' | 'files'

interface ChatBoxProps {
    isShareMode?: boolean
    className?: string
    activeTab?: ChatTab
    onTabChange?: (tab: ChatTab) => void
    isVisible?: boolean
    style?: React.CSSProperties
    sessionData?: ISession
}

const ChatBox = ({
    isShareMode = false,
    className = '',
    activeTab,
    onTabChange,
    isVisible = true,
    style,
    sessionData
}: ChatBoxProps) => {
    const { t, i18n } = useTranslation()
    const dispatch = useAppDispatch()
    const { sessionId } = useParams()

    const messagesEndRef = useRef<HTMLDivElement>(null)
    const { handleEvent, handleClickAction } = useAppEventsContext()

    const { isReplayMode, processAllEventsImmediately, isLoadingSession } =
        useSessionManager({
            handleEvent
        })

    // Session management handled by websocket context

    const { socket, connectSocket, sendMessage } = useWebSocketContext()

    const {
        handleEnhancePrompt,
        handleQuestionSubmit,
        handleKeyDown,
        handleBuildMilestone,
        handleBuildAllMilestones,
        handleModifyPlan,
        handleSubmitPlanModification
    } = useQuestionHandlers()

    const uploadedFiles = useAppSelector(selectUploadedFiles)
    const editingMessage = useAppSelector(selectEditingMessage)
    // Keep selectMessages for handleEditMessage which needs to slice the array
    const messages = useAppSelector(selectMessages)
    // Use memoized selector for review - only re-renders when last user message changes
    const lastUserMessageContent = useAppSelector(selectLastUserMessageContent)
    const toolSettings = useAppSelector(selectToolSettings)
    const isAgentInitialized = useAppSelector(selectIsAgentInitialized)
    const selectedModel = useAppSelector(selectSelectedAgentModel)
    const buildMode = useAppSelector(selectBuildMode)
    const activeAgentTab = useAppSelector(selectActiveTab)
    const {
        enable: enableDesignMode,
        disable: disableDesignMode,
        isEnabled: isDesignModeEnabled,
        isSaving: isDesignModeSaving,
        pendingChanges,
        redoChanges,
        saveChanges,
        highlightElement,
        revertChange,
        undoLastChange,
        redoLastChange,
        isMultiSelectMode,
        multiSelectedElements,
        toggleMultiSelectMode,
        deleteSelectedElements,
        registerChangesPanelHandler,
        isInteractMode,
        toggleInteractMode
    } = useDesignModeContext()

    // State to control changes popover
    const [isChangesPopoverOpen, setIsChangesPopoverOpen] = useState(false)
    const [isConfirmSyncOpen, setIsConfirmSyncOpen] = useState(false)
    const [isDeleteConfirmOpen, setIsDeleteConfirmOpen] = useState(false)
    const [changesToSync, setChangesToSync] = useState<DesignChange[] | null>(
        null
    )
    const [selectedChangeKeys, setSelectedChangeKeys] = useState<Set<string>>(
        () => new Set()
    )

    const pendingChangesCount = pendingChanges.length

    const multiSelectedCount = multiSelectedElements.length

    useEffect(() => {
        if (isDesignModeSaving) {
            setIsConfirmSyncOpen(false)
            setChangesToSync(null)
        }
    }, [isDesignModeSaving])

    useEffect(() => {
        if (!isDesignModeEnabled) {
            setIsChangesPopoverOpen(false)
            setIsConfirmSyncOpen(false)
            setChangesToSync(null)
        }
    }, [isDesignModeEnabled])

    useEffect(() => {
        if (
            isDeleteConfirmOpen &&
            (!isMultiSelectMode || multiSelectedCount === 0)
        ) {
            setIsDeleteConfirmOpen(false)
        }
    }, [isDeleteConfirmOpen, isMultiSelectMode, multiSelectedCount])

    // Register the changes panel handler (opens the changes popover)
    useEffect(() => {
        registerChangesPanelHandler(() =>
            setIsChangesPopoverOpen((prev) => !prev)
        )
    }, [registerChangesPanelHandler])

    const [internalActiveTab, setInternalActiveTab] = useState<ChatTab>('chat')
    const isMobile = useIsMobile()
    const prevBuildModeRef = useRef<BUILD_MODE>(buildMode)
    const onTabChangeRef = useRef(onTabChange)
    const didApplyReloadResetRef = useRef(false)

    // Only show Design tab when build mode is set to DESIGN
    const showDesignTab = buildMode === BUILD_MODE.DESIGN

    // Check if this is a nano banana slide session
    const isNanoBanana =
        sessionData?.agent_type === AGENT_TYPE.SLIDE_NANO_BANANA

    useEffect(() => {
        if (activeTab !== undefined) {
            setInternalActiveTab(activeTab)
        }
    }, [activeTab])

    useEffect(() => {
        onTabChangeRef.current = onTabChange
    }, [onTabChange])

    const currentActiveTab = useMemo(
        () => activeTab ?? internalActiveTab,
        [activeTab, internalActiveTab]
    )

    useEffect(() => {
        if (didApplyReloadResetRef.current) return
        didApplyReloadResetRef.current = true

        let isReload = false
        try {
            const entries = performance.getEntriesByType?.('navigation') as
                | PerformanceNavigationTiming[]
                | undefined
            const entry = entries?.[0]
            if (entry?.type === 'reload') {
                isReload = true
            } else if (
                typeof (
                    performance as unknown as {
                        navigation?: { type?: number }
                    }
                ).navigation?.type === 'number'
            ) {
                // Deprecated but still useful fallback (1 = reload)
                isReload =
                    (
                        performance as unknown as {
                            navigation: { type: number }
                        }
                    ).navigation.type === 1
            }
        } catch {
            // ignore
        }

        if (!isReload) return

        dispatch(setBuildMode(BUILD_MODE.BUILD))
        setInternalActiveTab('chat')
        onTabChangeRef.current?.('chat')
    }, [dispatch])

    // Auto-switch to design tab and enable design mode when build mode changes to DESIGN
    // Auto-switch to chat tab and disable design mode when build mode changes away from DESIGN
    useEffect(() => {
        const prevBuildMode = prevBuildModeRef.current

        if (
            buildMode === BUILD_MODE.DESIGN &&
            prevBuildMode !== BUILD_MODE.DESIGN
        ) {
            // Switched TO design mode - auto-switch tab and enable design mode
            setInternalActiveTab('design')
            onTabChange?.('design')
            enableDesignMode()
        } else if (
            buildMode !== BUILD_MODE.DESIGN &&
            prevBuildMode === BUILD_MODE.DESIGN
        ) {
            // Switched AWAY from design mode - auto-switch tab and disable design mode
            setInternalActiveTab('chat')
            onTabChange?.('chat')
            disableDesignMode()
        }

        prevBuildModeRef.current = buildMode
    }, [buildMode, onTabChange, enableDesignMode, disableDesignMode])

    const handleTabChange = (tab: ChatTab) => {
        if (currentActiveTab !== tab) {
            setInternalActiveTab(tab)
        }
        onTabChange?.(tab)

        // If switching away from design tab and currently in design mode, exit design mode
        if (tab !== 'design' && buildMode === BUILD_MODE.DESIGN) {
            dispatch(setBuildMode(BUILD_MODE.BUILD))
            disableDesignMode()
        }
    }

    const relativeTimeFormatter = useMemo(() => {
        try {
            return new Intl.RelativeTimeFormat(i18n.language, {
                numeric: 'auto'
            })
        } catch {
            return new Intl.RelativeTimeFormat('en', { numeric: 'auto' })
        }
    }, [i18n.language])

    const formatTimeAgo = (timestamp: number) => {
        const diffSeconds = Math.max(
            0,
            Math.floor((Date.now() - timestamp) / 1000)
        )
        if (diffSeconds < 60) {
            return relativeTimeFormatter.format(-diffSeconds, 'second')
        }
        const diffMinutes = Math.floor(diffSeconds / 60)
        if (diffMinutes < 60) {
            return relativeTimeFormatter.format(-diffMinutes, 'minute')
        }
        const diffHours = Math.floor(diffMinutes / 60)
        if (diffHours < 24) {
            return relativeTimeFormatter.format(-diffHours, 'hour')
        }
        const diffDays = Math.floor(diffHours / 24)
        if (diffDays < 7) {
            return relativeTimeFormatter.format(-diffDays, 'day')
        }
        const diffWeeks = Math.floor(diffDays / 7)
        if (diffWeeks < 4) {
            return relativeTimeFormatter.format(-diffWeeks, 'week')
        }
        const diffMonths = Math.floor(diffDays / 30)
        if (diffMonths < 12) {
            return relativeTimeFormatter.format(-diffMonths, 'month')
        }
        const diffYears = Math.floor(diffDays / 365)
        return relativeTimeFormatter.format(-diffYears, 'year')
    }

    const handleCancelQuery = () => {
        if (!socket || !socket.connected) {
            toast.error(t('agent.chatBox.errors.socketNotOpen'))
            return
        }

        // Send cancel message to the server
        sendMessage({
            session_uuid: sessionId || '',
            content: { command: CommandType.CANCEL }
        })
        // Set cancelling state - will be cleared when AGENT_RESPONSE_INTERRUPTED is received
        dispatch(setCancelling(true))
    }

    const handleEditMessage = (newQuestion: string) => {
        if (!socket || !socket.connected) {
            toast.error(t('agent.chatBox.errors.socketNotOpenRetry'))
            dispatch(setLoading(false))
            return
        }

        // TODO: edit_query is not yet a registered BE command
        sendMessage({
            session_uuid: sessionId || '',
            content: {
                command: CommandType.QUERY,
                text: newQuestion,
                files: uploadedFiles?.map((file) => `.${file}`) ?? []
            }
        })

        // Update the edited message and remove all subsequent messages
        const editIndex = messages.findIndex((m) => m.id === editingMessage?.id)

        if (editIndex >= 0) {
            const updatedMessages = [...messages.slice(0, editIndex + 1)]
            updatedMessages[editIndex] = {
                ...updatedMessages[editIndex],
                content: newQuestion
            }
            dispatch(setMessages(updatedMessages))
        }

        dispatch(setRunStatus('running'))
        dispatch(setCancelling(false))
        dispatch(setLoading(true))
        dispatch(setEditingMessage(undefined))
    }

    const handleReviewResult = () => {
        if (!socket || !socket.connected) {
            toast.error(t('agent.chatBox.errors.socketNotOpenRetry'))
            dispatch(setLoading(false))
            return
        }
        const { thinking_tokens, ...tool_args } = toolSettings

        dispatch(setLoading(true))

        // Only send init_agent event if agent is not already initialized
        if (!isAgentInitialized) {
            sendMessage({
                session_uuid: sessionId || '',
                content: {
                    command: CommandType.INIT_AGENT,
                    model_name: selectedModel,
                    tool_args,
                    thinking_tokens
                } as ChatMessagePayload['content']
            })
        }

        // TODO: review_result is not yet a registered BE command — send as query
        sendMessage({
            session_uuid: sessionId || '',
            content: {
                command: CommandType.QUERY,
                text: lastUserMessageContent
            }
        })
    }

    useEffect(() => {
        if (!isMobile || !isVisible || currentActiveTab !== 'chat') {
            return
        }
        window.requestAnimationFrame(() => {
            messagesEndRef.current?.scrollIntoView({
                behavior: 'smooth'
            })
        })
    }, [currentActiveTab, isVisible, isMobile])

    const showDesignModeActionBar = showDesignTab && !isShareMode
    const unsavedChangesLabel =
        pendingChangesCount === 0
            ? t('designMode.toolbar.unsavedChangeZero')
            : t('designMode.toolbar.unsavedChanges', {
                count: pendingChangesCount
            })

    const sortedPendingChangeEntries = useMemo(() => {
        return [...pendingChanges]
            .map((change) => ({
                change,
                key: buildDesignChangeKeyWithTimestamp(change)
            }))
            .sort((a, b) => b.change.timestamp - a.change.timestamp)
    }, [pendingChanges])

    const allPendingChangeKeys = useMemo(
        () => sortedPendingChangeEntries.map((entry) => entry.key),
        [sortedPendingChangeEntries]
    )

    const allPendingChangeKeySet = useMemo(() => {
        return new Set(allPendingChangeKeys)
    }, [allPendingChangeKeys])

    const areAllChangesSelected = useMemo(() => {
        if (allPendingChangeKeys.length === 0) return false
        if (selectedChangeKeys.size !== allPendingChangeKeys.length)
            return false
        for (const key of allPendingChangeKeys) {
            if (!selectedChangeKeys.has(key)) return false
        }
        return true
    }, [allPendingChangeKeys, selectedChangeKeys])

    const selectedChanges = useMemo(() => {
        if (selectedChangeKeys.size === 0) return []
        return sortedPendingChangeEntries
            .filter((entry) => selectedChangeKeys.has(entry.key))
            .map((entry) => entry.change)
    }, [selectedChangeKeys, sortedPendingChangeEntries])

    const selectedChangesCount = selectedChanges.length

    const popoverWasOpenRef = useRef(false)
    useEffect(() => {
        if (isChangesPopoverOpen && !popoverWasOpenRef.current) {
            setSelectedChangeKeys(new Set(allPendingChangeKeys))
        }
        popoverWasOpenRef.current = isChangesPopoverOpen
    }, [isChangesPopoverOpen, allPendingChangeKeys])

    const previousAllKeysRef = useRef<Set<string>>(new Set())
    useEffect(() => {
        setSelectedChangeKeys((prev) => {
            const previousAllKeys = previousAllKeysRef.current
            const previousAllSelected =
                previousAllKeys.size > 0 &&
                prev.size === previousAllKeys.size &&
                Array.from(previousAllKeys).every((key) => prev.has(key))

            const next = new Set<string>()
            for (const key of prev) {
                if (allPendingChangeKeySet.has(key)) {
                    next.add(key)
                }
            }
            if (previousAllSelected) {
                for (const key of allPendingChangeKeySet) {
                    next.add(key)
                }
            }
            return next
        })

        previousAllKeysRef.current = allPendingChangeKeySet
    }, [allPendingChangeKeySet])

    const formatPropertyLabel = (prop: string) =>
        prop.replace(/-/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())

    const formatValue = (value: string | null) => {
        if (value === null) return '(none)'
        if (!value) return '(empty)'
        if (value.length > 26) return value.slice(0, 26) + '…'
        return value
    }

    const getChangeSummary = (change: DesignChange) => {
        const elementLabel = change.designId.replace('design-', '').slice(0, 8)
        const isMove = change.type === 'move'
        const isIcon = change.type === 'attribute' && change.property === 'icon'
        const isDelete = change.type === 'delete'

        const formatIconName = (raw: string | null) => {
            if (!raw) return '(none)'
            try {
                const parsed = JSON.parse(raw) as { name?: unknown }
                if (
                    parsed &&
                    typeof parsed.name === 'string' &&
                    parsed.name.trim()
                ) {
                    return parsed.name.trim()
                }
            } catch {
                // ignore
            }
            return formatValue(raw)
        }

        const formatMoveAnchor = (anchor: string | null) => {
            if (!anchor) return '(none)'
            if (anchor === 'only') return '(only)'
            if (anchor.startsWith('before:')) {
                const target = anchor.slice('before:'.length)
                return `before #${target.replace('design-', '').slice(0, 8)}`
            }
            if (anchor.startsWith('after:')) {
                const target = anchor.slice('after:'.length)
                return `after #${target.replace('design-', '').slice(0, 8)}`
            }
            return formatValue(anchor)
        }

        const label =
            typeof change.groupLabel === 'string' && change.groupLabel.trim()
                ? change.groupLabel.trim()
                : isDelete
                    ? t('designMode.toolbar.delete')
                    : isMove
                        ? 'Move'
                        : isIcon
                            ? 'Icon'
                            : formatPropertyLabel(change.property)

        const valueSummary = isDelete
            ? ''
            : isMove
                ? `${formatMoveAnchor(change.value.from)} → ${formatMoveAnchor(
                    change.value.to
                )}`
                : isIcon
                    ? `${formatIconName(change.value.from)} → ${formatIconName(
                        change.value.to
                    )}`
                    : `${formatValue(change.value.from)} → ${formatValue(
                        change.value.to
                    )}`

        return {
            elementLabel,
            label,
            valueSummary
        }
    }

    const designModeActionBar = showDesignModeActionBar ? (
        <div
            data-design-mode-preserve-selection
            className="hidden md:flex w-full items-center justify-between gap-4 pl-2 pr-4 pt-[6px] pb-[6px] overflow-hidden border-y border-white/30 bg-[#181e1c]"
        >
            <div className="flex items-center gap-1">
                <button
                    type="button"
                    onClick={toggleInteractMode}
                    disabled={!isDesignModeEnabled}
                    className={clsx(
                        'group flex h-7 w-7 items-center justify-center rounded-full border transition-all duration-200',
                        'hover:scale-[1.02] active:scale-[0.98]',
                        !isDesignModeEnabled &&
                        'opacity-40 cursor-not-allowed hover:scale-100 active:scale-100',
                        isInteractMode
                            ? 'border-[#A6FFFF]/25 bg-[#A6FFFF]/10 text-[#A6FFFF]'
                            : 'border-transparent bg-[#A6FFFF]/10 text-[#A6FFFF] hover:bg-[#A6FFFF]/15'
                    )}
                    title={
                        isInteractMode
                            ? t('designMode.toolbar.selectMode')
                            : t('designMode.toolbar.interactMode')
                    }
                >
                    <Icon
                        name="cursor-pointer"
                        className="size-5 text-[#A6FFFF]"
                    />
                </button>
                <button
                    type="button"
                    onClick={toggleMultiSelectMode}
                    disabled={!isDesignModeEnabled}
                    className={clsx(
                        'group flex items-center justify-center rounded-full border transition-all duration-200',
                        'hover:scale-[1.02] active:scale-[0.98]',
                        isMultiSelectMode
                            ? 'h-7 min-w-[99px] px-3 gap-2'
                            : 'h-7 w-7',
                        !isDesignModeEnabled &&
                        'opacity-40 cursor-not-allowed hover:scale-100 active:scale-100',
                        isMultiSelectMode
                            ? 'border-[#A6FFFF]/25 bg-[#A6FFFF]/10 text-[#A6FFFF]'
                            : 'border-transparent bg-[#A6FFFF]/10 text-[#A6FFFF] hover:bg-[#A6FFFF]/15'
                    )}
                    title={
                        isMultiSelectMode
                            ? t('designMode.toolbar.exitMultiSelect')
                            : t('designMode.toolbar.multiSelectDelete')
                    }
                >
                    <Icon
                        name="cursor-magic-selection"
                        className={clsx(
                            'size-5 transition-colors',
                            isMultiSelectMode
                                ? 'text-[#A6FFFF]'
                                : 'text-[#A6FFFF]'
                        )}
                    />
                    {isMultiSelectMode && (
                        <span className="text-xs font-bold">
                            {t('designMode.toolbar.selected', {
                                count: multiSelectedCount
                            })}
                        </span>
                    )}
                </button>

                {isMultiSelectMode && multiSelectedCount > 0 && (
                    <button
                        type="button"
                        onClick={() => setIsDeleteConfirmOpen(true)}
                        className={clsx(
                            'group flex h-7 w-7 items-center justify-center rounded-full',
                            'transition-all duration-200 hover:bg-[#FF6B75]/10 hover:scale-[1.02] active:scale-[0.98]'
                        )}
                        title={t('designMode.toolbar.deleteSelected')}
                    >
                        <Icon
                            name="trash-selected"
                            className="size-5 fill-current text-[#FF6B75]"
                        />
                    </button>
                )}
            </div>

            <div className="flex items-center gap-2">
                <Popover
                    open={isChangesPopoverOpen}
                    onOpenChange={(open) => {
                        if (!isDesignModeEnabled) return
                        setIsChangesPopoverOpen(open)
                    }}
                >
                    <PopoverTrigger asChild>
                        <Button
                            data-design-mode-preserve-selection
                            variant="ghost"
                            size="sm"
                            disabled={!isDesignModeEnabled}
                            className={clsx(
                                'h-7 rounded-full border px-4 text-xs font-bold transition-colors whitespace-nowrap',
                                'py-1.5 gap-2.5',
                                pendingChangesCount > 0
                                    ? 'min-w-[147px] bg-white text-[#212121] border-white/10 hover:bg-white/95'
                                    : 'min-w-[135px] bg-white/10 text-white/30 border-white/10 hover:bg-white/15'
                            )}
                            title={t('designMode.toolbar.changes')}
                        >
                            {unsavedChangesLabel}
                        </Button>
                    </PopoverTrigger>
                    <PopoverContent
                        data-design-mode-preserve-selection
                        align="end"
                        side="bottom"
                        sideOffset={10}
                        className="w-80 overflow-hidden rounded-[12px] border-0 bg-white dark:bg-white p-0 text-black dark:text-black shadow-[0px_4px_24px_rgba(0,0,0,0.16)]"
                    >
                        <div className="flex items-center justify-between px-4 py-3">
                            <div className="flex items-center gap-2">
                                <Icon
                                    name="collections-bookmark"
                                    className="size-5 fill-[#141B34]"
                                />
                                <span className="text-sm font-bold text-gray-900">
                                    {t('designMode.toolbar.changesUnsaved', {
                                        count: pendingChangesCount
                                    })}
                                </span>
                            </div>
                            <button
                                type="button"
                                className={clsx(
                                    'group flex h-8 w-8 items-center justify-center rounded-lg transition-all duration-200',
                                    'hover:bg-gray-50 hover:scale-[1.02] active:scale-[0.98]',
                                    areAllChangesSelected
                                        ? 'text-gray-900'
                                        : 'text-gray-400 hover:text-gray-600'
                                )}
                                onClick={() => {
                                    setSelectedChangeKeys(
                                        areAllChangesSelected
                                            ? new Set()
                                            : new Set(allPendingChangeKeys)
                                    )
                                }}
                                title={t(
                                    areAllChangesSelected
                                        ? 'designMode.toolbar.deselectAll'
                                        : 'designMode.toolbar.selectAll'
                                )}
                            >
                                <Icon
                                    name="select-all"
                                    className="size-5 text-current transition-transform duration-200 group-active:scale-95"
                                />
                            </button>
                        </div>

                        <div className="max-h-80 overflow-y-auto bg-white no-scrollbar">
                            {sortedPendingChangeEntries.length === 0 ? (
                                <div className="px-4 py-6 text-center text-sm text-gray-400">
                                    {t('designMode.toolbar.noUnsaved')}
                                </div>
                            ) : (
                                <div className="divide-y divide-gray-100">
                                    {sortedPendingChangeEntries.map((entry) => {
                                        const change = entry.change
                                        const isSelected =
                                            selectedChangeKeys.has(entry.key)
                                        const summary = getChangeSummary(change)
                                        const idLabel = `#${summary.elementLabel}`
                                        const valueSummary =
                                            summary.valueSummary || ''

                                        return (
                                            <button
                                                key={entry.key}
                                                type="button"
                                                className={clsx(
                                                    'flex w-full items-start gap-3 bg-white px-4 py-3 text-left transition-colors hover:bg-gray-50'
                                                )}
                                                onClick={() => {
                                                    highlightElement(
                                                        change.designId
                                                    )
                                                    setSelectedChangeKeys(
                                                        (prev) => {
                                                            const next =
                                                                new Set(prev)
                                                            if (
                                                                next.has(
                                                                    entry.key
                                                                )
                                                            ) {
                                                                next.delete(
                                                                    entry.key
                                                                )
                                                            } else {
                                                                next.add(
                                                                    entry.key
                                                                )
                                                            }
                                                            return next
                                                        }
                                                    )
                                                }}
                                            >
                                                <div className="flex h-5 w-5 flex-shrink-0 items-center justify-center">
                                                    <svg
                                                        className={clsx(
                                                            'h-5 w-5 text-gray-900 transition-opacity duration-200',
                                                            isSelected
                                                                ? 'opacity-100'
                                                                : 'opacity-0'
                                                        )}
                                                        fill="none"
                                                        viewBox="0 0 24 24"
                                                        stroke="currentColor"
                                                        strokeWidth={1.5}
                                                    >
                                                        <path
                                                            strokeLinecap="round"
                                                            strokeLinejoin="round"
                                                            d="M5 13l4 4L19 7"
                                                        />
                                                    </svg>
                                                </div>
                                                <div className="min-w-0 flex-1">
                                                    <div className="inline-flex items-center rounded-full bg-[#BEE6F0] px-2 py-0.5 text-[11px] font-bold text-[#212121]">
                                                        {idLabel}
                                                    </div>
                                                    <div className="mt-1 truncate text-sm font-normal text-gray-900">
                                                        {summary.label}
                                                    </div>
                                                    {valueSummary && (
                                                        <div className="mt-0.5 text-xs text-gray-500 break-words">
                                                            {valueSummary}
                                                        </div>
                                                    )}
                                                    <div className="mt-1 text-xs text-gray-400">
                                                        {formatTimeAgo(
                                                            change.timestamp
                                                        )}
                                                    </div>
                                                </div>
                                            </button>
                                        )
                                    })}
                                </div>
                            )}
                        </div>

                        <div className="flex items-center gap-2 border-t border-gray-100 px-4 py-3">
                            <button
                                type="button"
                                disabled={
                                    !isDesignModeEnabled ||
                                    selectedChangesCount === 0 ||
                                    isDesignModeSaving
                                }
                                onClick={() => {
                                    setIsChangesPopoverOpen(false)
                                    setChangesToSync(selectedChanges)
                                    setIsConfirmSyncOpen(true)
                                }}
                                className={clsx(
                                    'h-9 flex-1 rounded-lg bg-[#BEE6F0] text-sm font-bold text-[#212121]',
                                    'transition hover:brightness-95 disabled:opacity-50'
                                )}
                            >
                                {isDesignModeSaving
                                    ? t('designMode.toolbar.syncing')
                                    : t('common.save')}
                            </button>
                            <button
                                type="button"
                                disabled={selectedChangesCount === 0}
                                onClick={() => {
                                    selectedChanges.forEach((c) => {
                                        revertChange(c)
                                    })
                                    setSelectedChangeKeys(new Set())
                                    setIsChangesPopoverOpen(false)
                                }}
                                className={clsx(
                                    'h-9 flex-1 rounded-lg text-sm font-normal text-[#F54260]',
                                    'transition hover:bg-black/5 disabled:opacity-40'
                                )}
                            >
                                {t('common.clear')}
                            </button>
                        </div>
                    </PopoverContent>
                </Popover>
                <Button
                    variant="ghost"
                    size="icon"
                    disabled={
                        !isDesignModeEnabled ||
                        pendingChangesCount === 0 ||
                        isDesignModeSaving
                    }
                    onClick={undoLastChange}
                    className="h-8 w-8 hover:bg-white/10 disabled:opacity-20"
                    title={t('designMode.toolbar.undo')}
                >
                    <Icon name="undo" className="size-6" />
                </Button>
                <Button
                    variant="ghost"
                    size="icon"
                    disabled={
                        !isDesignModeEnabled ||
                        redoChanges.length === 0 ||
                        isDesignModeSaving
                    }
                    onClick={redoLastChange}
                    className="h-8 w-8 hover:bg-white/10 disabled:opacity-20"
                    title={t('designMode.toolbar.redo')}
                >
                    <Icon name="redo" className="size-6" />
                </Button>
            </div>
        </div>
    ) : null

    return (
        <div
            className={clsx(
                'relative h-full w-full overflow-hidden md:border-l pt-4 md:pt-0 md:border-neutral-200 md:dark:border-white/30',
                (buildMode === BUILD_MODE.DESIGN && currentActiveTab === 'design') || (isNanoBanana && currentActiveTab === 'design')
                    ? 'md:!flex md:!flex-col'
                    : '',
                activeAgentTab === 'project'
                    ? 'md:w-[350px]'
                    : isNanoBanana && currentActiveTab === 'design'
                        ? 'md:w-[380px]'
                        : buildMode === BUILD_MODE.DESIGN &&
                            currentActiveTab === 'design'
                            ? 'md:w-[480px]'
                            : 'md:w-[600px]',
                className
            )}
            style={style}
        >
            <SyncConfirmDialog
                open={isConfirmSyncOpen}
                onOpenChange={(open) => {
                    setIsConfirmSyncOpen(open)
                    if (!open) setChangesToSync(null)
                }}
                pendingChangesCount={
                    changesToSync ? changesToSync.length : pendingChangesCount
                }
                onConfirm={() => {
                    const toSync = changesToSync
                    setChangesToSync(null)
                    if (toSync) {
                        saveChanges(toSync)
                        return
                    }
                    saveChanges()
                }}
            />
            <AlertDialog
                open={isDeleteConfirmOpen}
                onOpenChange={setIsDeleteConfirmOpen}
            >
                <AlertDialogContent
                    data-design-mode-preserve-selection
                    className="w-[640px] h-[232px] max-w-[calc(100%-2rem)] rounded-[12px] p-0 border-0 bg-white shadow-[0px_4px_24px_rgba(255,255,255,0.16)]"
                >
                    <div className="relative flex h-full flex-col px-6 py-6 text-black">
                        <button
                            type="button"
                            onClick={() => setIsDeleteConfirmOpen(false)}
                            className={clsx(
                                'absolute right-6 top-6 flex h-6 w-6 items-center justify-center transition',
                                'text-black hover:opacity-70 active:scale-95'
                            )}
                            aria-label={t('common.close')}
                        >
                            <Icon name="close-2" className="size-6" />
                        </button>

                        <AlertDialogTitle className="pr-10 text-[18px] leading-6 font-bold text-[#1B1B1B]">
                            {t('designMode.deleteDialog.title')}
                        </AlertDialogTitle>

                        <div className="mt-6 flex h-[70px] items-start gap-3 rounded-[12px] border-2 border-sky-blue bg-[#FFDE8A]/30 px-4 py-4">
                            <Icon
                                name="danger"
                                className="mt-0.5 size-6 text-[#292D32]"
                            />
                            <AlertDialogDescription className="text-sm leading-[19px] text-black">
                                {t('designMode.deleteDialog.warning')}
                            </AlertDialogDescription>
                        </div>

                        <div className="mt-auto flex items-center gap-2">
                            <AlertDialogAction
                                className={clsx(
                                    'h-[42px] w-[75px] rounded-lg bg-[#FF6B75] text-white font-bold',
                                    'transition hover:brightness-95'
                                )}
                                onClick={() => {
                                    setIsDeleteConfirmOpen(false)
                                    deleteSelectedElements()
                                }}
                            >
                                {t('designMode.toolbar.delete')}
                            </AlertDialogAction>
                            <AlertDialogCancel
                                className={clsx(
                                    'h-[42px] w-[114px] rounded-lg border-transparent bg-transparent px-0 text-[#181E1C] font-bold',
                                    'transition hover:bg-black/5 hover:text-[#181E1C]'
                                )}
                            >
                                {t('common.keepEditing')}
                            </AlertDialogCancel>
                        </div>
                    </div>
                </AlertDialogContent>
            </AlertDialog>
            {isLoadingSession && (
                <div className="absolute inset-0 z-20 flex items-center justify-center bg-white/85 dark:bg-charcoal/85">
                    <div className="flex flex-col items-center gap-3 text-firefly dark:text-white">
                        <Icon
                            name="loading"
                            className="size-10 animate-spin fill-firefly dark:fill-white"
                        />
                        <span className="text-sm font-medium uppercase tracking-wide">
                            {t('agent.chatBox.loadingSession')}
                        </span>
                    </div>
                </div>
            )}
            <div className="hidden md:flex gap-x-2 items-center p-4">
                <Button
                    className={clsx(
                        'h-7 text-xs font-semibold px-4 rounded-full border border-sky-blue',
                        {
                            'bg-firefly border-firefly dark:border-sky-blue-2 dark:bg-sky-blue text-sky-blue-2 dark:text-black':
                                currentActiveTab === 'chat',
                            'dark:border-sky-blue border-firefly dark:text-sky-blue':
                                currentActiveTab !== 'chat'
                        }
                    )}
                    onClick={() => handleTabChange('chat')}
                >
                    {t('agentTab.options.chat')}
                </Button>
                {showDesignTab && (
                    <Button
                        className={clsx(
                            'h-7 text-xs font-semibold px-4 rounded-full border border-sky-blue',
                            {
                                'bg-firefly border-firefly dark:border-sky-blue-2 dark:bg-sky-blue text-sky-blue-2 dark:text-black':
                                    currentActiveTab === 'design',
                                'dark:border-sky-blue border-firefly dark:text-sky-blue':
                                    currentActiveTab !== 'design'
                            }
                        )}
                        onClick={() => handleTabChange('design')}
                    >
                        {isNanoBanana
                            ? t('agentTab.options.liveEdit', 'Live edit')
                            : t('agentTab.options.design')}
                    </Button>
                )}
                <Button
                    className={clsx(
                        'h-7 text-xs font-semibold px-4 rounded-full border border-sky-blue',
                        {
                            'bg-firefly border-firefly dark:border-sky-blue-2 dark:bg-sky-blue text-sky-blue-2 dark:text-black':
                                currentActiveTab === 'files',
                            'dark:border-sky-blue border-firefly dark:text-sky-blue':
                                currentActiveTab !== 'files'
                        }
                    )}
                    onClick={() => handleTabChange('files')}
                >
                    {t('agentTab.options.files')}
                </Button>
            </div>
            {buildMode !== BUILD_MODE.DESIGN && !isNanoBanana && designModeActionBar}
            <div
                className={clsx(
                    'h-[calc(100vh-116px)]',
                    showDesignModeActionBar
                        ? 'md:h-[calc(100vh-201px)]'
                        : 'md:h-[calc(100vh-145px)]',
                    {
                        hidden: currentActiveTab !== 'chat'
                    }
                )}
            >
                <ChatMessage
                    forkInfo={sessionData?.metadata?.fork_info}
                    sessionId={sessionId}
                    llmSettingId={sessionData?.llm_setting_id}
                    agentType={sessionData?.agent_type}
                    isForkedSession={!!sessionData?.metadata?.fork_info}
                    handleClickAction={handleClickAction}
                    isReplayMode={isReplayMode}
                    messagesEndRef={messagesEndRef}
                    setCurrentQuestion={(value) =>
                        dispatch(setCurrentQuestion(value))
                    }
                    handleKeyDown={handleKeyDown}
                    handleQuestionSubmit={handleQuestionSubmit}
                    handleEnhancePrompt={handleEnhancePrompt}
                    handleCancel={handleCancelQuery}
                    handleEditMessage={handleEditMessage}
                    processAllEventsImmediately={processAllEventsImmediately}
                    connectWebSocket={connectSocket}
                    handleReviewSession={handleReviewResult}
                    isShareMode={isShareMode}
                    handleBuildMilestone={handleBuildMilestone}
                    handleBuildAllMilestones={handleBuildAllMilestones}
                    handleModifyPlan={handleModifyPlan}
                    handleSubmitPlanModification={handleSubmitPlanModification}
                />
            </div>
            <div
                className={clsx(
                    'h-[calc(100vh-116px)] overflow-y-auto overflow-x-hidden',
                    showDesignModeActionBar
                        ? 'md:h-[calc(100vh-201px)]'
                        : 'md:h-[calc(100vh-145px)]',
                    {
                        hidden: currentActiveTab !== 'files'
                    }
                )}
            >
                <AgentFiles
                    isActive={currentActiveTab === 'files'}
                    sessionId={sessionId}
                />
            </div>
            {buildMode === BUILD_MODE.DESIGN &&
                currentActiveTab === 'design' ? (
                isNanoBanana ? (
                    <div className="flex flex-1 min-h-0 flex-col">
                        <div
                            id="nano-banana-inspector-root"
                            className="flex-1 min-h-0 overflow-hidden"
                        />
                    </div>
                ) : (
                    <div className="flex flex-1 min-h-0 flex-col">
                        {designModeActionBar}
                        <div className="flex-1 min-h-0 overflow-hidden">
                            <DesignPanel />
                        </div>
                    </div>
                )
            ) : (
                <div
                    className={clsx(
                        'h-[calc(100vh-116px)] overflow-hidden',
                        showDesignModeActionBar
                            ? 'md:h-[calc(100vh-201px)]'
                            : 'md:h-[calc(100vh-145px)]',
                        {
                            hidden: currentActiveTab !== 'design'
                        }
                    )}
                >
                    {isNanoBanana ? (
                        <div
                            id="nano-banana-inspector-root"
                            className="h-full"
                        />
                    ) : (
                        <DesignPanel />
                    )}
                </div>
            )}
        </div>
    )
}

export default ChatBox
