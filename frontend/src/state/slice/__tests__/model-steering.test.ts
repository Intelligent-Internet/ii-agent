import { describe, it, expect } from 'vitest'
import { act } from 'react'
import { configureStore } from '@reduxjs/toolkit'
import {
    settingsReducer,
    setSelectedChatModel,
    setSelectedAgentModel,
    setAvailableModels,
    selectSelectedChatModel,
    selectSelectedAgentModel,
    type SettingsState
} from '../settings'
import type { IModel } from '@/typings/settings'

type RootState = {
    settings: SettingsState
}

// Mock store factory
function createMockStore(preloadedState?: Partial<RootState>) {
    return configureStore({
        reducer: {
            settings: settingsReducer
        },
        preloadedState: preloadedState as RootState | undefined
    })
}

describe('Model Steering - Hook Integration', () => {
    describe('useAppSelector with selectSelectedChatModel', () => {
        it('should select chat model from store', () => {
            const store = createMockStore({
                settings: {
                    toolSettings: {
                        task_agent: false,
                        deep_research: false,
                        design_document: false,
                        pdf: true,
                        media_generation: false,
                        audio_generation: false,
                        thinking_tokens: 10000,
                        enable_reviewer: false,
                        codex_tools: false,
                        claude_code: false
                    },
                    chatToolSettings: {
                        web_search: true,
                        web_visit: true,
                        image_search: true,
                        code_interpreter: true,
                        generate_image: true,
                        generate_video: false
                    },
                    chatMediaPreference: {
                        enabled: false,
                        type: 'image',
                        model_name: '',
                        provider: '',
                        voice_enabled: true,
                        rich_dialogue: false
                    },
                    councilPreference: {
                        enabled: false,
                        councilModelIds: [],
                        synthesisModelId: ''
                    },
                    selectedModel: undefined,
                    selectedChatModel: 'gpt-4o',
                    selectedAgentModel: undefined,
                    availableModels: [],
                    currentSettingData: undefined,
                    isSavingSetting: false,
                    claudeCodeConfig: undefined,
                    selectedGitHubRepository: undefined
                }
            })

            const state = store.getState()
            const chatModel = selectSelectedChatModel(state)
            
            expect(chatModel).toBe('gpt-4o')
        })

        it('should select agent model from store', () => {
            const store = createMockStore({
                settings: {
                    toolSettings: {
                        task_agent: false,
                        deep_research: false,
                        design_document: false,
                        pdf: true,
                        media_generation: false,
                        audio_generation: false,
                        thinking_tokens: 10000,
                        enable_reviewer: false,
                        codex_tools: false,
                        claude_code: false
                    },
                    chatToolSettings: {
                        web_search: true,
                        web_visit: true,
                        image_search: true,
                        code_interpreter: true,
                        generate_image: true,
                        generate_video: false
                    },
                    chatMediaPreference: {
                        enabled: false,
                        type: 'image',
                        model_name: '',
                        provider: '',
                        voice_enabled: true,
                        rich_dialogue: false
                    },
                    councilPreference: {
                        enabled: false,
                        councilModelIds: [],
                        synthesisModelId: ''
                    },
                    selectedModel: undefined,
                    selectedChatModel: undefined,
                    selectedAgentModel: 'claude-3-5-sonnet',
                    availableModels: [],
                    currentSettingData: undefined,
                    isSavingSetting: false,
                    claudeCodeConfig: undefined,
                    selectedGitHubRepository: undefined
                }
            })

            const state = store.getState()
            const agentModel = selectSelectedAgentModel(state)
            
            expect(agentModel).toBe('claude-3-5-sonnet')
        })
    })

    describe('Model Selection Dispatch', () => {
        it('should dispatch setSelectedChatModel action', () => {
            const store = createMockStore()
            
            act(() => {
                store.dispatch(setSelectedChatModel('gpt-4o'))
            })
            
            const state = store.getState()
            expect(selectSelectedChatModel(state)).toBe('gpt-4o')
        })

        it('should dispatch setSelectedAgentModel action', () => {
            const store = createMockStore()
            
            act(() => {
                store.dispatch(setSelectedAgentModel('claude-3-5-sonnet'))
            })
            
            const state = store.getState()
            expect(selectSelectedAgentModel(state)).toBe('claude-3-5-sonnet')
        })

        it('should handle independent model updates', () => {
            const store = createMockStore()
            
            act(() => {
                store.dispatch(setSelectedChatModel('gpt-4o'))
                store.dispatch(setSelectedAgentModel('claude-3-5-sonnet'))
            })
            
            const state = store.getState()
            expect(selectSelectedChatModel(state)).toBe('gpt-4o')
            expect(selectSelectedAgentModel(state)).toBe('claude-3-5-sonnet')
        })

        it('should update chat model without affecting agent model', () => {
            const store = createMockStore()
            
            act(() => {
                store.dispatch(setSelectedChatModel('gpt-4o'))
                store.dispatch(setSelectedAgentModel('claude-3-5-sonnet'))
            })

            // Update chat model
            act(() => {
                store.dispatch(setSelectedChatModel('gpt-4-turbo'))
            })
            
            const state = store.getState()
            expect(selectSelectedChatModel(state)).toBe('gpt-4-turbo')
            expect(selectSelectedAgentModel(state)).toBe('claude-3-5-sonnet')
        })

        it('should update agent model without affecting chat model', () => {
            const store = createMockStore()
            
            act(() => {
                store.dispatch(setSelectedChatModel('gpt-4o'))
                store.dispatch(setSelectedAgentModel('claude-3-5-sonnet'))
            })

            // Update agent model
            act(() => {
                store.dispatch(setSelectedAgentModel('claude-3-opus'))
            })
            
            const state = store.getState()
            expect(selectSelectedChatModel(state)).toBe('gpt-4o')
            expect(selectSelectedAgentModel(state)).toBe('claude-3-opus')
        })
    })
})

describe('Model Steering - Default Model Initialization', () => {
    it('should set both models to first available model on init', () => {
        const availableModels: IModel[] = [
            { id: 'gpt-4o', model: 'GPT-4o', provider: 'OpenAI', source: 'system' },
            { id: 'claude-3-opus', model: 'Claude 3 Opus', provider: 'Anthropic', source: 'system' }
        ]

        const store = createMockStore()

        act(() => {
            store.dispatch(setAvailableModels(availableModels))
            // Simulate auth-context initialization
            store.dispatch(setSelectedChatModel(availableModels[0].id))
            store.dispatch(setSelectedAgentModel(availableModels[0].id))
        })

        const state = store.getState()
        expect(selectSelectedChatModel(state)).toBe('gpt-4o')
        expect(selectSelectedAgentModel(state)).toBe('gpt-4o')
    })

    it('should handle empty available models gracefully', () => {
        const store = createMockStore()

        act(() => {
            store.dispatch(setAvailableModels([]))
        })

        const state = store.getState()
        expect(selectSelectedChatModel(state)).toBeUndefined()
        expect(selectSelectedAgentModel(state)).toBeUndefined()
    })

    it('should validate that model is in available models before setting', () => {
        const availableModels: IModel[] = [
            { id: 'gpt-4o', model: 'GPT-4o', provider: 'OpenAI', source: 'system' },
            { id: 'claude-3-opus', model: 'Claude 3 Opus', provider: 'Anthropic', source: 'system' }
        ]

        const store = createMockStore()

        act(() => {
            store.dispatch(setAvailableModels(availableModels))
        })

        // Verify that the available models are set
        const state = store.getState()
        const available = state.settings.availableModels
        expect(available).toHaveLength(2)
        
        // If we try to set a model that's available, it should work
        act(() => {
            const isAvailable = available.some(m => m.id === 'gpt-4o')
            if (isAvailable) {
                store.dispatch(setSelectedChatModel('gpt-4o'))
            }
        })

        const updatedState = store.getState()
        expect(selectSelectedChatModel(updatedState)).toBe('gpt-4o')
    })
})
