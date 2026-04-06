import type {
    CoworkChatSessionDetail,
    CoworkLiveSessionState
} from '@/typings/cowork'
import type { ActionStep } from '@/typings/agent'
import { Icon } from '@/components/ui/icon'
import { cn } from '@/lib/utils'
import { COWORK_MODES, type CoworkModeId } from './cowork.constants'
import OrganizeFileFolderMode from './modes/organize-file-folder'

interface CoworkMainProps {
    activeMode: CoworkModeId | null
    organizeSession: CoworkChatSessionDetail | null
    organizeLiveSession: CoworkLiveSessionState | null
    isOrganizeSessionLoading: boolean
    isOrganizeChatSending: boolean
    onSelectMode: (mode: CoworkModeId) => void
    organizeModeResetVersion: number
    onOrganizeWorkflowActiveChange: (active: boolean) => void
    onOrganizeSessionCreated: (session: CoworkChatSessionDetail) => void
    requestedOrganizeAction?: ActionStep | null
    requestedOrganizeActionToken?: number
}

const CoworkMain = ({
    activeMode,
    organizeSession,
    organizeLiveSession,
    isOrganizeSessionLoading,
    isOrganizeChatSending,
    onSelectMode,
    organizeModeResetVersion,
    onOrganizeWorkflowActiveChange,
    onOrganizeSessionCreated,
    requestedOrganizeAction = null,
    requestedOrganizeActionToken = 0
}: CoworkMainProps) => {
    if (activeMode === 'organize-file-folder') {
        return (
            <OrganizeFileFolderMode
                resetVersion={organizeModeResetVersion}
                session={organizeSession}
                liveSession={organizeLiveSession}
                isSessionLoading={isOrganizeSessionLoading}
                isSending={isOrganizeChatSending}
                onWorkflowActiveChange={onOrganizeWorkflowActiveChange}
                onSessionCreated={onOrganizeSessionCreated}
                requestedBuildAction={requestedOrganizeAction}
                requestedBuildActionToken={requestedOrganizeActionToken}
            />
        )
    }

    return (
        <div className="flex h-full w-full flex-col overflow-auto px-3 py-4 md:px-6 md:py-6">
            <div className="rounded-[32px] border border-neutral-200 bg-white p-5 dark:border-white/20 dark:bg-white/[0.03] md:p-8">
                <div className="max-w-3xl">
                    <p className="text-xs font-semibold uppercase tracking-[0.2em] text-black/50 dark:text-white/50">
                        II-Cowork
                    </p>
                    <h1 className="mt-2 text-2xl font-semibold text-black dark:text-white">
                        Homepage
                    </h1>
                    <p className="mt-2 text-sm text-black/60 dark:text-white/60">
                        Choose a mode to enter the Cowork workflow.
                    </p>
                </div>

                <div className="mt-8 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                    {COWORK_MODES.map((mode) => (
                        <button
                            key={mode.id}
                            type="button"
                            onClick={() => onSelectMode(mode.id)}
                            className={cn(
                                'group relative flex min-h-48 cursor-pointer flex-col items-start justify-between overflow-hidden rounded-[28px] border border-firefly/20 bg-gradient-to-br from-firefly/[0.06] via-white to-sky-blue-2/[0.08] p-6 text-left shadow-[0_16px_40px_-24px_rgba(0,0,0,0.45)] transition-all hover:-translate-y-1 hover:border-firefly/35 hover:shadow-[0_24px_50px_-24px_rgba(0,0,0,0.5)] active:translate-y-0 active:scale-[0.99] dark:border-sky-blue-2/25 dark:from-sky-blue-2/[0.14] dark:via-white/[0.04] dark:to-transparent dark:hover:border-sky-blue-2/40'
                            )}
                        >
                            <div className="absolute right-0 top-0 h-28 w-28 translate-x-8 -translate-y-8 rounded-full bg-sky-blue-2/20 blur-3xl dark:bg-sky-blue-2/10" />
                            <span className="relative flex size-14 items-center justify-center rounded-2xl bg-black text-sky-blue-2 transition-colors group-hover:bg-firefly group-hover:text-sky-blue-2 dark:bg-sky-blue-2 dark:text-black dark:group-hover:bg-sky-blue dark:group-hover:text-black">
                                <Icon
                                    name="folder-open"
                                    className="size-7 fill-sky-blue-2 transition-colors group-hover:fill-sky-blue-2 dark:fill-black dark:group-hover:fill-black"
                                />
                            </span>
                            <div className="relative">
                                <p className="text-lg font-semibold text-black dark:text-white">
                                    {mode.label}
                                </p>
                                <p className="mt-2 text-sm text-black/60 dark:text-white/60">
                                    Start with a dedicated file and folder
                                    organization workflow.
                                </p>
                            </div>
                        </button>
                    ))}
                </div>
            </div>
        </div>
    )
}

export default CoworkMain
