import { useCallback, useEffect, useMemo, useState } from 'react'
import clsx from 'clsx'

import { Button } from '../ui/button'
import { Icon } from '../ui/icon'
import { Switch } from '../ui/switch'
import { CHAT_TOOLS, INIT_TOOLS } from '@/constants/tool'
import { useAppDispatch, useAppSelector } from '@/state/store'
import {
    setCurrentSettingData,
    setIsSavingSetting,
    setToolSettings,
    setCodexToolsStatus,
    setClaudeCodeToolsStatus,
    setClaudeCodeConfig,
    setChatToolSettings,
    selectChatToolSettings,
    selectToolSettings
} from '@/state/slice/settings'
import ConnectToolMCP from './connect-tool-mcp'
import MediaSetting from './media-setting'
import { ISetting, QUESTION_MODE } from '@/typings/agent'
import { toast } from 'sonner'
import { settingsService } from '@/services/settings.service'
import { IMcpSettings } from '@/typings/settings'
import CodexSetting from './codex-setting'
import ClaudeCodeSetting from './claude-code-setting'
import { selectQuestionMode } from '@/state'
import { useTranslation } from 'react-i18next'
import { isAgenticQuestionMode } from '@/utils/question-mode'

interface ToolSettingProps {
    className?: string
}

enum TOOL {
    TASK_AGENT = 'Task Agent',
    DEEP_RESEARCH = 'Deep Research',
    DESIGN_DOCUMENT = 'Design Document',
    MEDIA_GENERATION = 'Media Generation',
    REVIEW_AGENT = 'Review Agent',
    CODEX = 'Codex',
    CLAUDE_CODE = 'Claude Code',
    WEB_SEARCH = 'Web Search',
    WEB_VISIT = 'Web Visit',
    IMAGE_SEARCH = 'Image Search',
    CODE_INTERPRETER = 'Code Interpreter'
}

const ToolSetting = ({ className }: ToolSettingProps) => {
    const { t } = useTranslation()
    const dispatch = useAppDispatch()
    const toolSettings = useAppSelector(selectToolSettings)
    const chatToolSettings = useAppSelector(selectChatToolSettings)
    const questionMode = useAppSelector(selectQuestionMode)
    const [isOpenConnectToolMCP, setOpenConnectToolMCP] = useState(false)
    const [isOpenMediaSetting, setOpenMediaSetting] = useState(false)
    const [isCodexSettingTabOpen, setCodexOpenCodexSettingTab] = useState(false)
    const [isClaudeCodeSettingTabOpen, setClaudeCodeSettingTabOpen] =
        useState(false)
    const [mcpSettings, setMcpSettings] = useState<IMcpSettings[]>([])
    const [editingMcp, setEditingMcp] = useState<IMcpSettings | null>(null)

    const fetchMcpSettings = useCallback(async () => {
        try {
            const response = await settingsService.getMcpSettings()
            setMcpSettings(response.settings)
        } catch (error) {
            console.error('Failed to fetch MCP settings:', error)
        }
    }, [])

    const fetchCodexStatus = useCallback(async () => {
        try {
            const codexSettings = await settingsService.getCodexSettings()
            const isActive = codexSettings?.is_active || false

            // Update Redux state with backend state
            dispatch(setCodexToolsStatus(isActive))
        } catch (error) {
            console.error('Failed to fetch Codex status:', error)

            // Update Redux state on error
            dispatch(setCodexToolsStatus(false))
        }
    }, [dispatch])

    const fetchClaudeCodeStatus = useCallback(async () => {
        try {
            const claudeCodeSettings =
                await settingsService.getClaudeCodeSettings()
            const isActive = claudeCodeSettings?.is_active || false

            // Update Redux state with backend state
            dispatch(setClaudeCodeToolsStatus(isActive))
            dispatch(
                setClaudeCodeConfig({
                    id: claudeCodeSettings?.id || '',
                    is_active: isActive,
                    updated_at: claudeCodeSettings?.updated_at || ''
                })
            )
        } catch (error) {
            console.error('Failed to fetch Claude Code status:', error)

            // Update Redux state on error
            dispatch(setClaudeCodeToolsStatus(false))
        }
    }, [dispatch])

    useEffect(() => {
        fetchMcpSettings()
        fetchCodexStatus()
        fetchClaudeCodeStatus()
    }, [fetchMcpSettings, fetchCodexStatus, fetchClaudeCodeStatus])

    const tools = useMemo(() => {
        if (questionMode === QUESTION_MODE.CHAT) {
            return CHAT_TOOLS.map((tool) => {
                let isActive = false
                switch (tool.name) {
                    case 'Web Search':
                        isActive = chatToolSettings?.web_search || false
                        break
                    case 'Web Visit':
                        isActive = chatToolSettings?.web_visit || false
                        break
                    case 'Image Search':
                        isActive = chatToolSettings?.image_search || false
                        break
                    case 'Code Interpreter':
                        isActive = chatToolSettings?.code_interpreter || false
                        break
                    default:
                        isActive = tool.isActive || false
                }
                return { ...tool, isActive }
            })
        }
        return INIT_TOOLS.map((tool) => {
            let isActive = false
            switch (tool.name) {
                case TOOL.TASK_AGENT:
                    isActive = toolSettings?.task_agent || false
                    break
                case TOOL.DEEP_RESEARCH:
                    isActive = toolSettings?.deep_research || false
                    break
                case TOOL.DESIGN_DOCUMENT:
                    isActive = toolSettings?.design_document || false
                    break
                case TOOL.MEDIA_GENERATION:
                    isActive = toolSettings?.media_generation || false
                    break
                case TOOL.REVIEW_AGENT:
                    isActive = toolSettings?.enable_reviewer || false
                    break
                case TOOL.CODEX:
                    isActive = toolSettings?.codex_tools || false
                    break
                case TOOL.CLAUDE_CODE:
                    isActive = toolSettings?.claude_code || false
                    break
                default:
                    isActive = tool.isActive || false
            }
            return { ...tool, isActive }
        })
    }, [toolSettings, chatToolSettings, questionMode])

    const handleToggle = async (
        toolName: string,
        checked: boolean,
        mcpId?: string
    ) => {
        if (mcpId) {
            try {
                const mcpSetting = mcpSettings.find((s) => s.id === mcpId)
                if (mcpSetting) {
                    await settingsService.updateMcpSettings(mcpId, {
                        is_active: checked
                    })
                    setMcpSettings((prev) =>
                        prev.map((s) =>
                            s.id === mcpId ? { ...s, is_active: checked } : s
                        )
                    )
                }
            } catch (error) {
                toast.error(
                    t('agentSetting.toolSetting.toasts.updateMcpFailed')
                )
                console.error('Error updating MCP tool:', error)
            }
        } else {
            // Handle built-in tool toggle
            const newSettings = { ...toolSettings }
            const newChatSettings = { ...chatToolSettings }
            switch (toolName) {
                case TOOL.TASK_AGENT:
                    newSettings.task_agent = checked
                    break
                case TOOL.DEEP_RESEARCH:
                    newSettings.deep_research = checked
                    break
                case TOOL.DESIGN_DOCUMENT:
                    newSettings.design_document = checked
                    break
                case TOOL.MEDIA_GENERATION:
                    newSettings.media_generation = checked
                    break
                case TOOL.REVIEW_AGENT:
                    newSettings.enable_reviewer = checked
                    break
                case TOOL.CODEX: {
                    const shouldEnableCodex = await handleCodexToggle(checked)
                    newSettings.codex_tools = shouldEnableCodex
                    break
                }
                case TOOL.CLAUDE_CODE: {
                    const shouldEnableClaudeCode =
                        await handleClaudeCodeToggle(checked)
                    newSettings.claude_code = shouldEnableClaudeCode
                    break
                }
                case TOOL.WEB_SEARCH:
                    newChatSettings.web_search = checked
                    break
                case TOOL.WEB_VISIT:
                    newChatSettings.web_visit = checked
                    break
                case TOOL.IMAGE_SEARCH:
                    newChatSettings.image_search = checked
                    break
                case TOOL.CODE_INTERPRETER:
                    newChatSettings.code_interpreter = checked
                    break
            }
            dispatch(setToolSettings(newSettings))
            dispatch(setChatToolSettings(newChatSettings))
        }
    }

    const handleCodexToggle = async (checked: boolean): Promise<boolean> => {
        if (checked) {
            // When toggling on, check if Codex is configured
            const codexSettings = await settingsService.getCodexSettings()
            if (!codexSettings || !codexSettings.metadata?.auth_json) {
                // Navigate to Codex settings if not configured
                setCodexOpenCodexSettingTab(true)
                return false // Don't enable the toggle since no content exists
            } else {
                // If configured but inactive, activate it
                if (!codexSettings.is_active) {
                    await settingsService.updateMcpSettings(codexSettings.id, {
                        is_active: true
                    })
                }
                dispatch(setCodexToolsStatus(true)) // Update Redux state
                return true // Enable the toggle since content exists
            }
        } else {
            // When toggling off, deactivate Codex if it exists
            const codexSettings = await settingsService.getCodexSettings()
            if (codexSettings) {
                await settingsService.updateMcpSettings(codexSettings.id, {
                    is_active: false
                })
            }
            dispatch(setCodexToolsStatus(false)) // Update Redux state
            return false // Disable the toggle when turning off
        }
    }

    const handleClaudeCodeToggle = async (
        checked: boolean
    ): Promise<boolean> => {
        if (checked) {
            // When toggling on, check if Claude Code is configured
            const claudeCodeSettings =
                await settingsService.getClaudeCodeSettings()
            if (
                !claudeCodeSettings ||
                !claudeCodeSettings.metadata?.auth_json
            ) {
                // Navigate to Claude Code settings if not configured
                setClaudeCodeSettingTabOpen(true)
                return false // Don't enable the toggle since no content exists
            } else {
                // If configured but inactive, activate it
                if (!claudeCodeSettings.is_active) {
                    await settingsService.updateMcpSettings(
                        claudeCodeSettings.id,
                        {
                            is_active: true
                        }
                    )
                }
                dispatch(setClaudeCodeToolsStatus(true)) // Update Redux state
                return true // Enable the toggle since content exists
            }
        } else {
            // When toggling off, deactivate Claude Code if it exists
            const claudeCodeSettings =
                await settingsService.getClaudeCodeSettings()
            if (claudeCodeSettings) {
                await settingsService.updateMcpSettings(claudeCodeSettings.id, {
                    is_active: false
                })
            }
            dispatch(setClaudeCodeToolsStatus(false)) // Update Redux state
            return false // Disable the toggle when turning off
        }
    }

    const handleOpenConnectToolMCP = () => {
        setEditingMcp(null) // Clear any editing state
        setOpenConnectToolMCP(true)
    }

    const handleEdit = (toolName: string, mcpId?: string) => {
        if (mcpId) {
            const mcpToEdit = mcpSettings.find((s) => s.id === mcpId)
            if (mcpToEdit) {
                setEditingMcp(mcpToEdit)
                setOpenConnectToolMCP(true)
            }
        } else if (toolName === TOOL.MEDIA_GENERATION) {
            setOpenMediaSetting(true)
        } else if (toolName === TOOL.CODEX) {
            setCodexOpenCodexSettingTab(true)
        } else if (toolName === TOOL.CLAUDE_CODE) {
            setClaudeCodeSettingTabOpen(true)
        }
    }

    const getMcpIcon = (mcpServerName: string) => {
        // Map specific MCP server names to appropriate icons
        const serverName = mcpServerName?.toLowerCase() || ''

        if (serverName.includes('codex')) {
            return 'ai-magic' // AI-powered coding icon
        } else if (
            serverName.includes('firebase') ||
            serverName.includes('database')
        ) {
            return 'document-code' // Database/data-related
        } else if (serverName.includes('auth')) {
            return 'lock' // Authentication/security
        } else if (
            serverName.includes('browser') ||
            serverName.includes('playwright')
        ) {
            return 'browser' // Browser automation
        }

        // Default icon for other MCP tools
        return 'link-2'
    }

    const getMcpDisplayName = (mcpServerName: string) => {
        // Map specific MCP server names to friendly display names
        const serverName = mcpServerName?.toLowerCase() || ''

        if (serverName.includes('codex')) {
            return t('agentSetting.toolSetting.mcp.serverNames.codexExecuting')
        } else if (serverName.includes('firebase')) {
            return 'Firebase'
        } else if (serverName.includes('auth0')) {
            return 'Auth0'
        } else if (serverName.includes('cloudflare')) {
            return 'Cloudflare'
        } else if (serverName.includes('playwright')) {
            return t('agentSetting.toolSetting.mcp.serverNames.playwright')
        } else if (serverName.includes('browser')) {
            return t('agentSetting.toolSetting.mcp.serverNames.browserTools')
        }

        // Default: use the original server name with proper capitalization
        return (
            mcpServerName?.charAt(0).toUpperCase() + mcpServerName?.slice(1) ||
            t('agentSetting.toolSetting.mcp.serverNames.default')
        )
    }

    const handleDeleteMcp = async (mcpId: string) => {
        try {
            await settingsService.deleteMcpSettings(mcpId)
            setMcpSettings((prev) => prev.filter((s) => s.id !== mcpId))
            toast.success(t('agentSetting.toolSetting.toasts.mcpDisconnected'))
        } catch (error) {
            toast.error(t('agentSetting.toolSetting.toasts.deleteMcpFailed'))
            console.error('Error deleting MCP tool:', error)
        }
    }

    const saveConfig = async (settingData: ISetting) => {
        try {
            dispatch(setIsSavingSetting(true))

            // await settingsService.saveSettings(settingData)

            dispatch(setCurrentSettingData(settingData))

            setOpenMediaSetting(false)
            setCodexOpenCodexSettingTab(false)
            setClaudeCodeSettingTabOpen(false)

            // Refresh MCP settings to sync state
            await fetchMcpSettings()
            // Refresh Codex status to sync toggle state
            await fetchCodexStatus()
            // Refresh Claude Code status to sync toggle state
            await fetchClaudeCodeStatus()

            toast.success(t('agentSetting.toolSetting.toasts.configSaved'))
        } catch (error) {
            console.error('Error saving configuration:', error)
            toast.error(t('agentSetting.toolSetting.toasts.configSaveFailed'))
        } finally {
            dispatch(setIsSavingSetting(false))
        }
    }

    return (
        <div className={`flex flex-col justify-between h-full ${className}`}>
            <div className="space-y-4 w-full flex-1 pb-30">
                <div>
                    <p className="text-lg font-semibold dark:text-white">
                        {t('agentSetting.toolSetting.magicTools.title')}
                    </p>
                    <p className="mt-1 dark:text-white/[0.56] text-sm">
                        {t('agentSetting.toolSetting.magicTools.subtitle')}
                    </p>
                </div>
                {tools.map((tool) => (
                    <div
                        key={tool.name}
                        className={`flex items-center justify-between rounded-2xl ${tool.isActive ? 'border-2 border-firefly dark:border-sky-blue-2 bg-sky-blue dark:bg-sky-blue-2/20 p-[14px]' : 'bg-firefly/10 dark:bg-sky-blue-2/5 p-4'}`}
                    >
                        <div className="flex items-center gap-x-4">
                            <div
                                className={`${tool.isActive ? 'bg-firefly dark:bg-sky-blue-2' : 'bg-firefly/10 dark:bg-white/10'} rounded-full size-[46px] flex items-center justify-center`}
                            >
                                <Icon
                                    name={tool.icon}
                                    className={clsx('size-7', {
                                        'stroke-sky-blue-2 dark:stroke-black':
                                            tool.isActive && !tool.isFill,
                                        ' stroke-black dark:stroke-white':
                                            !tool.isActive && !tool.isFill,
                                        'fill-sky-blue-2 dark:fill-black':
                                            tool.isActive && tool.isFill,
                                        'fill-black dark:fill-white':
                                            !tool.isActive && tool.isFill
                                    })}
                                />
                            </div>
                            <div className="flex-1">
                                <p className="text-base font-semibold dark:text-white">
                                    {tool.nameKey ? t(tool.nameKey) : tool.name}
                                </p>
                                <p className="mt-1 dark:text-white text-sm">
                                    {tool.descriptionKey
                                        ? t(tool.descriptionKey)
                                        : tool.description}
                                </p>
                            </div>
                        </div>
                        <div className="flex items-center gap-x-4">
                            {tool.isRequireKey && (
                                <Button
                                    className="p-0 size-6"
                                    onClick={() => handleEdit(tool.name)}
                                >
                                    <Icon
                                        name="edit-2"
                                        className="fill-black dark:fill-sky-blue-2 size-6"
                                    />
                                </Button>
                            )}
                            <Switch
                                checked={tool.isActive}
                                onCheckedChange={(checked: boolean) => {
                                    handleToggle(tool.name, checked)
                                }}
                            />
                        </div>
                    </div>
                ))}

                {/* MCP Connected Tools Section */}
                {mcpSettings.length > 0 && (
                    <>
                        <div className="mt-8">
                            <p className="text-lg font-semibold dark:text-white">
                                {t('agentSetting.toolSetting.mcp.title')}
                            </p>
                            <p className="mt-1 dark:text-white/[0.56] text-sm">
                                {t('agentSetting.toolSetting.mcp.subtitle')}
                            </p>
                        </div>
                        {mcpSettings.map((mcp) => (
                            <div
                                key={mcp.id}
                                className={`h-[77px] flex items-center justify-between rounded-2xl ${
                                    mcp.is_active
                                        ? 'border-2 border-firefly dark:border-sky-blue-2 bg-sky-blue dark:bg-sky-blue-2/20 p-[14px]'
                                        : 'bg-firefly/10 dark:bg-sky-blue-2/5 p-4'
                                }`}
                            >
                                <div className="flex items-center gap-x-4">
                                    <div
                                        className={`${
                                            mcp.is_active
                                                ? 'bg-firefly dark:bg-sky-blue-2'
                                                : 'bg-firefly/10 dark:bg-white/10'
                                        } rounded-full size-[46px] flex items-center justify-center`}
                                    >
                                        <Icon
                                            name={getMcpIcon(
                                                Object.keys(
                                                    mcp.mcp_config
                                                        ?.mcpServers || {}
                                                )[0]
                                            )}
                                            className={clsx('size-7', {
                                                'fill-sky-blue-2 dark:fill-black':
                                                    mcp.is_active,
                                                'fill-black dark:fill-white':
                                                    !mcp.is_active
                                            })}
                                        />
                                    </div>
                                    <div>
                                        <p className="text-base font-semibold dark:text-white">
                                            {getMcpDisplayName(
                                                Object.keys(
                                                    mcp.mcp_config
                                                        ?.mcpServers || {}
                                                )[0]
                                            )}
                                        </p>
                                        <p className="mt-1 dark:text-white text-sm">
                                            {t(
                                                'agentSetting.toolSetting.mcp.connectedTool'
                                            )}
                                        </p>
                                    </div>
                                </div>
                                <div className="flex items-center gap-x-3">
                                    <Button
                                        className="p-0 size-6"
                                        onClick={() => handleEdit('', mcp.id)}
                                    >
                                        <Icon
                                            name="edit-2"
                                            className="fill-sky-blue-2 size-6"
                                        />
                                    </Button>
                                    <Button
                                        className="p-0 size-6"
                                        variant="ghost"
                                        onClick={() => handleDeleteMcp(mcp.id)}
                                    >
                                        <Icon
                                            name="trash"
                                            className="stroke-red-500 size-6"
                                        />
                                    </Button>
                                    <Switch
                                        checked={mcp.is_active ?? false}
                                        onCheckedChange={(checked: boolean) => {
                                            handleToggle('', checked, mcp.id)
                                        }}
                                    />
                                </div>
                            </div>
                        ))}
                    </>
                )}
            </div>
            {isAgenticQuestionMode(questionMode) && (
                <div className="w-full px-3 md:px-6 pb-4 absolute left-0 bottom-0 bg-white dark:bg-charcoal shadow-top">
                    <Button
                        className="h-12 w-full bg-firefly dark:bg-sky-blue text-sky-blue-2 dark:text-black text-base gap-x-[6px] rounded-xl mt-6"
                        onClick={handleOpenConnectToolMCP}
                    >
                        <Icon
                            name="link-2"
                            className="fill-sky-blue-2 dark:fill-black size-[22px]"
                        />
                        {t('agentSetting.toolSetting.connectTools')}
                    </Button>
                </div>
            )}

            <ConnectToolMCP
                open={isOpenConnectToolMCP}
                onOpenChange={(open) => {
                    setOpenConnectToolMCP(open)
                    if (!open) {
                        setEditingMcp(null)
                        fetchMcpSettings()
                    }
                }}
                editingMcp={editingMcp}
            />
            <MediaSetting
                open={isOpenMediaSetting}
                onOpenChange={setOpenMediaSetting}
                onSaveConfig={saveConfig}
            />

            <CodexSetting
                open={isCodexSettingTabOpen}
                onOpenChange={setCodexOpenCodexSettingTab}
                onSaveConfig={saveConfig}
            />

            <ClaudeCodeSetting
                open={isClaudeCodeSettingTabOpen}
                onOpenChange={setClaudeCodeSettingTabOpen}
                onSaveConfig={saveConfig}
            />
        </div>
    )
}

export default ToolSetting
