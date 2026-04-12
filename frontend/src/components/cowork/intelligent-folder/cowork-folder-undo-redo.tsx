import clsx from 'clsx'
import { Icon } from '@/components/ui/icon'
import type { CoworkFolderUndoState } from '@/typings/cowork'

interface CoworkFolderUndoRedoProps {
    state?: CoworkFolderUndoState | null
    onUndo: () => void
    onRedo: () => void
    isBusy?: boolean
    className?: string
}

interface PillButtonProps {
    label: string
    iconName: string
    enabled: boolean
    onClick: () => void
    ariaLabel: string
}

/**
 * Single Undo or Redo pill — shares the visual language of
 * {@link CoworkFolderSteps} (size-7 circle + icon). Disabled pills are
 * kept visible (not removed) so the layout doesn't jitter every time
 * the user walks to a timeline boundary.
 */
const PillButton = ({ label, iconName, enabled, onClick, ariaLabel }: PillButtonProps) => {
    return (
        <button
            type="button"
            onClick={onClick}
            disabled={!enabled}
            aria-label={ariaLabel}
            className={clsx(
                'flex items-center gap-x-2 px-3 py-1.5 rounded-full border transition-all',
                'border-black/[0.58] dark:border-white/[0.58]',
                'cursor-pointer disabled:cursor-not-allowed disabled:opacity-40',
                enabled && 'hover:bg-firefly/15 dark:hover:bg-sky-blue/15'
            )}
        >
            <Icon
                name={iconName}
                className="size-4 stroke-black dark:stroke-white fill-black dark:fill-white"
            />
            
            <p className="text-sm font-medium text-black/[0.58] dark:text-white/[0.58]">
                {label}
            </p>
        </button>
    )
}

/**
 * Full Undo / Redo / Counter row rendered to the right of the
 * Source / Build / Result stepper in Intelligent Folder mode.
 *
 * - Rendered only when `state.total > 0` (i.e. the session has
 *   committed at least one snapshot to the timeline).
 * - Counter shows "current/total" — current is 1-based.
 * - Both pills are always shown; disabled when navigation in that
 *   direction isn't possible, so the row doesn't shift around as the
 *   cursor walks.
 */
const CoworkFolderUndoRedo = ({
    state,
    onUndo,
    onRedo,
    isBusy = false,
    className
}: CoworkFolderUndoRedoProps) => {
    if (!state || state.total === 0) {
        return null
    }

    const canUndo = state.can_undo && !isBusy
    const canRedo = state.can_redo && !isBusy

    return (
        <div className={clsx('flex items-center gap-x-3', className)}>
            <PillButton
                label="Undo"
                iconName="undo"
                enabled={canUndo}
                onClick={onUndo}
                ariaLabel="Undo to previous snapshot"
            />
            <span className="text-xs font-medium text-black/[0.58] dark:text-white/[0.58] tabular-nums">
                {state.current}/{state.total}
            </span>
            <PillButton
                label="Redo"
                iconName="redo"
                enabled={canRedo}
                onClick={onRedo}
                ariaLabel="Redo to next snapshot"
            />
        </div>
    )
}

export default CoworkFolderUndoRedo
