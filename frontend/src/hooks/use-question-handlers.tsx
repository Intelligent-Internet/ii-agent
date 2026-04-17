import { useMemo, useRef, useEffect } from 'react'
import { toast } from 'sonner'

import { isImageFile } from '@/lib/utils'

import {
    addMessage,
    clearPlanModificationOptions,
    selectAvailableModels,
    selectMessages,
    selectSelectedAgentModel,
    selectToolSettings,
    selectCurrentMessageFileIds,
    selectUploadedFiles,
    selectWsConnectionState,
    setBuildStep,
    setCurrentActionData,
    setCurrentQuestion,
    setGeneratingPrompt,
    setIsCreatingSession,
    setLoading,
    setMessages,
    setRequireClearFiles,
    clearCurrentMessageFileIds,
    setRunStatus,
    updateMessage,
    useAppDispatch,
    useAppSelector,
    selectSelectedFeature,
    selectSelectedSlideTemplate,
    resetSlideTemplate,
    setActiveTab,
    setSandboxIframeAwake,
    setPendingQuery,
    setIsMobileChatVisible,
    selectPendingQuery,
    selectActiveSessionId,
    selectSelectedGitHubRepository,
    selectBuildMode,
    selectHasPlan,
    moveSessionToTop,
    selectChats,
    selectProjects,
    selectChatMediaPreference
} from '@/state'
import {
    AGENT_TYPE,
    BUILD_MODE,
    ChatMessagePayload,
    CommandPayload,
    CommandType,
    Milestone,
    TAB,
    WebSocketConnectionState
} from '@/typings/agent'
import { BUILD_STEP, Message } from '@/typings/agent'
import { useSocketIOContext } from '@/contexts/websocket-context'
import { promptService } from '@/services/prompt.service'
import { useParams } from 'react-router'

export function useQuestionHandlers() {
    const dispatch = useAppDispatch()
    const { sendMessage, joinSession } = useSocketIOContext()
    const { sessionId } = useParams()

    const messages = useAppSelector(selectMessages)
    const selectedModelId = useAppSelector(selectSelectedAgentModel)
    const availableModels = useAppSelector(selectAvailableModels)
    const toolSettings = useAppSelector(selectToolSettings)
    const currentMessageFileIds = useAppSelector(selectCurrentMessageFileIds)
    const uploadedFiles = useAppSelector(selectUploadedFiles)
    const wsConnectionState = useAppSelector(selectWsConnectionState)
    const selectedFeature = useAppSelector(selectSelectedFeature)
    const selectedSlideTemplate = useAppSelector(selectSelectedSlideTemplate)
    const pendingQuery = useAppSelector(selectPendingQuery)
    const activeSessionId = useAppSelector(selectActiveSessionId)
    const selectedGitHubRepository = useAppSelector(
        selectSelectedGitHubRepository
    )
    const buildMode = useAppSelector(selectBuildMode)
    const hasPlan = useAppSelector(selectHasPlan)
    const chats = useAppSelector(selectChats)
    const projects = useAppSelector(selectProjects)
    const chatMediaPreference = useAppSelector(selectChatMediaPreference)

    // Track previous session ID to detect when session is created
    const previousSessionIdRef = useRef(activeSessionId)

    const selectedModel = useMemo(
        () => availableModels.find((m) => m.id === selectedModelId),
        [selectedModelId, availableModels]
    )

    // Send pending query when session ID transitions from null/undefined to a value
    useEffect(() => {
        const wasNoSession = !previousSessionIdRef.current
        const nowHasSession = !!activeSessionId

        // Only send when we transition to having a session AND there's a pending query
        if (wasNoSession && nowHasSession && pendingQuery) {
            console.log(
                'Session created, sending pending query with session_uuid:',
                activeSessionId
            )
            // Extract command type from pending query (defaults to 'query')
            const pendingQueryObj = pendingQuery as unknown as Record<
                string,
                unknown
            >
            const { _commandType, ...queryContent } = pendingQueryObj
            const cmd = (_commandType as string) || CommandType.QUERY
            sendMessage({
                session_uuid: activeSessionId,
                content: {
                    command: cmd as CommandType,
                    ...queryContent
                } as ChatMessagePayload['content']
            })
            dispatch(setPendingQuery(null))
        }

        // Update the previous value for next render
        previousSessionIdRef.current = activeSessionId
    }, [activeSessionId, sendMessage, pendingQuery, dispatch])

    const handleEnhancePrompt = async ({
        prompt,
        onSuccess
    }: {
        prompt: string
        onSuccess: (res: string) => void
    }) => {
        if (!prompt.trim()) {
            toast.error('Please enter a prompt to enhance.')
            return
        }

        dispatch(setGeneratingPrompt(true))

        try {
            const response = await promptService.enhancePrompt({
                prompt,
                context:
                    selectedFeature !== AGENT_TYPE.GENERAL
                        ? `This is for ${selectedFeature} feature`
                        : undefined
            })
            onSuccess(response.enhanced_prompt)
            dispatch(setGeneratingPrompt(false))
            toast.success('Prompt enhanced successfully!')
        } catch (error) {
            console.error('Error enhancing prompt:', error)
            dispatch(setGeneratingPrompt(false))
            toast.error('Failed to enhance prompt. Please try again.')
        }
    }

    const handleQuestionSubmit = (
        newQuestion: string,
        isNewSession = false
    ) => {
        if (!newQuestion.trim()) return

        // Clear plan modification suggestions when user submits a message
        dispatch(clearPlanModificationOptions())

        if (wsConnectionState !== WebSocketConnectionState.CONNECTED) {
            toast.error('WebSocket connection is not open. Please try again.')
            dispatch(setLoading(false))
            return
        }

        // Check if Codex is selected but tools are not enabled
        if (selectedFeature === AGENT_TYPE.CODEX && !toolSettings.codex_tools) {
            toast.warning(
                'Codex tools must be enabled to use the Codex agent. Please enable it in the settings.'
            )
            dispatch(setLoading(false))
            return
        }

        // Check if a model is selected
        if (!selectedModel || !selectedModel.id) {
            toast.error(
                'Please select a model before submitting your question.'
            )
            dispatch(setLoading(false))
            return
        }

        // Check if Claude Code is selected but tools are not enabled
        if (
            selectedFeature === AGENT_TYPE.CLAUDE_CODE &&
            !toolSettings.claude_code
        ) {
            toast.warning(
                'Claude code must be enabled to use. Please enable it in the settings.'
            )
            dispatch(setLoading(false))
            return
        }

        // Determine if this is a new session creation (no sessionId in route or explicitly new)
        const isCreatingNewSession = !sessionId || isNewSession

        dispatch(setRunStatus('running'))
        dispatch(setLoading(true))
        dispatch(setActiveTab(TAB.BUILD))
        dispatch(setIsMobileChatVisible(true))
        dispatch(setBuildStep(BUILD_STEP.THINKING))
        dispatch(setSandboxIframeAwake(true))
        dispatch(setCurrentActionData(undefined))

        // Show all hidden messages
        messages.forEach((message) => {
            if (message.isHidden) {
                dispatch(updateMessage({ ...message, isHidden: false }))
            }
        })

        // Build files data for display from uploadedFiles matching currentMessageFileIds
        const attachedFiles = uploadedFiles.filter((file) => {
            // Check if this file's ID is in currentMessageFileIds
            if (currentMessageFileIds.includes(file.id)) {
                return true
            }
            // For folders, check if any of the comma-separated IDs match
            if (file.id.includes(',')) {
                const folderFileIds = file.id.split(',')
                return folderFileIds.some((fid) =>
                    currentMessageFileIds.includes(fid)
                )
            }
            return false
        })

        const userMessageFiles =
            attachedFiles.length > 0
                ? attachedFiles.map((file) => {
                      // If it's a folder, format the name to include file count
                      const fileName =
                          file.folderName &&
                          file.fileCount &&
                          file.fileCount > 0
                              ? `${file.folderName} (${file.fileCount} file${file.fileCount === 1 ? '' : 's'})`
                              : file.name

                      return {
                          id: file.id,
                          file_name: fileName,
                          file_size: file.size,
                          content_type: file.path.startsWith('data:')
                              ? file.path.split(';')[0].replace('data:', '')
                              : 'application/octet-stream',
                          created_at: new Date().toISOString()
                      }
                  })
                : undefined

        const userMessageFileContents = attachedFiles.reduce<
            Record<string, string>
        >((acc, file) => {
            // Use the formatted file name for consistency with userMessageFiles
            const fileName =
                file.folderName && file.fileCount && file.fileCount > 0
                    ? `${file.folderName} (${file.fileCount} file${file.fileCount === 1 ? '' : 's'})`
                    : file.name

            if (isImageFile(file.name)) {
                acc[fileName] = file.path
            }
            return acc
        }, {})

        // Capture video frames before they get cleared (for display in chat)
        const videoFrames =
            chatMediaPreference.type === 'video' &&
            chatMediaPreference.video_frames &&
            chatMediaPreference.video_frames.length > 0
                ? [...chatMediaPreference.video_frames]
                : undefined

        const newUserMessage: Message = {
            id: Date.now().toString(),
            role: 'user',
            content: newQuestion,
            timestamp: Date.now(),
            ...(userMessageFiles && userMessageFiles.length > 0
                ? { files: userMessageFiles }
                : {}),
            ...(Object.keys(userMessageFileContents).length > 0
                ? { fileContents: userMessageFileContents }
                : {}),
            ...(videoFrames ? { videoFrames } : {})
        }

        if (isCreatingNewSession) {
            dispatch(setMessages([newUserMessage]))
            dispatch(setIsCreatingSession(true))
        } else {
            dispatch(setRequireClearFiles(true))
            dispatch(setCurrentQuestion(''))
            dispatch(addMessage(newUserMessage))
        }

        // Clear current message file IDs after sending
        dispatch(clearCurrentMessageFileIds())

        const { thinking_tokens, ...tool_args } = toolSettings

        // Prepare metadata
        const metadata: Record<string, unknown> = {}
        if (selectedFeature === AGENT_TYPE.SLIDE && selectedSlideTemplate) {
            metadata.template_id = selectedSlideTemplate.id
        }

        // Reset slide template after preparing metadata
        if (selectedSlideTemplate) {
            dispatch(resetSlideTemplate())
        }

        // Map BUILD_MODE to backend build_mode values
        // Force 'build' mode when feature is not GENERAL and not WEBSITE_BUILD
        const buildModeValue =
            selectedFeature !== AGENT_TYPE.GENERAL &&
            selectedFeature !== AGENT_TYPE.WEBSITE_BUILD
                ? 'build'
                : buildMode === BUILD_MODE.PLAN
                  ? hasPlan
                      ? 'modify_plan'
                      : 'plan'
                  : 'build'

        // Prepare the query content
        const queryContent = {
            model_id: selectedModel.id,
            provider: selectedModel.provider,
            source: selectedModel.source,
            agent_type: selectedFeature ?? undefined,
            tool_args,
            thinking_tokens,
            metadata: Object.keys(metadata).length > 0 ? metadata : undefined,
            // Query params
            text: newQuestion,
            resume: messages.length > 0,
            files: currentMessageFileIds,
            // Connector context
            github_repository: selectedGitHubRepository,
            // Plan mode
            build_mode: buildModeValue
        }

        // Determine command type based on build mode
        const commandType =
            buildModeValue === 'build'
                ? CommandType.QUERY
                : CommandType.PLAN

        if (isCreatingNewSession) {
            // New session: Join session first, then wait for session_id event
            // The pending query will be sent automatically when session_id is received
            console.log(
                'New session: storing pending query and joining session'
            )
            dispatch(
                setPendingQuery({ ...queryContent, _commandType: commandType })
            )
            joinSession()
        } else {
            // Existing session: Send query immediately
            console.log('Existing session: sending query immediately')

            // Move the session to the top of the list
            if (sessionId) {
                const isInChats = chats.some((s) => s.id === sessionId)
                const isInProjects = projects.some((s) => s.id === sessionId)

                if (isInChats) {
                    dispatch(
                        moveSessionToTop({
                            sessionId,
                            sessionType: 'chat'
                        })
                    )
                } else if (isInProjects) {
                    dispatch(
                        moveSessionToTop({
                            sessionId,
                            sessionType: 'agent'
                        })
                    )
                } else {
                    dispatch(
                        moveSessionToTop({
                            sessionId,
                            sessionType: 'chat'
                        })
                    )
                    dispatch(
                        moveSessionToTop({
                            sessionId,
                            sessionType: 'agent'
                        })
                    )
                }
            }

            sendMessage({
                session_uuid: sessionId || '',
                content: {
                    command: commandType,
                    ...queryContent
                } as CommandPayload
            })
        }
    }

    const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault()
            handleQuestionSubmit((e.target as HTMLTextAreaElement).value)
        }
    }

    const handleBuildMilestone = (
        milestone: Milestone,
        planContext: { summary: string; milestones: Milestone[] }
    ) => {
        if (wsConnectionState !== WebSocketConnectionState.CONNECTED) {
            toast.error('WebSocket connection is not open. Please try again.')
            return
        }

        if (!selectedModel || !selectedModel.id) {
            toast.error('Please select a model before building the milestone.')
            return
        }

        dispatch(setRunStatus('running'))
        dispatch(setLoading(true))
        dispatch(setActiveTab(TAB.BUILD))
        dispatch(setIsMobileChatVisible(true))
        dispatch(setBuildStep(BUILD_STEP.THINKING))
        dispatch(setSandboxIframeAwake(true))
        dispatch(setCurrentActionData(undefined))

        const { thinking_tokens, ...tool_args } = toolSettings

        // Prepare the query content for milestone execution
        const queryContent = {
            model_id: selectedModel.id,
            provider: selectedModel.provider,
            source: selectedModel.source,
            agent_type: selectedFeature ?? undefined,
            tool_args,
            thinking_tokens,
            // Query params
            text: `Build milestone ${milestone.id}: ${milestone.content}`,
            resume: true,
            files: currentMessageFileIds,
            // Connector context (same as regular queries)
            github_repository: selectedGitHubRepository,
            // Plan mode params
            build_mode: 'build',
            milestone_ids: [milestone.id], // Array of milestone IDs to build
            plan_context: planContext
        }

        // Clear current message file IDs after sending
        dispatch(clearCurrentMessageFileIds())

        sendMessage({
            session_uuid: sessionId || '',
            content: {
                command: CommandType.QUERY,
                ...queryContent
            } as CommandPayload
        })
    }

    const handleBuildAllMilestones = (planContext: {
        summary: string
        milestones: Milestone[]
    }) => {
        if (wsConnectionState !== WebSocketConnectionState.CONNECTED) {
            toast.error('WebSocket connection is not open. Please try again.')
            return
        }

        if (!selectedModel || !selectedModel.id) {
            toast.error('Please select a model before building milestones.')
            return
        }

        dispatch(setRunStatus('running'))
        dispatch(setLoading(true))
        dispatch(setActiveTab(TAB.BUILD))
        dispatch(setIsMobileChatVisible(true))
        dispatch(setBuildStep(BUILD_STEP.THINKING))
        dispatch(setSandboxIframeAwake(true))
        dispatch(setCurrentActionData(undefined))

        const { thinking_tokens, ...tool_args } = toolSettings

        // Build text listing all milestones
        const milestonesText = planContext.milestones
            .map((m, i) => `${i + 1}. ${m.content}`)
            .join('\n')

        // Extract all milestone IDs
        const allMilestoneIds = planContext.milestones.map((m) => m.id)

        // Prepare the query content for building all milestones
        const queryContent = {
            model_id: selectedModel.id,
            provider: selectedModel.provider,
            source: selectedModel.source,
            agent_type: selectedFeature ?? undefined,
            tool_args,
            thinking_tokens,
            // Query params
            text: `Build all milestones:\n${milestonesText}`,
            resume: true,
            files: currentMessageFileIds,
            // Connector context (same as regular queries)
            github_repository: selectedGitHubRepository,
            // Plan mode params
            build_mode: 'build',
            milestone_ids: allMilestoneIds, // Array of all milestone IDs
            plan_context: planContext
        }

        // Clear current message file IDs after sending
        dispatch(clearCurrentMessageFileIds())

        sendMessage({
            session_uuid: sessionId || '',
            content: {
                command: CommandType.QUERY,
                ...queryContent
            } as CommandPayload
        })
    }

    const handleModifyPlan = () => {
        if (wsConnectionState !== WebSocketConnectionState.CONNECTED) {
            toast.error('WebSocket connection is not open. Please try again.')
            return
        }

        if (!selectedModel || !selectedModel.id) {
            toast.error('Please select a model first.')
            return
        }

        dispatch(setRunStatus('running'))
        dispatch(setLoading(true))

        const { thinking_tokens, ...tool_args } = toolSettings

        // Send modify_plan_suggestions request to get AI-generated suggestions
        const queryContent = {
            model_id: selectedModel.id,
            provider: selectedModel.provider,
            source: selectedModel.source,
            agent_type: selectedFeature ?? undefined,
            tool_args,
            thinking_tokens,
            // Query params
            text: '', // Empty text triggers suggestions generation
            resume: true,
            files: [],
            // Connector context
            github_repository: selectedGitHubRepository,
            // Build mode - request suggestions
            build_mode: 'modify_plan_suggestions'
        }

        sendMessage({
            session_uuid: sessionId || '',
            content: {
                command: CommandType.PLAN,
                ...queryContent
            } as CommandPayload
        })
    }

    const handleSubmitPlanModification = (modificationText: string) => {
        if (!modificationText.trim()) return

        if (wsConnectionState !== WebSocketConnectionState.CONNECTED) {
            toast.error('WebSocket connection is not open. Please try again.')
            return
        }

        if (!selectedModel || !selectedModel.id) {
            toast.error('Please select a model first.')
            return
        }

        dispatch(setRunStatus('running'))
        dispatch(setLoading(true))
        dispatch(setActiveTab(TAB.BUILD))
        dispatch(setIsMobileChatVisible(true))
        dispatch(setBuildStep(BUILD_STEP.THINKING))
        dispatch(setSandboxIframeAwake(true))
        dispatch(setCurrentActionData(undefined))

        // Add user message to show in chat
        const newUserMessage: Message = {
            id: Date.now().toString(),
            role: 'user',
            content: modificationText,
            timestamp: Date.now()
        }
        dispatch(addMessage(newUserMessage))

        const { thinking_tokens, ...tool_args } = toolSettings

        // Send modify_plan request with the modification text
        const queryContent = {
            model_id: selectedModel.id,
            provider: selectedModel.provider,
            source: selectedModel.source,
            agent_type: selectedFeature ?? undefined,
            tool_args,
            thinking_tokens,
            // Query params
            text: modificationText,
            resume: true,
            files: [],
            // Connector context
            github_repository: selectedGitHubRepository,
            // Build mode - always modify_plan for plan modifications
            build_mode: 'modify_plan'
        }

        sendMessage({
            session_uuid: sessionId || '',
            content: {
                command: CommandType.PLAN,
                ...queryContent
            } as CommandPayload
        })
    }

    return {
        handleEnhancePrompt,
        handleQuestionSubmit,
        handleKeyDown,
        handleBuildMilestone,
        handleBuildAllMilestones,
        handleModifyPlan,
        handleSubmitPlanModification
    }
}
