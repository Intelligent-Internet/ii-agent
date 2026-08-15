import { AnimatePresence, motion } from 'framer-motion'
import { useMemo, useRef, useState } from 'react'
import clsx from 'clsx'
import ChatMessage from '@/components/agent/chat-message'
import { Button } from '@/components/ui/button'
import { useAppDispatch } from '@/state'
import { setCurrentQuestion } from '@/state'
import type { ActionStep } from '@/typings/agent'
import type {
    CoworkChatScope,
    CoworkChatFile,
    CoworkChatSessionDetail,
    CoworkLiveSessionState
} from '@/typings/cowork'
import { useCoworkChatMessageAdapter } from './use-cowork-chatmessage-adapter'
import CoworkModelSelector from './cowork-model-selector'

interface CoworkChatBoxProps {
    className?: string
    isVisible?: boolean
    scope: CoworkChatScope
    activeSession: CoworkChatSessionDetail | null
    liveSession?: CoworkLiveSessionState | null
    isLoading?: boolean
    isSending?: boolean
    isInputLocked?: boolean
    onSendMessage: (content: string) => Promise<void> | void
    onStopSession?: () => Promise<void> | void
    onSelectAction?: (action: ActionStep) => void
}

type CoworkChatTab = 'chat' | 'files'

const formatFileSize = (size: number) => {
    if (size >= 1024 * 1024) {
        return `${(size / (1024 * 1024)).toFixed(1)} MB`
    }
    if (size >= 1024) {
        return `${Math.round(size / 1024)} KB`
    }
    return `${size} B`
}

const COWORK_HIDE_UPLOAD_SCOPE_CLASS = 'cowork-chat-box--hide-upload'

const CoworkChatBox = ({
    className = '',
    isVisible = true,
    scope,
    activeSession,
    liveSession = null,
    isLoading = false,
    isSending = false,
    isInputLocked = false,
    onSendMessage,
    onStopSession,
    onSelectAction
}: CoworkChatBoxProps) => {
    const dispatch = useAppDispatch()
    const [activeTab, setActiveTab] = useState<CoworkChatTab>('chat')
    const messagesEndRef = useRef<HTMLDivElement>(null)

    useCoworkChatMessageAdapter({
        activeSession,
        liveSession,
        isLoading,
        isSending
    })

    const sessionFiles = activeSession?.files ?? []
    const hasUserStartedChat = Boolean(
        activeSession?.messages.some((message) => message.role === 'user')
    )
    const sessionContentKey = useMemo(
        () => activeSession?.id ?? `empty-${scope}`,
        [activeSession?.id, scope]
    )
    const emptyStateDescription =
        scope === 'intelligent-folder'
            ? 'Start a Cowork chat session to understand, discuss, and folder your folder.'
            : 'Start a new Cowork chat to discuss your task.'
    const responsiveChatBoxWidthClass = 'md:w-[clamp(320px,38vw,600px)]'

    if (!isVisible) return null

    return (
        <div
            className={clsx(
                'relative h-full w-full min-w-0 overflow-hidden pt-4 md:shrink md:border-l md:border-neutral-200 md:pt-0 md:dark:border-white/30',
                COWORK_HIDE_UPLOAD_SCOPE_CLASS,
                responsiveChatBoxWidthClass,
                className
            )}
        >
            <style>{`
                .${COWORK_HIDE_UPLOAD_SCOPE_CLASS} div:has(> input#file-upload) > :first-child {
                    display: none;
                }
            `}</style>
            <div className="hidden md:flex gap-x-2 items-center p-4">
                <Button
                    className={clsx(
                        'h-7 text-xs font-semibold px-4 rounded-full border border-sky-blue',
                        {
                            'bg-firefly border-firefly dark:border-sky-blue-2 dark:bg-sky-blue text-sky-blue-2 dark:text-black':
                                activeTab === 'chat',
                            'dark:border-sky-blue border-firefly dark:text-sky-blue':
                                activeTab !== 'chat'
                        }
                    )}
                    onClick={() => setActiveTab('chat')}
                >
                    Chat
                </Button>
                <Button
                    className={clsx(
                        'h-7 text-xs font-semibold px-4 rounded-full border border-sky-blue',
                        {
                            'bg-firefly border-firefly dark:border-sky-blue-2 dark:bg-sky-blue text-sky-blue-2 dark:text-black':
                                activeTab === 'files',
                            'dark:border-sky-blue border-firefly dark:text-sky-blue':
                                activeTab !== 'files'
                        }
                    )}
                    onClick={() => setActiveTab('files')}
                >
                    All files
                </Button>
                <CoworkModelSelector className="ml-auto" />
            </div>

            <div
                className={clsx('h-[calc(100vh-145px)]', {
                    hidden: activeTab !== 'chat'
                })}
            >
                <div className="relative h-full">
                    <div className="h-full">
                        <ChatMessage
                            isReplayMode={false}
                            messagesEndRef={messagesEndRef}
                            handleClickAction={(action) => {
                                if (action) {
                                    onSelectAction?.(action)
                                }
                            }}
                            setCurrentQuestion={(value) =>
                                dispatch(setCurrentQuestion(value))
                            }
                            handleKeyDown={(event) => {
                                dispatch(
                                    setCurrentQuestion(
                                        event.currentTarget.value
                                    )
                                )
                            }}
                            handleQuestionSubmit={(question) => {
                                if (isInputLocked || isSending) {
                                    return
                                }
                                dispatch(setCurrentQuestion(''))
                                void onSendMessage(question)
                            }}
                            handleEnhancePrompt={() => {}}
                            handleCancel={() => {
                                void onStopSession?.()
                            }}
                            handleEditMessage={() => {}}
                            connectWebSocket={() => {}}
                            handleReviewSession={() => {}}
                            submitDisabled={isInputLocked}
                        />
                    </div>

                    {!hasUserStartedChat && !isSending && !isLoading && (
                        <div className="pointer-events-none absolute left-3 right-3 top-0 z-[1] md:left-4 md:right-4">
                            <div className="inline-block text-left rounded-lg text-black dark:text-white w-full">
                                <p className="text-sm font-semibold text-black dark:text-white">
                                    New chat
                                </p>
                                <p className="text-sm text-black/60 dark:text-white/60">
                                    {emptyStateDescription}
                                </p>
                            </div>
                        </div>
                    )}

                    <div
                        className={clsx(
                            'pointer-events-none absolute inset-0 z-10 bg-white/45 opacity-0 backdrop-blur-[2px] transition-opacity dark:bg-black/20',
                            isLoading && 'opacity-100'
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

            <div
                className={clsx(
                    'h-[calc(100vh-145px)] overflow-y-auto overflow-x-hidden',
                    {
                        hidden: activeTab !== 'files'
                    }
                )}
            >
                <div className="px-3 md:px-4 py-4 h-full">
                    <div className="relative flex h-full flex-col gap-4">
                        <AnimatePresence mode="wait">
                            <motion.div
                                key={`files-${sessionContentKey}`}
                                initial={{ opacity: 0, x: 16 }}
                                animate={{ opacity: 1, x: 0 }}
                                exit={{ opacity: 0, x: -12 }}
                                transition={{
                                    duration: 0.2,
                                    ease: 'easeOut'
                                }}
                                className="flex h-full flex-col gap-4"
                            >
                                <div className="rounded-[24px] border border-neutral-200 bg-white px-4 py-4 dark:border-white/15 dark:bg-white/[0.03]">
                                    <p className="text-xs font-semibold uppercase tracking-[0.2em] text-black/50 dark:text-white/50">
                                        All files
                                    </p>
                                    <p className="mt-2 text-sm text-black/60 dark:text-white/60">
                                        Files associated with the active Cowork
                                        session.
                                    </p>
                                </div>
                                <div className="min-h-0 flex-1 space-y-3">
                                    {sessionFiles.length > 0 ? (
                                        sessionFiles.map(
                                            (file: CoworkChatFile) => (
                                                <div
                                                    key={file.id}
                                                    className="rounded-[24px] border border-neutral-200 bg-white px-4 py-4 dark:border-white/15 dark:bg-white/[0.03]"
                                                >
                                                    <div className="flex items-start justify-between gap-3">
                                                        <div className="min-w-0">
                                                            <p className="truncate text-sm font-semibold text-black dark:text-white">
                                                                {file.file_name}
                                                            </p>
                                                            <p className="mt-1 text-xs text-black/50 dark:text-white/50">
                                                                {
                                                                    file.content_type
                                                                }
                                                            </p>
                                                        </div>
                                                        <div className="shrink-0 rounded-full border border-firefly/20 bg-firefly/5 px-3 py-1 text-xs font-semibold text-firefly dark:border-sky-blue/20 dark:bg-sky-blue/10 dark:text-sky-blue">
                                                            {formatFileSize(
                                                                file.file_size
                                                            )}
                                                        </div>
                                                    </div>
                                                </div>
                                            )
                                        )
                                    ) : (
                                        <div className="rounded-[24px] border border-neutral-200 bg-white px-4 py-5 text-sm text-black/60 dark:border-white/15 dark:bg-white/[0.03] dark:text-white/60">
                                            No files in this Cowork session yet.
                                        </div>
                                    )}
                                </div>
                            </motion.div>
                        </AnimatePresence>
                        <div
                            className={clsx(
                                'pointer-events-none absolute inset-0 z-10 bg-white/45 opacity-0 backdrop-blur-[2px] transition-opacity dark:bg-black/20',
                                isLoading && 'opacity-100'
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
            </div>
        </div>
    )
}

export default CoworkChatBox
