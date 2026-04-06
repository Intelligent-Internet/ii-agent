import {
    useCallback,
    useMemo,
    useRef,
    useState,
    type KeyboardEvent as ReactKeyboardEvent
} from 'react'
import { useNavigate } from 'react-router'

import { Icon } from '@/components/ui/icon'
import {
    selectAvailableModels,
    selectQuestionMode,
    selectSelectedFeature,
    selectSelectedModel,
    setChatMediaPreference,
    setQuestionMode,
    setSelectedFeature,
    useAppDispatch,
    useAppSelector
} from '@/state'
import { AGENT_TYPE, QUESTION_MODE } from '@/typings/agent'
import { SidebarTrigger } from './ui/sidebar'
import { useTranslation } from 'react-i18next'
import QuestionInput from './question-input'
import type {
    DownloadedFile,
    GitHubRepository
} from '@/services/connector.service'
import clsx from 'clsx'
import { useChatMediaPreference } from '@/hooks/use-chat-media-preference'
import { useIsSageTheme } from '@/hooks/use-is-sage-theme'
import { ChatMediaType } from '@/constants/media-type-config'
import { MediaTemplate } from '@/services/media-template.service'
import ChatMediaSection from './media/chat-media-section'
import { MiniTool } from '@/constants/media-tools'
import { MediaTemplateExplorer } from './media/media-template-explorer'
import SwitchLanguage from './switch-language'
import LearnMore from './learn-more'
import {
    COWORK_ROUTE,
    isAgenticQuestionMode
} from '@/utils/question-mode'
import { isTauri } from '@/utils/is-tauri'

interface HomeMobileProps {
    currentQuestion: string
    onQuestionChange: (value: string) => void
    onSubmit: (value: string) => void
    onKeyDown: (event: ReactKeyboardEvent<HTMLTextAreaElement>) => void
    isInputDisabled?: boolean
    onOpenSetting?: () => void
    handleEnhancePrompt?: (payload: {
        prompt: string
        onSuccess: (res: string) => void
    }) => void
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
}

type FeatureType = {
    key: string
    icon: string
    name: string
    mode: QUESTION_MODE
    type?: string
    agentType?: AGENT_TYPE
}

const Features: FeatureType[] = [
    {
        key: 'image',
        icon: 'generate-image.svg',
        name: 'toolCatalog.chatFeatures.generateImage.name',
        mode: QUESTION_MODE.CHAT,
        type: 'image'
    },
    {
        key: 'infographic',
        icon: 'generate-infographic.svg',
        name: 'toolCatalog.chatFeatures.generateInfographic.name',
        mode: QUESTION_MODE.CHAT,
        type: 'infographic'
    },
    {
        key: 'poster',
        icon: 'generate-poster.svg',
        name: 'toolCatalog.chatFeatures.generatePoster.name',
        mode: QUESTION_MODE.CHAT,
        type: 'poster'
    },
    {
        key: 'storybook',
        icon: 'generate-storybook.svg',
        name: 'toolCatalog.chatFeatures.cookStorybook.name',
        mode: QUESTION_MODE.CHAT,
        type: 'storybook'
    },
    {
        key: 'video',
        icon: 'generate-video.svg',
        name: 'toolCatalog.chatFeatures.generateVideo.name',
        mode: QUESTION_MODE.CHAT,
        type: 'video'
    },
    {
        key: 'slide',
        icon: 'generate-slide.svg',
        name: 'toolCatalog.features.createSlide.name',
        mode: QUESTION_MODE.AGENT,
        agentType: AGENT_TYPE.SLIDE
    },
    {
        key: 'nano-banana',
        icon: 'generate-nano-banana-slide.svg',
        name: 'toolCatalog.features.aiSlideNanoBanana.name',
        mode: QUESTION_MODE.AGENT,
        agentType: AGENT_TYPE.SLIDE_NANO_BANANA
    },
    {
        key: 'website',
        icon: 'generate-website.svg',
        name: 'toolCatalog.features.createWebsite.name',
        mode: QUESTION_MODE.AGENT,
        agentType: AGENT_TYPE.WEBSITE_BUILD
    },
    {
        key: 'deep-research',
        icon: 'generate-deep-research.svg',
        name: 'toolCatalog.features.deepResearch.name',
        mode: QUESTION_MODE.AGENT,
        agentType: AGENT_TYPE.DEEP_RESEARCH
    },
    {
        key: 'fast-research',
        icon: 'generate-deep-research.svg',
        name: 'toolCatalog.features.fastResearch.name',
        mode: QUESTION_MODE.AGENT,
        agentType: AGENT_TYPE.FAST_RESEARCH
    },
    {
        key: 'codex',
        icon: 'generate-codex.svg',
        name: 'toolCatalog.features.codex.name',
        mode: QUESTION_MODE.AGENT,
        agentType: AGENT_TYPE.CODEX
    },
    {
        key: 'claude-code',
        icon: 'generate-claude-code.svg',
        name: 'toolCatalog.features.claudeCode.name',
        mode: QUESTION_MODE.AGENT,
        agentType: AGENT_TYPE.CLAUDE_CODE
    }
]

const HomeMobile = ({
    currentQuestion,
    onQuestionChange,
    onSubmit,
    onKeyDown,
    isInputDisabled,
    onOpenSetting,
    handleEnhancePrompt,
    onGoogleDriveClick,
    isGoogleDriveConnected,
    isGoogleDriveAuthLoading,
    googleDriveFiles,
    onGoogleDriveFilesHandled,
    onGitHubConnect,
    isGitHubConnected,
    onRepositorySelect,
    isConnectorDropdownOpen,
    onConnectorDropdownOpenChange
}: HomeMobileProps) => {
    const { t } = useTranslation()
    const dispatch = useAppDispatch()
    const navigate = useNavigate()
    const questionMode = useAppSelector(selectQuestionMode)
    const selectedModel = useAppSelector(selectSelectedModel)
    const availableModels = useAppSelector(selectAvailableModels)
    const selectedFeature = useAppSelector(selectSelectedFeature)
    const isSage = useIsSageTheme()

    const [showMediaTemplateExplorer, setShowMediaTemplateExplorer] =
        useState(false)
    const [miniToolClearSignal, setMiniToolClearSignal] = useState(0)
    const [miniToolBoardOpenSignal, setMiniToolBoardOpenSignal] = useState(0)
    const [focusTextareaSignal, setFocusTextareaSignal] = useState(0)
    const scrollRef = useRef<HTMLDivElement>(null)

    const {
        chatMediaPreference,
        selectMediaType,
        clearMediaPreference,
        clearMiniToolSelection,
        applyMiniToolSelection
    } = useChatMediaPreference()

    const currentTextareaValue = currentQuestion
    const setCurrentTextareaValue = onQuestionChange

    const model = useMemo(
        () => availableModels.find((m) => m.id === selectedModel),
        [selectedModel, availableModels]
    )

    const isChatMode = useMemo(
        () => questionMode === QUESTION_MODE.CHAT,
        [questionMode]
    )
    const isAgenticMode = useMemo(
        () => isAgenticQuestionMode(questionMode),
        [questionMode]
    )
    const featureMode = isChatMode ? QUESTION_MODE.CHAT : QUESTION_MODE.AGENT

    const selectedSuggestionType = useMemo(() => {
        if (
            questionMode === QUESTION_MODE.CHAT &&
            chatMediaPreference.enabled
        ) {
            return AGENT_TYPE.MEDIA
        }

        if (
            isAgenticMode &&
            selectedFeature !== AGENT_TYPE.GENERAL
        ) {
            return selectedFeature
        }

        return null
    }, [chatMediaPreference.enabled, isAgenticMode, questionMode, selectedFeature])

    const suggestionsToRender = useMemo(() => {
        if (!selectedSuggestionType) return []

        const translatedSuggestions = t(
            isSage ? 'chat.sageSuggestions' : 'chat.suggestions',
            {
                returnObjects: true
            }
        ) as Partial<Record<AGENT_TYPE, string[]>>

        return (
            translatedSuggestions?.[selectedSuggestionType as AGENT_TYPE] ??
            translatedSuggestions?.[AGENT_TYPE.GENERAL] ??
            []
        )
    }, [selectedSuggestionType, t, isSage])

    const shouldShowSuggestions =
        Boolean(selectedSuggestionType) && suggestionsToRender.length > 0

    const handleSelectFeature = (feature: (typeof Features)[0]) => {
        if (feature.mode === QUESTION_MODE.CHAT && feature.type) {
            dispatch(setQuestionMode(QUESTION_MODE.CHAT))
            selectMediaType(feature.type as ChatMediaType)
        } else if (feature.mode === QUESTION_MODE.AGENT && feature.agentType) {
            clearMediaPreference()
            dispatch(setQuestionMode(QUESTION_MODE.AGENT))
            dispatch(setSelectedFeature(feature.agentType))
        }
    }

    const handleSwitchToChatMode = () => {
        dispatch(setSelectedFeature(AGENT_TYPE.GENERAL))
        dispatch(setQuestionMode(QUESTION_MODE.CHAT))
    }

    const handleSwitchToAgentMode = () => {
        clearMediaPreference()
        dispatch(setQuestionMode(QUESTION_MODE.AGENT))
    }

    const handleSwitchToCowork = () => {
        clearMediaPreference()
        navigate(COWORK_ROUTE)
    }

    const handleMediaTemplateSelect = (template: MediaTemplate | undefined) => {
        setTimeout(() => {
            scrollRef.current?.scrollIntoView({ behavior: 'smooth' })
            setFocusTextareaSignal((prev) => prev + 1)
        }, 100)

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
    }

    const handleExploreMoreTemplates = () => {
        setShowMediaTemplateExplorer(true)
    }

    const handleClearMiniTool = useCallback(() => {
        clearMiniToolSelection({ removeReferencesFromMessage: true })
        setMiniToolClearSignal((prev) => prev + 1)
    }, [clearMiniToolSelection])

    const handleMiniToolSelectInternal = useCallback(
        (tool: MiniTool) => {
            const isNewTool = chatMediaPreference.mini_tools?.id !== tool.id
            applyMiniToolSelection(tool, {
                clearPreviousReferences: isNewTool
            })
        },
        [applyMiniToolSelection, chatMediaPreference.mini_tools?.id]
    )

    const handleTemplateClear = useCallback(() => {
        dispatch(
            setChatMediaPreference({
                ...chatMediaPreference,
                template_id: undefined,
                template_name: undefined,
                template_prompt: undefined
            })
        )
    }, [dispatch, chatMediaPreference])

    return (
        <div className="relative w-full min-h-screen overflow-hidden bg-white">
            <div
                className={clsx(
                    "absolute inset-0 w-[calc(100vw)] bg-cover bg-center bg-[url('/images/bg-light.png')] dark:bg-[url('/images/bg.png')]",
                    {
                        "dark:!bg-[url('/images/bg-sage.png')]": isSage
                    }
                )}
            />
            <div className="relative z-10 mx-auto flex min-h-screen flex-col px-3 pb-6 pt-6 animate-fadeIn">
                <div className="flex items-start justify-between">
                    <div className="flex items-center gap-3">
                        <SidebarTrigger className="size-6 p-0" />
                        <div className="leading-tight">
                            <p className="text-[10px]">
                                {t('home.thinkingWith')}
                            </p>
                            <p className="text-lg leading-tight">
                                {model?.model?.split('@')[0]}
                            </p>
                        </div>
                    </div>
                    <div className="flex items-center gap-4">
                        <SwitchLanguage />
                        <button
                            type="button"
                            className=""
                            aria-label={t('tooltips.agentSettings')}
                            onClick={onOpenSetting}
                        >
                            <Icon name="setting-3" className="size-6" />
                        </button>
                    </div>
                </div>

                <div className="mt-12 flex items-center rounded-full border border-black dark:border-sky-blue-2 p-1">
                    <button
                        type="button"
                        onClick={handleSwitchToChatMode}
                        className={`flex flex-1 items-center justify-center gap-2 rounded-full px-4 py-2 text-sm font-semibold transition ${
                            isChatMode
                                ? 'bg-firefly dark:bg-sky-blue-2 text-sky-blue-2 dark:text-black'
                                : ''
                        }`}
                    >
                        <Icon
                            name="chat"
                            className={`size-4 ${
                                isChatMode
                                    ? 'fill-sky-blue-2 dark:fill-black'
                                    : 'fill-black dark:fill-white'
                            }`}
                        />
                        {t('question.mode.chat')}
                    </button>
                    <button
                        type="button"
                        onClick={handleSwitchToAgentMode}
                        className={`flex flex-1 items-center justify-center gap-2 rounded-full px-4 py-2 text-sm font-semibold transition ${
                            questionMode === QUESTION_MODE.AGENT
                                ? 'bg-firefly dark:bg-sky-blue-2 text-sky-blue-2 dark:text-black'
                                : ''
                        }`}
                    >
                        <Icon
                            name="agent"
                            className={`size-4 ${
                                questionMode === QUESTION_MODE.AGENT
                                    ? 'fill-sky-blue-2 dark:fill-black'
                                    : 'fill-black dark:fill-white'
                            }`}
                        />
                        {t('question.mode.agent')}
                    </button>
                    {isTauri && (
                        <button
                            type="button"
                            onClick={handleSwitchToCowork}
                            className={`flex flex-1 items-center justify-center gap-2 rounded-full px-4 py-2 text-sm font-semibold transition ${
                                questionMode === QUESTION_MODE.COWORK
                                    ? 'bg-firefly dark:bg-sky-blue-2 text-sky-blue-2 dark:text-black'
                                    : ''
                            }`}
                        >
                            <Icon
                                name="messages"
                                className={`size-4 ${
                                    questionMode === QUESTION_MODE.COWORK
                                        ? 'fill-sky-blue-2 dark:fill-black'
                                        : 'fill-black dark:fill-white'
                                }`}
                            />
                            II-Cowork
                        </button>
                    )}
                </div>

                <div className="space-y-5 mt-6">
                    <h2 className="text-xl font-semibold text-center flex justify-center items-center">
                        {t('home.readyToVisualize')}
                        <LearnMore />
                    </h2>
                    {shouldShowSuggestions ? (
                        <div className="grid grid-rows-3 grid-flow-col auto-cols-max gap-2 overflow-x-auto no-scrollbar">
                            {suggestionsToRender.map((item) => (
                                <button
                                    key={item}
                                    type="button"
                                    className="text-left rounded-full bg-black/10 dark:bg-white/10 px-4 py-2 text-xs font-semibold text-black/70 dark:text-white/70 hover:bg-black/15 active:bg-black/20 dark:hover:bg-white/15 dark:active:bg-white/20"
                                    onClick={() => onQuestionChange(item)}
                                >
                                    <span className="whitespace-nowrap">
                                        {item}
                                    </span>
                                </button>
                            ))}
                        </div>
                    ) : (
                        <div
                            className={clsx('grid grid-cols-2 gap-3', {
                                hidden:
                                    (isAgenticMode &&
                                        selectedFeature !==
                                            AGENT_TYPE.GENERAL) ||
                                    (questionMode === QUESTION_MODE.CHAT &&
                                        chatMediaPreference.enabled)
                            })}
                        >
                            {Features.map((tile) => (
                                <div
                                    key={tile.key}
                                    className={clsx(
                                        `flex-1 flex gap-2 items-center flex-col justify-between rounded-xl bg-sky-blue dark:bg-sky-blue-2/10 p-3`,
                                        {
                                            hidden: tile.mode !== featureMode
                                        }
                                    )}
                                    onClick={() => handleSelectFeature(tile)}
                                >
                                    <img
                                        src={
                                            tile.key === 'infographic'
                                                ? '/images/tools/generate-infographic.svg'
                                                : tile.key === 'poster'
                                                  ? '/images/tools/generate-poster.svg'
                                                  : `https://sfile.ii.inc/home/${tile.icon}`
                                        }
                                    />
                                    <div className="text-center text-xs font-semibold leading-snug">
                                        <span>{t(tile.name)}</span>
                                    </div>
                                </div>
                            ))}
                        </div>
                    )}
                    {chatMediaPreference.enabled && (
                        <ChatMediaSection
                            questionMode={questionMode}
                            hideSuggestions
                            chatMediaPreference={chatMediaPreference}
                            currentTextareaValue={currentTextareaValue}
                            setCurrentTextareaValue={setCurrentTextareaValue}
                            onSelectMedia={selectMediaType}
                            onMediaTemplateSelect={handleMediaTemplateSelect}
                            onExploreMoreTemplates={handleExploreMoreTemplates}
                            miniToolClearSignal={miniToolClearSignal}
                            openBoardSignal={miniToolBoardOpenSignal}
                            onMiniToolSelect={handleMiniToolSelectInternal}
                            onMiniToolClear={handleClearMiniTool}
                            isSessionView={false}
                        />
                    )}
                </div>

                <div className="mt-auto space-y-2 pt-4">
                    <QuestionInput
                        className="z-30"
                        placeholder={t('home.askAnything')}
                        textareaClassName={clsx('min-h-[90px] !border')}
                        value={currentQuestion}
                        setValue={onQuestionChange}
                        handleKeyDown={onKeyDown}
                        handleSubmit={onSubmit}
                        isDisabled={isInputDisabled}
                        handleEnhancePrompt={handleEnhancePrompt}
                        onGoogleDriveClick={onGoogleDriveClick}
                        isGoogleDriveConnected={isGoogleDriveConnected}
                        isGoogleDriveAuthLoading={isGoogleDriveAuthLoading}
                        googleDriveFiles={googleDriveFiles}
                        onGoogleDriveFilesHandled={onGoogleDriveFilesHandled}
                        onGitHubConnect={onGitHubConnect}
                        isGitHubConnected={isGitHubConnected}
                        onRepositorySelect={onRepositorySelect}
                        isConnectorDropdownOpen={isConnectorDropdownOpen}
                        onConnectorDropdownOpenChange={
                            onConnectorDropdownOpenChange
                        }
                        onSetMiniToolBoardOpenSignalMobile={() =>
                            setMiniToolBoardOpenSignal((prev) => prev + 1)
                        }
                        focusTextareaSignal={focusTextareaSignal}
                        hideBuildModeSelector={isChatMode}
                    />
                    <p className="text-center text-[10px] leading-snug">
                        {t('home.disclaimer', {
                            appName: isSage ? 'SAGE' : t('common.appName')
                        })}
                    </p>
                    <MediaTemplateExplorer
                        isVisible={showMediaTemplateExplorer}
                        mediaType={chatMediaPreference.type}
                        onTemplateSelect={handleMediaTemplateSelect}
                        onClose={() => setShowMediaTemplateExplorer(false)}
                        handleTemplateClear={handleTemplateClear}
                    />
                    <div ref={scrollRef} />
                </div>
            </div>
        </div>
    )
}

export default HomeMobile
