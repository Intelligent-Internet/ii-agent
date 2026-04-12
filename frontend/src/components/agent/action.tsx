'use client'

import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import isEmpty from 'lodash/isEmpty'
import last from 'lodash/last'
import { FileText, Paperclip, SearchCheck, Share2, Sparkle } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { ActionStep, TOOL } from '@/typings/agent'
import { getCoworkActionValue } from '@/components/cowork/cowork-action-utils'
import { Icon } from '../ui/icon'
import { identifyFilesNeeded, identifySlidesNeeded } from '@/lib/utils'

interface ActionProps {
    workspaceInfo: string
    type: TOOL
    value: ActionStep['data']
    onClick: () => void
}

const Action = ({ workspaceInfo, type, value, onClick }: ActionProps) => {
    const { t } = useTranslation()
    // Use a ref to track if this component has already been animated
    const hasAnimated = useRef(false)
    const [isExpanded, setIsExpanded] = useState(false)

    // Set hasAnimated to true after first render
    useEffect(() => {
        hasAnimated.current = true
    }, [])

    const step_icon = useMemo(() => {
        const className = 'size-[18px]'

        if (type === TOOL.SUB_AGENT_RESEARCHER) {
            return (
                <Icon
                    name="search-status"
                    className={`${className} fill-current`}
                />
            )
        }

        if (type === TOOL.DESIGN_DOCUMENT_AGENT) {
            return <Icon name="note-2" className={`${className} fill-white`} />
        }

        if (type && type.toString().startsWith(TOOL.SUB_AGENT.toString())) {
            return <Icon name="bot" className={className} />
        }

        switch (type) {
            case TOOL.GITHUB:
                return (
                    <Icon name="github" className={`${className} fill-white`} />
                )
            case TOOL.CLAUDE_CODE:
                return <Icon name="claude" className={className} />
            case TOOL.CODEX_AGENT:
            case TOOL.CODEX_EXECUTE:
            case TOOL.CODEX_REVIEW:
            case TOOL.MCP_CODEX_EXECUTE:
            case TOOL.MCP_CODEX_REVIEW:
            case TOOL.CODEX_MCP_CODEX_EXECUTE:
            case TOOL.CODEX_MCP_CODEX_REVIEW:
                return <Icon name="codex" className={className} />
            case TOOL.WEB_SEARCH:
            case TOOL.WEB_BATCH_SEARCH:
                return <Icon name="search-2" className={className} />
            case TOOL.IMAGE_SEARCH:
                return <Icon name="image-search" className={className} />
            case TOOL.VISIT:
            case TOOL.VISIT_COMPRESS:
            case TOOL.BROWSER_USE:
                return <Icon name="browsing" className={className} />
            case TOOL.A2A_AGENT:
                return <Share2 className={className} />
            case TOOL.BASH:
            case TOOL.BASH_INIT:
            case TOOL.BASH_VIEW:
            case TOOL.BASH_STOP:
            case TOOL.BASH_KILL:
            case TOOL.BASH_LIST:
            case TOOL.BASH_WRITE_TO_PROCESS:
                return <Icon name="terminal" className={className} />
            case TOOL.READ:
                return <Icon name="read-file" className={className} />
            case TOOL.WRITE:
                return <Icon name="create-file" className={className} />
            case TOOL.EDIT:
                return <Icon name="edit-file" className={className} />
            case TOOL.STATIC_DEPLOY:
                return <Icon name="deploy" className={className} />
            case TOOL.SAVE_CHECKPOINT:
                return (
                    <Icon
                        name="bookmark"
                        className={`${className} fill-white`}
                    />
                )
            case TOOL.PDF_TEXT_EXTRACT:
                return <FileText className={className} />
            case TOOL.AUDIO_TRANSCRIBE:
                return <Icon name="gen-audio" className={className} />
            case TOOL.GENERATE_AUDIO_RESPONSE:
                return <Icon name="gen-audio" className={className} />
            case TOOL.VIDEO_GENERATE:
            case TOOL.CONCATENATE_VIDEOS:
            case TOOL.EXTRACT_FRAMES:
            case TOOL.LONG_VIDEO_GENERATE:
            case TOOL.LONG_VIDEO_GENERATE_FROM_IMAGE:
                return <Icon name="gen-video" className={className} />
            case TOOL.IMAGE_GENERATE:
            case TOOL.READ_REMOTE_IMAGE:
                return <Icon name="gen-image" className={className} />
            case TOOL.DEEP_RESEARCH:
                return <Sparkle className={className} />
            case TOOL.PRESENTATION:
                return <Icon name="slide" className={className} />
            case TOOL.FULLSTACK_PROJECT_INIT:
            case TOOL.MOBILE_APP_INIT:
                return <Icon name="init-project" className={className} />
            case TOOL.RESTART_FULLSTACK_SERVERS:
            case TOOL.RESTART_MOBILE_SERVER:
                return <Icon name="refresh-icon" className={className} />
            case TOOL.GET_SERVER_STATUS:
                return (
                    <Icon name="logs" className={`${className} fill-white`} />
                )
            case TOOL.REVIEWER_AGENT:
                return <SearchCheck className={className} />

            case TOOL.BROWSER_CLICK:
            case TOOL.BROWSER_CLOSE:
            case TOOL.BROWSER_CONSOLE_MESSAGES:
            case TOOL.BROWSER_DRAG:
            case TOOL.BROWSER_EVALUATE:
            case TOOL.BROWSER_HANDLE_DIALOG:
            case TOOL.BROWSER_HOVER:
            case TOOL.BROWSER_NAVIGATE:
            case TOOL.BROWSER_NETWORK_REQUESTS:
            case TOOL.BROWSER_PRESS_KEY:
            case TOOL.BROWSER_SELECT_OPTION:
            case TOOL.BROWSER_SNAPSHOT:
            case TOOL.BROWSER_TAKE_SCREENSHOT:
            case TOOL.BROWSER_TYPE:
            case TOOL.BROWSER_WAIT_FOR:
            case TOOL.BROWSER_TAB_CLOSE:
            case TOOL.BROWSER_TAB_LIST:
            case TOOL.BROWSER_TAB_NEW:
            case TOOL.BROWSER_TAB_SELECT:
            case TOOL.BROWSER_MOUSE_CLICK_XY:
            case TOOL.BROWSER_MOUSE_DRAG_XY:
            case TOOL.BROWSER_MOUSE_MOVE_XY:
            case TOOL.BROWSER_NAVIGATION:
            case TOOL.BROWSER_WAIT:
            case TOOL.BROWSER_VIEW_INTERACTIVE_ELEMENTS:
            case TOOL.BROWSER_SCROLL_DOWN:
            case TOOL.BROWSER_SCROLL_UP:
            case TOOL.BROWSER_SWITCH_TAB:
            case TOOL.BROWSER_OPEN_NEW_TAB:
            case TOOL.BROWSER_GET_SELECT_OPTIONS:
            case TOOL.BROWSER_SELECT_DROPDOWN_OPTION:
            case TOOL.BROWSER_RESTART:
            case TOOL.BROWSER_ENTER_TEXT:
            case TOOL.BROWSER_ENTER_MULTI_TEXTS:
                return <Icon name="browsing" className={className} />

            case TOOL.LS:
                return <Icon name="list-files" className={className} />
            case TOOL.GLOB:
                return <Icon name="glob" className={className} />
            case TOOL.GREP:
                return <Icon name="grep" className={className} />
            case TOOL.MULTI_EDIT:
                return <Icon name="edit-file" className={className} />
            case TOOL.REGISTER_PORT:
                return <Icon name="register-port" className={className} />
            case TOOL.MCP_TOOL: {
                const toolName = (
                    value.tool_input?.name ||
                    value.tool_input?.tool_name ||
                    value.tool_name ||
                    ''
                ).toLowerCase()
                if (
                    toolName.includes('codex_execute') ||
                    toolName.includes('codex_review') ||
                    toolName.includes('codex')
                ) {
                    return <Icon name="code" className={className} />
                }
                return <Icon name="mcp-tool" className={className} />
            }

            case TOOL.SLIDE_WRITE:
            case TOOL.SLIDE_EDIT:
            case TOOL.SLIDE_APPLY_PATCH:
            case TOOL.SLIDE_GENERATE:
                return <Icon name="slide" className={className} />
            case TOOL.APPLY_PATCH:
                return <Icon name="edit-file" className={className} />
            case TOOL.STR_REPLACE_BASED_EDIT:
                return <Icon name="edit-file" className={className} />
            case TOOL.STRIPE_WEBHOOK_REGISTER:
                return (
                    <Icon
                        name="stripe"
                        className={`${className} rounded-full`}
                    />
                )
            case TOOL.SEND_USER_FILES:
                return <Paperclip className={className} />
            case TOOL.SKILL:
                return (
                    <Icon name="book" className={`fill-white ${className}`} />
                )
            case TOOL.DESKTOP_SKILL_RUN:
                return (
                    <Icon
                        name="book"
                        className={`fill-current text-white ${className}`}
                    />
                )
            case TOOL.WASM_RUN:
                return (
                    <Icon
                        name="cpu"
                        className={`fill-current text-white ${className}`}
                    />
                )
            case TOOL.GET_DATABASE_CONNECTION:
                return (
                    <Icon
                        name="database"
                        className={`fill-white ${className}`}
                    />
                )
            case TOOL.ASK_USER_SELECT:
                return <Icon name="questions" className={className} />
            default:
                // Fallback to tool_logo if available
                if (value.tool_logo) {
                    return (
                        <img
                            src={value.tool_logo}
                            alt="tool icon"
                            className={`${className} rounded-full object-contain`}
                        />
                    )
                }
                return <></>
        }
    }, [type, value.tool_logo])

    const step_title = useMemo(() => {
        if (type === TOOL.SUB_AGENT_RESEARCHER) {
            return t('agent.action.titles.deepResearching')
        }
        if (type === TOOL.DESIGN_DOCUMENT_AGENT) {
            return t('agent.action.titles.creatingDesignDocument')
        }
        if (type === TOOL.CODEX_AGENT) {
            return t('agent.action.titles.codex')
        }

        if (type && type.toString().startsWith(TOOL.SUB_AGENT.toString())) {
            return t('agent.action.titles.delegatingTo', {
                name: value.tool_display_name || t('agent.subagent.defaultName')
            })
        }

        switch (type) {
            case TOOL.GITHUB:
                return t('agent.action.titles.github')
            case TOOL.CLAUDE_CODE:
                return t('agent.action.titles.claudeCode')
            case TOOL.CODEX_EXECUTE:
                return t('agent.action.titles.codexExecuting')
            case TOOL.CODEX_REVIEW:
                return t('agent.action.titles.codexReviewing')
            case TOOL.A2A_AGENT:
                return t('agent.action.titles.a2aAgent')
            case TOOL.MCP_CODEX_EXECUTE:
            case TOOL.CODEX_MCP_CODEX_EXECUTE:
                return t('agent.action.titles.codexExecuting')
            case TOOL.MCP_CODEX_REVIEW:
            case TOOL.CODEX_MCP_CODEX_REVIEW:
                return t('agent.action.titles.codexReviewing')
            case TOOL.SEQUENTIAL_THINKING:
            case TOOL.MESSAGE_USER:
            case TOOL.SEND_USER_FILES:
                return t('agent.action.titles.sendUserFiles')
            case TOOL.WEB_SEARCH:
            case TOOL.WEB_BATCH_SEARCH:
                return t('agent.action.titles.searching')
            case TOOL.IMAGE_SEARCH:
                return t('agent.action.titles.imageSearch')
            case TOOL.GET_DATABASE_CONNECTION:
                return t('agent.action.titles.getDatabaseConnection')
            case TOOL.GET_OPENAI_KEY:
                return t('agent.action.titles.getOpenAiKey')
            case TOOL.VISIT:
            case TOOL.VISIT_COMPRESS:
            case TOOL.BROWSER_USE:
                return t('agent.action.titles.browsing')
            case TOOL.BASH:
                return t('agent.action.titles.bash')
            case TOOL.BASH_INIT:
                return t('agent.action.titles.bashInit')
            case TOOL.BASH_VIEW:
                return t('agent.action.titles.bashView')
            case TOOL.BASH_STOP:
                return t('agent.action.titles.bashStop')
            case TOOL.BASH_KILL:
                return t('agent.action.titles.bashKill')
            case TOOL.BASH_LIST:
                return t('agent.action.titles.bashList')
            case TOOL.BASH_WRITE_TO_PROCESS:
                return t('agent.action.titles.bashWrite')

            case TOOL.SHELL_EXEC:
                return t('agent.action.titles.shellExec')
            case TOOL.SHELL_WRITE_TO_PROCESS:
                return t('agent.action.titles.shellWrite')
            case TOOL.SHELL_KILL_PROCESS:
                return t('agent.action.titles.shellKill')
            case TOOL.SHELL_VIEW:
                return t('agent.action.titles.shellView')
            case TOOL.SHELL_WAIT:
                return t('agent.action.titles.shellWait')
            case TOOL.READ:
                return t('agent.action.titles.readFile')
            case TOOL.WRITE:
                return t('agent.action.titles.createFile')
            case TOOL.EDIT:
                return t('agent.action.titles.editFile')
            case TOOL.STATIC_DEPLOY:
                return t('agent.action.titles.deploying')
            case TOOL.PDF_TEXT_EXTRACT:
                return t('agent.action.titles.extractText')
            case TOOL.AUDIO_TRANSCRIBE:
                return t('agent.action.titles.transcribeAudio')
            case TOOL.GENERATE_AUDIO_RESPONSE:
                return t('agent.action.titles.generateAudio')
            case TOOL.VIDEO_GENERATE:
                return t('agent.action.titles.generateVideo')
            case TOOL.CONCATENATE_VIDEOS:
                return t(
                    'agent.action.titles.concatenateVideos',
                    'Concatenating Videos'
                )
            case TOOL.EXTRACT_FRAMES:
                return t(
                    'agent.action.titles.extractFrames',
                    'Extracting Frames'
                )
            case TOOL.LONG_VIDEO_GENERATE:
                return t('agent.action.titles.generateLongVideoFromText')
            case TOOL.LONG_VIDEO_GENERATE_FROM_IMAGE:
                return t('agent.action.titles.generateLongVideoFromImage')
            case TOOL.IMAGE_GENERATE:
                return t('agent.action.titles.generateImage')
            case TOOL.READ_REMOTE_IMAGE:
                return t('agent.action.titles.readRemoteImage')
            case TOOL.DEEP_RESEARCH:
                return t('agent.action.titles.deepResearching')
            case TOOL.PRESENTATION:
                return t('agent.action.titles.presentationAgent')
            case TOOL.FULLSTACK_PROJECT_INIT:
                return t('agent.action.titles.startingProject')
            case TOOL.RESTART_FULLSTACK_SERVERS:
                return t('agent.action.titles.restartingDevServers')
            case TOOL.RESTART_MOBILE_SERVER:
                return t('agent.action.titles.restartingMobileServer')
            case TOOL.GET_SERVER_STATUS:
                return t('agent.action.titles.checkingServerStatus')
            case TOOL.REVIEWER_AGENT:
                return t('agent.action.titles.reviewerAgent')
            case TOOL.BROWSER_CLICK:
                return t('agent.action.titles.browserClick')
            case TOOL.BROWSER_CLOSE:
                return t('agent.action.titles.browserClose')
            case TOOL.BROWSER_CONSOLE_MESSAGES:
                return t('agent.action.titles.browserConsoleMessages')
            case TOOL.BROWSER_DRAG:
                return t('agent.action.titles.browserDrag')
            case TOOL.BROWSER_EVALUATE:
                return t('agent.action.titles.browserEvaluate')
            case TOOL.BROWSER_HANDLE_DIALOG:
                return t('agent.action.titles.browserHandleDialog')
            case TOOL.BROWSER_HOVER:
                return t('agent.action.titles.browserHover')
            case TOOL.BROWSER_NAVIGATE:
                return t('agent.action.titles.browserNavigate')
            case TOOL.BROWSER_NETWORK_REQUESTS:
                return t('agent.action.titles.browserNetworkRequests')
            case TOOL.BROWSER_PRESS_KEY:
                return t('agent.action.titles.browserPressKey')
            case TOOL.BROWSER_SELECT_OPTION:
                return t('agent.action.titles.browserSelectOption')
            case TOOL.BROWSER_SNAPSHOT:
                return t('agent.action.titles.browserSnapshot')
            case TOOL.BROWSER_TAKE_SCREENSHOT:
                return t('agent.action.titles.browserScreenshot')
            case TOOL.BROWSER_TYPE:
                return t('agent.action.titles.browserType')
            case TOOL.BROWSER_WAIT_FOR:
                return t('agent.action.titles.browserWaitFor')
            case TOOL.BROWSER_TAB_CLOSE:
                return t('agent.action.titles.browserTabClose')
            case TOOL.BROWSER_TAB_LIST:
                return t('agent.action.titles.browserTabList')
            case TOOL.BROWSER_TAB_NEW:
                return t('agent.action.titles.browserTabNew')
            case TOOL.BROWSER_TAB_SELECT:
                return t('agent.action.titles.browserTabSelect')
            case TOOL.BROWSER_MOUSE_CLICK_XY:
                return t('agent.action.titles.browserMouseClick')
            case TOOL.BROWSER_MOUSE_DRAG_XY:
                return t('agent.action.titles.browserMouseDrag')
            case TOOL.BROWSER_MOUSE_MOVE_XY:
                return t('agent.action.titles.browserMouseMove')
            case TOOL.BROWSER_NAVIGATION:
                return t('agent.action.titles.browserNavigation')
            case TOOL.BROWSER_WAIT:
                return t('agent.action.titles.waiting')
            case TOOL.BROWSER_VIEW_INTERACTIVE_ELEMENTS:
                return t('agent.action.titles.browserViewElements')
            case TOOL.BROWSER_SCROLL_DOWN:
                return t('agent.action.titles.browserScrollDown')
            case TOOL.BROWSER_SCROLL_UP:
                return t('agent.action.titles.browserScrollUp')
            case TOOL.BROWSER_SWITCH_TAB:
                return t('agent.action.titles.browserSwitchTab')
            case TOOL.BROWSER_OPEN_NEW_TAB:
                return t('agent.action.titles.browserTabNew')
            case TOOL.BROWSER_GET_SELECT_OPTIONS:
                return t('agent.action.titles.browserGetSelectOptions')
            case TOOL.BROWSER_SELECT_DROPDOWN_OPTION:
                return t('agent.action.titles.browserSelectDropdownOption')
            case TOOL.BROWSER_RESTART:
                return t('agent.action.titles.browserRestart')
            case TOOL.BROWSER_ENTER_TEXT:
                return t('agent.action.titles.browserEnterText')
            case TOOL.BROWSER_ENTER_MULTI_TEXTS:
                return t('agent.action.titles.browserEnterMultipleTexts')
            case TOOL.LS:
                return t('agent.action.titles.ls')
            case TOOL.GLOB:
                return t('agent.action.titles.glob')
            case TOOL.GREP:
                return t('agent.action.titles.grep')
            case TOOL.MULTI_EDIT:
                return t('agent.action.titles.editFile')
            case TOOL.REGISTER_PORT:
                return t('agent.action.titles.registerPort')
            case TOOL.MCP_TOOL: {
                if (value.tool_display_name) {
                    return value.tool_display_name
                }
                const mcpToolName = (
                    value.tool_input?.name ||
                    value.tool_input?.tool_name ||
                    value.tool_name ||
                    ''
                ).toLowerCase()
                if (mcpToolName.includes('codex_execute')) {
                    return t('agent.action.titles.codexExecuting')
                } else if (mcpToolName.includes('codex_review')) {
                    return t('agent.action.titles.codexReviewing')
                } else if (mcpToolName.includes('codex')) {
                    return t('agent.action.titles.codex')
                }
                return t('agent.action.titles.mcpTool')
            }
            case TOOL.TASK:
                return t('agent.action.titles.agentTask')
            case TOOL.SLIDE_WRITE:
                return t('agent.action.titles.slideWrite')
            case TOOL.SLIDE_EDIT:
                return t('agent.action.titles.slideEdit')
            case TOOL.SLIDE_GENERATE:
                return t('agent.action.titles.slideGenerate')
            case TOOL.APPLY_PATCH:
                return t('agent.action.titles.editing')
            case TOOL.SLIDE_APPLY_PATCH:
                return t('agent.action.titles.slideApplyPatch')
            case TOOL.STR_REPLACE_BASED_EDIT: {
                const command = value.tool_input?.command || ''

                if (command.startsWith('view')) {
                    return t('agent.action.titles.viewFile')
                } else if (command.startsWith('create')) {
                    return t('agent.action.titles.createFile')
                } else if (command.startsWith('str_replace')) {
                    return t('agent.action.titles.editFile')
                } else if (command.startsWith('insert')) {
                    return t('agent.action.titles.editFile')
                } else if (command.startsWith('undo_edit')) {
                    return t('agent.action.titles.undoEdit')
                }

                return t('agent.action.titles.fileEditor')
            }
            case TOOL.SAVE_CHECKPOINT:
                return t('agent.action.titles.saveCheckpoint')
            case TOOL.STRIPE_WEBHOOK_REGISTER:
                return t('agent.action.titles.registerStripeWebhook')
            case TOOL.MOBILE_APP_INIT:
                return t('agent.action.titles.mobileAppInit')
            case TOOL.DESKTOP_SKILL_RUN:
                return 'Desktop Skill'
            case TOOL.WASM_RUN:
                return 'Process'
            default:
                // Fallback to tool_display_name if available
                return value.tool_display_name || type
        }
    }, [type, value, t])

    const step_value = useMemo<ReactNode>(() => {
        if (type === TOOL.SUB_AGENT_RESEARCHER) {
            return value.tool_input?.instruction || value.tool_input?.query
        }
        if (type === TOOL.DESIGN_DOCUMENT_AGENT) {
            return value.tool_input?.prompt || value.tool_input?.instruction
        }

        // Handle other sub_agent tools
        if (type && type.toString().startsWith(TOOL.SUB_AGENT.toString())) {
            return value.tool_input?.instruction || value.tool_input?.prompt
        }

        if (type === TOOL.A2A_AGENT) {
            const query =
                value.tool_input?.query ||
                value.tool_input?.instruction ||
                value.tool_input?.prompt ||
                ''
            const url =
                value.tool_input?.agent_url ||
                value.tool_input?.url ||
                value.tool_input?.agent
            const formattedUrl =
                typeof url === 'string' ? url : url ? JSON.stringify(url) : ''

            if (query && formattedUrl) {
                return `${formattedUrl} - ${query}`
            }
            if (query) return query
            if (formattedUrl) return formattedUrl
            return value.tool_input
                ? JSON.stringify(value.tool_input, null, 2)
                : ''
        }

        // Handle Codex tools specifically
        if (
            type === TOOL.CODEX_AGENT ||
            type === TOOL.CODEX_EXECUTE ||
            type === TOOL.CODEX_REVIEW ||
            type === TOOL.MCP_CODEX_EXECUTE ||
            type === TOOL.CODEX_MCP_CODEX_EXECUTE ||
            type === TOOL.MCP_CODEX_REVIEW ||
            type === TOOL.CODEX_MCP_CODEX_REVIEW
        ) {
            return (
                value.tool_input?.prompt ||
                value.tool_input?.instruction ||
                value.tool_input?.query ||
                t('agent.action.values.codexOperation')
            )
        }

        switch (type) {
            case TOOL.GITHUB:
                return value.tool_input?.repo
                    ? `${value.tool_input?.repo} | ${value.tool_input?.action}`
                    : value.tool_input?.action
            case TOOL.SEQUENTIAL_THINKING:
            case TOOL.MESSAGE_USER:
                return value.tool_input?.thought
            case TOOL.GET_DATABASE_CONNECTION:
                return value.tool_input?.database_type
            case TOOL.WEB_SEARCH:
                return value.tool_input?.query
            case TOOL.WEB_BATCH_SEARCH:
                return value.tool_input?.queries?.join(', ')
            case TOOL.IMAGE_SEARCH:
                return value.tool_input?.query
            case TOOL.VISIT:
                return value.tool_input?.url
            case TOOL.VISIT_COMPRESS:
                return value.tool_input?.urls?.[0]
            case TOOL.BROWSER_USE:
                return value.tool_input?.url
            case TOOL.BASH:
                return value.tool_input?.command
            case TOOL.BASH_INIT:
                return value.tool_input?.session_name
            case TOOL.BASH_VIEW:
                return value.tool_input?.session_names?.join(', ')
            case TOOL.BASH_STOP:
                return value.tool_input?.session_name
            case TOOL.BASH_KILL:
                return value.tool_input?.session_name
            case TOOL.BASH_WRITE_TO_PROCESS:
                return value.tool_input?.input
            case TOOL.SHELL_WRITE_TO_PROCESS:
                return value.tool_input?.input
            case TOOL.SHELL_KILL_PROCESS:
                return value.tool_input?.session_id
            case TOOL.SHELL_VIEW:
                return value.tool_input?.session_id
            case TOOL.SHELL_WAIT:
                return t('agent.action.values.waitSeconds', {
                    seconds: value.tool_input?.seconds
                })
            case TOOL.READ:
            case TOOL.WRITE:
            case TOOL.EDIT:
                return last(value.tool_input?.file_path?.split('/'))
            case TOOL.LS:
                return last(value.tool_input?.path?.split('/'))
            case TOOL.STATIC_DEPLOY:
                return value.tool_input?.file_path === workspaceInfo
                    ? workspaceInfo
                    : value.tool_input?.file_path?.replace(workspaceInfo, '')
            case TOOL.PDF_TEXT_EXTRACT:
                return value.tool_input?.file_path === workspaceInfo
                    ? workspaceInfo
                    : value.tool_input?.file_path?.replace(workspaceInfo, '')
            case TOOL.AUDIO_TRANSCRIBE:
                return value.tool_input?.file_path === workspaceInfo
                    ? workspaceInfo
                    : value.tool_input?.file_path?.replace(workspaceInfo, '')
            case TOOL.GENERATE_AUDIO_RESPONSE:
                return value.tool_input?.output_filename === workspaceInfo
                    ? workspaceInfo
                    : value.tool_input?.output_filename?.replace(
                          workspaceInfo,
                          ''
                      )
            case TOOL.VIDEO_GENERATE:
            case TOOL.CONCATENATE_VIDEOS:
            case TOOL.EXTRACT_FRAMES:
            case TOOL.LONG_VIDEO_GENERATE:
            case TOOL.LONG_VIDEO_GENERATE_FROM_IMAGE:
                return value.tool_input?.output_path
            case TOOL.IMAGE_GENERATE:
                return value.tool_input?.output_path
            case TOOL.READ_REMOTE_IMAGE:
                return value.tool_input?.url
            case TOOL.DEEP_RESEARCH:
                return value.tool_input?.query
            case TOOL.PRESENTATION:
                return (
                    value.tool_input?.action +
                    ': ' +
                    value.tool_input?.description
                )
            case TOOL.FULLSTACK_PROJECT_INIT:
                return value.tool_input?.project_name
            case TOOL.REVIEWER_AGENT:
                return value.content

            case TOOL.BROWSER_CLICK:
                return value.tool_input?.element
            case TOOL.BROWSER_TAKE_SCREENSHOT:
                return value.tool_input?.filename
            case TOOL.BROWSER_CLOSE:
            case TOOL.BROWSER_CONSOLE_MESSAGES:
            case TOOL.BROWSER_DRAG:
                return `(${value.tool_input?.coordinate_x_start}, ${value.tool_input?.coordinate_y_start}) → (${value.tool_input?.coordinate_x_end}, ${value.tool_input?.coordinate_y_end})`
            case TOOL.BROWSER_EVALUATE:
            case TOOL.BROWSER_HANDLE_DIALOG:
            case TOOL.BROWSER_HOVER:
            case TOOL.BROWSER_NAVIGATE:
            case TOOL.BROWSER_NETWORK_REQUESTS:
            case TOOL.BROWSER_SELECT_OPTION:
            case TOOL.BROWSER_SNAPSHOT:
            case TOOL.BROWSER_WAIT_FOR:
            case TOOL.BROWSER_TAB_CLOSE:
            case TOOL.BROWSER_TAB_LIST:
            case TOOL.BROWSER_TAB_NEW:
            case TOOL.BROWSER_TAB_SELECT:
                return value.tool_input?.url
            case TOOL.BROWSER_PRESS_KEY:
                return value.tool_input?.key
            case TOOL.BROWSER_TYPE:
                return value.tool_input?.text
            case TOOL.BROWSER_MOUSE_CLICK_XY:
            case TOOL.BROWSER_MOUSE_DRAG_XY:
            case TOOL.BROWSER_MOUSE_MOVE_XY:
                return `${value.tool_input?.x}, ${value.tool_input?.y}`
            case TOOL.BROWSER_NAVIGATION:
                return value.tool_input?.url
            case TOOL.BROWSER_WAIT:
                return ``
            case TOOL.BROWSER_VIEW_INTERACTIVE_ELEMENTS:
                return t('agent.action.values.viewElements')
            case TOOL.BROWSER_SCROLL_DOWN:
            case TOOL.BROWSER_SCROLL_UP:
                return (
                    value.tool_input?.element || t('agent.action.values.page')
                )
            case TOOL.BROWSER_SWITCH_TAB:
            case TOOL.BROWSER_OPEN_NEW_TAB:
                return value.tool_input?.url
            case TOOL.BROWSER_GET_SELECT_OPTIONS:
            case TOOL.BROWSER_SELECT_DROPDOWN_OPTION:
                return value.tool_input?.element
            case TOOL.BROWSER_RESTART:
                return t('agent.action.values.restart')
            case TOOL.BROWSER_ENTER_TEXT:
                return value.tool_input?.text
            case TOOL.BROWSER_ENTER_MULTI_TEXTS: {
                const enterTexts = value.tool_input?.enter_texts as Array<{
                    text: string
                }>
                return enterTexts
                    ? t('agent.action.values.fieldsCount', {
                          count: enterTexts.length
                      })
                    : ''
            }
            case TOOL.GLOB:
                return value.tool_input?.pattern
            case TOOL.GREP:
                return value.tool_input?.pattern
            case TOOL.MULTI_EDIT:
                return last(value.tool_input?.file_path?.split('/'))
            case TOOL.REGISTER_PORT:
                return value.tool_input?.port
            case TOOL.MCP_TOOL:
                return (
                    value.tool_input?.prompt ||
                    value.tool_input?.instruction ||
                    value.tool_input?.query ||
                    value.tool_input?.description ||
                    value.tool_input?.name ||
                    value.tool_input?.tool_name ||
                    value.tool_name ||
                    t('agent.action.titles.mcpTool')
                )
            case TOOL.TASK:
                return value.tool_input?.prompt || value.tool_input?.description
            case TOOL.SLIDE_WRITE:
            case TOOL.SLIDE_EDIT:
                return t('agent.action.values.slideNumber', {
                    number: value.tool_input?.slide_number
                })
            case TOOL.SLIDE_GENERATE:
                return t('agent.action.values.slideNumber', {
                    number: value?.tool_input?.slide_number
                })

            case TOOL.SLIDE_APPLY_PATCH:
                return identifySlidesNeeded(value.tool_input?.input || '')
                    ?.map((slide) =>
                        t('agent.action.values.slideNumber', {
                            number: last(slide.split('/'))
                        })
                    )
                    .join(', ')

            case TOOL.APPLY_PATCH: {
                if (!isEmpty(value.tool_input?.changes)) {
                    return Object.keys(value.tool_input?.changes)
                        .map((file) => last(file.split('/')))
                        .join(', ')
                }

                return identifyFilesNeeded(value.tool_input?.input || '')
                    ?.map((file) => last(file.split('/')))
                    .join(', ')
            }

            case TOOL.STR_REPLACE_BASED_EDIT: {
                const command = value.tool_input?.command || ''
                const filePath =
                    value.tool_input?.file_path || value.tool_input?.path

                return filePath ? last(filePath.split('/')) : command
            }

            case TOOL.CLAUDE_CODE:
                return value.tool_input?.prompt

            case TOOL.STRIPE_WEBHOOK_REGISTER:
                return value.tool_input?.endpoint_url
            case TOOL.SEND_USER_FILES: {
                const attachments = value.tool_input?.attachments || []
                if (attachments.length > 0) {
                    // Show file names (last part of path)
                    return attachments
                        .map((file: string) => last(file.split('/')))
                        .join(', ')
                }
                return value.tool_input?.message
            }
            case TOOL.SKILL:
                return value.tool_input?.skill
            case TOOL.DESKTOP_SKILL_RUN:
            case TOOL.WASM_RUN:
                return getCoworkActionValue({ type, data: value })

            case TOOL.MOBILE_APP_INIT:
                return value.tool_input?.project_name
            default:
                break
        }
    }, [type, value, workspaceInfo, t])

    if (
        !type ||
        type === TOOL.COMPLETE ||
        type === TOOL.LIST_HTML_LINKS ||
        type === TOOL.RETURN_CONTROL_TO_USER ||
        type === TOOL.SLIDE_DECK_INIT ||
        type === TOOL.SLIDE_DECK_COMPLETE ||
        type === TOOL.DISPLAY_IMAGE ||
        type === TOOL.TODO_READ ||
        type === TOOL.TODO_WRITE ||
        type === TOOL.ADD_USER_ENV ||
        type === TOOL.ASK_USER_ENV
    )
        return null

    const handleDetailClick = (e: React.MouseEvent) => {
        e.stopPropagation()
        setIsExpanded(!isExpanded)
    }

    const shouldShowExpandButton = step_value && String(step_value).length > 50

    return (
        <div
            onClick={onClick}
            className={`group cursor-pointer flex flex-col gap-2 px-3 py-2 bg-firefly dark:bg-[#000000]/50 rounded-xl backdrop-blur-sm
      shadow-sm
      transition-all duration-200 ease-out
      hover:bg-neutral-800
      hover:border-neutral-700
      active:scale-[0.98] overflow-hidden
      ${hasAnimated.current ? 'animate-none' : 'animate-fadeIn'}`}
        >
            <div className="flex items-center justify-between gap-4">
                <div className="flex items-center gap-2 text-sm">
                    {step_icon}
                    <span className="text-white">{step_title}</span>
                </div>
                <div className="flex items-center gap-2 flex-1 justify-end">
                    {!isExpanded && (
                        <span
                            className={`text-white text-right font-semibold text-sm truncate ${shouldShowExpandButton ? 'max-w-[100px] md:max-w-[200px]' : 'break-all whitespace-break-spaces'}`}
                            title={
                                typeof step_value === 'string'
                                    ? step_value
                                    : String(step_value)
                            }
                        >
                            {step_value}
                        </span>
                    )}
                    {shouldShowExpandButton && (
                        <button
                            onClick={handleDetailClick}
                            className="text-xs text-gray-400 hover:text-white transition-colors px-2 py-1 rounded hover:bg-white/10"
                        >
                            {isExpanded
                                ? t('agent.action.less')
                                : t('agent.action.more')}
                        </button>
                    )}
                </div>
            </div>
            {isExpanded && step_value && (
                <div className="text-white text-sm break-all bg-black/20 rounded p-2 mt-1">
                    {step_value}
                </div>
            )}
        </div>
    )
}

export default Action
