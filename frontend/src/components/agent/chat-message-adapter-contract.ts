import type {
    ActionStep,
    AgentContext,
    Message,
    RunStatus
} from '@/typings/agent'

export interface ChatMessageAdapterState {
    messages: Message[]
    runStatus: RunStatus | string | null
    isLoading: boolean
    workspaceInfo?: string
    resetEditingOnKey?: string | null
    clearCurrentQuestionOnCleanup?: boolean
}

export interface ChatMessageAdapterHandlers {
    handleQuestionSubmit: (question: string) => void
    handleCancel: () => void
    handleClickAction: (
        data: ActionStep | undefined,
        showTabOnly?: boolean
    ) => void
    connectWebSocket: () => void
}

export const CHAT_MESSAGE_MINIMAL_EVENT_CONTRACT = [
    'session.user_message',
    'agent.reasoning.delta',
    'agent.reasoning',
    'agent.tool.call',
    'agent.tool.result',
    'agent.response.delta',
    'agent.response',
    'agent.sub_agent.complete',
    'run_status'
] as const

export type ChatMessageMinimalEvent =
    (typeof CHAT_MESSAGE_MINIMAL_EVENT_CONTRACT)[number]

export type ChatMessageAdapterOutput = Pick<
    ChatMessageAdapterState,
    'messages' | 'runStatus' | 'isLoading'
>

export type ChatMessageAdapterMessage = Message
export type ChatMessageAdapterAction = ActionStep
export type ChatMessageAdapterAgentContext = AgentContext
