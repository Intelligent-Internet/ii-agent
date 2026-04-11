import { AnimatePresence, motion } from 'framer-motion'
import { FolderOpen, LoaderCircle } from 'lucide-react'
import { useEffect, useLayoutEffect, useMemo, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { coworkService } from '@/services/cowork.service'
import type {
    CoworkChatSessionDetail,
    CoworkLiveSessionState,
    CoworkOrganizeTreeNode,
    CoworkOrganizeTreePair
} from '@/typings/cowork'
import type { ActionStep } from '@/typings/agent'
import { cn } from '@/lib/utils'
import { getCurrentWindow } from '@tauri-apps/api/window'
import CoworkOrganizeBuild from '../organize-file-folder/cowork-organize-build'
import CoworkOrganizeResult from '../organize-file-folder/cowork-organize-result'
import CoworkOrganizeSource from '../organize-file-folder/cowork-organize-source'
import { ORGANIZE_TREE_READ_OPTIONS } from '../organize-file-folder/organize-tree-utils'
import CoworkOrganizeSteps, {
    type CoworkOrganizeStep
} from '../organize-file-folder/cowork-organize-steps'

const organizeStepTransition = {
    duration: 0.14,
    ease: 'easeOut'
} as const

interface OrganizeFileFolderModeProps {
    resetVersion?: number
    session?: CoworkChatSessionDetail | null
    liveSession?: CoworkLiveSessionState | null
    isSessionLoading?: boolean
    isSending?: boolean
    onWorkflowActiveChange?: (active: boolean) => void
    onSessionCreated?: (session: CoworkChatSessionDetail) => void
    requestedBuildAction?: ActionStep | null
    requestedBuildActionToken?: number
}

const OrganizeFileFolderMode = ({
    resetVersion = 0,
    session = null,
    liveSession = null,
    isSessionLoading = false,
    isSending = false,
    onWorkflowActiveChange,
    onSessionCreated,
    requestedBuildAction = null,
    requestedBuildActionToken = 0
}: OrganizeFileFolderModeProps) => {
    const [sourcePath, setSourcePath] = useState('')
    const [isLoadingPath, setIsLoadingPath] = useState(false)
    const [loadError, setLoadError] = useState<string | null>(null)
    const [isDragActive, setIsDragActive] = useState(false)
    const [loadedTreePair, setLoadedTreePair] =
        useState<CoworkOrganizeTreePair | null>(null)
    const [isProcessing, setIsProcessing] = useState(false)
    const [activeStep, setActiveStep] = useState<CoworkOrganizeStep>('source')

    useEffect(() => {
        onWorkflowActiveChange?.(isProcessing)
    }, [isProcessing, onWorkflowActiveChange])

    useLayoutEffect(() => {
        setSourcePath('')
        setLoadError(null)
        setIsDragActive(false)
        setLoadedTreePair(null)
        setIsLoadingPath(false)
        setIsProcessing(false)
        setActiveStep('source')
    }, [resetVersion])

    useLayoutEffect(() => {
        if (!session) return
        setSourcePath(session.organize_tree_pair?.source_root ?? '')
        setLoadedTreePair(null)
        setActiveStep('source')
        setIsProcessing(true)
    }, [session?.id, session?.organize_tree_pair?.source_root])

    const organizeTreePair = loadedTreePair ?? session?.organize_tree_pair
    const modeResultTree: CoworkOrganizeTreeNode | null =
        organizeTreePair?.result_tree ?? null
    const hasStreamingBuildActivity = Boolean(
        liveSession?.thinking.trim() ||
            liveSession?.response.trim() ||
            liveSession?.current_action ||
            liveSession?.tool_calls.length ||
            liveSession?.is_awaiting_turn_action
    )
    const isRunCompleted = session?.run_status === 'completed'
    const sessionContentKey = useMemo(
        () => loadedTreePair?.source_root ?? session?.id ?? 'organize-entry',
        [loadedTreePair?.source_root, session?.id]
    )

    useEffect(() => {
        if (!isProcessing) {
            return
        }

        if (isRunCompleted) {
            setActiveStep('result')
            return
        }

        if (requestedBuildAction) {
            setActiveStep('build')
            return
        }

        if (
            isSending ||
            hasStreamingBuildActivity ||
            session?.run_status === 'thinking' ||
            session?.run_status === 'waiting_for_input'
        ) {
            setActiveStep('build')
        }
    }, [
        hasStreamingBuildActivity,
        isProcessing,
        isRunCompleted,
        isSending,
        requestedBuildAction,
        requestedBuildActionToken,
        session?.run_status
    ])

    const resolveFolderPath = async (candidatePaths: string[]) => {
        let lastError: Error | null = null

        for (const rawPath of candidatePaths) {
            const nextPath = rawPath.trim()
            if (!nextPath) {
                continue
            }

            try {
                const probeTree = await coworkService.readPathTree(nextPath, {
                    max_depth: 0,
                    max_entries: 1,
                    include_hidden: false
                })

                if (probeTree.kind === 'folder') {
                    return nextPath
                }
            } catch (error) {
                lastError =
                    error instanceof Error
                        ? error
                        : new Error('Failed to inspect the dropped path.')
            }
        }

        throw (
            lastError ??
            new Error(
                'Please choose or drop a folder. Files are not supported.'
            )
        )
    }

    const getErrorMessage = (error: unknown, fallback: string) => {
        if (error instanceof Error && error.message.trim()) {
            return error.message
        }

        if (typeof error === 'string' && error.trim()) {
            return error
        }

        if (
            typeof error === 'object' &&
            error !== null &&
            'message' in error &&
            typeof error.message === 'string' &&
            error.message.trim()
        ) {
            return error.message
        }

        return fallback
    }

    const handleLoadPath = async (pathValue?: string | string[]) => {
        if (isLoadingPath) {
            return
        }

        setIsLoadingPath(true)
        setLoadError(null)

        try {
            const resolvedPath = await resolveFolderPath(
                Array.isArray(pathValue) ? pathValue : [pathValue ?? sourcePath]
            )

            setSourcePath(resolvedPath)

            const sourceTree = await coworkService.readPathTree(resolvedPath, {
                ...ORGANIZE_TREE_READ_OPTIONS
            })

            const treePair = {
                source_root: resolvedPath,
                result_root: resolvedPath,
                source_tree: sourceTree,
                result_tree: null
            }
            const persistedSession =
                await coworkService.createOrganizeSession(treePair)

            setLoadedTreePair({
                source_root:
                    persistedSession.organize_tree_pair?.source_root ??
                    resolvedPath,
                result_root:
                    persistedSession.organize_tree_pair?.result_root ??
                    resolvedPath,
                source_tree:
                    persistedSession.organize_tree_pair?.source_tree ??
                    sourceTree,
                result_tree:
                    persistedSession.organize_tree_pair?.result_tree ?? null
            })
            onSessionCreated?.(persistedSession)
            setActiveStep('source')
            setIsProcessing(true)
        } catch (error) {
            setLoadError(
                getErrorMessage(
                    error,
                    'Failed to load the path from your machine.'
                )
            )
        } finally {
            setIsLoadingPath(false)
        }
    }

    useEffect(() => {
        if (isProcessing) {
            return
        }

        let isMounted = true

        const registerListener = async () => {
            const currentWindow = getCurrentWindow()
            const unlisten = await currentWindow.onDragDropEvent((event) => {
                if (!isMounted) {
                    return
                }

                if (
                    event.payload.type === 'enter' ||
                    event.payload.type === 'over'
                ) {
                    setIsDragActive(true)
                    return
                }

                if (event.payload.type === 'leave') {
                    setIsDragActive(false)
                    return
                }

                if (event.payload.type === 'drop') {
                    setIsDragActive(false)
                    if (event.payload.paths.length > 0) {
                        void handleLoadPath(event.payload.paths)
                    }
                }
            })

            if (!isMounted) {
                unlisten()
            }

            return unlisten
        }

        let cleanup: (() => void) | undefined

        void registerListener().then((unlisten) => {
            cleanup = unlisten
        })

        return () => {
            isMounted = false
            cleanup?.()
        }
    }, [isProcessing])

    const handlePickFolder = async () => {
        if (isLoadingPath) {
            return
        }

        setLoadError(null)

        try {
            const pickedPath = await coworkService.pickFolderPath(sourcePath)
            if (!pickedPath) {
                return
            }

            await handleLoadPath(pickedPath)
        } catch (error) {
            setLoadError(
                getErrorMessage(error, 'Failed to open the folder picker.')
            )
        }
    }

    return (
        <AnimatePresence mode="wait" initial={false}>
            {!isProcessing ? (
                <motion.div
                    key={`organize-entry-${resetVersion}`}
                    initial={{ opacity: 0, y: 18, scale: 0.985 }}
                    animate={{ opacity: 1, y: 0, scale: 1 }}
                    exit={{ opacity: 0, y: -12, scale: 0.99 }}
                    transition={{ duration: 0.2, ease: 'easeOut' }}
                    className={cn(
                        'relative flex h-full w-full items-center justify-center bg-white p-6 transition-colors dark:bg-white/[0.01]',
                        isDragActive && 'bg-[#eef8fb] dark:bg-[#091112]'
                    )}
                >
                    <div
                        className={cn(
                            'pointer-events-none absolute inset-4 rounded-[40px] border-2 border-dashed opacity-0 transition-all duration-150',
                            isDragActive &&
                                'border-firefly bg-firefly/5 opacity-100 dark:border-sky-blue dark:bg-sky-blue/8'
                        )}
                    />
                    <div
                        className={cn(
                            'relative w-full max-w-2xl rounded-[32px] border border-neutral-200 bg-white p-8 text-center shadow-sm transition-all duration-200 dark:border-white/20 dark:bg-white/[0.03]',
                            isDragActive &&
                                'translate-y-[-2px] border-firefly shadow-[0_24px_80px_rgba(15,157,206,0.16)] dark:border-sky-blue'
                        )}
                    >
                        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-black/50 dark:text-white/50">
                            Intelligent Folder
                        </p>
                        <h2 className="mt-3 text-2xl font-semibold text-black dark:text-white">
                            Start a new Intelligent Folder session
                        </h2>
                        {/* <p className="mt-3 text-sm text-black/60 dark:text-white/60">
                            Enter a local path, browse with the native picker, or
                            drop a folder anywhere on this screen.
                        </p> */}
                        <div className="mx-auto mt-8 max-w-xl rounded-[28px] border border-neutral-200 bg-[#f8fafb] p-4 text-left dark:border-white/15 dark:bg-[#121716]">
                            <label
                                htmlFor="organize-source-path"
                                className="text-xs font-semibold uppercase tracking-[0.2em] text-black/50 dark:text-white/50"
                            >
                                Source path
                            </label>
                            <div className="mt-3 flex flex-col gap-3 md:flex-row">
                                <Input
                                    id="organize-source-path"
                                    value={sourcePath}
                                    onChange={(event) =>
                                        setSourcePath(event.target.value)
                                    }
                                    onKeyDown={(event) => {
                                        if (event.key === 'Enter') {
                                            event.preventDefault()
                                            void handleLoadPath()
                                        }
                                    }}
                                    placeholder="/home/user/folder"
                                    className="h-10 flex-1 rounded-full border-neutral-300 bg-white px-4 dark:border-white/15 dark:bg-black"
                                />
                                <Button
                                    type="button"
                                    className="h-10 rounded-full bg-firefly px-6 text-sm font-semibold text-sky-blue-2 hover:bg-firefly/90 dark:bg-sky-blue dark:text-black"
                                    onClick={() => {
                                        void handleLoadPath()
                                    }}
                                    disabled={
                                        !sourcePath.trim() || isLoadingPath
                                    }
                                >
                                    {isLoadingPath ? (
                                        <>
                                            <LoaderCircle className="size-4 animate-spin" />
                                            Loading
                                        </>
                                    ) : (
                                        'Load path'
                                    )}
                                </Button>
                            </div>
                            <div
                                className={cn(
                                    'mt-3 rounded-[24px] border border-dashed px-4 py-5 text-center transition-colors',
                                    isDragActive
                                        ? 'border-firefly bg-firefly/8 dark:border-sky-blue dark:bg-sky-blue/10'
                                        : 'border-neutral-300 bg-white/70 dark:border-white/15 dark:bg-black/20'
                                )}
                            >
                                <div className="flex flex-col items-center gap-3">
                                    <span
                                        className={cn(
                                            'flex size-11 items-center justify-center rounded-2xl border',
                                            isDragActive
                                                ? 'border-firefly/20 bg-firefly/10 text-firefly dark:border-sky-blue/20 dark:bg-sky-blue/10 dark:text-sky-blue'
                                                : 'border-neutral-300 bg-white text-black/60 dark:border-white/15 dark:bg-black dark:text-white/60'
                                        )}
                                    >
                                        <FolderOpen className="size-5" />
                                    </span>
                                    <div>
                                        <p className="text-sm font-semibold text-black dark:text-white">
                                            Drag and drop folders only
                                        </p>
                                        <p className="mt-1 text-sm text-black/55 dark:text-white/55">
                                            Or open the native folder picker to
                                            choose a folder from your machine.
                                        </p>
                                    </div>
                                    <Button
                                        type="button"
                                        variant="outline"
                                        className="h-10 rounded-full border-firefly px-5 text-sm font-semibold text-firefly hover:bg-firefly/5 dark:border-sky-blue dark:text-sky-blue dark:hover:bg-sky-blue/10"
                                        onClick={() => {
                                            void handlePickFolder()
                                        }}
                                        disabled={isLoadingPath}
                                    >
                                        <FolderOpen className="size-4" />
                                        Browse folders
                                    </Button>
                                </div>
                            </div>
                            {loadError && (
                                <p className="mt-3 rounded-2xl border border-red-500/20 bg-red-500/8 px-4 py-3 text-sm text-red-700 dark:text-red-300">
                                    {loadError}
                                </p>
                            )}
                        </div>
                    </div>
                </motion.div>
            ) : (
                <motion.div
                    key={`organize-process-${sessionContentKey}`}
                    initial={{ opacity: 0, y: 18, scale: 0.992 }}
                    animate={{ opacity: 1, y: 0, scale: 1 }}
                    exit={{ opacity: 0, y: -12, scale: 0.992 }}
                    transition={{ duration: 0.2, ease: 'easeOut' }}
                    className="h-full w-full overflow-hidden bg-white dark:bg-white/[0.01]"
                >
                    <div className="flex h-full flex-col items-center justify-between px-3 pb-8 pt-8 md:p-6">
                        <CoworkOrganizeSteps
                            activeStep={activeStep}
                            onSelectStep={setActiveStep}
                        />
                        <div className="relative flex min-h-0 w-full flex-1 pt-6">
                            <AnimatePresence mode="wait" initial={false}>
                                <motion.div
                                    key={`${sessionContentKey}-${activeStep}`}
                                    initial={{
                                        opacity: 0,
                                        filter: 'blur(6px)'
                                    }}
                                    animate={{
                                        opacity: 1,
                                        filter: 'blur(0px)'
                                    }}
                                    exit={{ opacity: 1, filter: 'blur(0px)' }}
                                    transition={organizeStepTransition}
                                    className="flex min-h-0 w-full flex-1"
                                >
                                    {activeStep === 'source' && (
                                        <CoworkOrganizeSource
                                            rootSource={
                                                organizeTreePair?.source_root ??
                                                'root_source'
                                            }
                                            tree={organizeTreePair?.source_tree}
                                        />
                                    )}
                                    {activeStep === 'build' && (
                                        <CoworkOrganizeBuild
                                            session={session}
                                            liveSession={liveSession}
                                            isRunning={
                                                isSending ||
                                                hasStreamingBuildActivity ||
                                                session?.run_status ===
                                                    'thinking'
                                            }
                                            requestedAction={
                                                requestedBuildAction
                                            }
                                            requestedActionToken={
                                                requestedBuildActionToken
                                            }
                                        />
                                    )}
                                    {activeStep === 'result' && (
                                        <CoworkOrganizeResult
                                            rootResult={
                                                organizeTreePair?.result_root ??
                                                'root_result'
                                            }
                                            tree={modeResultTree}
                                        />
                                    )}
                                </motion.div>
                            </AnimatePresence>
                            <div
                                className={cn(
                                    'pointer-events-none absolute inset-0 z-10 rounded-[32px] bg-white/55 opacity-0 backdrop-blur-[2px] transition-opacity dark:bg-black/30',
                                    isSessionLoading && 'opacity-100'
                                )}
                            >
                                <div className="flex h-full items-start justify-end p-4">
                                    <div className="rounded-full border border-firefly/15 bg-white px-3 py-1.5 text-xs font-semibold text-black/65 shadow-sm dark:border-sky-blue/20 dark:bg-[#121716] dark:text-white/70">
                                        Switching session...
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </motion.div>
            )}
        </AnimatePresence>
    )
}

export default OrganizeFileFolderMode
