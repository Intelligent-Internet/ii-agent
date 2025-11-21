import { useRef, useState, useEffect, useMemo } from 'react'
import clsx from 'clsx'
import { toast } from 'sonner'

import { Button } from '../ui/button'
import { Context, ContextTrigger } from '@/components/ai-elements/context'
import { selectContext } from '@/state/slice/context'
import { useAppSelector } from '@/state/store'
import { Icon } from '../ui/icon'
import ChatMessage from './chat-message'
import { useWebSocketContext } from '@/contexts/websocket-context'
import {
    selectEditingMessage,
    selectIsAgentInitialized,
    selectMessages,
    selectSelectedModel,
    selectToolSettings,
    selectUploadedFiles,
    setCompleted,
    setEditingMessage,
    setLoading,
    setMessages,
    setStopped,
    useAppDispatch,
    useAppSelector
} from '@/state'
import { useSessionManager } from '@/hooks/use-session-manager'
import { useParams } from 'react-router'
import { useAppEvents } from '@/hooks/use-app-events'
import { useQuestionHandlers } from '@/hooks/use-question-handlers'
import AgentFiles from './agent-files'
import { useIsMobile } from '@/hooks/use-mobile'

type ChatTab = 'chat' | 'design' | 'files'

interface ChatBoxProps {
    isShareMode?: boolean
    className?: string
    activeTab?: ChatTab
    onTabChange?: (tab: ChatTab) => void
    isVisible?: boolean
}

const ChatBox = ({
    isShareMode = false,
    className = '',
    activeTab,
    onTabChange,
    isVisible = true
}: ChatBoxProps) => {
    const dispatch = useAppDispatch()
    const { sessionId } = useParams()

    const messagesEndRef = useRef<HTMLDivElement>(null)
    const { handleEvent, handleClickAction } = useAppEvents()

    const { isReplayMode, processAllEventsImmediately, isLoadingSession } =
        useSessionManager({
            handleEvent
        })

    // Session management handled by websocket context

    const { socket, connectSocket, sendMessage } = useWebSocketContext()

    const { handleEnhancePrompt, handleQuestionSubmit, handleKeyDown } =
        useQuestionHandlers()

    const uploadedFiles = useAppSelector(selectUploadedFiles)
    const editingMessage = useAppSelector(selectEditingMessage)
    const messages = useAppSelector(selectMessages)
    const toolSettings = useAppSelector(selectToolSettings)
    const isAgentInitialized = useAppSelector(selectIsAgentInitialized)
    const selectedModel = useAppSelector(selectSelectedModel)

    const [internalActiveTab, setInternalActiveTab] = useState<ChatTab>('chat')
    const isMobile = useIsMobile()

    useEffect(() => {
        if (activeTab !== undefined) {
            setInternalActiveTab(activeTab)
        }
    }, [activeTab])

    const currentActiveTab = useMemo(
        () => activeTab ?? internalActiveTab,
        [activeTab, internalActiveTab]
    )

    const handleTabChange = (tab: ChatTab) => {
        if (currentActiveTab !== tab) {
            setInternalActiveTab(tab)
        }
        onTabChange?.(tab)
    }

    const handleCancelQuery = () => {
        if (!socket || !socket.connected) {
            toast.error('Socket.IO connection is not open.')
            return
        }

        // Send cancel message to the server
        sendMessage({
            type: 'cancel',
            content: {}
        })
        dispatch(setLoading(false))
        dispatch(setStopped(true))
    }

    const handleEditMessage = (newQuestion: string) => {
        if (!socket || !socket.connected) {
            toast.error('Socket.IO connection is not open. Please try again.')
            dispatch({ type: 'SET_LOADING', payload: false })
            return
        }

        sendMessage({
            type: 'edit_query',
            content: {
                text: newQuestion,
                files: uploadedFiles?.map((file) => `.${file}`)
            }
        })

        // Update the edited message and remove all subsequent messages
        const editIndex = messages.findIndex((m) => m.id === editingMessage?.id)

        if (editIndex >= 0) {
            const updatedMessages = [...messages.slice(0, editIndex + 1)]
            updatedMessages[editIndex] = {
                ...updatedMessages[editIndex],
                content: newQuestion
            }
            dispatch(setMessages(updatedMessages))
        }

        dispatch(setCompleted(false))
        dispatch(setStopped(false))
        dispatch(setLoading(true))
        dispatch(setEditingMessage(undefined))
    }

    const handleReviewResult = () => {
        if (!socket || !socket.connected) {
            toast.error('Socket.IO connection is not open. Please try again.')
            dispatch({ type: 'SET_LOADING', payload: false })
            return
        }
        const { thinking_tokens, ...tool_args } = toolSettings

        dispatch({ type: 'SET_LOADING', payload: true })
        dispatch({ type: 'SET_COMPLETED', payload: false })

        // Only send init_agent event if agent is not already initialized
        if (!isAgentInitialized) {
            sendMessage({
                type: 'init_agent',
                content: {
                    model_name: selectedModel,
                    tool_args,
                    thinking_tokens
                }
            })
        }

        // Find the last user message
        const userMessages = messages.filter((msg) => msg.role === 'user')
        const lastUserMessage =
            userMessages.length > 0
                ? userMessages[userMessages.length - 1].content
                : ''

        sendMessage({
            type: 'review_result',
            content: {
                user_input: lastUserMessage
            }
        })
    }

    useEffect(() => {
        if (!isMobile || !isVisible || currentActiveTab !== 'chat') {
            return
        }
        window.requestAnimationFrame(() => {
            messagesEndRef.current?.scrollIntoView({
                behavior: 'smooth'
            })
        })
    }, [currentActiveTab, isVisible, isMobile])

    return (
        <div
            className={`relative h-full w-full md:w-[600px] md:border-l pt-4 md:pt-0 md:border-neutral-200 md:dark:border-white/30 ${className}`}
        >
            {isLoadingSession && (
                <div className="absolute inset-0 z-20 flex items-center justify-center bg-white/85 dark:bg-charcoal/85">
                    <div className="flex flex-col items-center gap-3 text-firefly dark:text-white">
                        <Icon
                            name="loading"
                            className="size-10 animate-spin fill-firefly dark:fill-white"
                        />
                        <span className="text-sm font-medium uppercase tracking-wide">
                            Loading session
                        </span>
                    </div>
                </div>
            )}
                <div className="hidden md:flex gap-x-2 items-center p-4">
                <Button
                    className={clsx(
                        'h-7 text-xs font-semibold px-4 rounded-full border border-sky-blue',
                        {
                            'bg-firefly border-firefly dark:border-sky-blue-2 dark:bg-sky-blue text-sky-blue-2 dark:text-black':
                                currentActiveTab === 'chat',
                            'dark:border-sky-blue border-firefly dark:text-sky-blue':
                                currentActiveTab !== 'chat'
                        }
                    )}
                    onClick={() => handleTabChange('chat')}
                >
                    Chat
                </Button>
                {/* Context usage indicator */}
                <div className="ml-auto">
                    {(() => {
                        const ctx = useAppSelector(selectContext)
                        if (!ctx) return null
                        return (
                            <Context usedTokens={ctx.usedTokens} maxTokens={ctx.maxTokens} usage={ctx.usage} modelId={ctx.modelId}>
                                <ContextTrigger />
                            </Context>
                        )
                    })()}
                </div>
                <Button
                    className={clsx(
                        'h-7 text-xs font-semibold px-4 rounded-full border border-sky-blue hidden',
                        {
                            'bg-firefly border-firefly dark:border-sky-blue-2 dark:bg-sky-blue text-sky-blue-2 dark:text-black':
                                currentActiveTab === 'design',
                            'dark:border-sky-blue border-firefly dark:text-sky-blue':
                                currentActiveTab !== 'design'
                        }
                    )}
                    onClick={() => handleTabChange('design')}
                >
                    Design
                </Button>
                <Button
                    className={clsx(
                        'h-7 text-xs font-semibold px-4 rounded-full border border-sky-blue',
                        {
                            'bg-firefly border-firefly dark:border-sky-blue-2 dark:bg-sky-blue text-sky-blue-2 dark:text-black':
                                currentActiveTab === 'files',
                            'dark:border-sky-blue border-firefly dark:text-sky-blue':
                                currentActiveTab !== 'files'
                        }
                    )}
                    onClick={() => handleTabChange('files')}
                >
                    All files
                </Button>
            </div>
            <div
                className={clsx(
                    'h-[calc(100vh-116px)] md:h-[calc(100vh-145px)] overflow-y-auto overflow-x-hidden',
                    {
                        hidden: currentActiveTab !== 'chat'
                    }
                )}
            >
                <ChatMessage
                    handleClickAction={handleClickAction}
                    isReplayMode={isReplayMode}
                    messagesEndRef={messagesEndRef}
                    setCurrentQuestion={(value) =>
                        dispatch({
                            type: 'SET_CURRENT_QUESTION',
                            payload: value
                        })
                    }
                    handleKeyDown={handleKeyDown}
                    handleQuestionSubmit={handleQuestionSubmit}
                    handleEnhancePrompt={handleEnhancePrompt}
                    handleCancel={handleCancelQuery}
                    handleEditMessage={handleEditMessage}
                    processAllEventsImmediately={processAllEventsImmediately}
                    connectWebSocket={connectSocket}
                    handleReviewSession={handleReviewResult}
                    isShareMode={isShareMode}
                />
            </div>
            <div
                className={clsx(
                    'h-[calc(100vh-116px)] md:h-[calc(100vh-145px)] overflow-y-auto overflow-x-hidden',
                    {
                        hidden: currentActiveTab !== 'files'
                    }
                )}
            >
                <AgentFiles
                    isActive={currentActiveTab === 'files'}
                    sessionId={sessionId}
                />
            </div>
        </div>
    )
}

export default ChatBox
