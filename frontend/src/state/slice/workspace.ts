import { createSlice, PayloadAction } from '@reduxjs/toolkit'

interface WorkspaceState {
    workspaceInfo: string
    browserUrl: string
    vscodeUrl: string
    vncUrl: string
    mobileAppUrl: string
    currentQuestion: string
}

const initialState: WorkspaceState = {
    workspaceInfo: '',
    browserUrl: '',
    vscodeUrl: '',
    vncUrl: '',
    mobileAppUrl: '',
    currentQuestion: ''
}

const workspaceSlice = createSlice({
    name: 'workspace',
    initialState,
    reducers: {
        setWorkspaceInfo: (state, action: PayloadAction<string>) => {
            state.workspaceInfo = action.payload
        },
        setBrowserUrl: (state, action: PayloadAction<string>) => {
            state.browserUrl = action.payload
        },
        setVscodeUrl: (state, action: PayloadAction<string>) => {
            state.vscodeUrl = action.payload
        },
        setVncUrl: (state, action: PayloadAction<string>) => {
            state.vncUrl = action.payload
        },
        setMobileAppUrl: (state, action: PayloadAction<string>) => {
            state.mobileAppUrl = action.payload
        },
        setCurrentQuestion: (state, action: PayloadAction<string>) => {
            state.currentQuestion = action.payload
        }
    }
})

export const {
    setWorkspaceInfo,
    setBrowserUrl,
    setVscodeUrl,
    setVncUrl,
    setMobileAppUrl,
    setCurrentQuestion
} = workspaceSlice.actions
export const workspaceReducer = workspaceSlice.reducer

// Selectors
export const selectWorkspaceInfo = (state: { workspace: WorkspaceState }) =>
    state.workspace.workspaceInfo
export const selectBrowserUrl = (state: { workspace: WorkspaceState }) =>
    state.workspace.browserUrl
export const selectVscodeUrl = (state: { workspace: WorkspaceState }) =>
    state.workspace.vscodeUrl
export const selectVncUrl = (state: { workspace: WorkspaceState }) =>
    state.workspace.vncUrl
export const selectMobileAppUrl = (state: { workspace: WorkspaceState }) =>
    state.workspace.mobileAppUrl
export const selectCurrentQuestion = (state: { workspace: WorkspaceState }) =>
    state.workspace.currentQuestion
