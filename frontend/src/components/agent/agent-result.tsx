import { useRef, useState, useEffect, useMemo } from 'react'
import { toast } from 'sonner'

import { useSocketIOContext } from '@/contexts/websocket-context'
import {
    selectActiveTab,
    selectIsLoading,
    selectIsSandboxIframeAwake,
    selectMessages,
    selectSandboxStatus,
    useAppSelector
} from '@/state'
import { CommandType, TAB, TOOL } from '@/typings/agent'
import SlidesResult from './slides-result'
import MobileResult from './mobile-result'
import { Icon } from '../ui/icon'
import AwakeMeUpScreen from './awake-me-up-screen'
import { useLocation, useParams } from 'react-router'
import { cn, isSandboxLink, rewriteLocalhostUrl } from '@/lib/utils'
import { DesignModeWrapper } from '@/components/design-mode'
import { useTranslation } from 'react-i18next'
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuTrigger
} from '@/components/ui/dropdown-menu'
import { Check } from 'lucide-react'
import {
    DEVICE_PRESETS,
    type DevicePreset
} from '@/components/design-mode/device-presets'

interface AgentResultProps {
    className?: string
}

const AgentResult = ({ className }: AgentResultProps) => {
    const { t } = useTranslation()
    const iframeRef = useRef<HTMLIFrameElement>(null)
    const [iframeKey, setIframeKey] = useState(0)
    const [isLoading, setIsLoading] = useState(false)
    const { socket, sendMessage } = useSocketIOContext()
    const { sessionId } = useParams()
    const location = useLocation()

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
                    message.action?.type === TOOL.SLIDE_APPLY_PATCH ||
                    message.action?.type === TOOL.SLIDE_GENERATE
            ),
        [messages]
    )

    const hasMobileAppTools = useMemo(
        () =>
            messages.some(
                (message) => message.action?.type === TOOL.MOBILE_APP_INIT
            ),
        [messages]
    )

    const resultUrl = useMemo(() => {
        // Check mobile app result first
        const mobileAppToolResult = [...messages]
            .reverse()
            .find(
                (message) =>
                    (message.action?.type === TOOL.MOBILE_APP_INIT ||
                        message.action?.type === TOOL.RESTART_MOBILE_SERVER) &&
                    message.action?.data?.result
            )

        const mobileAppResult = mobileAppToolResult?.action?.data?.result
        if (mobileAppResult && typeof mobileAppResult === 'object') {
            const webPreviewUrl = (
                mobileAppResult as { web_preview_url?: string }
            ).web_preview_url
            if (webPreviewUrl) {
                return rewriteLocalhostUrl(webPreviewUrl)
            }
        }

        // Check fullstack result second
        const fullstackResult = [...messages]
            .reverse()
            .find(
                (message) =>
                    message.action?.type === TOOL.FULLSTACK_PROJECT_INIT &&
                    message.action?.data?.result
            )

        const result = fullstackResult?.action?.data?.result
        if (result && typeof result === 'object') {
            const previewUrl = (result as { preview_url?: string }).preview_url
            if (previewUrl) {
                return rewriteLocalhostUrl(previewUrl)
            }
        }
        return ''
    }, [messages])

    const [selectedDeviceId, setSelectedDeviceId] = useState<
        DevicePreset['id']
    >(DEVICE_PRESETS[0].id)

    useEffect(() => {
        setSelectedDeviceId(DEVICE_PRESETS[0].id)
    }, [resultUrl])

    const selectedDevice = useMemo(
        () =>
            DEVICE_PRESETS.find((d) => d.id === selectedDeviceId) ??
            DEVICE_PRESETS[0],
        [selectedDeviceId]
    )

    const renderDeviceIcon = (device: DevicePreset) => {
        if (device.id === 'tablet-portrait')
            return (
                <Icon
                    name="device-tablet-vertical"
                    className="size-5 fill-black"
                />
            )
        if (device.id === 'tablet-landscape')
            return (
                <Icon
                    name="device-tablet-horizontal"
                    className="size-5 fill-black"
                />
            )
        if (device.id === 'phone-portrait')
            return (
                <Icon
                    name="device-phone-vertical"
                    className="size-5 fill-black"
                />
            )
        if (device.id === 'phone-landscape')
            return (
                <Icon
                    name="device-phone-horizontal"
                    className="size-5 fill-black"
                />
            )
        return <Icon name="device-desktop" className="size-5 fill-black" />
    }
    const restartMobileServerCount = useMemo(
        () =>
            messages.filter(
                (message) => message.action?.type === TOOL.RESTART_MOBILE_SERVER
            ).length,
        [messages]
    )

    const mobileAppUrl = useMemo(() => {
        const mobileAppToolResult = [...messages]
            .reverse()
            .find(
                (message) =>
                    (message.action?.type === TOOL.MOBILE_APP_INIT ||
                        message.action?.type === TOOL.RESTART_MOBILE_SERVER) &&
                    message.action?.data?.result
            )

        const mobileAppResult = mobileAppToolResult?.action?.data?.result
        if (mobileAppResult && typeof mobileAppResult === 'object') {
            const mobileAppUrl = (mobileAppResult as { qr_code_value?: string })
                .qr_code_value
            if (mobileAppUrl) {
                return mobileAppUrl
            }
        }
        return ''
    }, [messages])

    // sandbox_status is requested by the parent agent.tsx for both CODE and RESULT tabs

    const handleCopy = () => {
        if (!resultUrl) return
        navigator.clipboard.writeText(resultUrl)
        toast.success(t('common.copiedToClipboard'))
    }

    const handleRefresh = () => {
        setIframeKey((prev) => prev + 1)
        if (socket?.connected) {
            sendMessage({
                session_uuid: sessionId || '',
                content: { command: CommandType.SANDBOX_STATUS }
            })
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
            sendMessage({
                session_uuid: sessionId || '',
                content: { command: CommandType.AWAKE_SANDBOX }
            })
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
                    message.action?.type === TOOL.SLIDE_APPLY_PATCH ||
                    message.action?.type === TOOL.SLIDE_GENERATE
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

    // Check if design mode should be available (only for e2b sandbox websites)
    const isDesignModeAvailable = useMemo(() => {
        if (!resultUrl) return false
        if (!isSandboxLink(resultUrl)) return false
        if (detectUrlType(resultUrl) !== 'website') return false
        if (isShareMode) return false
        return true
    }, [resultUrl, isShareMode])

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

    if (!resultUrl && !mobileAppUrl) return null

    if (hasMobileAppTools && activeTab === TAB.RESULT) {
        return (
            <MobileResult
                resultUrl={resultUrl}
                mobileAppUrl={mobileAppUrl}
                refreshKey={restartMobileServerCount}
                className={className}
            />
        )
    }

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
                    {isDesignModeAvailable && (
                        <DropdownMenu>
                            <DropdownMenuTrigger asChild>
                                <button
                                    type="button"
                                    className="cursor-pointer"
                                    title={selectedDevice.name}
                                >
                                    <Icon
                                        name="responsive"
                                        className="size-5 fill-black dark:fill-white"
                                    />
                                </button>
                            </DropdownMenuTrigger>
                            <DropdownMenuContent
                                align="end"
                                className="h-[196px] w-[216px] rounded-xl bg-white p-4 text-black !shadow-[0px_4px_24px_rgba(0,0,0,0.16)]"
                            >
                                <div className="flex flex-col gap-4">
                                    {DEVICE_PRESETS.map((device) => {
                                        const isSelected =
                                            device.id === selectedDeviceId

                                        return (
                                            <DropdownMenuItem
                                                key={device.id}
                                                onClick={() =>
                                                    setSelectedDeviceId(
                                                        device.id
                                                    )
                                                }
                                                className={cn(
                                                    'h-5 !p-0 !px-0 !py-0 rounded-none',
                                                    'flex items-center gap-1.5',
                                                    'text-[14px] leading-[19px] text-black',
                                                    'hover:bg-gray-50 focus:bg-gray-50 focus:text-black'
                                                )}
                                            >
                                                {renderDeviceIcon(device)}
                                                <span className="flex-1">
                                                    {device.name}
                                                </span>
                                                <Check
                                                    className={cn(
                                                        'size-5 text-black transition-opacity',
                                                        isSelected
                                                            ? 'opacity-100'
                                                            : 'opacity-0'
                                                    )}
                                                    strokeWidth={1.5}
                                                />
                                            </DropdownMenuItem>
                                        )
                                    })}
                                </div>
                            </DropdownMenuContent>
                        </DropdownMenu>
                    )}
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
            ) : isDesignModeAvailable ? (
                <DesignModeWrapper
                    key={iframeKey}
                    src={resultUrl}
                    sessionId={sessionId}
                    deviceId={selectedDeviceId}
                    className="w-full h-full flex-1"
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
