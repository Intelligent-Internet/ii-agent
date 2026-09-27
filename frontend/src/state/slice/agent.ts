import { createSlice, PayloadAction } from '@reduxjs/toolkit'
import { BUILD_STEP, RunStatus, WebSocketConnectionState } from '@/typings/agent'

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
    _commandType?: string
}

interface CheckpointData {
    projectDirectory: string
    revision: string
}

interface AgentState {
    /** Single source of truth for agent run status, synced from BE */
    runStatus: string | null
    /** Client-only: user clicked cancel, waiting for BE confirmation */
    isCancelling: boolean
    isAgentInitialized: boolean
    wsConnectionState: WebSocketConnectionState
    buildStep: BUILD_STEP
    selectedBuildStep: BUILD_STEP
    plans: {
        id: string
        content: string
        status: 'pending' | 'in_progress' | 'completed'
    }[]
    isSandboxIframeAwake: boolean
    sandboxStatus: string
    pendingQuery: PendingQuery | null
    fullstackProjectInitialized: boolean
    projectId: string | null
    published: string | null
    latestCheckpoint: CheckpointData | null
}

const initialState: AgentState = {
    runStatus: null,
    isCancelling: false,
    isAgentInitialized: false,
    wsConnectionState: WebSocketConnectionState.CONNECTING,
    buildStep: BUILD_STEP.THINKING,
    selectedBuildStep: BUILD_STEP.THINKING,
    plans: [],
    isSandboxIframeAwake: false,
    sandboxStatus: '',
    pendingQuery: null,
    fullstackProjectInitialized: false,
    projectId: null,
    published: null,
    latestCheckpoint: null
}

const agentSlice = createSlice({
    name: 'agent',
    initialState,
    reducers: {
        setRunStatus: (state, action: PayloadAction<string | null>) => {
            state.runStatus = action.payload
        },
        setCancelling: (state, action: PayloadAction<boolean>) => {
            state.isCancelling = action.payload
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
        setSandboxIframeAwake: (state, action: PayloadAction<boolean>) => {
            state.isSandboxIframeAwake = action.payload
        },
        setSandboxStatus: (state, action: PayloadAction<string>) => {
            state.sandboxStatus = action.payload
        },
        setPendingQuery: (
            state,
            action: PayloadAction<PendingQuery | null>
        ) => {
            state.pendingQuery = action.payload
        },
        setFullstackProjectInitialized: (
            state,
            action: PayloadAction<boolean>
        ) => {
            state.fullstackProjectInitialized = action.payload
        },
        setProjectId: (state, action: PayloadAction<string | null>) => {
            state.projectId = action.payload
        },
        setPublished: (state, action: PayloadAction<string | null>) => {
            state.published = action.payload
        },
        setLatestCheckpoint: (state, action: PayloadAction<CheckpointData | null>) => {
            state.latestCheckpoint = action.payload
        }
    }
})

export const {
    setRunStatus,
    setCancelling,
    setAgentInitialized,
    setWsConnectionState,
    setBuildStep,
    setSelectedBuildStep,
    setSandboxIframeAwake,
    setSandboxStatus,
    setPendingQuery,
    setFullstackProjectInitialized,
    setProjectId,
    setPublished,
    setLatestCheckpoint
} = agentSlice.actions
export const agentReducer = agentSlice.reducer

// Selectors — isCompleted, isStopped, isWaitingForInput derived from runStatus
export const selectRunStatus = (state: { agent: AgentState }) =>
    state.agent.runStatus
export const selectIsAgentRunning = (state: { agent: AgentState }) =>
    state.agent.runStatus === 'running'
export const selectIsCompleted = (state: { agent: AgentState }) =>
    state.agent.runStatus === 'completed'
export const selectIsStopped = (state: { agent: AgentState }) => {
    const status = state.agent.runStatus
    return (
        status === RunStatus.ABORTED ||
        status === RunStatus.CANCELLED ||
        status === RunStatus.FAILED ||
        status === RunStatus.ERROR ||
        status === RunStatus.SYSTEM_INTERRUPTED
    )
}
export const selectIsCancelling = (state: { agent: AgentState }) =>
    state.agent.isCancelling
export const selectIsWaitingForInput = (state: { agent: AgentState }) =>
    state.agent.runStatus === 'paused'
export const selectIsAgentInitialized = (state: { agent: AgentState }) =>
    state.agent.isAgentInitialized
export const selectWsConnectionState = (state: { agent: AgentState }) =>
    state.agent.wsConnectionState
export const selectBuildStep = (state: { agent: AgentState }) =>
    state.agent.buildStep
export const selectSelectedBuildStep = (state: { agent: AgentState }) =>
    state.agent.selectedBuildStep
export const selectIsSandboxIframeAwake = (state: { agent: AgentState }) =>
    state.agent.isSandboxIframeAwake
export const selectSandboxStatus = (state: { agent: AgentState }) =>
    state.agent.sandboxStatus
export const selectPendingQuery = (state: { agent: AgentState }) =>
    state.agent.pendingQuery
export const selectFullstackProjectInitialized = (
    state: { agent: AgentState }
) => state.agent.fullstackProjectInitialized
export const selectProjectId = (state: { agent: AgentState }) =>
    state.agent.projectId
export const selectPublished = (state: { agent: AgentState }) =>
    state.agent.published
export const selectLatestCheckpoint = (state: { agent: AgentState }) =>
    state.agent.latestCheckpoint
