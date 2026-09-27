import { describe, it, expect, beforeEach } from 'vitest'
import {
    settingsReducer,
    setSelectedModel,
    setSelectedChatModel,
    setSelectedAgentModel,
    selectSelectedModel,
    selectSelectedChatModel,
    selectSelectedAgentModel,
    setAvailableModels,
    selectAvailableModels
} from '../settings'
import type { SettingsState } from '../settings'
import type { IModel } from '@/typings/settings'

describe('Settings Redux Slice - Model Steering', () => {
    let initialState: SettingsState

    beforeEach(() => {
        initialState = settingsReducer(undefined, { type: '@@INIT' })
    })

    describe('Model State Structure', () => {
        it('should have selectedModel field for backwards compatibility', () => {
            expect(initialState).toHaveProperty('selectedModel')
            expect(initialState.selectedModel).toBeUndefined()
        })

        it('should have selectedChatModel field for chat mode', () => {
            expect(initialState).toHaveProperty('selectedChatModel')
            expect(initialState.selectedChatModel).toBeUndefined()
        })

        it('should have selectedAgentModel field for agent mode', () => {
            expect(initialState).toHaveProperty('selectedAgentModel')
            expect(initialState.selectedAgentModel).toBeUndefined()
        })
    })

    describe('setSelectedModel action (deprecated)', () => {
        it('should update selectedModel field', () => {
            const newState = settingsReducer(
                initialState,
                setSelectedModel('model-123')
            )
            expect(newState.selectedModel).toBe('model-123')
        })

        it('should handle undefined to clear selection', () => {
            const withModel = settingsReducer(
                initialState,
                setSelectedModel('model-456')
            )
            const cleared = settingsReducer(
                withModel,
                setSelectedModel(undefined)
            )
            expect(cleared.selectedModel).toBeUndefined()
        })
    })

    describe('setSelectedChatModel action', () => {
        it('should update selectedChatModel field independently', () => {
            const newState = settingsReducer(
                initialState,
                setSelectedChatModel('chat-model-1')
            )
            expect(newState.selectedChatModel).toBe('chat-model-1')
            expect(newState.selectedAgentModel).toBeUndefined()
        })

        it('should not affect selectedAgentModel', () => {
            let state = settingsReducer(initialState, setSelectedAgentModel('agent-model-1'))
            state = settingsReducer(state, setSelectedChatModel('chat-model-2'))
            
            expect(state.selectedChatModel).toBe('chat-model-2')
            expect(state.selectedAgentModel).toBe('agent-model-1')
        })

        it('should handle undefined to clear chat model', () => {
            const withModel = settingsReducer(
                initialState,
                setSelectedChatModel('chat-model-789')
            )
            const cleared = settingsReducer(
                withModel,
                setSelectedChatModel(undefined)
            )
            expect(cleared.selectedChatModel).toBeUndefined()
        })
    })

    describe('setSelectedAgentModel action', () => {
        it('should update selectedAgentModel field independently', () => {
            const newState = settingsReducer(
                initialState,
                setSelectedAgentModel('agent-model-1')
            )
            expect(newState.selectedAgentModel).toBe('agent-model-1')
            expect(newState.selectedChatModel).toBeUndefined()
        })

        it('should not affect selectedChatModel', () => {
            let state = settingsReducer(initialState, setSelectedChatModel('chat-model-1'))
            state = settingsReducer(state, setSelectedAgentModel('agent-model-2'))
            
            expect(state.selectedChatModel).toBe('chat-model-1')
            expect(state.selectedAgentModel).toBe('agent-model-2')
        })

        it('should handle undefined to clear agent model', () => {
            const withModel = settingsReducer(
                initialState,
                setSelectedAgentModel('agent-model-xyz')
            )
            const cleared = settingsReducer(
                withModel,
                setSelectedAgentModel(undefined)
            )
            expect(cleared.selectedAgentModel).toBeUndefined()
        })
    })

    describe('selectSelectedModel selector (deprecated)', () => {
        it('should return selectedModel field value', () => {
            const state = settingsReducer(initialState, setSelectedModel('old-model'))
            const storeState = { settings: state }
            
            const selected = selectSelectedModel(storeState)
            expect(selected).toBe('old-model')
        })

        it('should return undefined when not set', () => {
            const storeState = { settings: initialState }
            const selected = selectSelectedModel(storeState)
            expect(selected).toBeUndefined()
        })
    })

    describe('selectSelectedChatModel selector', () => {
        it('should return selectedChatModel field value', () => {
            const state = settingsReducer(initialState, setSelectedChatModel('gpt-4o'))
            const storeState = { settings: state }
            
            const selected = selectSelectedChatModel(storeState)
            expect(selected).toBe('gpt-4o')
        })

        it('should return undefined when not set', () => {
            const storeState = { settings: initialState }
            const selected = selectSelectedChatModel(storeState)
            expect(selected).toBeUndefined()
        })

        it('should be independent from agent model', () => {
            let state = settingsReducer(
                initialState,
                setSelectedChatModel('gpt-4o')
            )
            state = settingsReducer(
                state,
                setSelectedAgentModel('claude-3-opus')
            )
            const storeState = { settings: state }
            
            const chat = selectSelectedChatModel(storeState)
            const agent = selectSelectedAgentModel(storeState)
            
            expect(chat).toBe('gpt-4o')
            expect(agent).toBe('claude-3-opus')
        })
    })

    describe('selectSelectedAgentModel selector', () => {
        it('should return selectedAgentModel field value', () => {
            const state = settingsReducer(initialState, setSelectedAgentModel('claude-3-opus'))
            const storeState = { settings: state }
            
            const selected = selectSelectedAgentModel(storeState)
            expect(selected).toBe('claude-3-opus')
        })

        it('should return undefined when not set', () => {
            const storeState = { settings: initialState }
            const selected = selectSelectedAgentModel(storeState)
            expect(selected).toBeUndefined()
        })

        it('should be independent from chat model', () => {
            let state = settingsReducer(
                initialState,
                setSelectedAgentModel('claude-3-opus')
            )
            state = settingsReducer(
                state,
                setSelectedChatModel('gpt-4o')
            )
            const storeState = { settings: state }
            
            const chat = selectSelectedChatModel(storeState)
            const agent = selectSelectedAgentModel(storeState)
            
            expect(chat).toBe('gpt-4o')
            expect(agent).toBe('claude-3-opus')
        })
    })

    describe('Model Selection Workflow', () => {
        it('should support independent model selection for chat and agent', () => {
            // User sets chat model
            let state = settingsReducer(
                initialState,
                setSelectedChatModel('gpt-4o')
            )
            
            // User sets agent model (different from chat)
            state = settingsReducer(
                state,
                setSelectedAgentModel('claude-3-5-sonnet')
            )
            
            const storeState = { settings: state }
            
            // Both should be retained independently
            expect(selectSelectedChatModel(storeState)).toBe('gpt-4o')
            expect(selectSelectedAgentModel(storeState)).toBe('claude-3-5-sonnet')
        })

        it('should support changing chat model without affecting agent model', () => {
            // Setup: both models selected
            let state = settingsReducer(initialState, setSelectedChatModel('gpt-4o'))
            state = settingsReducer(state, setSelectedAgentModel('claude-3-5-sonnet'))
            
            // User changes chat model
            state = settingsReducer(state, setSelectedChatModel('gpt-4-turbo'))
            
            const storeState = { settings: state }
            
            expect(selectSelectedChatModel(storeState)).toBe('gpt-4-turbo')
            expect(selectSelectedAgentModel(storeState)).toBe('claude-3-5-sonnet')
        })

        it('should support changing agent model without affecting chat model', () => {
            // Setup: both models selected
            let state = settingsReducer(initialState, setSelectedChatModel('gpt-4o'))
            state = settingsReducer(state, setSelectedAgentModel('claude-3-5-sonnet'))
            
            // User changes agent model
            state = settingsReducer(state, setSelectedAgentModel('claude-3-opus'))
            
            const storeState = { settings: state }
            
            expect(selectSelectedChatModel(storeState)).toBe('gpt-4o')
            expect(selectSelectedAgentModel(storeState)).toBe('claude-3-opus')
        })
    })

    describe('Integration with availableModels', () => {
        it('should work with setAvailableModels', () => {
            const models: IModel[] = [
                { id: 'gpt-4o', model: 'GPT-4o', provider: 'OpenAI', source: 'system' },
                { id: 'claude-3-opus', model: 'Claude 3 Opus', provider: 'Anthropic', source: 'system' }
            ]
            
            let state = settingsReducer(initialState, setAvailableModels(models))
            state = settingsReducer(state, setSelectedChatModel('gpt-4o'))
            state = settingsReducer(state, setSelectedAgentModel('claude-3-opus'))
            
            const storeState = { settings: state }
            
            expect(selectAvailableModels(storeState)).toEqual(models)
            expect(selectSelectedChatModel(storeState)).toBe('gpt-4o')
            expect(selectSelectedAgentModel(storeState)).toBe('claude-3-opus')
        })
    })
})
