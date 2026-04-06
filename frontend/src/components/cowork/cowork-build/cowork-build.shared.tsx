import { useEffect, useMemo, useState } from 'react'
import Action from '@/components/agent/action'
import { Button } from '@/components/ui/button'
import { Icon } from '@/components/ui/icon'
import { Slider } from '@/components/ui/slider'
import { parseJson } from '@/lib/utils'
import { TOOL, type ActionStep } from '@/typings/agent'
import type {
    CoworkBuildActionMessage,
    CoworkBuildRendererContext,
    CoworkBuildRendererDefinition,
    CoworkBuildState,
    UseCoworkBuildStateOptions
} from './cowork-build.types'
import { coworkBuildEventToolGroups } from './cowork-build.renderers'

const stringifyValue = (value: unknown) => {
    if (typeof value === 'string') return value
    if (value === null || value === undefined) return ''

    try {
        return JSON.stringify(value, null, 2)
    } catch {
        return String(value)
    }
}

const getPreviewPath = (action?: ActionStep) => {
    if (action?.type === TOOL.APPLY_PATCH && action.data.tool_input?.changes) {
        const firstPath = Object.keys(action.data.tool_input.changes)[0]
        if (firstPath) {
            return firstPath
        }
    }

    return (
        action?.data.tool_input?.path ||
        action?.data.tool_input?.file_path ||
        action?.data.tool_input?.file ||
        action?.data.tool_input?.filename
    )
}

const getPreviewContent = (action?: ActionStep) => {
    if (!action) return ''

    if (action.type === TOOL.WRITE) {
        return stringifyValue(action.data.tool_input?.content)
    }

    if (action.type === TOOL.EDIT || action.type === TOOL.MULTI_EDIT) {
        return stringifyValue(
            action.data.tool_input?.new_string ?? action.data.result
        )
    }

    if (action.type === TOOL.STR_REPLACE_BASED_EDIT) {
        return stringifyValue(
            action.data.tool_input?.file_text ?? action.data.result
        )
    }

    if (action.type === TOOL.APPLY_PATCH && action.data.tool_input?.changes) {
        const firstPath = Object.keys(action.data.tool_input.changes)[0]
        const firstChange = firstPath
            ? action.data.tool_input.changes[firstPath]
            : undefined

        return stringifyValue(
            firstChange?.update?.unified_diff ||
                firstChange?.add?.content ||
                firstChange?.delete?.content ||
                action.data.result
        )
    }

    return stringifyValue(action.data.result)
}

const getRequestedActionIndex = (
    actionMessages: CoworkBuildActionMessage[],
    requestedAction?: ActionStep | null
) => {
    if (!requestedAction) {
        return -1
    }

    const requestedToolCallId = requestedAction.data.tool_call_id
    if (requestedToolCallId) {
        const toolCallIndex = actionMessages.findIndex(
            (message) =>
                message.action.data.tool_call_id === requestedToolCallId
        )
        if (toolCallIndex >= 0) {
            return toolCallIndex
        }
    }

    const typeAndInputIndex = actionMessages.findIndex(
        (message) =>
            message.action.type === requestedAction.type &&
            message.action.data.tool_input === requestedAction.data.tool_input
    )

    if (typeAndInputIndex >= 0) {
        return typeAndInputIndex
    }

    return actionMessages.findIndex(
        (message) =>
            message.action.type === requestedAction.type &&
            message.action.data.tool_name === requestedAction.data.tool_name
    )
}

export const useCoworkBuildState = ({
    liveSession = null,
    requestedAction = null,
    requestedActionToken = 0
}: UseCoworkBuildStateOptions): CoworkBuildState => {
    const actionMessages = useMemo(
        () =>
            ((liveSession?.event_messages ?? []).filter(
                (message) => message.action
            ) as CoworkBuildActionMessage[]),
        [liveSession?.event_messages]
    )
    const totalSteps = actionMessages.length
    const [currentStep, setCurrentStep] = useState(0)
    const [isLiveUpdate, setIsLiveUpdate] = useState(true)

    useEffect(() => {
        setCurrentStep(0)
        setIsLiveUpdate(true)
    }, [liveSession?.session_id])

    useEffect(() => {
        if (!liveSession?.is_awaiting_turn_action) {
            return
        }

        setCurrentStep(0)
        setIsLiveUpdate(true)
    }, [liveSession?.is_awaiting_turn_action])

    useEffect(() => {
        if (isLiveUpdate && totalSteps > 0) {
            setCurrentStep(totalSteps)
        }
    }, [isLiveUpdate, totalSteps])

    useEffect(() => {
        const requestedIndex = getRequestedActionIndex(
            actionMessages,
            requestedAction
        )

        if (requestedIndex >= 0) {
            setCurrentStep(requestedIndex + 1)
            setIsLiveUpdate(false)
        }
    }, [actionMessages, requestedAction, requestedActionToken])

    const step =
        totalSteps > 0
            ? currentStep > 0
                ? Math.min(currentStep, totalSteps)
                : totalSteps
            : 0
    const hasActionHistory = totalSteps > 0
    const isAwaitingTurnAction =
        Boolean(liveSession?.is_awaiting_turn_action) && isLiveUpdate
    const selectedAction =
        step > 0 ? actionMessages[step - 1]?.action : undefined

    const currentAction =
        (!isAwaitingTurnAction ? selectedAction : undefined) ??
        (!isAwaitingTurnAction ? liveSession?.current_action : undefined)

    const currentToolCall = useMemo(() => {
        const toolCalls = liveSession?.tool_calls ?? []

        if (!currentAction?.data.tool_call_id) {
            return toolCalls.at(-1)
        }

        return (
            toolCalls.find(
                (toolCall) => toolCall.id === currentAction.data.tool_call_id
            ) ?? toolCalls.at(-1)
        )
    }, [currentAction, liveSession?.tool_calls])

    const previewPath = getPreviewPath(currentAction)
    const previewContent = getPreviewContent(currentAction)
    const searchKeyword =
        currentAction?.data.tool_input?.query ||
        currentAction?.data.tool_input?.queries?.join(', ')
    const searchResults =
        currentAction &&
        coworkBuildEventToolGroups.search.has(currentAction.type) &&
        currentAction.data.result
            ? typeof currentAction.data.result === 'string'
                ? parseJson(currentAction.data.result)
                : currentAction.data.result
            : undefined
    const browserUrl =
        currentAction &&
        coworkBuildEventToolGroups.browser.has(currentAction.type)
            ? currentAction.data.tool_input?.url ||
              currentAction.data.tool_input?.urls?.[0]
            : undefined
    const browserRaw =
        currentAction && browserUrl !== undefined
            ? typeof currentAction.data.result === 'string'
                ? currentAction.data.result
                : stringifyValue(currentAction.data.result)
            : undefined
    const fallbackContent = currentToolCall?.result || currentToolCall?.input || ''

    return {
        actionMessages,
        totalSteps,
        step,
        isLiveUpdate,
        hasActionHistory,
        isAwaitingTurnAction,
        currentAction,
        currentToolCall,
        fallbackContent,
        previewPath,
        previewContent,
        browserUrl,
        browserRaw,
        searchKeyword,
        searchResults,
        setStep: (nextStep, liveUpdate = false) => {
            setCurrentStep(nextStep)
            setIsLiveUpdate(liveUpdate)
        },
        jumpToLatest: () => {
            setCurrentStep(totalSteps)
            setIsLiveUpdate(true)
        }
    }
}

interface CoworkBuildControllerProps {
    step: number
    totalSteps: number
    isLiveUpdate: boolean
    onStepChange: (step: number, liveUpdate?: boolean) => void
    onJumpToLatest: () => void
}

export const CoworkBuildController = ({
    step,
    totalSteps,
    isLiveUpdate,
    onStepChange,
    onJumpToLatest
}: CoworkBuildControllerProps) => {
    if (totalSteps === 0) {
        return null
    }

    return (
        <div className="flex items-baseline justify-between gap-4 mt-3">
            <div className="flex-1">
                <div className="flex gap-x-[6px] items-center mb-[6px]">
                    <button
                        className="cursor-pointer disabled:opacity-30"
                        disabled={step <= 1}
                        onClick={() => onStepChange(step - 1, false)}
                    >
                        <Icon
                            name="arrow-left-2"
                            className="size-4 fill-black dark:fill-white"
                        />
                    </button>
                    <div className="flex gap-x-[2px] text-xs">
                        <span>{step}</span>
                        <span>/</span>
                        <span>{totalSteps}</span>
                    </div>
                    <button
                        className="cursor-pointer disabled:opacity-30"
                        disabled={step >= totalSteps}
                        onClick={() => onStepChange(step + 1)}
                    >
                        <Icon
                            name="arrow-right-2"
                            className="size-4 fill-black dark:fill-white"
                        />
                    </button>
                </div>
                <Slider
                    value={[step]}
                    onValueChange={(value) =>
                        onStepChange(value[0], value[0] >= totalSteps)
                    }
                    max={totalSteps}
                    step={1}
                />
            </div>
            {isLiveUpdate && step === totalSteps ? (
                <div className="flex items-center bg-firefly text-sky-blue-2 dark:bg-sky-blue-2 dark:text-black h-6 px-3 text-xs font-semibold rounded-3xl">
                    Live update
                </div>
            ) : (
                <Button
                    className="dark:text-sky-blue-2 border dark:border-sky-blue-2 h-6 text-xs font-semibold rounded-3xl"
                    onClick={onJumpToLatest}
                >
                    Jump to latest
                </Button>
            )}
        </div>
    )
}

export const CoworkBuildViewport = ({
    state,
    renderers,
    renderUnsupportedAction = true,
    unsupportedMessage = 'This event does not have a dedicated build renderer yet.',
    emptyLabel = 'Cowork build',
    emptyTitle = 'Waiting for streaming events'
}: {
    state: CoworkBuildState
    renderers: CoworkBuildRendererDefinition[]
    renderUnsupportedAction?: boolean
    unsupportedMessage?: string
    emptyLabel?: string
    emptyTitle?: string
}) => {
    const {
        currentAction,
        currentToolCall,
        fallbackContent,
        previewPath,
        previewContent,
        browserUrl,
        browserRaw,
        searchKeyword,
        searchResults
    } = state

    if (!currentAction) {
        return (
            <div className="flex h-full w-full items-center justify-center text-white rounded-b-xl overflow-auto">
                <div className="flex flex-col items-center gap-4 text-center px-6">
                    <div className="relative">
                        <div className="h-16 w-16 rounded-full border-2 border-white/30 flex items-center justify-center">
                            <Icon
                                name="loading"
                                className="size-8 animate-spin fill-white"
                            />
                        </div>
                        <span className="absolute inset-0 rounded-full border border-white/10 animate-ping" />
                    </div>
                    <div className="space-y-1">
                        <p className="text-sm uppercase tracking-[0.25em] text-white/70">
                            {emptyLabel}
                        </p>
                        <p className="text-lg font-semibold">
                            {emptyTitle}
                        </p>
                    </div>
                    <div className="w-[min(640px,90vw)] rounded-full h-3 bg-white/10 overflow-hidden">
                        <div
                            className="h-full bg-gradient-to-r from-sky-400 via-blue-400 to-cyan-300 animate-[pulse_1.4s_ease-in-out_infinite]"
                            style={{ width: '76%' }}
                        />
                    </div>
                    {fallbackContent ? (
                        <p className="max-w-[420px] text-sm text-white/70 whitespace-pre-wrap break-words">
                            {fallbackContent}
                        </p>
                    ) : null}
                </div>
            </div>
        )
    }

    const context: CoworkBuildRendererContext = {
        currentAction,
        currentToolCall,
        previewPath,
        previewContent,
        browserUrl,
        browserRaw,
        searchKeyword,
        searchResults
    }

    const renderer = renderers.find((entry) => entry.matches(currentAction))
    if (renderer) {
        return <>{renderer.render(context)}</>
    }

    if (!renderUnsupportedAction) {
        return (
            <div className="flex h-full w-full items-center justify-center px-6 text-center text-sm text-white/70">
                {unsupportedMessage}
            </div>
        )
    }

    return (
        <div className="h-full w-full overflow-auto rounded-b-xl px-3 md:px-4 py-4">
            <div className="w-full max-w-[560px] mx-auto">
                <Action
                    workspaceInfo=""
                    type={currentAction.type}
                    value={currentAction.data}
                    onClick={() => {}}
                />
                <p className="mt-3 text-xs font-semibold uppercase tracking-[0.14em] text-black/45 dark:text-white/45">
                    {unsupportedMessage}
                </p>
                {(currentToolCall?.result || currentToolCall?.input) && (
                    <pre className="mt-3 whitespace-pre-wrap break-words rounded-2xl bg-white/70 px-4 py-3 text-xs text-black/70 dark:bg-white/[0.08] dark:text-white/70">
                        {currentToolCall?.result ?? currentToolCall?.input}
                    </pre>
                )}
            </div>
        </div>
    )
}
