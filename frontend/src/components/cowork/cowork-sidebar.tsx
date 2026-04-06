import { Icon } from '@/components/ui/icon'
import {
    Sheet,
    SheetClose,
    SheetContent,
    SheetDescription,
    SheetHeader,
    SheetTitle
} from '@/components/ui/sheet'
import { cn } from '@/lib/utils'
import {
    COWORK_HOME_LABEL,
    COWORK_MODES,
    type CoworkModeId
} from './cowork.constants'

interface CoworkSidebarProps {
    open: boolean
    activeMode: CoworkModeId | null
    onOpenChange: (open: boolean) => void
    onGoHomepage: () => void
    onSelectMode: (mode: CoworkModeId) => void
}

const CoworkSidebar = ({
    open,
    activeMode,
    onOpenChange,
    onGoHomepage,
    onSelectMode
}: CoworkSidebarProps) => {
    return (
        <Sheet open={open} onOpenChange={onOpenChange}>
            <SheetContent side="left" className="w-[280px] p-0 sm:max-w-[280px]">
                <SheetHeader className="gap-2 border-b border-neutral-200 px-4 py-4 dark:border-white/20">
                    <div className="flex items-center justify-between gap-3">
                        <div>
                            <SheetTitle className="text-lg text-black dark:text-white">
                                II-Cowork
                            </SheetTitle>
                            <SheetDescription className="text-xs text-black/60 dark:text-white/60">
                                Workspace navigation
                            </SheetDescription>
                        </div>
                        <SheetClose className="rounded-full p-1">
                            <Icon
                                name="close"
                                className="size-5 fill-black dark:fill-white"
                            />
                        </SheetClose>
                    </div>
                </SheetHeader>
                <div className="flex flex-1 flex-col gap-2 p-4">
                    <button
                        type="button"
                        onClick={() => {
                            onGoHomepage()
                            onOpenChange(false)
                        }}
                        className={cn(
                            'flex cursor-pointer items-center gap-3 rounded-2xl border px-4 py-3 text-left transition-all hover:-translate-y-0.5 active:translate-y-0',
                            activeMode === null
                                ? 'border-firefly bg-firefly/10 text-black dark:border-sky-blue dark:bg-sky-blue/10 dark:text-white'
                                : 'border-firefly/25 hover:border-firefly hover:bg-firefly/5 dark:border-sky-blue/25 dark:hover:border-sky-blue dark:hover:bg-sky-blue/10'
                        )}
                    >
                        <span
                            className={cn(
                                'flex size-8 items-center justify-center rounded-full transition-colors',
                                activeMode === null
                                    ? 'bg-firefly text-sky-blue-2 dark:bg-sky-blue dark:text-black'
                                    : 'bg-firefly/10 text-firefly dark:bg-sky-blue/10 dark:text-sky-blue'
                            )}
                        >
                            <Icon
                                name="home"
                                className={cn(
                                    'size-4',
                                    activeMode === null
                                        ? 'fill-sky-blue-2 dark:fill-black'
                                        : 'fill-firefly dark:fill-sky-blue'
                                )}
                            />
                        </span>
                        <span className="text-sm font-semibold text-black dark:text-white">
                            {COWORK_HOME_LABEL}
                        </span>
                    </button>
                    <div className="mt-3 border-t border-neutral-200 pt-3 dark:border-white/10">
                        <p className="mb-2 px-1 text-xs font-semibold uppercase tracking-[0.2em] text-black/50 dark:text-white/50">
                            Modes
                        </p>
                        <div className="flex flex-col gap-2">
                            {COWORK_MODES.map((mode) => {
                                const isActive = activeMode === mode.id

                                return (
                                    <button
                                        key={mode.id}
                                        type="button"
                                        onClick={() => {
                                            onSelectMode(mode.id)
                                            onOpenChange(false)
                                        }}
                                        className={cn(
                                            'flex cursor-pointer items-center gap-3 rounded-2xl border px-4 py-3 text-left transition-all hover:-translate-y-0.5 active:translate-y-0',
                                            isActive
                                                ? 'border-firefly bg-firefly/10 text-black dark:border-sky-blue dark:bg-sky-blue/10 dark:text-white'
                                                : 'border-firefly/25 hover:border-firefly hover:bg-firefly/5 dark:border-sky-blue/25 dark:hover:border-sky-blue dark:hover:bg-sky-blue/10'
                                        )}
                                    >
                                        <span
                                            className={cn(
                                                'flex size-8 items-center justify-center rounded-full transition-colors',
                                                isActive
                                                    ? 'bg-firefly text-sky-blue-2 dark:bg-sky-blue dark:text-black'
                                                    : 'bg-firefly/10 text-firefly dark:bg-sky-blue/10 dark:text-sky-blue'
                                            )}
                                        >
                                            <Icon
                                                name="folder-open"
                                                className={cn(
                                                    'size-4',
                                                    isActive
                                                        ? 'fill-sky-blue-2 dark:fill-black'
                                                        : 'fill-firefly dark:fill-sky-blue'
                                                )}
                                            />
                                        </span>
                                        <div className="min-w-0">
                                            <p className="truncate text-sm font-semibold text-black dark:text-white">
                                                {mode.label}
                                            </p>
                                        </div>
                                    </button>
                                )
                            })}
                        </div>
                    </div>
                </div>
            </SheetContent>
        </Sheet>
    )
}

export default CoworkSidebar
