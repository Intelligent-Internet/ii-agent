import { useCallback, useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import dayjs from 'dayjs'
import utc from 'dayjs/plugin/utc'

import { memoryService } from '@/services/memory.service'
import type { Memory } from '@/typings/memory'
import { cn } from '@/lib/utils'
import { Button } from '../ui/button'
import { Input } from '../ui/input'
import { Textarea } from '../ui/textarea'
import { Badge } from '../ui/badge'
import { Icon } from '../ui/icon'
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow
} from '../ui/table'
import {
    Dialog,
    DialogContent,
    DialogFooter,
    DialogHeader,
    DialogTitle
} from '../ui/dialog'
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue
} from '../ui/select'
import {
    Collapsible,
    CollapsibleContent,
    CollapsibleTrigger
} from '../ui/collapsible'
import { toast } from 'sonner'

dayjs.extend(utc)

const PER_PAGE = 10

const MemoryTable = () => {
    const { t } = useTranslation()

    // Data
    const [memories, setMemories] = useState<Memory[]>([])
    const [loading, setLoading] = useState(false)
    const [allTopics, setAllTopics] = useState<string[]>([])

    // Pagination
    const [page, setPage] = useState(1)
    const [total, setTotal] = useState(0)

    // Search / Filter / Sort
    const [search, setSearch] = useState('')
    const [debouncedSearch, setDebouncedSearch] = useState('')
    const [selectedTopic, setSelectedTopic] = useState('')
    const [sortBy, setSortBy] = useState<
        'updated_at' | 'memory' | 'topics_count'
    >('updated_at')
    const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc')

    // Expandable rows
    const [expandedRows, setExpandedRows] = useState<Set<string>>(new Set())

    // Dialog states
    const [formDialogOpen, setFormDialogOpen] = useState(false)
    const [editingMemory, setEditingMemory] = useState<Memory | null>(null)
    const [formMemory, setFormMemory] = useState('')
    const [formTopics, setFormTopics] = useState('')
    const [formSaving, setFormSaving] = useState(false)

    // Delete state
    const [deleteDialogOpen, setDeleteDialogOpen] = useState(false)
    const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null)

    const totalPages = useMemo(
        () => Math.max(1, Math.ceil(total / PER_PAGE)),
        [total]
    )

    // Fetch memories
    const fetchMemories = useCallback(async () => {
        setLoading(true)
        try {
            const result = await memoryService.listMemories({
                page,
                perPage: PER_PAGE,
                search: debouncedSearch || undefined,
                topics: selectedTopic || undefined,
                sortBy,
                sortOrder
            })
            setMemories(result.memories)
            setTotal(result.total)
        } catch {
            toast.error(t('errors.generic'))
        } finally {
            setLoading(false)
        }
    }, [page, debouncedSearch, selectedTopic, sortBy, sortOrder, t])

    // Debounce search
    useEffect(() => {
        const timer = setTimeout(() => {
            setDebouncedSearch(search)
            setPage(1)
        }, 300)
        return () => clearTimeout(timer)
    }, [search])

    // Fetch on param change
    useEffect(() => {
        fetchMemories()
    }, [fetchMemories])

    // Load topics for filter
    useEffect(() => {
        memoryService.getTopics().then(setAllTopics).catch(() => {})
    }, [])

    // Refresh topics after mutations
    const refreshTopics = () => {
        memoryService.getTopics().then(setAllTopics).catch(() => {})
    }

    // Sort handler
    const handleSort = (column: 'updated_at' | 'memory' | 'topics_count') => {
        if (sortBy === column) {
            setSortOrder((prev) => (prev === 'asc' ? 'desc' : 'asc'))
        } else {
            setSortBy(column)
            setSortOrder('desc')
        }
        setPage(1)
    }

    // Expand/collapse row
    const toggleRow = (memoryId: string) => {
        setExpandedRows((prev) => {
            const next = new Set(prev)
            if (next.has(memoryId)) next.delete(memoryId)
            else next.add(memoryId)
            return next
        })
    }

    // Open add dialog
    const openAddDialog = () => {
        setEditingMemory(null)
        setFormMemory('')
        setFormTopics('')
        setFormDialogOpen(true)
    }

    // Open edit dialog
    const openEditDialog = (memory: Memory) => {
        setEditingMemory(memory)
        setFormMemory(memory.memory)
        setFormTopics(memory.topics?.join(', ') ?? '')
        setFormDialogOpen(true)
    }

    // Save (add or edit)
    const handleSave = async () => {
        if (!formMemory.trim()) return
        setFormSaving(true)

        const topicsList = formTopics
            .split(',')
            .map((t) => t.trim())
            .filter(Boolean)

        try {
            if (editingMemory) {
                await memoryService.updateMemory(editingMemory.memory_id, {
                    memory: formMemory.trim(),
                    topics: topicsList
                })
            } else {
                await memoryService.createMemory({
                    memory: formMemory.trim(),
                    topics: topicsList
                })
            }
            setFormDialogOpen(false)
            fetchMemories()
            refreshTopics()
        } catch {
            toast.error(t('errors.generic'))
        } finally {
            setFormSaving(false)
        }
    }

    // Delete
    const handleDelete = async () => {
        if (!pendingDeleteId) return
        try {
            await memoryService.deleteMemory(pendingDeleteId)
            setDeleteDialogOpen(false)
            setPendingDeleteId(null)
            fetchMemories()
            refreshTopics()
        } catch {
            toast.error(t('errors.generic'))
        }
    }

    // Pagination
    const goPrev = () => setPage((p) => Math.max(1, p - 1))
    const goNext = () => setPage((p) => Math.min(totalPages, p + 1))

    const SortIndicator = ({
        column
    }: {
        column: 'updated_at' | 'memory' | 'topics_count'
    }) =>
        sortBy === column ? (
            <span className="ml-1 text-xs">
                {sortOrder === 'asc' ? '↑' : '↓'}
            </span>
        ) : null

    return (
        <div>
            {/* Header */}
            <div className="mb-4">
                <h2 className="text-[18px] font-semibold mb-1">
                    {t('settings.personalization.memoriesTitle')}
                </h2>
                <p className="text-xs">
                    {t('settings.personalization.memoriesDescription')}
                </p>
            </div>

            {/* Toolbar */}
            <div className="flex flex-col md:flex-row gap-3 mb-4">
                <Input
                    className="flex-1"
                    placeholder={t(
                        'settings.personalization.searchPlaceholder'
                    )}
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                />
                <Select
                    value={selectedTopic}
                    onValueChange={(v) => {
                        setSelectedTopic(v === '__all__' ? '' : v)
                        setPage(1)
                    }}
                >
                    <SelectTrigger className="w-full md:w-[200px]">
                        <SelectValue
                            placeholder={t(
                                'settings.personalization.filterByTopics'
                            )}
                        />
                    </SelectTrigger>
                    <SelectContent>
                        <SelectItem value="__all__">
                            {t('settings.personalization.allTopics')}
                        </SelectItem>
                        {allTopics.map((topic) => (
                            <SelectItem key={topic} value={topic}>
                                {topic}
                            </SelectItem>
                        ))}
                    </SelectContent>
                </Select>
                <Button
                    onClick={openAddDialog}
                    className="h-12 bg-firefly border-firefly text-sky-blue-2 dark:bg-sky-blue dark:border-sky-blue-2 dark:text-black hover:opacity-90 px-6 rounded-xl text-sm font-medium"
                >
                    {t('settings.personalization.addMemory')}
                </Button>
            </div>

            {/* Table */}
            <div className="rounded-xl overflow-hidden border border-white/10">
                <Table>
                    <TableHeader>
                        <TableRow>
                            <TableHead className="w-8" />
                            <TableHead className="py-3">
                                <button
                                    className="flex items-center cursor-pointer font-medium"
                                    onClick={() => handleSort('memory')}
                                >
                                    {t(
                                        'settings.personalization.columnMemory'
                                    )}
                                    <SortIndicator column="memory" />
                                </button>
                            </TableHead>
                            <TableHead className="py-3 hidden md:table-cell">
                                <button
                                    className="flex items-center cursor-pointer font-medium"
                                    onClick={() =>
                                        handleSort('topics_count')
                                    }
                                >
                                    {t(
                                        'settings.personalization.columnTopics'
                                    )}
                                    <SortIndicator column="topics_count" />
                                </button>
                            </TableHead>
                            <TableHead className="py-3">
                                <button
                                    className="flex items-center cursor-pointer font-medium"
                                    onClick={() =>
                                        handleSort('updated_at')
                                    }
                                >
                                    {t(
                                        'settings.personalization.columnUpdatedAt'
                                    )}
                                    <SortIndicator column="updated_at" />
                                </button>
                            </TableHead>
                            <TableHead className="py-3 w-20" />
                        </TableRow>
                    </TableHeader>
                    <TableBody>
                        {loading && (
                            <TableRow>
                                <TableCell colSpan={5} className="py-8 text-center">
                                    {t('common.loading')}
                                </TableCell>
                            </TableRow>
                        )}
                        {!loading && memories.length === 0 && (
                            <TableRow>
                                <TableCell colSpan={5} className="py-8 text-center text-muted-foreground">
                                    {debouncedSearch || selectedTopic
                                        ? t('settings.personalization.noMatchingMemories')
                                        : t('settings.personalization.noMemories')}
                                </TableCell>
                            </TableRow>
                        )}
                        {!loading &&
                            memories.map((mem) => (
                                <Collapsible
                                    key={mem.memory_id}
                                    open={expandedRows.has(mem.memory_id)}
                                    onOpenChange={() =>
                                        toggleRow(mem.memory_id)
                                    }
                                    asChild
                                >
                                    <>
                                        <TableRow className="group">
                                            <TableCell className="py-3 pl-2">
                                                <CollapsibleTrigger asChild>
                                                    <button className="cursor-pointer p-1">
                                                        <span
                                                            className={cn(
                                                                'inline-block transition-transform text-xs',
                                                                expandedRows.has(
                                                                    mem.memory_id
                                                                ) &&
                                                                    'rotate-90'
                                                            )}
                                                        >
                                                            ▶
                                                        </span>
                                                    </button>
                                                </CollapsibleTrigger>
                                            </TableCell>
                                            <TableCell className="py-3 max-w-[300px]">
                                                <span className="line-clamp-2 text-sm">
                                                    {mem.memory}
                                                </span>
                                            </TableCell>
                                            <TableCell className="py-3 hidden md:table-cell">
                                                <div className="flex flex-wrap gap-1">
                                                    {mem.topics?.map(
                                                        (topic) => (
                                                            <Badge
                                                                key={topic}
                                                                variant="outline"
                                                                className="text-[10px] px-1.5 py-0"
                                                            >
                                                                {topic}
                                                            </Badge>
                                                        )
                                                    )}
                                                </div>
                                            </TableCell>
                                            <TableCell className="py-3 text-sm text-muted-foreground whitespace-nowrap">
                                                {mem.updated_at
                                                    ? dayjs
                                                          .unix(
                                                              mem.updated_at
                                                          )
                                                          .format(
                                                              'DD MMM YYYY'
                                                          )
                                                    : '—'}
                                            </TableCell>
                                            <TableCell className="py-3">
                                                <div className="flex items-center gap-1">
                                                    <Button
                                                        variant="ghost"
                                                        size="icon"
                                                        className="size-8 text-black/70 dark:text-white/70 hover:text-black dark:hover:text-white hover:bg-black/10 dark:hover:bg-white/10"
                                                        onClick={(e) => {
                                                            e.stopPropagation()
                                                            openEditDialog(
                                                                mem
                                                            )
                                                        }}
                                                        title={t(
                                                            'settings.personalization.editMemory'
                                                        )}
                                                    >
                                                        <Icon
                                                            name="pencil-edit"
                                                            className="size-4 stroke-current"
                                                        />
                                                    </Button>
                                                    <Button
                                                        variant="ghost"
                                                        size="icon"
                                                        className="size-8 text-red-400 hover:text-red-400 hover:bg-red-500/20"
                                                        onClick={(e) => {
                                                            e.stopPropagation()
                                                            setPendingDeleteId(
                                                                mem.memory_id
                                                            )
                                                            setDeleteDialogOpen(
                                                                true
                                                            )
                                                        }}
                                                        title={t(
                                                            'settings.personalization.deleteMemory'
                                                        )}
                                                    >
                                                        <Icon
                                                            name="trash"
                                                            className="size-4"
                                                        />
                                                    </Button>
                                                </div>
                                            </TableCell>
                                        </TableRow>
                                        <CollapsibleContent asChild>
                                            <tr>
                                                <td
                                                    colSpan={5}
                                                    className="bg-white/5 dark:bg-white/5 px-4 py-3"
                                                >
                                                    <div className="text-sm space-y-2">
                                                        <p className="whitespace-pre-wrap">
                                                            {mem.memory}
                                                        </p>
                                                        {mem.topics &&
                                                            mem.topics.length >
                                                                0 && (
                                                                <div className="flex flex-wrap gap-1 md:hidden">
                                                                    {mem.topics.map(
                                                                        (
                                                                            topic
                                                                        ) => (
                                                                            <Badge
                                                                                key={
                                                                                    topic
                                                                                }
                                                                                variant="outline"
                                                                                className="text-[10px] px-1.5 py-0"
                                                                            >
                                                                                {
                                                                                    topic
                                                                                }
                                                                            </Badge>
                                                                        )
                                                                    )}
                                                                </div>
                                                            )}
                                                        {mem.created_at && (
                                                            <div className="text-xs text-muted-foreground">
                                                                <span>
                                                                    {t(
                                                                        'settings.personalization.expandCreatedAt'
                                                                    )}
                                                                    :{' '}
                                                                    {dayjs
                                                                        .unix(
                                                                            mem.created_at
                                                                        )
                                                                        .format(
                                                                            'DD MMM YYYY, HH:mm'
                                                                        )}
                                                                </span>
                                                            </div>
                                                        )}
                                                    </div>
                                                </td>
                                            </tr>
                                        </CollapsibleContent>
                                    </>
                                </Collapsible>
                            ))}
                    </TableBody>
                </Table>
            </div>

            {/* Pagination */}
            {total > PER_PAGE && (
                <div className="flex items-center justify-center gap-2 py-4 select-none">
                    <Button
                        variant="ghost"
                        size="sm"
                        onClick={goPrev}
                        disabled={page === 1}
                    >
                        <Icon
                            name="arrow-left-2"
                            className="size-4 fill-black/40 dark:fill-white/40"
                        />
                        {t('common.previous')}
                    </Button>
                    <Button
                        variant="ghost"
                        size="sm"
                        className="pointer-events-none font-medium"
                    >
                        {page}
                    </Button>
                    {page < totalPages && (
                        <Button
                            variant="ghost"
                            size="sm"
                            onClick={() =>
                                setPage(Math.min(totalPages, page + 1))
                            }
                            className="text-black/60 dark:text-white/60"
                        >
                            {page + 1}
                        </Button>
                    )}
                    <Button
                        variant="ghost"
                        size="sm"
                        onClick={goNext}
                        disabled={page === totalPages}
                    >
                        {t('common.next')}
                        <Icon
                            name="arrow-right-2"
                            className="size-4 fill-black/40 dark:fill-white/40"
                        />
                    </Button>
                </div>
            )}

            {/* Add/Edit Dialog */}
            <Dialog open={formDialogOpen} onOpenChange={setFormDialogOpen}>
                <DialogContent>
                    <DialogHeader>
                        <DialogTitle className="text-black dark:text-white">
                            {editingMemory
                                ? t('settings.personalization.editMemory')
                                : t('settings.personalization.addMemory')}
                        </DialogTitle>
                    </DialogHeader>
                    <div className="space-y-4 py-2">
                        <div>
                            <label className="text-sm font-medium mb-1 block">
                                {t(
                                    'settings.personalization.memoryContent'
                                )}
                            </label>
                            <Textarea
                                value={formMemory}
                                onChange={(e) =>
                                    setFormMemory(e.target.value)
                                }
                                placeholder={t(
                                    'settings.personalization.memoryContentPlaceholder'
                                )}
                                className="min-h-[100px]"
                            />
                        </div>
                        <div>
                            <label className="text-sm font-medium mb-1 block">
                                {t(
                                    'settings.personalization.topicsLabel'
                                )}
                            </label>
                            <Input
                                value={formTopics}
                                onChange={(e) =>
                                    setFormTopics(e.target.value)
                                }
                                placeholder={t(
                                    'settings.personalization.topicsPlaceholder'
                                )}
                            />
                        </div>
                    </div>
                    <DialogFooter>
                        <Button
                            variant="outline"
                            onClick={() => setFormDialogOpen(false)}
                        >
                            {t('common.cancel')}
                        </Button>
                        <Button
                            onClick={handleSave}
                            disabled={!formMemory.trim() || formSaving}
                            className="bg-firefly border-firefly text-sky-blue-2 dark:bg-sky-blue dark:border-sky-blue-2 dark:text-black hover:opacity-90 disabled:opacity-50"
                        >
                            {formSaving
                                ? t('common.saving')
                                : t('common.save')}
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>

            {/* Delete Confirmation */}
            <Dialog
                open={deleteDialogOpen}
                onOpenChange={setDeleteDialogOpen}
            >
                <DialogContent>
                    <DialogHeader>
                        <DialogTitle className="text-black dark:text-white">
                            {t(
                                'settings.personalization.deleteMemoryConfirmTitle'
                            )}
                        </DialogTitle>
                    </DialogHeader>
                    <p className="text-sm text-black/70 dark:text-white/70 py-2">
                        {t(
                            'settings.personalization.deleteMemoryConfirmDescription'
                        )}
                    </p>
                    <DialogFooter>
                        <Button
                            variant="outline"
                            onClick={() => setDeleteDialogOpen(false)}
                        >
                            {t('common.cancel')}
                        </Button>
                        <Button
                            onClick={handleDelete}
                            className="bg-red-500 hover:bg-red-600 text-white"
                        >
                            {t('common.delete')}
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </div>
    )
}

export default MemoryTable