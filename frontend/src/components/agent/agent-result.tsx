import { useRef, useState, useEffect, useMemo } from 'react'
import { toast } from 'sonner'

import { useSocketIOContext } from '@/contexts/websocket-context'
import {
    selectActiveTab,
    selectIsLoading,
    selectIsSandboxIframeAwake,
    selectMessages,
    selectResultUrl,
    selectSandboxStatus,
    useAppSelector
} from '@/state'
import { TAB, TOOL } from '@/typings/agent'
import SlidesResult from './slides-result'
import { Icon } from '../ui/icon'
import AwakeMeUpScreen from './awake-me-up-screen'
import { useLocation, useParams } from 'react-router'

interface AgentResultProps {
    className?: string
}

const AgentResult = ({ className }: AgentResultProps) => {
    const iframeRef = useRef<HTMLIFrameElement>(null)
    const [iframeKey, setIframeKey] = useState(0)
    const [isLoading, setIsLoading] = useState(false)
    const { socket } = useSocketIOContext()
    const { sessionId } = useParams()
    const location = useLocation()

    const resultUrl = useAppSelector(selectResultUrl)
    const activeTab = useAppSelector(selectActiveTab)
    const isSandboxIframeAwake = useAppSelector(selectIsSandboxIframeAwake)
    const sandboxStatus = useAppSelector(selectSandboxStatus)
    const messages = useAppSelector(selectMessages)
    const isRunning = useAppSelector(selectIsLoading)
    const isShareMode = useMemo(
        () => location.pathname.includes('/share/'),
        [location.pathname]
    )

    const hasSlideTools = useMemo(
        () =>
            messages.some(
                (message) =>
                    message.action?.type === TOOL.SLIDE_WRITE ||
                    message.action?.type === TOOL.SLIDE_EDIT ||
                    message.action?.type === TOOL.SLIDE_APPLY_PATCH
            ),
        [messages]
    )

    const handleCopy = () => {
        if (!resultUrl) return
        navigator.clipboard.writeText(resultUrl)
        toast.success('Copied to clipboard')
    }

    const handleRefresh = () => {
        setIframeKey((prev) => prev + 1)
        if (socket?.connected) {
            socket.emit('chat_message', { type: 'sandbox_status', session_uuid: sessionId })
        }
    }

    const detectUrlType = (url: string): 'website' | 'image' | 'video' => {
        try {
            const parsed = new URL(url)
            const pathname = parsed.pathname.toLowerCase()

            // Common image extensions
            const imageExt = [
                '.png',
                '.jpg',
                '.jpeg',
                '.gif',
                '.bmp',
                '.webp',
                '.svg'
            ]
            // Common video extensions
            const videoExt = [
                '.mp4',
                '.mov',
                '.avi',
                '.mkv',
                '.webm',
                '.flv',
                '.wmv'
            ]

            if (imageExt.some((ext) => pathname.endsWith(ext))) {
                return 'image'
            }
            if (videoExt.some((ext) => pathname.endsWith(ext))) {
                return 'video'
            }

            return 'website'
        } catch {
            return 'website' // fallback if URL is invalid
        }
    }

    const handleAwakeClick = () => {
        setIsLoading(true)
        if (socket?.connected) {
            socket.emit('chat_message', { type: 'awake_sandbox', session_uuid: sessionId })
        }
    }

    const shouldShowAwakeScreen = useMemo(() => {
        return (
            sandboxStatus === 'paused' &&
            !isSandboxIframeAwake &&
            !isRunning &&
            !isShareMode
        )
    }, [sandboxStatus, isSandboxIframeAwake, isRunning, isShareMode])

    // Extract slide data from SlideWrite and SlideEdit messages
    const slideContent = useMemo(() => {
        const slidesMap = new Map<number, string>()

        messages
            .filter(
                (message) =>
                    message.action?.type === TOOL.SLIDE_WRITE ||
                    message.action?.type === TOOL.SLIDE_EDIT ||
                    message.action?.type === TOOL.SLIDE_APPLY_PATCH
            )
            .forEach((message, index) => {
                let content = (
                    message.action?.data?.result as { content: string }
                )?.content

                if (Array.isArray(message.action?.data?.result)) {
                    content = (
                        message.action?.data?.result as {
                            new_content: string
                        }[]
                    )[0]?.new_content
                }

                if (content) {
                    // Extract slide number from tool input if available
                    const slideNumber =
                        message.action?.data?.tool_input?.slide_number ||
                        index + 1

                    // Update the content for this slide number (overwrites if duplicate)
                    slidesMap.set(slideNumber, content)
                }
            })

        // Convert map to array, sorted by slide number
        return Array.from(slidesMap.entries())
            .sort(([a], [b]) => a - b)
            .map(([slideNumber, content]) => ({
                slideNumber,
                content
            }))
    }, [messages])

    useEffect(() => {
        if (activeTab === TAB.RESULT) {
            handleRefresh()
        }
    }, [activeTab])

    useEffect(() => {
        if (isSandboxIframeAwake) {
            setIsLoading(false)
        }
    }, [isSandboxIframeAwake])

    if (hasSlideTools && activeTab === TAB.RESULT) {
        return (
            <SlidesResult
                key={JSON.stringify(slideContent)}
                className={className}
            />
        )
    }

    if (shouldShowAwakeScreen)
        return (
            <AwakeMeUpScreen
                isLoading={isLoading}
                onAwakeClick={handleAwakeClick}
            />
        )

    if (!resultUrl) return null

    return (
        <div
            className={`flex flex-col items-center w-full h-full bg-white dark:bg-charcoal ${className}`}
        >
            <div className="w-full flex items-center justify-between pl-6 pr-4 py-2 gap-4 overflow-hidden border-b border-white/30">
                <div className="rounded-lg w-full flex items-center gap-4 group transition-colors">
                    <button className="cursor-pointer" onClick={handleRefresh}>
                        <Icon
                            name="refresh"
                            className="size-5 stroke-black dark:stroke-white"
                        />
                    </button>
                    <span className="text-sm text-black bg-[#f4f4f4] dark:bg-white line-clamp-1 break-all flex-1 font-semibold px-4 py-1 rounded-sm">
                        {resultUrl}
                    </span>
                </div>
                <div className="flex items-center gap-4">
                    <button className="cursor-pointer" onClick={handleCopy}>
                        <Icon
                            name="copy"
                            className="size-5 fill-black dark:fill-white"
                        />
                    </button>
                    <button
                        className="cursor-pointer"
                        onClick={() => window.open(resultUrl, '_blank')}
                    >
                        <Icon
                            name="maximize"
                            className="size-5 fill-black dark:fill-white"
                        />
                    </button>
                </div>
            </div>
            {detectUrlType(resultUrl) === 'image' ? (
                <div className="max-h-[calc(100vh-159px)]">
                    <img
                        src={resultUrl}
                        className="w-full h-full object-contain object-top flex-1"
                    />
                </div>
            ) : detectUrlType(resultUrl) === 'video' ? (
                <video
                    loop
                    muted
                    controls
                    src={resultUrl}
                    className="w-full h-full object-contain object-top flex-1 max-h-[calc(100vh-159px)]"
                />
            ) : (
                <iframe
                    key={iframeKey}
                    ref={iframeRef}
                    src={resultUrl}
                    className="w-full h-full flex-1"
                />
            )}
        </div>
    )
}

export default AgentResult
