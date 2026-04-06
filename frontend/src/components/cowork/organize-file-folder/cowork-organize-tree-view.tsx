import { useEffect, useMemo, useState } from 'react'
import { ChevronDown, ChevronRight } from 'lucide-react'
import type { CoworkOrganizeTreeNode } from '@/typings/cowork'
import { cn } from '@/lib/utils'
import { getTreeNodeVisual } from './cowork-organize-tree-icons'

export type OrganizeTreeNode = CoworkOrganizeTreeNode

interface FlattenedTreeNode extends OrganizeTreeNode {
    path: string
}

interface CoworkOrganizeTreeViewProps {
    label: string
    rootPath: string
    tree: OrganizeTreeNode
}

const getAllFolderIds = (node: OrganizeTreeNode): string[] => [
    ...(node.kind === 'folder' ? [node.id] : []),
    ...(node.children?.flatMap((child) => getAllFolderIds(child)) ?? [])
]

const flattenTree = (
    node: OrganizeTreeNode,
    rootPath: string,
    parentPath = ''
): FlattenedTreeNode[] => {
    const currentPath = parentPath ? `${parentPath}/${node.name}` : rootPath

    return [
        { ...node, path: currentPath },
        ...(node.children?.flatMap((child) =>
            flattenTree(child, rootPath, currentPath)
        ) ?? [])
    ]
}

const getDirectChildCounts = (node: OrganizeTreeNode) => ({
    folders:
        node.children?.filter((child) => child.kind === 'folder').length ?? 0,
    files: node.children?.filter((child) => child.kind === 'file').length ?? 0
})

const renderTreeNode = ({
    node,
    depth,
    expandedIds,
    selectedId,
    onToggle,
    onSelect
}: {
    node: OrganizeTreeNode
    depth: number
    expandedIds: Set<string>
    selectedId: string
    onToggle: (id: string) => void
    onSelect: (id: string) => void
}) => {
    const hasChildren = Boolean(node.children?.length)
    const isExpanded = expandedIds.has(node.id)
    const isSelected = selectedId === node.id
    const visual = getTreeNodeVisual({
        kind: node.kind,
        extension: node.extension,
        expanded: isExpanded
    })

    return (
        <div key={node.id}>
            <button
                type="button"
                onClick={() => {
                    onSelect(node.id)
                    if (hasChildren) onToggle(node.id)
                }}
                className={cn(
                    'flex w-full cursor-pointer items-center gap-3 rounded-2xl border border-transparent pr-3 text-left transition-all hover:-translate-y-0.5 hover:border-firefly/20 hover:bg-firefly/5 active:translate-y-0 active:scale-[0.995] dark:hover:border-sky-blue/20 dark:hover:bg-sky-blue/10',
                    isSelected &&
                        'border-firefly/30 bg-firefly/10 dark:border-sky-blue/30 dark:bg-sky-blue/10'
                )}
                style={{
                    paddingLeft: `${depth * 18 + 12}px`,
                    paddingTop: 10,
                    paddingBottom: 10
                }}
            >
                <span className="flex size-5 items-center justify-center text-black/40 dark:text-white/40">
                    {hasChildren ? (
                        isExpanded ? (
                            <ChevronDown className="size-4" />
                        ) : (
                            <ChevronRight className="size-4" />
                        )
                    ) : null}
                </span>
                <span
                    className={cn(
                        'flex size-9 shrink-0 items-center justify-center rounded-xl border',
                        visual.containerClassName
                    )}
                >
                    <visual.Icon className={cn('size-4.5', visual.iconClassName)} />
                </span>
                <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                        <span className="truncate text-sm font-semibold text-black dark:text-white">
                            {node.name}
                        </span>
                        {node.kind === 'file' && node.extension && (
                            <span
                                className={cn(
                                    'rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.16em]',
                                    visual.chipClassName
                                )}
                            >
                                {node.extension}
                            </span>
                        )}
                    </div>
                </div>
                {node.size && (
                    <span className="shrink-0 text-xs font-medium text-black/45 dark:text-white/45">
                        {node.size}
                    </span>
                )}
            </button>
            {hasChildren &&
                isExpanded &&
                node.children?.map((child) =>
                    renderTreeNode({
                        node: child,
                        depth: depth + 1,
                        expandedIds,
                        selectedId,
                        onToggle,
                        onSelect
                    })
                )}
        </div>
    )
}

const CoworkOrganizeTreeView = ({
    label,
    rootPath,
    tree
}: CoworkOrganizeTreeViewProps) => {
    const [expandedIds, setExpandedIds] = useState<Set<string>>(
        () => new Set(getAllFolderIds(tree))
    )
    const [selectedId, setSelectedId] = useState(() => tree.id)

    useEffect(() => {
        setExpandedIds(new Set(getAllFolderIds(tree)))
        setSelectedId(tree.id)
    }, [tree])

    const flatTree = useMemo(() => flattenTree(tree, rootPath), [rootPath, tree])
    const selectedNode = useMemo(
        () => flatTree.find((node) => node.id === selectedId) ?? flatTree[0],
        [flatTree, selectedId]
    )
    const selectedChildCounts = useMemo(
        () => getDirectChildCounts(selectedNode),
        [selectedNode]
    )

    return (
        <div className="flex h-full w-full flex-col gap-4 overflow-hidden rounded-[32px] border border-neutral-200 bg-white p-4 dark:border-white/20 dark:bg-white/[0.03] md:p-6">
            <div className="flex flex-wrap items-start justify-between gap-4">
                <div className="max-w-2xl">
                    <p className="text-xs font-semibold uppercase tracking-[0.2em] text-black/50 dark:text-white/50">
                        {label}{' '}
                        <span className="normal-case text-black/70 dark:text-white/70">
                            {rootPath}
                        </span>
                    </p>
                </div>
            </div>
            <div className="grid min-h-0 flex-1 gap-4 xl:grid-cols-[minmax(0,1.5fr)_minmax(320px,0.9fr)]">
                <div className="min-h-0 overflow-hidden rounded-[28px] border border-neutral-200 bg-white dark:border-white/15 dark:bg-[#121716]">
                    <div className="h-full overflow-auto p-3">
                        {renderTreeNode({
                            node: tree,
                            depth: 0,
                            expandedIds,
                            selectedId,
                            onToggle: (id) =>
                                setExpandedIds((prev) => {
                                    const next = new Set(prev)
                                    if (next.has(id)) next.delete(id)
                                    else next.add(id)
                                    return next
                                }),
                            onSelect: setSelectedId
                        })}
                    </div>
                </div>

                <div className="flex min-h-0 flex-col gap-4">
                    <div className="rounded-[28px] border border-neutral-200 bg-white p-5 dark:border-white/15 dark:bg-[#121716]">
                        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-black/50 dark:text-white/50">
                            Selected
                        </p>
                        <div className="mt-4 flex items-start gap-3">
                            <span
                                className={cn(
                                    'flex size-11 shrink-0 items-center justify-center rounded-2xl border',
                                    getTreeNodeVisual({
                                        kind: selectedNode.kind,
                                        extension: selectedNode.extension,
                                        expanded: expandedIds.has(selectedNode.id)
                                    }).containerClassName
                                )}
                            >
                                {(() => {
                                    const visual = getTreeNodeVisual({
                                        kind: selectedNode.kind,
                                        extension: selectedNode.extension,
                                        expanded: expandedIds.has(selectedNode.id)
                                    })
                                    return (
                                        <visual.Icon
                                            className={cn('size-5', visual.iconClassName)}
                                        />
                                    )
                                })()}
                            </span>
                            <div className="min-w-0">
                                <p className="text-lg font-semibold text-black dark:text-white">
                                    {selectedNode.name}
                                </p>
                                <p className="mt-1 break-all text-sm text-black/55 dark:text-white/55">
                                    {selectedNode.path}
                                </p>
                            </div>
                        </div>
                    </div>

                    <div className="rounded-[28px] border border-neutral-200 bg-white p-5 dark:border-white/15 dark:bg-[#121716]">
                        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-black/50 dark:text-white/50">
                            File details
                        </p>
                        <div className="mt-4 grid gap-3">
                            {(
                                selectedNode.kind === 'folder'
                                    ? [
                                          {
                                              label: 'Node type',
                                              value: 'Folder'
                                          },
                                          {
                                              label: 'Subfolders',
                                              value: selectedChildCounts.folders
                                          },
                                          {
                                              label: 'Files',
                                              value: selectedChildCounts.files
                                          }
                                      ]
                                    : [
                                          {
                                              label: 'Node type',
                                              value:
                                                  selectedNode.extension?.toUpperCase() ??
                                                  'File'
                                          },
                                          {
                                              label: 'Size',
                                              value: selectedNode.size ?? '-'
                                          },
                                          {
                                              label: 'Children',
                                              value: 0
                                          }
                                      ]
                            ).map((item) => (
                                <div
                                    key={item.label}
                                    className="flex items-center justify-between rounded-2xl border border-firefly/10 bg-firefly/5 px-4 py-3 dark:border-sky-blue/10 dark:bg-sky-blue/10"
                                >
                                    <span className="text-sm font-medium text-black/60 dark:text-white/60">
                                        {item.label}
                                    </span>
                                    <span className="text-sm font-semibold text-black dark:text-white">
                                        {item.value}
                                    </span>
                                </div>
                            ))}
                        </div>
                    </div>
                </div>
            </div>
        </div>
    )
}

export default CoworkOrganizeTreeView


