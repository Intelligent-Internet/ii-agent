import type { CoworkOrganizeTreeNode } from '@/typings/cowork'
import CoworkOrganizeTreeView from './cowork-organize-tree-view'

interface CoworkOrganizeResultProps {
    rootResult?: string
    tree?: CoworkOrganizeTreeNode | null
}

const CoworkOrganizeResult = ({
    rootResult = 'root_result',
    tree = null
}: CoworkOrganizeResultProps) => {
    if (!tree) {
        return (
            <div className="flex h-full w-full items-center justify-center rounded-[32px] border border-neutral-200 bg-white p-6 dark:border-white/20 dark:bg-white/[0.03]">
                <div className="max-w-md text-center">
                    <p className="text-xs font-semibold uppercase tracking-[0.2em] text-black/50 dark:text-white/50">
                        Result{' '}
                        <span className="normal-case text-black/70 dark:text-white/70">
                            {rootResult}
                        </span>
                    </p>
                    <p className="mt-4 text-sm text-black/60 dark:text-white/60">
                        No mode-specific result is available yet.
                    </p>
                </div>
            </div>
        )
    }

    return (
        <CoworkOrganizeTreeView
            label="Result"
            rootPath={rootResult}
            tree={tree}
        />
    )
}

export default CoworkOrganizeResult
