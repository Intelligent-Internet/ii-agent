import { createSlice, PayloadAction } from '@reduxjs/toolkit'
import {
    ChatMediaPreference,
    ChatToolSettings,
    ISetting,
    ToolSettings
} from '@/typings/agent'
import { IModel } from '@/typings/settings'
import { GitHubRepositoryContext } from '@/typings/chat'

export interface CouncilPreference {
    enabled: boolean
    councilModelIds: string[]
    synthesisModelId: string
}

export interface SettingsState {
    toolSettings: ToolSettings
    chatToolSettings: ChatToolSettings
    chatMediaPreference: ChatMediaPreference
    councilPreference: CouncilPreference
    selectedModel?: string  // Deprecated: use selectedChatModel and selectedAgentModel
    selectedChatModel?: string  // Model for chat mode
    selectedAgentModel?: string  // Model for agent mode
    availableModels: IModel[]
    currentSettingData?: ISetting
    isSavingSetting: boolean
    claudeCodeConfig?: {
        id: string
        is_active: boolean
        updated_at: string
    }
    selectedGitHubRepository?: GitHubRepositoryContext
}

const initialState: SettingsState = {
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
    selectedAgentModel: undefined,
    availableModels: [],
    currentSettingData: undefined,
    isSavingSetting: false,
    claudeCodeConfig: undefined,
    selectedGitHubRepository: undefined
}

const settingsSlice = createSlice({
    name: 'settings',
    initialState,
    reducers: {
        setToolSettings: (state, action: PayloadAction<ToolSettings>) => {
            state.toolSettings = action.payload
        },
        setChatToolSettings: (
            state,
            action: PayloadAction<ChatToolSettings>
        ) => {
            state.chatToolSettings = action.payload
        },
        setChatMediaPreference: (
            state,
            action: PayloadAction<ChatMediaPreference>
        ) => {
            state.chatMediaPreference = action.payload
        },
        clearChatMediaTool: (state) => {
            state.chatMediaPreference = {
                ...state.chatMediaPreference,
                mini_tools: undefined
            }
        },
        resetChatMediaEnabled: (state) => {
            state.chatMediaPreference = {
                ...state.chatMediaPreference,
                enabled: false
            }
        },
        setCodexToolsStatus: (state, action: PayloadAction<boolean>) => {
            state.toolSettings.codex_tools = action.payload
        },
        setClaudeCodeToolsStatus: (state, action: PayloadAction<boolean>) => {
            state.toolSettings.claude_code = action.payload
        },
        setSelectedModel: (
            state,
            action: PayloadAction<string | undefined>
        ) => {
            state.selectedModel = action.payload
        },
        setSelectedChatModel: (
            state,
            action: PayloadAction<string | undefined>
        ) => {
            state.selectedChatModel = action.payload
        },
        setSelectedAgentModel: (
            state,
            action: PayloadAction<string | undefined>
        ) => {
            state.selectedAgentModel = action.payload
        },
        setAvailableModels: (state, action: PayloadAction<IModel[]>) => {
            state.availableModels = action.payload
        },
        setCurrentSettingData: (
            state,
            action: PayloadAction<ISetting | undefined>
        ) => {
            state.currentSettingData = action.payload
        },
        setIsSavingSetting: (state, action: PayloadAction<boolean>) => {
            state.isSavingSetting = action.payload
        },
        setClaudeCodeConfig: (
            state,
            action: PayloadAction<{
                id: string
                is_active: boolean
                updated_at: string
            }>
        ) => {
            state.claudeCodeConfig = action.payload
        },
        setSelectedGitHubRepository: (
            state,
            action: PayloadAction<GitHubRepositoryContext | undefined>
        ) => {
            state.selectedGitHubRepository = action.payload
        },
        setCouncilPreference: (
            state,
            action: PayloadAction<CouncilPreference>
        ) => {
            state.councilPreference = action.payload
        },
        resetCouncilMode: (state) => {
            state.councilPreference = {
                ...state.councilPreference,
                enabled: false
            }
        }
    }
})

export const {
    setToolSettings,
    setChatToolSettings,
    setCodexToolsStatus,
    setClaudeCodeToolsStatus,
    setSelectedModel,
    setSelectedChatModel,
    setSelectedAgentModel,
    setAvailableModels,
    setCurrentSettingData,
    setIsSavingSetting,
    setClaudeCodeConfig,
    setSelectedGitHubRepository,
    setChatMediaPreference,
    clearChatMediaTool,
    resetChatMediaEnabled,
    setCouncilPreference,
    resetCouncilMode
} = settingsSlice.actions
export const settingsReducer = settingsSlice.reducer

// Selectors
export const selectToolSettings = (state: { settings: SettingsState }) =>
    state.settings.toolSettings
export const selectChatToolSettings = (state: { settings: SettingsState }) =>
    state.settings.chatToolSettings
export const selectChatMediaPreference = (state: { settings: SettingsState }) =>
    state.settings.chatMediaPreference
export const selectSelectedChatModel = (state: { settings: SettingsState }) =>
    state.settings.selectedChatModel
export const selectSelectedAgentModel = (state: { settings: SettingsState }) =>
    state.settings.selectedAgentModel
export const selectSelectedModel = (state: { settings: SettingsState }) =>
    state.settings.selectedModel
export const selectAvailableModels = (state: { settings: SettingsState }) =>
    state.settings.availableModels
export const selectCurrentSettingData = (state: { settings: SettingsState }) =>
    state.settings.currentSettingData
export const selectIsSavingSetting = (state: { settings: SettingsState }) =>
    state.settings.isSavingSetting
export const selectClaudeCodeConfig = (state: { settings: SettingsState }) =>
    state.settings.claudeCodeConfig
export const selectSelectedGitHubRepository = (state: {
    settings: SettingsState
}) => state.settings.selectedGitHubRepository
export const selectCouncilPreference = (state: { settings: SettingsState }) =>
    state.settings.councilPreference
