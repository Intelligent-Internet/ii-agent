import ButtonIcon from '@/components/button-icon'
import { Pencil, Plus, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
    Popover,
    PopoverContent,
    PopoverTrigger
} from '@/components/ui/popover'
import {
    COWORK_HOME_LABEL,
    getCoworkModeLabel,
    type CoworkModeId
} from './cowork.constants'
import type { CoworkChatSessionSummary } from '@/typings/cowork'

interface CoworkTabsProps {
    activeMode: CoworkModeId | null
    onOpenSidebar: () => void
    onGoHomepage: () => void
    onOpenModeFirstPage: () => void
    isChatSessionsBoardOpen: boolean
    onChatSessionsBoardOpenChange: (open: boolean) => void
    chatSessions: CoworkChatSessionSummary[]
    activeChatSessionId: string | null
    isChatSessionsLoading: boolean
    onNewChatSession: () => void
    onSelectChatSession: (sessionId: string) => void
    onRenameChatSession: (sessionId: string) => void
    onDeleteChatSession: (sessionId: string) => void
    isSessionsBoardOpen: boolean
    onSessionsBoardOpenChange: (open: boolean) => void
    modeSessions: CoworkChatSessionSummary[]
    activeModeSessionId: string | null
    isModeSessionsLoading: boolean
    onSelectSession: (sessionId: string) => void
    onRenameSession: (sessionId: string) => void
    onDeleteSession: (sessionId: string) => void
}

const getSessionPreviewLabel = (preview: string) => {
    const trimmedPreview = preview.trim()

    if (!trimmedPreview.startsWith('Source:')) {
        return trimmedPreview
    }

    const normalizedPath = trimmedPreview
        .slice('Source:'.length)
        .trim()
        .replace(/[\\/]+$/, '')

    if (!normalizedPath) {
        return trimmedPreview
    }

    const folderName = normalizedPath
        .split(/[\\/]/)
        .filter(Boolean)
        .at(-1)

    return `Source: ${folderName || normalizedPath}`
}

const CoworkTabs = ({
    activeMode,
    onOpenSidebar,
    onGoHomepage,
    onOpenModeFirstPage,
    isChatSessionsBoardOpen,
    onChatSessionsBoardOpenChange,
    chatSessions,
    activeChatSessionId,
    isChatSessionsLoading,
    onNewChatSession,
    onSelectChatSession,
    onRenameChatSession,
    onDeleteChatSession,
    isSessionsBoardOpen,
    onSessionsBoardOpenChange,
    modeSessions,
    activeModeSessionId,
    isModeSessionsLoading,
    onSelectSession,
    onRenameSession,
    onDeleteSession
}: CoworkTabsProps) => {
    const currentLabel = activeMode ? getCoworkModeLabel(activeMode) : null

    return (
        <div className="border-b border-neutral-200 dark:border-white/20">
            <div className="flex items-center justify-between gap-3 px-3 py-4 md:px-6">
                <div className="flex items-center gap-2">
                    <ButtonIcon
                        name="sidebar-open"
                        className="bg-black size-8"
                        iconClassName="fill-sky-blue-2 dark:fill-black"
                        onClick={onOpenSidebar}
                    />
                    <Button
                        type="button"
                        variant="outline"
                        className="h-8 rounded-full border-firefly px-4 text-xs font-semibold dark:border-sky-blue"
                        onClick={onGoHomepage}
                    >
                        {COWORK_HOME_LABEL}
                    </Button>
                    {currentLabel && (
                        <Button
                            type="button"
                            className="inline-flex h-8 shrink-0 items-center justify-center rounded-full border border-firefly bg-firefly px-4 text-xs font-semibold text-sky-blue-2 hover:bg-firefly/90 dark:border-sky-blue-2 dark:bg-sky-blue dark:text-black dark:hover:bg-sky-blue/90"
                            onClick={onOpenModeFirstPage}
                        >
                            {currentLabel}
                        </Button>
                    )}
                </div>
                {activeMode === null && (
                    <Popover
                        open={isChatSessionsBoardOpen}
                        onOpenChange={onChatSessionsBoardOpenChange}
                    >
                        <PopoverTrigger asChild>
                            <Button
                                type="button"
                                variant="outline"
                                className={`h-8 rounded-full border px-4 text-xs font-semibold transition-colors ${
                                    isChatSessionsBoardOpen
                                        ? 'border-firefly bg-firefly text-sky-blue-2 dark:border-sky-blue dark:bg-sky-blue dark:text-black'
                                        : 'border-firefly text-firefly hover:bg-firefly/5 dark:border-sky-blue dark:text-sky-blue dark:hover:bg-sky-blue/10'
                                }`}
                            >
                                Chat Sessions
                            </Button>
                        </PopoverTrigger>
                        <PopoverContent
                            instant
                            align="end"
                            side="bottom"
                            sideOffset={8}
                            className="w-[240px] overflow-hidden rounded-[24px] border border-neutral-200 bg-white p-0 shadow-[0_24px_64px_-32px_rgba(0,0,0,0.45)] dark:border-white/20 dark:bg-[#141918]"
                        >
                            <div className="border-b border-neutral-200 px-4 py-4 dark:border-white/10">
                                <p className="text-xs font-semibold uppercase tracking-[0.2em] text-black/50 dark:text-white/50">
                                    Chat Sessions
                                </p>
                            </div>
                            <div className="max-h-[320px] overflow-y-auto p-3">
                                <Button
                                    type="button"
                                    variant="outline"
                                    className="mb-3 h-11 w-full justify-start rounded-2xl border-firefly px-4 text-sm font-semibold text-firefly transition-colors hover:bg-firefly/5 dark:border-sky-blue dark:text-sky-blue dark:hover:bg-sky-blue/10"
                                    onClick={onNewChatSession}
                                >
                                    <Plus className="size-4" />
                                    New chat
                                </Button>
                                {isChatSessionsLoading ? (
                                    <div className="rounded-2xl border border-black/10 px-4 py-4 text-sm text-black/55 dark:border-white/10 dark:text-white/55">
                                        Loading chat sessions...
                                    </div>
                                ) : chatSessions.length > 0 ? (
                                    chatSessions.map((session) => (
                                        <div
                                            key={session.id}
                                            role="button"
                                            tabIndex={0}
                                            className={`group relative mb-2 h-auto w-full cursor-pointer rounded-2xl border px-4 py-3 text-left transition-colors last:mb-0 ${
                                                activeChatSessionId === session.id
                                                    ? 'border-firefly bg-firefly/8 dark:border-sky-blue dark:bg-sky-blue/10'
                                                    : 'border-black/20 hover:border-firefly/40 hover:bg-firefly/5 dark:border-white/20 dark:hover:border-sky-blue/40 dark:hover:bg-sky-blue/10'
                                            }`}
                                            onClick={() =>
                                                onSelectChatSession(session.id)
                                            }
                                            onKeyDown={(event) => {
                                                if (
                                                    event.key === 'Enter' ||
                                                    event.key === ' '
                                                ) {
                                                    event.preventDefault()
                                                    onSelectChatSession(
                                                        session.id
                                                    )
                                                }
                                            }}
                                        >
                                            <div className="min-w-0">
                                                <p className="truncate text-sm font-semibold text-black dark:text-white">
                                                    {session.title}
                                                </p>
                                                <p className="mt-1 truncate text-xs text-black/50 dark:text-white/50">
                                                    {session.preview}
                                                </p>
                                            </div>
                                            <div className="pointer-events-none absolute right-2 top-2 z-10 flex translate-y-1 items-center gap-2 rounded-full bg-white/90 px-1.5 py-1 opacity-0 shadow-sm backdrop-blur-sm transition-all duration-150 group-hover:pointer-events-auto group-hover:translate-y-0 group-hover:opacity-100 dark:bg-[#141918]/90">
                                                <Button
                                                    type="button"
                                                    variant="outline"
                                                    className="h-8 cursor-pointer rounded-full border-black/10 bg-transparent px-2.5 text-black/65 shadow-none hover:border-firefly/40 hover:bg-firefly/5 dark:border-white/10 dark:text-white/65 dark:hover:border-sky-blue/40 dark:hover:bg-sky-blue/10"
                                                    onClick={(event) => {
                                                        event.stopPropagation()
                                                        onRenameChatSession(
                                                            session.id
                                                        )
                                                    }}
                                                    aria-label={`Rename ${session.title}`}
                                                >
                                                    <Pencil className="size-3.5" />
                                                </Button>
                                                <Button
                                                    type="button"
                                                    variant="outline"
                                                    className="h-8 cursor-pointer rounded-full border-red-500/20 bg-transparent px-2.5 text-red-600 shadow-none hover:bg-red-500/8 dark:text-red-300"
                                                    onClick={(event) => {
                                                        event.stopPropagation()
                                                        onDeleteChatSession(
                                                            session.id
                                                        )
                                                    }}
                                                    aria-label={`Delete ${session.title}`}
                                                >
                                                    <Trash2 className="size-3.5" />
                                                </Button>
                                            </div>
                                        </div>
                                    ))
                                ) : (
                                    <div className="rounded-2xl border border-black/10 px-4 py-4 text-sm text-black/55 dark:border-white/10 dark:text-white/55">
                                        No chat sessions yet.
                                    </div>
                                )}
                            </div>
                        </PopoverContent>
                    </Popover>
                )}
                {activeMode === 'intelligent-folder' && (
                    <div className="flex items-center gap-2">
                        <Popover
                            open={isSessionsBoardOpen}
                            onOpenChange={onSessionsBoardOpenChange}
                        >
                            <PopoverTrigger asChild>
                                <Button
                                    type="button"
                                    variant="outline"
                                    className={`h-8 rounded-full border px-4 text-xs font-semibold transition-colors ${
                                        isSessionsBoardOpen
                                            ? 'border-firefly bg-firefly text-sky-blue-2 dark:border-sky-blue dark:bg-sky-blue dark:text-black'
                                            : 'border-firefly text-firefly hover:bg-firefly/5 dark:border-sky-blue dark:text-sky-blue dark:hover:bg-sky-blue/10'
                                    }`}
                                >
                                    Sessions
                                </Button>
                            </PopoverTrigger>
                            <PopoverContent
                                instant
                                align="end"
                                side="bottom"
                                sideOffset={8}
                                className="w-[240px] overflow-hidden rounded-[24px] border border-neutral-200 bg-white p-0 shadow-[0_24px_64px_-32px_rgba(0,0,0,0.45)] dark:border-white/20 dark:bg-[#141918]"
                            >
                                <div className="border-b border-neutral-200 px-4 py-4 dark:border-white/10">
                                    <p className="text-xs font-semibold uppercase tracking-[0.2em] text-black/50 dark:text-white/50">
                                        Sessions
                                    </p>
                                </div>
                                <div className="max-h-[320px] overflow-y-auto p-3">
                                    {isModeSessionsLoading ? (
                                        <div className="rounded-2xl border border-black/10 px-4 py-4 text-sm text-black/55 dark:border-white/10 dark:text-white/55">
                                            Loading mode sessions...
                                        </div>
                                    ) : modeSessions.length > 0 ? (
                                        modeSessions.map((session) => (
                                            <div
                                                key={session.id}
                                                role="button"
                                                tabIndex={0}
                                                className={`group relative mb-2 h-auto w-full cursor-pointer rounded-2xl border px-4 py-3 text-left transition-colors last:mb-0 ${
                                                    activeModeSessionId ===
                                                    session.id
                                                        ? 'border-firefly bg-firefly/8 dark:border-sky-blue dark:bg-sky-blue/10'
                                                        : 'border-black/20 hover:border-firefly/40 hover:bg-firefly/5 dark:border-white/20 dark:hover:border-sky-blue/40 dark:hover:bg-sky-blue/10'
                                                }`}
                                                onClick={() =>
                                                    onSelectSession(session.id)
                                                }
                                                onKeyDown={(event) => {
                                                    if (
                                                        event.key === 'Enter' ||
                                                        event.key === ' '
                                                    ) {
                                                        event.preventDefault()
                                                        onSelectSession(
                                                            session.id
                                                        )
                                                    }
                                                }}
                                            >
                                                <div className="min-w-0">
                                                    <p className="truncate text-sm font-semibold text-black dark:text-white">
                                                        {session.title}
                                                    </p>
                                                    <p className="mt-1 text-xs text-black/50 dark:text-white/50">
                                                        {getSessionPreviewLabel(
                                                            session.preview
                                                        )}
                                                    </p>
                                                </div>
                                                <div className="pointer-events-none absolute right-2 top-2 z-10 flex translate-y-1 items-center gap-2 rounded-full bg-white/90 px-1.5 py-1 opacity-0 shadow-sm backdrop-blur-sm transition-all duration-150 group-hover:pointer-events-auto group-hover:translate-y-0 group-hover:opacity-100 dark:bg-[#141918]/90">
                                                    <Button
                                                        type="button"
                                                        variant="outline"
                                                        className="h-8 cursor-pointer rounded-full border-black/10 bg-transparent px-2.5 text-black/65 shadow-none hover:border-firefly/40 hover:bg-firefly/5 dark:border-white/10 dark:text-white/65 dark:hover:border-sky-blue/40 dark:hover:bg-sky-blue/10"
                                                        onClick={(event) => {
                                                            event.stopPropagation()
                                                            onRenameSession(session.id)
                                                        }}
                                                        aria-label={`Rename ${session.title}`}
                                                    >
                                                        <Pencil className="size-3.5" />
                                                    </Button>
                                                    <Button
                                                        type="button"
                                                        variant="outline"
                                                        className="h-8 cursor-pointer rounded-full border-red-500/20 bg-transparent px-2.5 text-red-600 shadow-none hover:bg-red-500/8 dark:text-red-300"
                                                        onClick={(event) => {
                                                            event.stopPropagation()
                                                            onDeleteSession(session.id)
                                                        }}
                                                        aria-label={`Delete ${session.title}`}
                                                    >
                                                        <Trash2 className="size-3.5" />
                                                    </Button>
                                                </div>
                                            </div>
                                        ))
                                    ) : (
                                        <div className="rounded-2xl border border-black/10 px-4 py-4 text-sm text-black/55 dark:border-white/10 dark:text-white/55">
                                            No mode sessions yet.
                                        </div>
                                    )}
                                </div>
                            </PopoverContent>
                        </Popover>
                    </div>
                )}
            </div>
        </div>
    )
}

export default CoworkTabs
