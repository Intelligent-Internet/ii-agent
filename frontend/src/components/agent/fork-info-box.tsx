import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ExternalLinkIcon, PlayIcon, FileTextIcon, Loader2Icon } from 'lucide-react'
import { Link } from 'react-router'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import type { ForkInfo } from '@/typings/agent'
import { CommandType } from '@/typings/agent'
import { useSocketIOContext } from '@/contexts/websocket-context'
import {
    selectSelectedAgentModel,
    selectToolSettings,
    setLoading,
    setRunStatus,
    useAppDispatch,
    useAppSelector
} from '@/state'

interface ForkInfoBoxProps {
    sessionId: string
    forkInfo: ForkInfo
    llmSettingId?: string | null
    hasStarted?: boolean
}

export function ForkInfoBox({
    sessionId: _sessionId,
    forkInfo,
    llmSettingId,
    hasStarted = false
}: ForkInfoBoxProps) {
    const { t } = useTranslation()
    const dispatch = useAppDispatch()
    const { socket, sendMessage } = useSocketIOContext()
    const selectedModel = useAppSelector(selectSelectedAgentModel)
    const toolSettings = useAppSelector(selectToolSettings)
    const [isStarting, setIsStarting] = useState(false)

    const handleStart = () => {
        if (isStarting) return

        if (!socket || !socket.connected) {
            toast.error(t('agent.chatBox.errors.socketNotOpen'))
            return
        }

        setIsStarting(true)

        // Determine agent type based on fork_type
        const agentType = getAgentTypeForFork(forkInfo.fork_type)

        // Extract tool settings
        const { thinking_tokens, ...tool_args } = toolSettings

        // Send start_fork command - backend will read fork_info and construct the prompt
        sendMessage({
            session_uuid: _sessionId,
            content: {
                command: CommandType.START_FORK,
                model_id: llmSettingId || selectedModel,
                source: llmSettingId ? 'user' : 'system',
                agent_type: agentType,
                tool_args,
                thinking_tokens
            }
        })

        // Update UI state
        dispatch(setRunStatus('running'))
        dispatch(setLoading(true))
    }

    const getAgentTypeForFork = (forkType: string): string => {
        switch (forkType) {
            case 'research_to_website':
                return 'research_to_website'
            case 'research_to_slide':
                return 'slide'
            default:
                return 'general'
        }
    }

    const getForkTypeLabel = (forkType: string) => {
        switch (forkType) {
            case 'research_to_website':
                return t('forkInfo.type.researchToWebsite', 'Create Website from Research')
            case 'research_to_slide':
                return t('forkInfo.type.researchToSlide', 'Create Presentation from Research')
            default:
                return forkType
        }
    }

    return (
        <div className="py-3 w-full">
            <div className="bg-[rgb(33,33,33)] rounded-2xl border border-gray-700 p-4 space-y-3 w-full">
                {/* Header */}
                <div className="flex items-center gap-2">
                    <div
                        className="size-8 rounded-full flex items-center justify-center"
                        style={{ backgroundColor: 'rgb(166, 255, 255)' }}
                    >
                        <PlayIcon className="size-4 text-black" />
                    </div>
                    <div>
                        <h3 className="text-white font-medium text-sm">
                            {getForkTypeLabel(forkInfo.fork_type)}
                        </h3>
                        <p className="text-gray-400 text-xs">
                            {t('forkInfo.description', 'Continue from previous research')}
                        </p>
                    </div>
                </div>

                {/* Parent Session Link */}
                <div className="flex items-center justify-between bg-[rgb(45,45,45)] rounded-lg px-3 py-2">
                    <div className="flex items-center gap-2 text-gray-300">
                        <FileTextIcon className="size-4" />
                        <span className="text-sm">{t('forkInfo.parentSession', 'Parent Session')}</span>
                    </div>
                    <Link
                        to={`/${forkInfo.parent_session_id}`}
                        target="_blank"
                        className="flex items-center gap-1 text-sm hover:underline"
                        style={{ color: 'rgb(166, 255, 255)' }}
                    >
                        {t('forkInfo.viewParent', 'View')}
                        <ExternalLinkIcon className="size-3" />
                    </Link>
                </div>

                {/* Additional Instructions */}
                {forkInfo.context.additional_instruction && (
                    <div className="bg-[rgb(45,45,45)] rounded-lg px-3 py-2">
                        <div className="text-xs text-gray-400 mb-1">
                            {t('forkInfo.additionalInstructions', 'Additional Instructions')}
                        </div>
                        <p className="text-white text-sm whitespace-pre-wrap">
                            {forkInfo.context.additional_instruction}
                        </p>
                    </div>
                )}

                {/* Attachments */}
                {forkInfo.context.attachments.length > 0 && (
                    <div className="bg-[rgb(45,45,45)] rounded-lg px-3 py-2">
                        <div className="text-xs text-gray-400 mb-1">
                            {t('forkInfo.files', 'Files')} ({forkInfo.context.attachments.length})
                        </div>
                        <ul className="space-y-0.5">
                            {forkInfo.context.attachments.slice(0, 3).map((file, index) => (
                                <li key={index} className="text-white text-sm truncate">
                                    {file.split('/').pop()}
                                </li>
                            ))}
                            {forkInfo.context.attachments.length > 3 && (
                                <li className="text-gray-400 text-xs">
                                    +{forkInfo.context.attachments.length - 3} {t('forkInfo.moreFiles', 'more')}
                                </li>
                            )}
                        </ul>
                    </div>
                )}

                {/* Start Button - hidden after started */}
                {!hasStarted && (
                    <Button
                        onClick={handleStart}
                        disabled={isStarting}
                        className="w-full text-black font-medium h-9 text-sm"
                        style={{ backgroundColor: 'rgb(166, 255, 255)' }}
                    >
                        {isStarting ? (
                            <>
                                <Loader2Icon className="size-4 mr-2 animate-spin" />
                                {t('forkInfo.starting', 'Building...')}
                            </>
                        ) : (
                            <>
                                <PlayIcon className="size-4 mr-2" />
                                {t('forkInfo.start', 'Start Building')}
                            </>
                        )}
                    </Button>
                )}
            </div>
        </div>
    )
}
