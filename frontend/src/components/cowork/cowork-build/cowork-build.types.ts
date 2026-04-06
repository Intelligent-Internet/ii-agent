import type { ReactNode } from 'react'
import type { ActionStep, Message } from '@/typings/agent'
import type { CoworkLiveSessionState, CoworkLiveToolCall } from '@/typings/cowork'

export type CoworkBuildActionMessage = Message & {
    action: ActionStep
}

export type CoworkBuildRendererKey = 'terminal' | 'code' | 'search' | 'browser'

export type CoworkBuildSearchResult =
    | string
    | Record<string, unknown>
    | Record<string, unknown>[]

export interface CoworkBuildRendererContext {
    currentAction: ActionStep
    currentToolCall?: CoworkLiveToolCall
    previewPath?: string
    previewContent: string
    browserUrl?: string
    browserRaw?: string
    searchKeyword?: string
    searchResults?: CoworkBuildSearchResult
}

export interface CoworkBuildRendererDefinition {
    key: string
    matches: (action: ActionStep) => boolean
    render: (context: CoworkBuildRendererContext) => ReactNode
}

export interface UseCoworkBuildStateOptions {
    liveSession?: CoworkLiveSessionState | null
    requestedAction?: ActionStep | null
    requestedActionToken?: number
}

export interface CoworkBuildState {
    actionMessages: CoworkBuildActionMessage[]
    totalSteps: number
    step: number
    isLiveUpdate: boolean
    hasActionHistory: boolean
    isAwaitingTurnAction: boolean
    currentAction?: ActionStep
    currentToolCall?: CoworkLiveToolCall
    fallbackContent: string
    previewPath?: string
    previewContent: string
    browserUrl?: string
    browserRaw?: string
    searchKeyword?: string
    searchResults?: CoworkBuildSearchResult
    setStep: (step: number, liveUpdate?: boolean) => void
    jumpToLatest: () => void
}
