import { createSlice, PayloadAction } from '@reduxjs/toolkit'
import {
    AGENT_TYPE,
    BUILD_MODE,
    Milestone,
    PlanModificationSuggestion,
    QUESTION_MODE,
    TAB,
    VIEW_MODE
} from '@/typings/agent'
import { type SlideTemplate } from '@/services/slide.service'

interface UIState {
    activeTab: TAB
    viewMode: VIEW_MODE
    isLoading: boolean
    isGeneratingPrompt: boolean
    isFromNewQuestion: boolean
    isCreatingSession: boolean
    selectedFeature: string | null
    shouldFocusInput: boolean
    selectedSlideTemplate: SlideTemplate | null
    isMobileChatVisible: boolean
    questionMode: QUESTION_MODE
    buildMode: BUILD_MODE
    milestones: Milestone[]
    selectedMilestoneId: string | null
    planSummary: string | null
    planModificationOptions: {
        message: string
        suggestions: PlanModificationSuggestion[]
    } | null
}

const initialState: UIState = {
    activeTab: TAB.BUILD,
    viewMode: VIEW_MODE.CHAT,
    isLoading: false,
    isGeneratingPrompt: false,
    isFromNewQuestion: false,
    isCreatingSession: false,
    selectedFeature: AGENT_TYPE.GENERAL,
    shouldFocusInput: false,
    selectedSlideTemplate: null,
    isMobileChatVisible: true,
    questionMode: QUESTION_MODE.CHAT,
    buildMode: BUILD_MODE.BUILD,
    milestones: [],
    selectedMilestoneId: null,
    planSummary: null,
    planModificationOptions: null
}

const uiSlice = createSlice({
    name: 'ui',
    initialState,
    reducers: {
        setActiveTab: (state, action: PayloadAction<TAB>) => {
            state.activeTab = action.payload
        },
        setViewMode: (state, action: PayloadAction<VIEW_MODE>) => {
            state.viewMode = action.payload
        },
        setLoading: (state, action: PayloadAction<boolean>) => {
            state.isLoading = action.payload
        },
        setGeneratingPrompt: (state, action: PayloadAction<boolean>) => {
            state.isGeneratingPrompt = action.payload
        },
        setIsFromNewQuestion: (state, action: PayloadAction<boolean>) => {
            state.isFromNewQuestion = action.payload
        },
        setIsCreatingSession: (state, action: PayloadAction<boolean>) => {
            state.isCreatingSession = action.payload
        },
        setSelectedFeature: (state, action: PayloadAction<string | null>) => {
            state.selectedFeature = action.payload
        },
        setShouldFocusInput: (state, action: PayloadAction<boolean>) => {
            state.shouldFocusInput = action.payload
        },
        setSelectedSlideTemplate: (
            state,
            action: PayloadAction<SlideTemplate | null>
        ) => {
            state.selectedSlideTemplate = action.payload
        },
        resetSlideTemplate: (state) => {
            state.selectedSlideTemplate = null
        },
        setIsMobileChatVisible: (state, action: PayloadAction<boolean>) => {
            state.isMobileChatVisible = action.payload
        },
        setQuestionMode: (state, action: PayloadAction<QUESTION_MODE>) => {
            state.questionMode = action.payload
        },
        setBuildMode: (state, action: PayloadAction<BUILD_MODE>) => {
            state.buildMode = action.payload
        },
        setMilestones: (state, action: PayloadAction<Milestone[]>) => {
            state.milestones = action.payload
        },
        updateMilestoneContent: (
            state,
            action: PayloadAction<{ id: string; content: string }>
        ) => {
            const milestone = state.milestones.find(
                (m) => m.id === action.payload.id
            )
            if (milestone) {
                milestone.content = action.payload.content
            }
        },
        addMilestone: (state, action: PayloadAction<Milestone>) => {
            state.milestones.push(action.payload)
            // If all milestones were completed, select the newly added one
            if (!state.selectedMilestoneId) {
                state.selectedMilestoneId = action.payload.id
            }
        },
        deleteMilestone: (state, action: PayloadAction<{ id: string }>) => {
            const deletedId = action.payload.id
            state.milestones = state.milestones.filter(
                (m) => m.id !== deletedId
            )

            if (state.milestones.length === 0) {
                state.selectedMilestoneId = null
                state.planModificationOptions = null
                return
            }

            if (state.selectedMilestoneId === deletedId) {
                const nextPending = state.milestones.find(
                    (m) => m.status === 'pending'
                )
                state.selectedMilestoneId = nextPending?.id || null
            }
        },
        updateMilestoneStatus: (
            state,
            action: PayloadAction<{ id: string; status: Milestone['status'] }>
        ) => {
            const milestone = state.milestones.find(
                (m) => m.id === action.payload.id
            )
            if (milestone) {
                milestone.status = action.payload.status

                // If this milestone was just completed and it's currently selected,
                // automatically move selection to the next pending milestone
                if (
                    action.payload.status === 'completed' &&
                    state.selectedMilestoneId === action.payload.id
                ) {
                    const nextPending = state.milestones.find(
                        (m) => m.status === 'pending'
                    )
                    state.selectedMilestoneId = nextPending?.id || null
                }
            }
        },
        clearMilestones: (state) => {
            state.milestones = []
            state.selectedMilestoneId = null
            state.planSummary = null
            state.planModificationOptions = null
        },
        setSelectedMilestoneId: (
            state,
            action: PayloadAction<string | null>
        ) => {
            state.selectedMilestoneId = action.payload
        },
        setPlanSummary: (state, action: PayloadAction<string | null>) => {
            state.planSummary = action.payload
        },
        setPlanData: (
            state,
            action: PayloadAction<{ summary: string; milestones: Milestone[] }>
        ) => {
            state.planSummary = action.payload.summary
            state.milestones = action.payload.milestones
            // Auto-select the first pending milestone
            const firstPending = action.payload.milestones.find(
                (m) => m.status === 'pending'
            )
            state.selectedMilestoneId = firstPending?.id || null
            // Clear modification options when new plan is set
            state.planModificationOptions = null
        },
        setPlanModificationOptions: (
            state,
            action: PayloadAction<{
                message: string
                suggestions: PlanModificationSuggestion[]
            } | null>
        ) => {
            state.planModificationOptions = action.payload
        },
        clearPlanModificationOptions: (state) => {
            state.planModificationOptions = null
        }
    }
})

export const {
    setActiveTab,
    setViewMode,
    setLoading,
    setGeneratingPrompt,
    setIsFromNewQuestion,
    setIsCreatingSession,
    setSelectedFeature,
    setShouldFocusInput,
    setSelectedSlideTemplate,
    resetSlideTemplate,
    setIsMobileChatVisible,
    setQuestionMode,
    setBuildMode,
    setMilestones,
    updateMilestoneContent,
    addMilestone,
    deleteMilestone,
    updateMilestoneStatus,
    clearMilestones,
    setSelectedMilestoneId,
    setPlanSummary,
    setPlanData,
    setPlanModificationOptions,
    clearPlanModificationOptions
} = uiSlice.actions
export const uiReducer = uiSlice.reducer

// Selectors
export const selectActiveTab = (state: { ui: UIState }) => state.ui.activeTab
export const selectViewMode = (state: { ui: UIState }) => state.ui.viewMode
export const selectIsLoading = (state: { ui: UIState }) => state.ui.isLoading
export const selectIsGeneratingPrompt = (state: { ui: UIState }) =>
    state.ui.isGeneratingPrompt
export const selectIsFromNewQuestion = (state: { ui: UIState }) =>
    state.ui.isFromNewQuestion
export const selectIsCreatingSession = (state: { ui: UIState }) =>
    state.ui.isCreatingSession
export const selectSelectedFeature = (state: { ui: UIState }) =>
    state.ui.selectedFeature
export const selectShouldFocusInput = (state: { ui: UIState }) =>
    state.ui.shouldFocusInput
export const selectSelectedSlideTemplate = (state: { ui: UIState }) =>
    state.ui.selectedSlideTemplate
export const selectIsMobileChatVisible = (state: { ui: UIState }) =>
    state.ui.isMobileChatVisible
export const selectQuestionMode = (state: { ui: UIState }) =>
    state.ui.questionMode
export const selectBuildMode = (state: { ui: UIState }) => state.ui.buildMode
export const selectMilestones = (state: { ui: UIState }) => state.ui.milestones
export const selectCurrentMilestone = (state: { ui: UIState }) => {
    const milestones = state.ui.milestones
    return (
        milestones.find((m) => m.status === 'in_progress') ||
        milestones.find((m) => m.status === 'pending')
    )
}
export const selectMilestoneProgress = (state: { ui: UIState }) => {
    const milestones = state.ui.milestones
    if (milestones.length === 0) return 0
    const completed = milestones.filter((m) => m.status === 'completed').length
    return Math.round((completed / milestones.length) * 100)
}
export const selectSelectedMilestoneId = (state: { ui: UIState }) =>
    state.ui.selectedMilestoneId
export const selectSelectedMilestone = (state: { ui: UIState }) => {
    const { milestones, selectedMilestoneId } = state.ui
    // Honor explicit selection only if the milestone is still actionable.
    // If the selection points at a milestone that's already completed/failed
    // (e.g. because a MILESTONE_UPDATE event was missed or state diverged
    // from the server), fall through to the next pending milestone instead
    // of leaving the "next milestone" indicator stuck on a stale entry.
    if (selectedMilestoneId) {
        const selected = milestones.find((m) => m.id === selectedMilestoneId)
        if (
            selected &&
            (selected.status === 'pending' || selected.status === 'in_progress')
        ) {
            return selected
        }
    }
    // Default: return the first in-progress or pending milestone
    return (
        milestones.find((m) => m.status === 'in_progress') ||
        milestones.find((m) => m.status === 'pending') ||
        null
    )
}
export const selectPlanSummary = (state: { ui: UIState }) =>
    state.ui.planSummary
export const selectHasPlan = (state: { ui: UIState }) =>
    state.ui.milestones.length > 0 && state.ui.planSummary !== null
export const selectPlanModificationOptions = (state: { ui: UIState }) =>
    state.ui.planModificationOptions
