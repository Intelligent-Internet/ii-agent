import type { CoworkFolderTreeNode } from '@/typings/cowork'
import CoworkFolderTreeView from './cowork-folder-tree-view'

interface CoworkFolderResultProps {
    rootResult?: string
    tree?: CoworkFolderTreeNode | null
}

const CoworkFolderResult = ({
    rootResult = 'root_result',
    tree = null
}: CoworkFolderResultProps) => {
    if (!tree) {
        return (
            <div className="flex h-full w-full items-center justify-center rounded-[32px] border border-neutral-200 bg-white p-6 dark:border-white/20 dark:bg-white/[0.03]">
                <div className="min-w-0 max-w-md text-center">
                    <p className="text-xs font-semibold uppercase tracking-[0.2em] text-black/50 dark:text-white/50">
                        Result{' '}
                        <span className="break-all normal-case text-black/70 dark:text-white/70">
                            {rootResult}
                        </span>
                    </p>
                    <p className="mt-4 text-sm text-black/60 dark:text-white/60">
                        No changes from the source folder yet.
                    </p>
                </div>
            </div>
        )
    }

    return (
        <CoworkFolderTreeView
            label="Result"
            rootPath={rootResult}
            tree={tree}
        />
    )
}

export default CoworkFolderResult
