import { createSlice, PayloadAction } from '@reduxjs/toolkit'
import { BUILD_STEP, WebSocketConnectionState } from '@/typings/agent'

interface PendingQuery {
    // Init agent params
    model_id?: string
    provider?: string
    source?: string
    agent_type?: string | null
    tool_args?: Record<string, unknown>
    thinking_tokens?: number
    metadata?: Record<string, unknown>
    // Query params
    text: string
    resume: boolean
    files: string[]
}

interface AgentState {
    isCompleted: boolean
    isStopped: boolean
    isAgentInitialized: boolean
    wsConnectionState: WebSocketConnectionState
    buildStep: BUILD_STEP
    selectedBuildStep: BUILD_STEP
    plans: {
        id: string
        content: string
        status: 'pending' | 'in_progress' | 'completed'
    }[]
    resultUrl: string
    isSandboxIframeAwake: boolean
    sandboxStatus: string
    pendingQuery: PendingQuery | null
    fullstackProjectInitialized: boolean
    published: string | null
}

const initialState: AgentState = {
    isCompleted: false,
    isStopped: false,
    isAgentInitialized: false,
    wsConnectionState: WebSocketConnectionState.CONNECTING,
    buildStep: BUILD_STEP.THINKING,
    selectedBuildStep: BUILD_STEP.THINKING,
    plans: [],
    resultUrl: '',
    isSandboxIframeAwake: false,
    sandboxStatus: '',
    pendingQuery: null,
    fullstackProjectInitialized: false,
    published: null
}

const agentSlice = createSlice({
    name: 'agent',
    initialState,
    reducers: {
        setCompleted: (state, action: PayloadAction<boolean>) => {
            state.isCompleted = action.payload
        },
        setStopped: (state, action: PayloadAction<boolean>) => {
            state.isStopped = action.payload
        },
        setAgentInitialized: (state, action: PayloadAction<boolean>) => {
            state.isAgentInitialized = action.payload
        },
        setWsConnectionState: (
            state,
            action: PayloadAction<WebSocketConnectionState>
        ) => {
            state.wsConnectionState = action.payload
        },
        setBuildStep: (state, action: PayloadAction<BUILD_STEP>) => {
            state.buildStep = action.payload
            state.selectedBuildStep = action.payload
        },
        setSelectedBuildStep: (state, action: PayloadAction<BUILD_STEP>) => {
            if (
                state.buildStep === BUILD_STEP.PLAN &&
                action.payload === BUILD_STEP.BUILD
            ) {
                state.buildStep = action.payload
            }
            state.selectedBuildStep = action.payload
        },
        setResultUrl: (state, action: PayloadAction<string>) => {
            state.resultUrl = action.payload
        },
        setSandboxIframeAwake: (state, action: PayloadAction<boolean>) => {
            state.isSandboxIframeAwake = action.payload
        },
        setSandboxStatus: (state, action: PayloadAction<string>) => {
            state.sandboxStatus = action.payload
        },
        setPendingQuery: (state, action: PayloadAction<PendingQuery | null>) => {
            state.pendingQuery = action.payload
        },
        setFullstackProjectInitialized: (
            state,
            action: PayloadAction<boolean>
        ) => {
            state.fullstackProjectInitialized = action.payload
        },
        setPublished: (state, action: PayloadAction<string | null>) => {
            state.published = action.payload
        }
    }
})

export const {
    setCompleted,
    setStopped,
    setAgentInitialized,
    setWsConnectionState,
    setBuildStep,
    setSelectedBuildStep,
    setResultUrl,
    setSandboxIframeAwake,
    setSandboxStatus,
    setPendingQuery,
    setFullstackProjectInitialized,
    setPublished
} = agentSlice.actions
export const agentReducer = agentSlice.reducer

// Selectors
export const selectIsCompleted = (state: { agent: AgentState }) =>
    state.agent.isCompleted
export const selectIsStopped = (state: { agent: AgentState }) =>
    state.agent.isStopped
export const selectIsAgentInitialized = (state: { agent: AgentState }) =>
    state.agent.isAgentInitialized
export const selectWsConnectionState = (state: { agent: AgentState }) =>
    state.agent.wsConnectionState
export const selectBuildStep = (state: { agent: AgentState }) =>
    state.agent.buildStep
export const selectSelectedBuildStep = (state: { agent: AgentState }) =>
    state.agent.selectedBuildStep
export const selectResultUrl = (state: { agent: AgentState }) =>
    state.agent.resultUrl
export const selectIsSandboxIframeAwake = (state: { agent: AgentState }) =>
    state.agent.isSandboxIframeAwake
export const selectSandboxStatus = (state: { agent: AgentState }) =>
    state.agent.sandboxStatus
export const selectPendingQuery = (state: { agent: AgentState }) =>
    state.agent.pendingQuery
export const selectFullstackProjectInitialized = (
    state: { agent: AgentState }
) => state.agent.fullstackProjectInitialized
export const selectPublished = (state: { agent: AgentState }) =>
    state.agent.published
