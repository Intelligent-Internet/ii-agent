import { createSlice, PayloadAction } from '@reduxjs/toolkit'

export interface ContextState {
    usedTokens: number
    maxTokens: number
    usage?: {
        inputTokens?: number
        outputTokens?: number
        totalTokens?: number
    }
    modelId?: string
    harmonicMissStats?: Record<string, unknown>
}

const initialState: ContextState = {
    usedTokens: 0,
    maxTokens: 128000,
    usage: { inputTokens: 0, outputTokens: 0, totalTokens: 0 },
    modelId: undefined,
    harmonicMissStats: undefined
}

export const contextSlice = createSlice({
    name: 'context',
    initialState,
    reducers: {
        setContextUsage: (
            state,
            action: PayloadAction<{
                usedTokens: number
                maxTokens?: number
                usage?: { inputTokens?: number; outputTokens?: number; totalTokens?: number }
                modelId?: string
            }>
        ) => {
            state.usedTokens = action.payload.usedTokens
            if (action.payload.maxTokens) state.maxTokens = action.payload.maxTokens
            if (action.payload.usage) state.usage = action.payload.usage
            if (action.payload.modelId) state.modelId = action.payload.modelId
        },
        setHarmonicMissStats: (state, action: PayloadAction<Record<string, unknown>>) => {
            state.harmonicMissStats = action.payload
        },
        clearContextUsage: (state) => {
            state.usedTokens = 0
            state.usage = { inputTokens: 0, outputTokens: 0, totalTokens: 0 }
        }
    }
})

export const { setContextUsage, setHarmonicMissStats, clearContextUsage } = contextSlice.actions

export const contextReducer = contextSlice.reducer

// Selectors
export const selectContext = (state: { context: ContextState }) => state.context
