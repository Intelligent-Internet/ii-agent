'use client'

import { motion } from 'framer-motion'
import {
    ChevronRight,
    Bot,
    CheckCircle2,
    XCircle,
    Loader2,
    Clock,
    StopCircle
} from 'lucide-react'
import { useState, useMemo } from 'react'
import { AgentContext, Message } from '@/typings/agent'
import { formatDuration } from '@/lib/utils'
import { useAppSelector, selectIsStopped } from '@/state'

interface SubagentContainerProps {
    agentContext: AgentContext
    messages: Message[]
    children: React.ReactNode
}

enum SubAgentStatus {
    RUNNING = 'running',
    COMPLETED = 'completed',
    FAILED = 'failed',
    STOPPED = 'stopped'
}

const SubagentContainer = ({
    agentContext,
    messages,
    children
}: SubagentContainerProps) => {
    const [isExpanded, setIsExpanded] = useState(true)
    const isStopped = useAppSelector(selectIsStopped)

    // Calculate execution time
    const executionTime = useMemo(() => {
        if (agentContext.startTime && agentContext.endTime) {
            return agentContext.endTime - agentContext.startTime
        }
        if (agentContext.startTime) {
            return Date.now() - agentContext.startTime
        }
        return 0
    }, [agentContext.startTime, agentContext.endTime])

    // Count actions
    const actionCount = useMemo(() => {
        return messages.filter((msg) => msg.action).length
    }, [messages])

    // Determine actual status - use completed if endTime exists, even if status is not set properly
    // Also check global isStopped state - if agent is stopped, any running subagent should show as stopped
    const actualStatus = useMemo(() => {
        if (agentContext.endTime) {
            return SubAgentStatus.COMPLETED
        }
        const contextStatus = agentContext.status || SubAgentStatus.RUNNING
        // If global agent is stopped and this subagent was still running, show as stopped
        if (isStopped && contextStatus === SubAgentStatus.RUNNING) {
            return SubAgentStatus.STOPPED
        }
        return contextStatus
    }, [
        agentContext.status,
        agentContext.endTime,
        agentContext.agentId,
        agentContext.agentName,
        isStopped
    ])

    // Get status icon
    const StatusIcon = useMemo(() => {
        switch (actualStatus) {
            case SubAgentStatus.COMPLETED:
                return <CheckCircle2 className="size-4 text-green-500" />
            case SubAgentStatus.FAILED:
                return <XCircle className="size-4 text-red-500" />
            case SubAgentStatus.STOPPED:
                return <StopCircle className="size-4 text-yellow-500" />
            case SubAgentStatus.RUNNING:
                return <Loader2 className="size-4 text-white animate-spin" />
            default:
                return null
        }
    }, [actualStatus])

    // Consistent background and border colors for all subagents
    const containerStyles = useMemo(() => {
        const baseStyles = 'rounded-xl transition-all duration-200'
        const subagentStyles =
            'bg-[#f5f5f5] dark:bg-sky-blue/[0.18] border border-grey'
        return `${baseStyles} ${subagentStyles}`
    }, [])

    return (
        <div className="mb-4">
            <motion.div
                className={containerStyles}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.3 }}
            >
                {/* Header */}
                <button
                    onClick={(e) => {
                        e.stopPropagation()
                        setIsExpanded(!isExpanded)
                    }}
                    className="w-full px-4 py-3 flex items-center justify-between hover:bg-white/5 dark:hover:bg-black/10 transition-colors rounded-t-xl"
                >
                    <div className="flex items-center gap-3">
                        {/* Agent Icon */}
                        <div className="flex items-center justify-center size-8 bg-gradient-to-br from-mist to-sky-blue-2 rounded-lg">
                            <Bot className="size-5 text-black" />
                        </div>

                        {/* Agent Name */}
                        <div className="flex flex-col items-start">
                            <span className="font-semibold text-sm">
                                {agentContext.agentName || 'Sub Agent'}
                            </span>
                        </div>

                        {/* Status Icon */}
                        {StatusIcon}
                    </div>

                    <div className="hidden md:flex items-center gap-4 text-xs text-gray-400">
                        {/* Action Count */}
                        <span className="flex items-center gap-1">
                            <span className="font-medium">{actionCount}</span>
                            <span>actions</span>
                        </span>

                        {/* Execution Time */}
                        {executionTime > 0 && (
                            <span className="flex items-center gap-1">
                                <Clock className="size-3" />
                                <span>{formatDuration(executionTime)}</span>
                            </span>
                        )}

                        {/* Status Badge */}
                        <span
                            className={`
                            px-2 py-1 rounded-full text-xs font-medium capitalize
                            ${actualStatus === SubAgentStatus.COMPLETED ? 'bg-green-500/20 text-green-400' : ''}
                            ${actualStatus === SubAgentStatus.RUNNING ? 'bg-blue-500/20 text-blue-400' : ''}
                            ${actualStatus === SubAgentStatus.FAILED ? 'bg-red-500/20 text-red-400' : ''}
                            ${actualStatus === SubAgentStatus.STOPPED ? 'bg-yellow-500/20 text-yellow-400' : ''}
                        `}
                        >
                            {actualStatus}
                        </span>
                        {/* Expand/Collapse Icon */}
                        <motion.div
                            animate={{ rotate: isExpanded ? 90 : 0 }}
                            transition={{ duration: 0.2 }}
                        >
                            <ChevronRight className="size-4 text-gray-400" />
                        </motion.div>
                    </div>
                </button>

                {/* Content */}
                {isExpanded && (
                    <div
                        className="overflow-hidden"
                        style={{ pointerEvents: 'auto' }}
                    >
                        <div
                            className="px-4 pb-4 pt-2"
                            style={{ pointerEvents: 'auto' }}
                        >
                            {/* Progress Bar for Running Status */}
                            {actualStatus === SubAgentStatus.RUNNING && (
                                <div className="mb-3">
                                    <div className="h-1 bg-firefly/[0.18] rounded-full overflow-hidden">
                                        <motion.div
                                            className="h-full bg-gradient-to-r dark:from-mist to-charcoal dark:to-sky-blue-2"
                                            animate={{ x: ['-200%', '200%'] }}
                                            transition={{
                                                duration: 2.5,
                                                repeat: Infinity,
                                                ease: 'linear'
                                            }}
                                            style={{ width: '40%' }}
                                        />
                                    </div>
                                </div>
                            )}

                            {/* Actions/Messages */}
                            <div
                                className="space-y-2"
                                style={{ pointerEvents: 'auto' }}
                            >
                                {children}
                            </div>

                            {/* Summary for Completed Agents */}
                            {actualStatus === SubAgentStatus.COMPLETED &&
                                messages.length > 0 && (
                                    <div className="mt-3 p-3 bg-firefly/[0.18]  dark:bg-sky-blue/[0.18] rounded-lg">
                                        <h4 className="text-xs font-semibold  mb-2">
                                            Summary
                                        </h4>
                                        <div className="grid grid-cols-2 gap-2 text-xs">
                                            <div>
                                                <span className="">
                                                    Total Actions:
                                                </span>
                                                <span className="ml-2  font-medium">
                                                    {actionCount}
                                                </span>
                                            </div>
                                            <div>
                                                <span className="">
                                                    Duration:
                                                </span>
                                                <span className="ml-2  font-medium">
                                                    {formatDuration(
                                                        executionTime
                                                    )}
                                                </span>
                                            </div>
                                        </div>
                                    </div>
                                )}
                        </div>
                    </div>
                )}
            </motion.div>
        </div>
    )
}

export default SubagentContainer
