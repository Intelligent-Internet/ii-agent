import {
    useCallback,
    useEffect,
    useLayoutEffect,
    useRef,
    useState
} from 'react'
import { useLocation, useParams } from 'react-router'

import { type MiniTool } from '@/constants/media-tools'
import { getMediaTypeConfig } from '@/constants/media-type-config'
import { FEATURES } from '@/constants/tool'
import { useChatMediaPreference } from '@/hooks/use-chat-media-preference'
import { useIsMobile } from '@/hooks/use-mobile'
import { useUploadFiles, type FileUploadStatus } from '@/hooks/use-upload-files'
import { useVideoFrameUpload } from '@/hooks/use-video-frame-upload'
import {
    getComposerBottomInset,
    keepTextareaTailVisible
} from '@/lib/textarea-visibility'
import { isImageFile } from '@/lib/utils'
import type {
    DownloadedFile,
    GitHubRepository
} from '@/services/connector.service'
import { type MediaTemplate } from '@/services/media-template.service'
import { type SlideTemplate } from '@/services/slide.service'
import {
    addToCurrentMessageFileIds,
    addUploadedFiles,
    clearCurrentMessageFileIds,
    selectAvailableModels,
    selectBuildMode,
    selectCouncilPreference,
    selectCurrentMessageFileIds,
    selectIsCancelling,
    selectQuestionMode,
    selectRequireClearFiles,
    selectSelectedFeature,
    selectSelectedChatModel,
    selectSelectedAgentModel,
    selectSelectedSlideTemplate,
    selectShouldFocusInput,
    selectSubscriptionPlan,
    selectUploadedFiles,
    resetCouncilMode,
    setBuildMode,
    setChatMediaPreference,
    setQuestionMode,
    setRequireClearFiles,
    setSelectedFeature,
    setSelectedSlideTemplate,
    setShouldFocusInput,
    useAppDispatch,
    useAppSelector
} from '@/state'
import { AGENT_TYPE, QUESTION_MODE } from '@/typings'
import type { AdvancedModeSettings } from '@/typings/chat'
import { useTranslation } from 'react-i18next'
import BuildModeDropdown, {
    LANDING_AVAILABLE_MODES
} from './build-mode-dropdown'
// Hidden: GitHub connector
// import ConnectorDropdown from './connector-dropdown'
import ChatMediaControlsMobile from './media/chat-media-controls-mobile'
import ChatMediaSection from './media/chat-media-section'
import ChatMediaToolbar from './media/chat-media-toolbar'
import ChatMediaVideoFrames from './media/chat-media-video-frames'
import { AdvancedModeController } from './media/image/advanced-mode-controller'
import { MediaTemplateExplorer } from './media/media-template-explorer'
import MediaTypeSelector from './media/media-type-selector'
import EnhanceButton from './question-enhance-button'
import FeatureSelector from './question-feature-selector'
import QuestionFileUpload from './question-file-upload'
import VoiceDictationButton from './voice-dictation-button'
import QuestionFilesPreview from './question-files-preview'
import ModeSelector from './question-mode-selector'
import SubmitButton from './question-submit-button'
import Suggestions from './question-suggestions'
import { SlideTemplateSelector } from './slide-template-selector'
import { Button } from './ui/button'
import { Icon } from './ui/icon'
import { Textarea } from './ui/textarea'
import clsx from 'clsx'
import { useMediaModels } from '@/hooks/use-media-models'
import { useChat } from '@/hooks/use-chat-query'
import { StorybookStylePicker } from './media/image/image-settings-picker'

interface QuestionInputProps {
    value: string
    setValue?: (value: string) => void
    handleKeyDown: (e: React.KeyboardEvent<HTMLTextAreaElement>) => void
    handleSubmit: (question: string) => void
    className?: string
    textareaClassName?: string
    placeholder?: string
    isDisabled?: boolean
    handleEnhancePrompt?: (payload: {
        prompt: string
        onSuccess: (res: string) => void
    }) => void
    handleCancel?: () => void
    onFilesChange?: (filesCount: number) => void
    hideSuggestions?: boolean
    hideFeatureSelector?: boolean
    hideModeSelector?: boolean
    hideBuildModeSelector?: boolean
    hideAdvancedMode?: boolean
    onOpenSetting?: () => void
    onGoogleDriveClick?: () => void
    isGoogleDriveConnected?: boolean
    isGoogleDriveAuthLoading?: boolean
    googleDriveFiles?: DownloadedFile[]
    onGoogleDriveFilesHandled?: () => void
    onGitHubConnect?: () => void
    isGitHubConnected?: boolean
    onRepositorySelect?: (repository: GitHubRepository | undefined) => void
    isConnectorDropdownOpen?: boolean
    onConnectorDropdownOpenChange?: (open: boolean) => void
    hideChatMediaCancel?: boolean
    // Mini Tools props
    miniToolsSessionId?: string
    miniToolsDisabled?: boolean
    advancedModeSettings?: AdvancedModeSettings | null
    onAdvancedModeSettingsChange?: (
        settings: AdvancedModeSettings | null
    ) => void
    onMiniToolSelect?: (tool: MiniTool) => void
    onMiniToolClear?: () => void
    onSetMiniToolBoardOpenSignalMobile?: () => void
    focusTextareaSignal?: number
}

const QuestionInput = ({
    className,
    textareaClassName,
    placeholder,
    value,
    handleKeyDown,
    handleSubmit,
    isDisabled,
    handleEnhancePrompt,
    handleCancel,
    onFilesChange,
    hideSuggestions,
    hideFeatureSelector,
    hideModeSelector,
    hideBuildModeSelector,
    hideAdvancedMode,
    onOpenSetting,
    onGoogleDriveClick,
    isGoogleDriveConnected,
    isGoogleDriveAuthLoading,
    googleDriveFiles,
    onGoogleDriveFilesHandled,
    // Hidden: GitHub connector props
    // onGitHubConnect,
    // isGitHubConnected,
    onRepositorySelect,
    // isConnectorDropdownOpen,
    // onConnectorDropdownOpenChange,
    hideChatMediaCancel,
    miniToolsSessionId,
    miniToolsDisabled,
    advancedModeSettings,
    onAdvancedModeSettingsChange,
    onMiniToolSelect,
    onMiniToolClear,
    focusTextareaSignal
}: QuestionInputProps) => {
    const { t } = useTranslation()
    const dispatch = useAppDispatch()
    const requireClearFiles = useAppSelector(selectRequireClearFiles)
    const uploadedFiles = useAppSelector(selectUploadedFiles)
    const currentMessageFileIds = useAppSelector(selectCurrentMessageFileIds)
    const selectedFeature = useAppSelector(selectSelectedFeature)
    const shouldFocusInput = useAppSelector(selectShouldFocusInput)
    const selectedSlideTemplate = useAppSelector(selectSelectedSlideTemplate)
    const questionMode = useAppSelector(selectQuestionMode)
    const buildMode = useAppSelector(selectBuildMode)
    const availableModels = useAppSelector(selectAvailableModels)
    const selectedChatModel = useAppSelector(selectSelectedChatModel)
    const selectedAgentModel = useAppSelector(selectSelectedAgentModel)
    const selectedModel = questionMode === QUESTION_MODE.CHAT
        ? selectedChatModel
        : selectedAgentModel
    const subscriptionPlan = useAppSelector(selectSubscriptionPlan)
    const councilPreference = useAppSelector(selectCouncilPreference)
    const isUploading = useAppSelector((state) => state.files.isUploading)
    const isLoading = useAppSelector((state) => state.ui.isLoading)
    const isCancelling = useAppSelector(selectIsCancelling)
    const isGeneratingPrompt = useAppSelector(
        (state) => state.ui.isGeneratingPrompt
    )
    const { isStorybookPolling, cancelStorybookGeneration } = useChat()
    const { getModelsForMediaType } = useMediaModels()
    const isCreatingSession = useAppSelector(
        (state) => state.ui.isCreatingSession
    )
    const {
        chatMediaPreference,
        hasMiniToolSelection,
        selectMediaType,
        clearMediaPreference,
        selectMediaModel,
        changeAspectRatio,
        changeResolution,
        changePageCount,
        changeTextPosition,
        changeLanguage,
        changeGenre,
        changeMangaLayout,
        changeRichDialogue,
        changeVoiceEnabled,
        changeVideoSettings,
        clearVideoFrames,
        clearMiniToolSelection,
        applyMiniToolSelection
    } = useChatMediaPreference()

    const {
        uploadingFrames: uploadingVideoFrames,
        addFrame: handleVideoFrameAdd,
        removeFrame: handleVideoFrameRemove
    } = useVideoFrameUpload()
    const { sessionId } = useParams()
    const location = useLocation()
    const normalizedPathname = location.pathname.replace(/\/+$/, '')
    const isChatRoute =
        normalizedPathname === '/chat' || normalizedPathname.endsWith('/chat')
    const isSessionView = Boolean(sessionId) || isChatRoute

    const textareaRef = useRef<HTMLTextAreaElement | null>(null)
    const composerFooterRef = useRef<HTMLDivElement | null>(null)
    const clearedAttachmentIdsRef = useRef<Set<string>>(new Set())

    const [files, setFiles] = useState<FileUploadStatus[]>([])
    const [composerFooterHeight, setComposerFooterHeight] = useState(0)
    const [currentTextareaValue, setCurrentTextareaValue] = useState(value)
    const [isGeneratingStorybook, setIsGeneratingStorybook] = useState(false)
    const [isStorybookCancelling, setIsStorybookCancelling] = useState(false)
    const [showTemplateSelector, setShowTemplateSelector] = useState(false)
    const [showMediaTemplateExplorer, setShowMediaTemplateExplorer] =
        useState(false)
    const [isDragging, setIsDragging] = useState(false)
    const [selectedRepository, setSelectedRepository] =
        useState<GitHubRepository>()
    const [miniToolClearSignal, setMiniToolClearSignal] = useState(0)
    const [miniToolBoardOpenSignal, setMiniToolBoardOpenSignal] = useState(0)

    const typeConfig = getMediaTypeConfig(chatMediaPreference.type)

    // Clear storybook template selection when generation is complete
    useEffect(() => {
        if (
            isLoading &&
            chatMediaPreference.enabled &&
            chatMediaPreference.type === 'storybook' &&
            chatMediaPreference.template_id
        ) {
            setIsGeneratingStorybook(true)
        }

        if (!isLoading && isGeneratingStorybook) {
            handleTemplateClear()
            setIsGeneratingStorybook(false)
        }
    }, [
        isLoading,
        isGeneratingStorybook,
        chatMediaPreference.enabled,
        chatMediaPreference.type,
        chatMediaPreference.template_id
    ])

    const shouldShowStop = isLoading || isStorybookPolling

    const handleStop = useCallback(async () => {
        if (isLoading) {
            handleCancel?.()
        }
        if (!isStorybookPolling) return
        setIsStorybookCancelling(true)
        try {
            await cancelStorybookGeneration()
        } catch (error) {
            console.error('Failed to cancel storybook generation', error)
            setIsStorybookCancelling(false)
        }
    }, [cancelStorybookGeneration, handleCancel, isLoading, isStorybookPolling])

    useLayoutEffect(() => {
        const footer = composerFooterRef.current

        if (!footer) return

        const updateHeight = () => {
            const nextHeight = Math.ceil(footer.getBoundingClientRect().height)
            setComposerFooterHeight((prev) =>
                prev === nextHeight ? prev : nextHeight
            )
        }

        updateHeight()

        const observer = new ResizeObserver(() => {
            updateHeight()
        })

        observer.observe(footer)

        return () => {
            observer.disconnect()
        }
    }, [])

    useEffect(() => {
        if (!isStorybookPolling && isStorybookCancelling) {
            setIsStorybookCancelling(false)
        }
    }, [isStorybookCancelling, isStorybookPolling])

    const currentVideoModel =
        chatMediaPreference.type === 'video'
            ? getModelsForMediaType('video').find(
                  (model) => model.model_name === chatMediaPreference.model_name
              )
            : null

    const isMobile = useIsMobile()
    const [advancedPreviewTarget, setAdvancedPreviewTarget] =
        useState<HTMLDivElement | null>(null)
    const composerBottomInset = getComposerBottomInset(
        composerFooterHeight,
        isMobile
    )

    const {
        handleRemoveFile,
        handleFileUploadWithSignedUrl,
        handlePastedImageUpload
    } = useUploadFiles()

    const removeFile = (fileName: string) => {
        handleRemoveFile(fileName)
        setFiles((prev) => prev.filter((file) => file.name !== fileName))
    }

    const clearAttachmentsAfterSubmit = useCallback(() => {
        dispatch(setRequireClearFiles(true))
        dispatch(clearCurrentMessageFileIds())
    }, [dispatch])

    // Handle key down events with auto-scroll for Shift+Enter
    const handleKeyDownWithAutoScroll = (
        e: React.KeyboardEvent<HTMLTextAreaElement>
    ) => {
        // For Enter key, use the actual textarea value (DOM) instead of React state
        // to avoid race conditions where state hasn't synced yet
        const actualValue = textareaRef.current?.value || ''

        if (e.key === 'Enter') {
            if (e.shiftKey) {
                // Check if cursor is at the last line before allowing default behavior
                const textarea = textareaRef.current
                if (textarea) {
                    const cursorPosition = textarea.selectionStart
                    const text = textarea.value

                    // Check if cursor is at or near the end of the text
                    const isAtLastLine = !text
                        .substring(cursorPosition)
                        .includes('\n')

                    // Allow default behavior for Shift+Enter (new line)
                    // Only schedule auto-scroll if we're at the last line
                    if (isAtLastLine) {
                        requestAnimationFrame(() => {
                            keepTextareaTailVisible(
                                textarea,
                                composerBottomInset
                            )
                        })
                    }
                }
            } else {
                // For Enter key submission, check conditions using actual DOM value
                // to avoid race conditions where React state hasn't synced yet
                e.preventDefault()

                // Allow submission without prompt if mini_tools is active and has reference files
                // Use default prompt if no user input and mini_tools is active
                const submissionValue =
                    actualValue.trim() ||
                    (hasMiniToolSelection
                        ? t('media.miniTools.defaultPrompt')
                        : '')

                // Check if submission should be blocked
                if (
                    !submissionValue ||
                    isDisabled ||
                    isCreatingSession ||
                    files?.some((file) => file.loading) ||
                    isUploading
                ) {
                    return
                }

                handleSubmit(submissionValue)
                clearAttachmentsAfterSubmit()

                // Clear video frames after submission
                if (
                    chatMediaPreference.type === 'video' &&
                    chatMediaPreference.video_frames?.length
                ) {
                    clearVideoFrames()
                }

                // Clear the textarea after submission
                if (textareaRef.current) {
                    textareaRef.current.value = ''
                    setCurrentTextareaValue('')
                }
            }
        } else {
            // Pass other key events to the original handler, but modify to work with uncontrolled input
            const modifiedEvent = {
                ...e,
                target: {
                    ...e.target,
                    value: textareaRef.current?.value || ''
                }
            } as React.KeyboardEvent<HTMLTextAreaElement>
            handleKeyDown(modifiedEvent)
        }
    }

    const handleFileChange = async (filesToUpload: File[]) => {
        await handleFileUploadWithSignedUrl(filesToUpload, setFiles)
    }

    // Handle drag and drop events
    const handleDragEnter = useCallback((e: React.DragEvent) => {
        e.preventDefault()
        e.stopPropagation()
        if (e.dataTransfer.items && e.dataTransfer.items.length > 0) {
            setIsDragging(true)
        }
    }, [])

    const handleDragLeave = useCallback((e: React.DragEvent) => {
        e.preventDefault()
        e.stopPropagation()
        // Only set isDragging to false if we're leaving the main container
        const rect = (e.currentTarget as HTMLElement).getBoundingClientRect()
        const x = e.clientX
        const y = e.clientY
        if (
            x <= rect.left ||
            x >= rect.right ||
            y <= rect.top ||
            y >= rect.bottom
        ) {
            setIsDragging(false)
        }
    }, [])

    const handleDragOver = useCallback((e: React.DragEvent) => {
        e.preventDefault()
        e.stopPropagation()
    }, [])

    const handleDrop = useCallback(
        async (e: React.DragEvent) => {
            e.preventDefault()
            e.stopPropagation()
            setIsDragging(false)

            if (isDisabled || isUploading || isCreatingSession) {
                return
            }

            const droppedFiles = Array.from(e.dataTransfer.files)
            if (droppedFiles.length > 0) {
                await handleFileUploadWithSignedUrl(droppedFiles, setFiles)
            }
        },
        [
            isDisabled,
            isUploading,
            isCreatingSession,
            handleFileUploadWithSignedUrl
        ]
    )

    // Handle clipboard paste (images upload + keep caret in view)
    const handlePaste = useCallback(
        async (e: React.ClipboardEvent<HTMLTextAreaElement>) => {
            const clipboardItems = e.clipboardData?.items
            if (!clipboardItems) return

            const imageItems = Array.from(clipboardItems).filter((item) =>
                item.type.startsWith('image/')
            )

            if (imageItems.length > 0) {
                // Prevent default paste behavior for images
                e.preventDefault()

                for (const item of imageItems) {
                    const file = item.getAsFile()
                    if (!file) continue

                    // Generate a unique filename for the pasted image
                    const timestamp = Date.now()
                    const extension = file.type.split('/')[1] || 'png'
                    const fileName = `pasted-image-${timestamp}.${extension}`

                    // Create a new File object with the generated name
                    const renamedFile = new File([file], fileName, {
                        type: file.type
                    })

                    await handlePastedImageUpload(
                        renamedFile,
                        fileName,
                        setFiles
                    )
                }
            }

            // Scroll to the end after text paste so the caret stays in view
            setTimeout(() => {
                const textarea = textareaRef.current
                if (!textarea) return
                keepTextareaTailVisible(textarea, composerBottomInset)
                setCurrentTextareaValue(textarea.value)
            }, 0)
        },
        [handlePastedImageUpload, setFiles]
    )

    const handleSelectFeature = (type: string) => {
        if (type === AGENT_TYPE.SLIDE) {
            // Show template selector instead of immediately setting the agent type
            clearMediaPreference()
            setShowTemplateSelector(true)
            dispatch(setQuestionMode(QUESTION_MODE.AGENT))
        } else if (type === AGENT_TYPE.MEDIA) {
            handleSelectMedia('image')
            dispatch(setQuestionMode(QUESTION_MODE.CHAT))
            dispatch(setSelectedFeature(AGENT_TYPE.GENERAL))
        } else {
            clearMediaPreference()
            dispatch(setSelectedFeature(type))
            dispatch(setQuestionMode(QUESTION_MODE.AGENT))
            setTimeout(() => {
                textareaRef.current?.focus()
            }, 300)
        }
    }

    const handleSelectMode = (mode: QUESTION_MODE) => {
        dispatch(setQuestionMode(mode))
        setTimeout(() => {
            textareaRef.current?.focus()
        }, 300)
        if (mode === QUESTION_MODE.CHAT) {
            dispatch(setSelectedFeature(AGENT_TYPE.GENERAL))
        }
        if (mode === QUESTION_MODE.AGENT) {
            clearMediaPreference()
        }
    }

    const handleSelectMedia = selectMediaType

    const handleClearMediaPreference = () => {
        dispatch(setSelectedFeature(AGENT_TYPE.GENERAL))
        clearMediaPreference()
    }

    const handleClearMiniTool = useCallback(() => {
        clearMiniToolSelection({ removeReferencesFromMessage: true })
        setMiniToolClearSignal((prev) => prev + 1)
        onMiniToolClear?.()
    }, [clearMiniToolSelection, onMiniToolClear])

    const handleMiniToolSelectInternal = useCallback(
        (tool: MiniTool) => {
            const isNewTool = chatMediaPreference.mini_tools?.id !== tool.id
            applyMiniToolSelection(tool, {
                clearPreviousReferences: isNewTool
            })
            onMiniToolSelect?.(tool)
        },
        [
            applyMiniToolSelection,
            chatMediaPreference.mini_tools?.id,
            onMiniToolSelect
        ]
    )

    const handleMediaModelSelect = selectMediaModel

    const handleAspectRatioChange = changeAspectRatio

    const handleResolutionChange = changeResolution

    const handlePageCountChange = changePageCount

    const handleTextPositionChange = changeTextPosition

    const handleLanguageChange = changeLanguage

    const handleGenreChange = changeGenre

    const handleMangaLayoutChange = changeMangaLayout

    const handleRichDialogueChange = changeRichDialogue

    const handleVoiceEnabledChange = changeVoiceEnabled

    const handleMediaTemplateSelect = (template: MediaTemplate | undefined) => {
        if (template) {
            dispatch(
                setChatMediaPreference({
                    ...chatMediaPreference,
                    template_id: template.id,
                    template_name: template.name,
                    template_prompt: undefined
                })
            )
        } else {
            // Clear template (toggle off)
            dispatch(
                setChatMediaPreference({
                    ...chatMediaPreference,
                    template_id: undefined,
                    template_name: undefined,
                    template_prompt: undefined
                })
            )
        }

        // Focus textarea
        setTimeout(() => {
            textareaRef.current?.focus()
        }, 100)
    }

    const handleTemplateClear = () => {
        dispatch(
            setChatMediaPreference({
                ...chatMediaPreference,
                template_id: undefined,
                template_name: undefined,
                template_prompt: undefined
            })
        )
    }

    const handleExploreMoreTemplates = () => {
        setShowMediaTemplateExplorer(true)
    }

    const removeFeature = () => {
        dispatch(setSelectedFeature(AGENT_TYPE.GENERAL))
        dispatch(setSelectedSlideTemplate(null))
    }

    const handleTemplateSelect = (template: SlideTemplate | null) => {
        dispatch(setSelectedSlideTemplate(template))
        setShowTemplateSelector(false)
        dispatch(setSelectedFeature(AGENT_TYPE.SLIDE))

        setTimeout(() => {
            textareaRef.current?.focus()
        }, 300)
    }

    const handleTemplateSelectorClose = () => {
        setShowTemplateSelector(false)
    }

    useEffect(() => {
        if (onFilesChange) {
            onFilesChange(files.length)
        }
    }, [files, onFilesChange])

    useEffect(() => {
        if (requireClearFiles) {
            if (currentMessageFileIds.length > 0) {
                clearedAttachmentIdsRef.current = new Set(currentMessageFileIds)
            } else {
                clearedAttachmentIdsRef.current.clear()
            }
            files.forEach((file) => {
                if (file.preview?.startsWith('blob:'))
                    URL.revokeObjectURL(file.preview)
            })
            setFiles([])

            // Reset the flag
            dispatch(setRequireClearFiles(false))
        }
    }, [requireClearFiles, dispatch, files, currentMessageFileIds])

    useEffect(() => {
        if (requireClearFiles) return

        setFiles((prev) => {
            const currentIdsSet = new Set(currentMessageFileIds)

            const filtered = prev.filter((file) => {
                if (!file.id) return true
                return currentIdsSet.has(file.id)
            })

            const existingKeys = new Set(
                filtered.map((file) => file.id || file.name)
            )

            const additions: FileUploadStatus[] = []

            currentMessageFileIds.forEach((fileId) => {
                if (clearedAttachmentIdsRef.current.has(fileId)) return

                const meta = uploadedFiles.find((file) => file.id === fileId)
                if (!meta) return

                const key = meta.id || meta.name
                if (existingKeys.has(key)) return

                const isImage =
                    meta.folderName || meta.fileCount
                        ? false
                        : isImageFile(meta.name)

                additions.push({
                    id: meta.id,
                    name: meta.name,
                    loading: false,
                    isImage,
                    preview: isImage ? meta.path : undefined,
                    isFolder: Boolean(meta.folderName),
                    fileCount: meta.fileCount
                })
            })

            if (additions.length === 0 && filtered.length === prev.length) {
                return prev
            }

            return [...filtered, ...additions]
        })

        if (currentMessageFileIds.length === 0) {
            clearedAttachmentIdsRef.current.clear()
        }
    }, [currentMessageFileIds, uploadedFiles, requireClearFiles])

    // Clean up object URLs when component unmounts
    useEffect(() => {
        return () => {
            files.forEach((file) => {
                if (file.preview?.startsWith('blob:'))
                    URL.revokeObjectURL(file.preview)
            })
        }
    }, [files])

    // Add effect to sync textarea with external value changes
    useEffect(() => {
        if (textareaRef.current && textareaRef.current.value !== value) {
            textareaRef.current.value = value
            setCurrentTextareaValue(value)
        }
    }, [value])

    // Handle auto-focus when shouldFocusInput is triggered
    useEffect(() => {
        if (shouldFocusInput && textareaRef.current) {
            // Small delay to ensure DOM is ready after navigation
            setTimeout(() => {
                if (textareaRef.current?.value) {
                    textareaRef.current.value = ''
                    setCurrentTextareaValue('')
                }
                textareaRef.current?.focus()
                // Reset the focus trigger
                dispatch(setShouldFocusInput(false))
            }, 100)
        }
    }, [shouldFocusInput, dispatch])

    useEffect(() => {
        if (!focusTextareaSignal) return

        requestAnimationFrame(() => {
            textareaRef.current?.focus()
            keepTextareaTailVisible(textareaRef.current, composerBottomInset)
        })
    }, [composerBottomInset, focusTextareaSignal])

    useLayoutEffect(() => {
        requestAnimationFrame(() => {
            keepTextareaTailVisible(textareaRef.current, composerBottomInset)
        })
    }, [composerBottomInset, currentTextareaValue])

    useEffect(() => {
        if (!googleDriveFiles || googleDriveFiles.length === 0) return

        const existingDriveIds = new Set(
            files
                .map((file) => file.googleDriveId)
                .filter((id): id is string => typeof id === 'string')
        )

        const newFiles = googleDriveFiles.filter(
            (file) => !existingDriveIds.has(file.id)
        )

        if (newFiles.length === 0) {
            onGoogleDriveFilesHandled?.()
            return
        }

        const newStatuses: FileUploadStatus[] = newFiles.map((file) => {
            const isImage = isImageFile(file.name)
            const isFolder = file.is_folder ?? false
            return {
                id: file.id,
                name: file.name,
                loading: false,
                isImage,
                preview: isImage && file.file_url ? file.file_url : undefined,
                googleDriveId: file.id,
                isFolder,
                fileCount: file.file_count
            }
        })

        setFiles((prev) => [...prev, ...newStatuses])

        dispatch(
            addUploadedFiles(
                newFiles.map((file) => {
                    if (file.is_folder && file.file_ids) {
                        return {
                            id: file.id,
                            name: `${file.name} (${t('uploads.fileCount', { count: file.file_count })})`,
                            path: '',
                            size: file.size,
                            folderName: file.name,
                            fileCount: file.file_count
                        }
                    }
                    return {
                        id: file.id,
                        name: file.name,
                        path: file.file_url ?? '',
                        size: file.size
                    }
                })
            )
        )
        dispatch(
            addToCurrentMessageFileIds(
                newFiles.flatMap((file) => {
                    if (file.is_folder && file.file_ids) {
                        return file.file_ids.map(String)
                    }
                    return [file.id]
                })
            )
        )

        onGoogleDriveFilesHandled?.()
    }, [dispatch, files, googleDriveFiles, onGoogleDriveFilesHandled])

    return (
        <div className="w-full">
            <div
                className={`relative ${className}`}
                onDragEnter={handleDragEnter}
                onDragLeave={handleDragLeave}
                onDragOver={handleDragOver}
                onDrop={handleDrop}
            >
                {/* File Previews */}
                <QuestionFilesPreview
                    files={files}
                    isUploading={isUploading}
                    className={clsx({
                        'top-13 md:top-4':
                            chatMediaPreference?.enabled && files.length > 0
                    })}
                    onRemove={removeFile}
                />

                {/* Drag and Drop Overlay */}
                {isDragging && (
                    <div className="absolute inset-0 z-50 flex items-center justify-center bg-grey-3/90 dark:bg-black/90 border-2 border-dashed border-sky-blue rounded-xl pointer-events-none">
                        <div className="flex flex-col items-center gap-3 text-center">
                            <Icon
                                name="link"
                                className="size-10 fill-sky-blue animate-pulse"
                            />
                            <p className="text-lg font-medium text-black dark:text-sky-blue">
                                {t('questionInput.dragDrop.dropToUpload')}
                            </p>
                        </div>
                    </div>
                )}

                {/* Slide Template Selector - Modal overlay */}
                <SlideTemplateSelector
                    isVisible={showTemplateSelector}
                    onTemplateSelect={handleTemplateSelect}
                    onClose={handleTemplateSelectorClose}
                />

                {/* Media Template Explorer - Modal overlay */}
                <MediaTemplateExplorer
                    isVisible={showMediaTemplateExplorer}
                    mediaType={chatMediaPreference.type}
                    selectedTemplate={chatMediaPreference.template_id}
                    handleTemplateClear={handleTemplateClear}
                    onTemplateSelect={handleMediaTemplateSelect}
                    onClose={() => setShowMediaTemplateExplorer(false)}
                />

                <div className="relative">
                    {/* Portal target for advanced mode preview on mobile */}
                    {isMobile && (
                        <div
                            ref={setAdvancedPreviewTarget}
                            className="absolute -top-14 right-3 z-30"
                        />
                    )}
                    {/* Mode Selector - Above Textarea */}
                    <div className="flex items-center gap-2 justify-end -mb-px absolute -top-8 right-2">
                        <ModeSelector
                            hide={hideModeSelector}
                            selectedMode={questionMode}
                            onSelect={handleSelectMode}
                        />
                    </div>
                    {chatMediaPreference.enabled &&
                        questionMode === QUESTION_MODE.CHAT &&
                        isMobile && (
                            <ChatMediaControlsMobile
                                disabled={
                                    isUploading ||
                                    isCreatingSession ||
                                    (sessionId ? isLoading : false)
                                }
                                onTextPositionChange={handleTextPositionChange}
                                onLanguageChange={handleLanguageChange}
                                onGenreChange={handleGenreChange}
                                onMangaLayoutChange={handleMangaLayoutChange}
                                onRichDialogueChange={handleRichDialogueChange}
                                onVoiceEnabledChange={handleVoiceEnabledChange}
                                onPageCountChange={handlePageCountChange}
                                onAspectRatioChange={handleAspectRatioChange}
                                onResolutionChange={handleResolutionChange}
                                onModelSelect={handleMediaModelSelect}
                                onVideoSettingsChange={changeVideoSettings}
                                onVideoFrameAdd={handleVideoFrameAdd}
                                uploadingVideoFrames={uploadingVideoFrames}
                                onVideoFrameRemove={handleVideoFrameRemove}
                            />
                        )}

                    <Textarea
                        ref={textareaRef}
                        style={{
                            paddingBottom: `${composerBottomInset}px`,
                            scrollPaddingBottom: `${composerBottomInset}px`
                        }}
                        className={clsx(
                            'relative z-[22] w-full p-4 rounded-3xl md:rounded-xl resize-none overflow-y-auto whitespace-break-spaces break-words !placeholder-black/[0.48] dark:!placeholder-white/40 !bg-sidebar-bg dark:!bg-black border-2 border-charcoal dark:border-white md:dark:border-sky-blue-2 max-h-[400px] text-base md:text-sm',
                            files.length > 0
                                ? '!pt-[72px] !min-h-[240px]'
                                : 'min-h-[167px]',
                            questionMode === QUESTION_MODE.CHAT &&
                                files.length > 0 &&
                                '!min-h-[200px]',
                            chatMediaPreference.enabled &&
                                questionMode === QUESTION_MODE.CHAT &&
                                '!pt-12 md:!pt-4 min-h-[60px]',
                            chatMediaPreference.enabled &&
                                questionMode === QUESTION_MODE.CHAT &&
                                files.length > 0 &&
                                '!pt-[102px] md:!pt-[72px]',
                            chatMediaPreference.enabled &&
                                questionMode === QUESTION_MODE.CHAT &&
                                (chatMediaPreference.type === 'storybook' ||
                                    chatMediaPreference.type === 'image' ||
                                    chatMediaPreference.type === 'infographic' ||
                                    chatMediaPreference.type === 'poster') &&
                                'md:!min-h-[204px]',
                            chatMediaPreference.enabled &&
                                questionMode === QUESTION_MODE.CHAT &&
                                chatMediaPreference.type === 'video' &&
                                '!min-h-[220px] md:!min-h-[240px]',
                            textareaClassName
                        )}
                        placeholder={
                            placeholder || t('questionInput.placeholder')
                        }
                        wrap="soft"
                        defaultValue={value}
                        onChange={(e) => {
                            const newValue = e.target.value
                            setCurrentTextareaValue(newValue)

                            requestAnimationFrame(() => {
                                keepTextareaTailVisible(
                                    textareaRef.current,
                                    composerBottomInset
                                )
                            })
                        }}
                        onKeyDown={handleKeyDownWithAutoScroll}
                        onPaste={handlePaste}
                        onInput={() => {
                            requestAnimationFrame(() => {
                                keepTextareaTailVisible(
                                    textareaRef.current,
                                    composerBottomInset
                                )
                            })
                        }}
                    />

                    <div
                        ref={composerFooterRef}
                        className="absolute bottom-0 left-0 px-3 md:px-4 w-full flex flex-col gap-2 z-[22]"
                    >
                        <div className="flex items-end justify-between !bg-sidebar-bg dark:!bg-black py-3 md:pb-4 md:pt-3 mb-[2px] rounded-b-xl">
                            <div className="flex items-start gap-x-2 gap-y-2 flex-wrap flex-1">
                                {questionMode === QUESTION_MODE.CHAT &&
                                    !chatMediaPreference.enabled &&
                                    isChatRoute && (
                                        <MediaTypeSelector
                                            onMediaTypeSelect={
                                                handleSelectMedia
                                            }
                                        />
                                    )}
                                {questionMode === QUESTION_MODE.CHAT &&
                                    chatMediaPreference.enabled &&
                                    (isMobile ? (
                                        <>
                                            <ChatMediaVideoFrames
                                                className="mt-3"
                                                mediaPreference={
                                                    chatMediaPreference
                                                }
                                                currentVideoModel={
                                                    currentVideoModel || null
                                                }
                                                onVideoFrameAdd={
                                                    handleVideoFrameAdd
                                                }
                                                uploadingVideoFrames={
                                                    uploadingVideoFrames
                                                }
                                                onVideoFrameRemove={
                                                    handleVideoFrameRemove
                                                }
                                                disabled={
                                                    isUploading ||
                                                    isCreatingSession ||
                                                    (sessionId
                                                        ? isLoading
                                                        : false)
                                                }
                                            />
                                            <div className="flex items-center gap-1 rounded-full px-2 py-1 bg-blue-gradient text-sky-900 dark:text-black">
                                                <Icon
                                                    name={typeConfig?.icon}
                                                    className="size-5"
                                                />

                                                <Button
                                                    type="button"
                                                    size="icon"
                                                    variant="ghost"
                                                    className="h-5 w-5 rounded-full"
                                                    onClick={
                                                        handleClearMediaPreference
                                                    }
                                                >
                                                    <Icon
                                                        name="cancel"
                                                        className="size-4 stroke-sky-900 dark:stroke-black"
                                                    />
                                                </Button>
                                            </div>
                                            {typeConfig.supportsStyles && (
                                                <div
                                                    className={clsx(
                                                        'flex justify-center size-7 items-center gap-1.5 rounded-full bg-charcoal/10 dark:bg-sky-blue-2/10 cursor-pointer',
                                                        {
                                                            '!bg-sky-blue':
                                                                chatMediaPreference.template_name
                                                        }
                                                    )}
                                                    role="button"
                                                    onClick={
                                                        handleExploreMoreTemplates
                                                    }
                                                >
                                                    <Icon
                                                        name="note-2"
                                                        className={clsx(
                                                            'size-[18px] fill-black dark:fill-sky-blue',
                                                            {
                                                                '!fill-black':
                                                                    chatMediaPreference.template_name
                                                            }
                                                        )}
                                                    />
                                                </div>
                                            )}
                                            {!hideAdvancedMode &&
                                                chatMediaPreference.type ===
                                                'image' && (
                                                <AdvancedModeController
                                                    disabled={
                                                        isUploading ||
                                                        isCreatingSession ||
                                                        (sessionId
                                                            ? isLoading
                                                            : false)
                                                    }
                                                    sessionId={
                                                        miniToolsSessionId ||
                                                        sessionId ||
                                                        undefined
                                                    }
                                                    modelName={
                                                        chatMediaPreference.model_name
                                                    }
                                                    provider={
                                                        chatMediaPreference.provider
                                                    }
                                                    advancedModeSettings={
                                                        advancedModeSettings
                                                    }
                                                    onAdvancedModeSettingsChange={
                                                        onAdvancedModeSettingsChange
                                                    }
                                                    hiddenByMiniTool={
                                                        !!chatMediaPreference.mini_tools
                                                    }
                                                    showPreviewPosition="inline"
                                                    previewPortalTarget={
                                                        advancedPreviewTarget
                                                    }
                                                />
                                            )}
                                            {chatMediaPreference.type ===
                                                'storybook' && (
                                                <StorybookStylePicker
                                                    mangaLayout={
                                                        chatMediaPreference.manga_layout ??
                                                        false
                                                    }
                                                    onMangaLayoutChange={
                                                        handleMangaLayoutChange
                                                    }
                                                    disabled={
                                                        isUploading ||
                                                        isCreatingSession ||
                                                        (sessionId
                                                            ? isLoading
                                                            : false)
                                                    }
                                                />
                                            )}
                                        </>
                                    ) : (
                                        <ChatMediaToolbar
                                            mediaPreference={
                                                chatMediaPreference
                                            }
                                            disabled={
                                                isUploading ||
                                                isCreatingSession ||
                                                (sessionId ? isLoading : false)
                                            }
                                            isSessionView={isSessionView}
                                            hideChatMediaCancel={
                                                hideChatMediaCancel
                                            }
                                            isPro={
                                                subscriptionPlan === 'pro' ||
                                                subscriptionPlan === 'plus'
                                            }
                                            onModelSelect={
                                                handleMediaModelSelect
                                            }
                                            onClear={handleClearMediaPreference}
                                            onMiniToolChipClick={() =>
                                                setMiniToolBoardOpenSignal(
                                                    (prev) => prev + 1
                                                )
                                            }
                                            onMiniToolClear={
                                                handleClearMiniTool
                                            }
                                            onTemplateClear={
                                                handleTemplateClear
                                            }
                                            onAspectRatioChange={
                                                handleAspectRatioChange
                                            }
                                            onResolutionChange={
                                                handleResolutionChange
                                            }
                                            onPageCountChange={
                                                handlePageCountChange
                                            }
                                            onTextPositionChange={
                                                handleTextPositionChange
                                            }
                                            onLanguageChange={
                                                handleLanguageChange
                                            }
                                            onGenreChange={handleGenreChange}
                                            onMangaLayoutChange={
                                                handleMangaLayoutChange
                                            }
                                            onRichDialogueChange={
                                                handleRichDialogueChange
                                            }
                                            onVoiceEnabledChange={
                                                handleVoiceEnabledChange
                                            }
                                            onVideoSettingsChange={
                                                changeVideoSettings
                                            }
                                            onVideoFrameAdd={
                                                handleVideoFrameAdd
                                            }
                                            uploadingVideoFrames={
                                                uploadingVideoFrames
                                            }
                                            onVideoFrameRemove={
                                                handleVideoFrameRemove
                                            }
                                            onOpenPickStyleModal={
                                                handleExploreMoreTemplates
                                            }
                                            sessionId={
                                                miniToolsSessionId ||
                                                sessionId ||
                                                undefined
                                            }
                                            advancedModeSettings={
                                                advancedModeSettings
                                            }
                                            onAdvancedModeSettingsChange={
                                                onAdvancedModeSettingsChange
                                            }
                                        />
                                    ))}

                                {onOpenSetting && !isChatRoute && (
                                    <Button
                                        variant="secondary"
                                        size="icon"
                                        className={`hidden md:flex text-xs px-2 w-auto h-7 bg-white border border-black dark:bg-sky-blue text-black rounded-full cursor-pointer`}
                                        onClick={onOpenSetting}
                                    >
                                        {
                                            availableModels
                                                .find(
                                                    (m) =>
                                                        m.id === selectedModel
                                                )
                                                ?.model?.split('@')[0]
                                        }
                                        <Icon
                                            name="arrow-down"
                                            className="fill-black"
                                        />
                                    </Button>
                                )}
                                <FeatureSelector
                                    hide={hideFeatureSelector}
                                    selectedFeature={selectedFeature}
                                    selectedTemplateName={
                                        selectedSlideTemplate?.slide_template_name
                                    }
                                    onRemove={removeFeature}
                                    onSelect={handleSelectFeature}
                                />
                                {councilPreference.enabled &&
                                    questionMode === QUESTION_MODE.CHAT && (
                                        <div className="flex items-center gap-[6px] bg-blue-gradient text-black rounded-lg px-2 h-7 pointer-events-none">
                                            <Icon
                                                name="brain"
                                                className="size-5 fill-black"
                                            />
                                            <button
                                                type="button"
                                                className="cursor-pointer pointer-events-auto"
                                                onClick={() =>
                                                    dispatch(resetCouncilMode())
                                                }
                                            >
                                                <Icon
                                                    name="cancel"
                                                    className="size-4 stroke-black"
                                                />
                                            </button>
                                        </div>
                                    )}
                                {!hideBuildModeSelector &&
                                    questionMode === QUESTION_MODE.AGENT &&
                                    (selectedFeature === AGENT_TYPE.GENERAL ||
                                        selectedFeature ===
                                        AGENT_TYPE.WEBSITE_BUILD ||
                                        selectedFeature ===
                                        AGENT_TYPE.SLIDE ||
                                        selectedFeature ===
                                        AGENT_TYPE.SLIDE_NANO_BANANA) && (
                                        <BuildModeDropdown
                                            selectedMode={buildMode}
                                            onSelect={(mode) =>
                                                dispatch(setBuildMode(mode))
                                            }
                                            disabled={isDisabled || isLoading}
                                            availableModes={
                                                location.pathname === '/'
                                                    ? LANDING_AVAILABLE_MODES
                                                    : undefined
                                            }
                                        />
                                    )}
                                {selectedRepository && (
                                    <Button
                                        disabled={isDisabled}
                                        className={`text-xs px-2 w-auto h-7 bg-white dark:bg-sky-blue text-black rounded-full cursor-pointer`}
                                    >
                                        <span className="truncate text-sm font-medium">
                                            {selectedRepository.name}
                                        </span>
                                        <button
                                            className="cursor-pointer"
                                            onClick={() => {
                                                setSelectedRepository(undefined)
                                                onRepositorySelect?.(undefined)
                                            }}
                                        >
                                            <Icon
                                                name="cancel"
                                                className="size-4 stroke-black"
                                            />
                                        </button>
                                    </Button>
                                )}
                            </div>
                            <div className="flex items-center gap-x-3 gap-y-2 flex-wrap justify-between">
                                <QuestionFileUpload
                                    onFileChange={handleFileChange}
                                    onGoogleDriveClick={onGoogleDriveClick}
                                    isGoogleDriveConnected={
                                        isGoogleDriveConnected
                                    }
                                    isGoogleDriveAuthLoading={
                                        isGoogleDriveAuthLoading
                                    }
                                    isDisabled={
                                        isUploading ||
                                        (sessionId ? isLoading : false)
                                    }
                                />

                                {/* GitHub connector hidden */}
                                {/* <ConnectorDropdown
                                    isDisabled={
                                        isUploading ||
                                        (sessionId ? isLoading : false)
                                    }
                                    isGitHubConnected={isGitHubConnected}
                                    onGitHubConnect={onGitHubConnect}
                                    onRepositorySelect={(repository) => {
                                        setSelectedRepository(repository)
                                        onRepositorySelect?.(repository)
                                    }}
                                    isOpen={isConnectorDropdownOpen}
                                    onOpenChange={onConnectorDropdownOpenChange}
                                /> */}

                                <VoiceDictationButton
                                    textareaRef={textareaRef}
                                    onTranscriptionChange={
                                        setCurrentTextareaValue
                                    }
                                    disabled={
                                        isDisabled ||
                                        isLoading ||
                                        isUploading ||
                                        isCreatingSession
                                    }
                                />

                                {questionMode === QUESTION_MODE.AGENT && (
                                    <EnhanceButton
                                        isGenerating={isGeneratingPrompt}
                                        onClick={() => {
                                            if (handleEnhancePrompt)
                                                handleEnhancePrompt({
                                                    prompt: currentTextareaValue,
                                                    onSuccess: (res) => {
                                                        if (
                                                            textareaRef.current
                                                        ) {
                                                            textareaRef.current.value =
                                                                res
                                                            setCurrentTextareaValue(
                                                                res
                                                            )
                                                        }
                                                    }
                                                })
                                        }}
                                        disabled={
                                            isGeneratingPrompt ||
                                            !currentTextareaValue.trim() ||
                                            isDisabled ||
                                            isLoading ||
                                            isUploading
                                        }
                                    />
                                )}

                                <SubmitButton
                                    isLoading={shouldShowStop}
                                    isCreatingSession={isCreatingSession}
                                    isCancelling={
                                        isCancelling || isStorybookCancelling
                                    }
                                    disabled={
                                        (!currentTextareaValue.trim() &&
                                            !hasMiniToolSelection) ||
                                        isDisabled ||
                                        isCreatingSession ||
                                        files?.some((file) => file.loading) ||
                                        isUploading ||
                                        (chatMediaPreference.type === 'video' &&
                                            uploadingVideoFrames.size > 0)
                                    }
                                    onCancel={handleStop}
                                    onSubmit={() => {
                                        const currentValue =
                                            textareaRef.current?.value || ''

                                        // If no prompt but mini_tools with reference files, use default prompt
                                        const finalPrompt = currentValue.trim()
                                            ? currentValue
                                            : questionMode ===
                                                    QUESTION_MODE.CHAT &&
                                                chatMediaPreference.enabled &&
                                                chatMediaPreference.mini_tools &&
                                                chatMediaPreference.mini_tools
                                                    .reference_file_ids &&
                                                chatMediaPreference.mini_tools
                                                    .reference_file_ids.length >
                                                    0
                                              ? t(
                                                    'media.miniTools.defaultPrompt'
                                                )
                                              : currentValue

                                        if (finalPrompt.trim()) {
                                            handleSubmit(finalPrompt)
                                            clearAttachmentsAfterSubmit()

                                            // Clear template selection after submission (except for storybooks)
                                            if (
                                                chatMediaPreference.template_id &&
                                                chatMediaPreference.type !==
                                                    'storybook'
                                            ) {
                                                dispatch(
                                                    setChatMediaPreference({
                                                        ...chatMediaPreference,
                                                        template_id: undefined,
                                                        template_name:
                                                            undefined,
                                                        template_prompt:
                                                            undefined
                                                    })
                                                )
                                            }

                                            // Clear video frames after submission
                                            if (
                                                chatMediaPreference.type ===
                                                    'video' &&
                                                chatMediaPreference.video_frames
                                                    ?.length
                                            ) {
                                                clearVideoFrames()
                                            }
                                            if (textareaRef.current) {
                                                textareaRef.current.value = ''
                                                setCurrentTextareaValue('')
                                            }
                                        }
                                    }}
                                />
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            {!hideSuggestions &&
                questionMode === QUESTION_MODE.AGENT &&
                selectedFeature !== AGENT_TYPE.GENERAL && (
                    <Suggestions
                        className="mt-6"
                        hidden={!!currentTextareaValue.trim()}
                        agentType={selectedFeature}
                        onSelect={(item) => {
                            if (textareaRef.current) {
                                textareaRef.current.value = item
                                setCurrentTextareaValue(item)
                                setTimeout(() => {
                                    textareaRef.current?.focus()
                                }, 300)
                            }
                        }}
                    />
                )}

            {!hideFeatureSelector &&
                questionMode === QUESTION_MODE.AGENT &&
                selectedFeature === AGENT_TYPE.GENERAL && (
                    <div className="hidden md:flex items-center justify-center w-full mt-6 z-10">
                        <div className="flex items-center gap-3 md:gap-4 md:justify-center flex-wrap">
                            {FEATURES.map((feature) => (
                                <Button
                                    variant="outline"
                                    key={feature.name}
                                    onClick={() =>
                                        handleSelectFeature(feature.type)
                                    }
                                    className="h-7 md:h-8 !px-4 cursor-pointer rounded-full text-xs border-charcoal dark:border-sky-blue text-charcoal dark:text-sky-blue"
                                >
                                    {feature.icon && (
                                        <Icon
                                            name={feature.icon}
                                            className="hidden md:block size-4 fill-charcoal dark:fill-sky-blue"
                                        />
                                    )}
                                    {feature.nameKey
                                        ? t(feature.nameKey)
                                        : feature.name}
                                </Button>
                            ))}
                        </div>
                    </div>
                )}

            {!hideFeatureSelector &&
                questionMode === QUESTION_MODE.CHAT &&
                !isMobile && (
                    <ChatMediaSection
                        questionMode={questionMode}
                        hideFeatureSelector={hideFeatureSelector}
                        hideSuggestions={hideSuggestions}
                        chatMediaPreference={chatMediaPreference}
                        currentTextareaValue={currentTextareaValue}
                        setCurrentTextareaValue={setCurrentTextareaValue}
                        textareaRef={
                            textareaRef as React.RefObject<HTMLTextAreaElement>
                        }
                        onSelectMedia={handleSelectMedia}
                        onMediaTemplateSelect={handleMediaTemplateSelect}
                        onExploreMoreTemplates={handleExploreMoreTemplates}
                        miniToolsSessionId={miniToolsSessionId}
                        miniToolsDisabled={miniToolsDisabled}
                        miniToolClearSignal={miniToolClearSignal}
                        openBoardSignal={miniToolBoardOpenSignal}
                        onMiniToolSelect={handleMiniToolSelectInternal}
                        onMiniToolClear={handleClearMiniTool}
                        isSessionView={isSessionView}
                        fallbackSessionId={sessionId}
                    />
                )}
        </div>
    )
}

export default QuestionInput
