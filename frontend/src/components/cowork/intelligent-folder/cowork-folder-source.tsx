import type { CoworkFolderTreeNode } from '@/typings/cowork'
import CoworkFolderTreeView from './cowork-folder-tree-view'

interface CoworkFolderSourceProps {
    rootSource?: string
    tree?: CoworkFolderTreeNode | null
}

const CoworkFolderSource = ({
    rootSource = 'root_source',
    tree = null
}: CoworkFolderSourceProps) => {
    if (!tree) {
        return (
            <div className="flex h-full w-full items-center justify-center rounded-[32px] border border-neutral-200 bg-white p-6 dark:border-white/20 dark:bg-white/[0.03]">
                <div className="max-w-md text-center">
                    <p className="text-xs font-semibold uppercase tracking-[0.2em] text-black/50 dark:text-white/50">
                        Source{' '}
                        <span className="normal-case text-black/70 dark:text-white/70">
                            {rootSource}
                        </span>
                    </p>
                    <p className="mt-4 text-sm text-black/60 dark:text-white/60">
                        Load a local path above to render its source tree.
                    </p>
                </div>
            </div>
        )
    }

    return (
        <CoworkFolderTreeView
            label="Source"
            rootPath={rootSource}
            tree={tree}
        />
    )
}

export default CoworkFolderSource
