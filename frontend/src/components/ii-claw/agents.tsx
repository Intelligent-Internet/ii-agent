import { useState, useEffect, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import clsx from 'clsx'

import { Switch } from '@/components/ui/switch'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Button } from '@/components/ui/button'
import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
    DialogDescription,
} from '@/components/ui/dialog'
import {
    AlertDialog,
    AlertDialogContent,
    AlertDialogHeader,
    AlertDialogTitle,
    AlertDialogDescription,
    AlertDialogFooter,
    AlertDialogCancel,
    AlertDialogAction,
} from '@/components/ui/alert-dialog'
import {
    Select,
    SelectContent,
    SelectGroup,
    SelectItem,
    SelectLabel,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select'
import {
    iiClawService,
    type UserAgent,
    type UserAgentCreateRequest,
} from '@/services/ii-claw.service'
import { AGENT_TYPE } from '@/typings'
import { Icon } from '@/components/ui/icon'
import { INIT_TOOLS } from '@/constants/tool'
import { PROVIDER_MODELS, PROVIDERS_NAME } from '@/constants/models'

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

// Map INIT_TOOLS name → tool_args key (irregular names only; rest derived via snake_case)
const TOOL_KEY_OVERRIDES: Record<string, string> = {
    'Codex': 'codex_tools',
    'Claude Code': 'claude_code',
}

function toSnakeCase(name: string) {
    return name.toLowerCase().replace(/\s+/g, '_')
}

const TOOL_TOGGLES = INIT_TOOLS.map((tool) => ({
    key: TOOL_KEY_OVERRIDES[tool.name] ?? toSnakeCase(tool.name),
    label: tool.name,
    icon: tool.icon,
    isFill: tool.isFill,
    defaultActive: tool.isActive,
}))

const SKILL_MODES = [
    { value: 'default', label: 'Default' },
    { value: 'custom_skill', label: 'Custom Only' },
    { value: 'default_and_custom_skill', label: 'Default + Custom' },
]

const CONNECTOR_MODES = [
    { value: 'default', label: 'Default' },
    { value: 'custom_connector', label: 'Custom Only' },
    { value: 'default_and_custom_connector', label: 'Default + Custom' },
]

export const BUILTIN_AGENTS = [
    { type: AGENT_TYPE.GENERAL, nameKey: 'iiClaw.agents.builtinAgents.general.name', descKey: 'iiClaw.agents.builtinAgents.general.description', icon: 'agent', isFill: false },
    { type: AGENT_TYPE.FAST_RESEARCH, nameKey: 'iiClaw.agents.builtinAgents.fastResearch.name', descKey: 'iiClaw.agents.builtinAgents.fastResearch.description', icon: 'search-fast', isFill: false },
    { type: AGENT_TYPE.DEEP_RESEARCH, nameKey: 'iiClaw.agents.builtinAgents.deepResearch.name', descKey: 'iiClaw.agents.builtinAgents.deepResearch.description', icon: 'search-status', isFill: true },
    { type: AGENT_TYPE.WEBSITE_BUILD, nameKey: 'iiClaw.agents.builtinAgents.websiteBuilder.name', descKey: 'iiClaw.agents.builtinAgents.websiteBuilder.description', icon: 'monitor', isFill: false },
    { type: AGENT_TYPE.MOBILE_APP, nameKey: 'iiClaw.agents.builtinAgents.mobileApp.name', descKey: 'iiClaw.agents.builtinAgents.mobileApp.description', icon: 'mobile', isFill: false },
    { type: AGENT_TYPE.MEDIA, nameKey: 'iiClaw.agents.builtinAgents.media.name', descKey: 'iiClaw.agents.builtinAgents.media.description', icon: 'image', isFill: false },
    { type: AGENT_TYPE.SLIDE, nameKey: 'iiClaw.agents.builtinAgents.slide.name', descKey: 'iiClaw.agents.builtinAgents.slide.description', icon: 'presentation-2', isFill: false },
    { type: AGENT_TYPE.CODEX, nameKey: 'iiClaw.agents.builtinAgents.codex.name', descKey: 'iiClaw.agents.builtinAgents.codex.description', icon: 'codex', isFill: false },
    { type: AGENT_TYPE.CLAUDE_CODE, nameKey: 'iiClaw.agents.builtinAgents.claudeCode.name', descKey: 'iiClaw.agents.builtinAgents.claudeCode.description', icon: 'claude', isFill: false },
]

const TOTAL_STEPS = 4

// ---------------------------------------------------------------------------
// Step Indicator
// ---------------------------------------------------------------------------

const StepIndicator = ({ currentStep, totalSteps }: { currentStep: number; totalSteps: number }) => (
    <div className="flex items-center gap-1.5">
        {Array.from({ length: totalSteps }, (_, i) => (
            <div
                key={i}
                className={clsx(
                    'h-1.5 rounded-full transition-all',
                    i + 1 === currentStep
                        ? 'w-6 bg-sky-blue'
                        : i + 1 < currentStep
                          ? 'w-3 bg-sky-blue/50'
                          : 'w-3 bg-charcoal/10 dark:bg-white/10'
                )}
            />
        ))}
    </div>
)

// ---------------------------------------------------------------------------
// Create Agent Dialog
// ---------------------------------------------------------------------------

const CreateAgentDialog = ({
    open,
    onOpenChange,
    onCreated,
    editAgent,
}: {
    open: boolean
    onOpenChange: (open: boolean) => void
    onCreated: () => void
    editAgent: UserAgent | null
}) => {
    const { t } = useTranslation()

    // Sidebar: custom agent list
    const [agents, setAgents] = useState<UserAgent[]>([])
    const [loadingAgents, setLoadingAgents] = useState(false)

    // Wizard state
    const [formActive, setFormActive] = useState(false)
    const [editingAgentId, setEditingAgentId] = useState<string | null>(null)
    const [step, setStep] = useState(1)
    const [submitting, setSubmitting] = useState(false)
    const [error, setError] = useState<string | null>(null)
    const [confirmDelete, setConfirmDelete] = useState<string | null>(null)
    const [mobileListOpen, setMobileListOpen] = useState(false)

    // Step 1: Identity
    const [agentName, setAgentName] = useState('')
    const [tag, setTag] = useState('')
    const [systemPrompt, setSystemPrompt] = useState('')

    // Step 2: Model
    const [modelId, setModelId] = useState('')

    // Step 3: Tools
    const [toolArgs, setToolArgs] = useState<Record<string, boolean>>(() =>
        Object.fromEntries(TOOL_TOGGLES.map((t) => [t.key, t.defaultActive]))
    )

    // Step 4: Skills & Connectors
    const [skillMode, setSkillMode] = useState('default')
    const [connectorMode, setConnectorMode] = useState('default')

    const fetchAgents = useCallback(async () => {
        setLoadingAgents(true)
        try {
            const list = await iiClawService.listUserAgents()
            setAgents(list)
        } catch {
            setAgents([])
        } finally {
            setLoadingAgents(false)
        }
    }, [])

    useEffect(() => {
        if (open) {
            fetchAgents()
            if (editAgent) {
                populateFromAgent(editAgent)
            } else {
                startNew()
            }
        }
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [open, editAgent, fetchAgents])

    const resetForm = () => {
        setFormActive(false)
        setEditingAgentId(null)
        setStep(1)
        setAgentName('')
        setTag('')
        setSystemPrompt('')
        setModelId('')
        setToolArgs(Object.fromEntries(TOOL_TOGGLES.map((t) => [t.key, t.defaultActive])))
        setSkillMode('default')
        setConnectorMode('default')
        setError(null)
    }

    const startNew = () => {
        resetForm()
        setFormActive(true)
    }

    const populateFromAgent = (agent: UserAgent) => {
        setFormActive(true)
        setEditingAgentId(agent.id)
        setStep(1)
        setAgentName(agent.agent_name)
        setTag(agent.tag || '')
        setSystemPrompt(agent.system_prompt || '')
        setModelId(agent.model_id || '')
        const tools: Record<string, boolean> = {}
        TOOL_TOGGLES.forEach((t) => {
            tools[t.key] = agent.tool_args?.[t.key] === true || (agent.tool_args?.[t.key] === undefined && t.defaultActive)
        })
        setToolArgs(tools)
        setSkillMode(agent.skill_mode || 'default')
        setConnectorMode(agent.connector_mode || 'default')
        setError(null)
    }

    const handleSelectAgent = (agent: UserAgent) => {
        populateFromAgent(agent)
    }

    const canNext = () => {
        if (step === 1) return agentName.trim().length > 0
        return true
    }

    const handleNext = () => {
        if (step < TOTAL_STEPS) setStep(step + 1)
    }
    const handleBack = () => {
        if (step > 1) setStep(step - 1)
    }

    const handleSubmit = async () => {
        if (!agentName.trim()) {
            setError('Agent name is required')
            return
        }

        setSubmitting(true)
        setError(null)
        try {
            const payload: UserAgentCreateRequest = {
                agent_name: agentName.trim(),
                tag: tag.trim() || undefined,
                system_prompt: systemPrompt.trim() || undefined,
                model_id: modelId || undefined,
                tool_args: toolArgs,
                skill_mode: skillMode,
                connector_mode: connectorMode,
            }

            if (editingAgentId) {
                await iiClawService.updateUserAgent(editingAgentId, payload)
            } else {
                await iiClawService.createUserAgent(payload)
            }

            resetForm()
            onCreated()
            await fetchAgents()
        } catch (e: unknown) {
            const msg = e instanceof Error ? e.message : 'Failed to save agent'
            setError(msg)
        } finally {
            setSubmitting(false)
        }
    }

    const handleDeleteAgent = async (agentId: string) => {
        try {
            await iiClawService.deleteUserAgent(agentId)
            if (editingAgentId === agentId) {
                resetForm()
            }
            onCreated()
            await fetchAgents()
        } catch (e: unknown) {
            const msg = e instanceof Error ? e.message : 'Failed to delete agent'
            setError(msg)
        }
    }

    // ---- Step renderers ----

    const renderStep1 = () => (
        <div className="space-y-4">
            <div className="flex gap-3">
                <div className="flex-1 space-y-1.5">
                    <label className="text-xs sm:text-sm font-medium text-black dark:text-white flex items-center gap-2">
                        {t('iiClaw.agents.dialog.fields.agentName')}
                        <span className="text-red text-xs">*</span>
                    </label>
                    <Input
                        type="text"
                        placeholder="e.g. My Research Assistant"
                        value={agentName}
                        onChange={(e) => setAgentName(e.target.value)}
                        className="h-10 text-sm"
                    />
                </div>

                <div className="w-40 shrink-0 space-y-1.5">
                    <label className="text-xs sm:text-sm font-medium text-black dark:text-white">
                        {t('iiClaw.agents.dialog.fields.tag')}
                    </label>
                    <Input
                        type="text"
                        placeholder={t('iiClaw.agents.dialog.fields.tagPlaceholder')}
                        value={tag}
                        onChange={(e) => {
                            const v = e.target.value
                                .toLowerCase()
                                .replace(/[^a-z0-9\s-]/g, '')
                                .replace(/\s+/g, '-')
                                .replace(/-+/g, '-')
                            setTag(v)
                        }}
                        className="h-10 text-sm"
                        maxLength={64}
                    />
                </div>
            </div>

            <div className="space-y-1.5">
                <label className="text-xs sm:text-sm font-medium text-black dark:text-white">
                    {t('iiClaw.agents.dialog.fields.systemPrompt')}
                </label>
                <Textarea
                    placeholder={t('iiClaw.agents.dialog.fields.systemPromptPlaceholder')}
                    value={systemPrompt}
                    onChange={(e) => setSystemPrompt(e.target.value)}
                    className="text-sm min-h-[200px] resize-y"
                />
                <p className="text-[10px] text-charcoal/40 dark:text-white/30">
                    {t('iiClaw.agents.dialog.fields.systemPromptHint')}
                </p>
            </div>
        </div>
    )

    const renderStep2 = () => (
        <div className="space-y-4">
            <div className="space-y-1.5">
                <label className="text-xs sm:text-sm font-medium text-black dark:text-white">
                    {t('iiClaw.agents.dialog.fields.llmModel')}
                </label>
                <Select value={modelId || '_default'} onValueChange={(v) => setModelId(v === '_default' ? '' : v)}>
                    <SelectTrigger className="!h-10 text-sm">
                        <SelectValue placeholder={t('iiClaw.agents.dialog.fields.llmModelDefault')} />
                    </SelectTrigger>
                    <SelectContent>
                        <SelectItem value="_default" className="text-sm">
                            {t('iiClaw.agents.dialog.fields.llmModelDefault')}
                        </SelectItem>
                        {Object.entries(PROVIDER_MODELS)
                            .filter(([, models]) => models.length > 0)
                            .map(([provider, models]) => (
                                <SelectGroup key={provider}>
                                    <SelectLabel className="text-xs font-semibold text-charcoal/40 dark:text-white/30">
                                        {PROVIDERS_NAME[provider] ?? provider}
                                    </SelectLabel>
                                    {models.map((m) => (
                                        <SelectItem key={m.id} value={m.model} className="text-sm">
                                            {m.model}
                                        </SelectItem>
                                    ))}
                                </SelectGroup>
                            ))}
                    </SelectContent>
                </Select>
                <p className="text-[10px] text-charcoal/40 dark:text-white/30">
                    {t('iiClaw.agents.dialog.fields.llmModelHint')}
                </p>
            </div>
        </div>
    )

    const renderStep3 = () => (
        <div className="space-y-3">
            <p className="text-xs text-charcoal/50 dark:text-white/40">
                {t('iiClaw.agents.dialog.fields.toolsDescription')}
            </p>
            <div className="space-y-2">
                {TOOL_TOGGLES.map((tool) => (
                    <div
                        key={tool.key}
                        className={clsx(
                            'flex items-center justify-between px-3 py-2.5 rounded-xl border transition-colors',
                            toolArgs[tool.key]
                                ? 'border-sky-blue/30 bg-sky-blue/5 dark:border-sky-blue/20 dark:bg-sky-blue/5'
                                : 'border-charcoal/10 dark:border-white/10'
                        )}
                    >
                        <div className="flex items-center gap-2.5">
                            <Icon name={tool.icon} className={clsx('size-4', tool.isFill ? 'fill-charcoal/40 dark:fill-white/40' : 'stroke-charcoal/40 dark:stroke-white/40')} />
                            <span className="text-sm font-medium text-black dark:text-white">
                                {tool.label}
                            </span>
                        </div>
                        <Switch
                            checked={toolArgs[tool.key]}
                            onCheckedChange={(checked) =>
                                setToolArgs((prev) => ({ ...prev, [tool.key]: checked }))
                            }
                        />
                    </div>
                ))}
            </div>
        </div>
    )

    const renderStep4 = () => (
        <div className="space-y-4">
            <div className="space-y-1.5">
                <label className="text-xs sm:text-sm font-medium text-black dark:text-white">
                    {t('iiClaw.agents.dialog.fields.skillMode')}
                </label>
                <Select value={skillMode} onValueChange={setSkillMode}>
                    <SelectTrigger className="!h-10 text-sm">
                        <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                        {SKILL_MODES.map((m) => (
                            <SelectItem key={m.value} value={m.value} className="text-sm">
                                {m.label}
                            </SelectItem>
                        ))}
                    </SelectContent>
                </Select>
            </div>

            <div className="space-y-1.5">
                <label className="text-xs sm:text-sm font-medium text-black dark:text-white">
                    {t('iiClaw.agents.dialog.fields.connectorMode')}
                </label>
                <Select value={connectorMode} onValueChange={setConnectorMode}>
                    <SelectTrigger className="!h-10 text-sm">
                        <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                        {CONNECTOR_MODES.map((m) => (
                            <SelectItem key={m.value} value={m.value} className="text-sm">
                                {m.label}
                            </SelectItem>
                        ))}
                    </SelectContent>
                </Select>
            </div>
        </div>
    )

    const STEP_TITLES = [
        t('iiClaw.agents.dialog.steps.identity'),
        t('iiClaw.agents.dialog.steps.model'),
        t('iiClaw.agents.dialog.steps.tools'),
        t('iiClaw.agents.dialog.steps.skills'),
    ]

    return (
        <>
            <Dialog open={open} onOpenChange={onOpenChange}>
                <DialogContent className="max-w-[calc(100%-1rem)] sm:max-w-2xl md:max-w-3xl">
                    <DialogHeader>
                        <div className="flex items-center gap-3">
                            <div className="w-10 h-10 rounded-xl bg-sky-blue/20 dark:bg-sky-blue/10 flex items-center justify-center shrink-0">
                                <Icon name="agent" className="size-5 fill-firefly dark:fill-sky-blue" />
                            </div>
                            <div>
                                <DialogTitle className="dark:text-white">
                                    {editingAgentId ? t('iiClaw.agents.dialog.editTitle') : t('iiClaw.agents.dialog.createTitle')}
                                </DialogTitle>
                                <DialogDescription className="mt-1">
                                    {t('iiClaw.agents.dialog.stepOf', { current: step, total: TOTAL_STEPS })}: {STEP_TITLES[step - 1]}
                                </DialogDescription>
                            </div>
                        </div>
                    </DialogHeader>

                    {/* Mobile: button to open agent list */}
                    <button
                        type="button"
                        onClick={() => setMobileListOpen(true)}
                        className={clsx(
                            'sm:hidden w-full h-9 rounded-lg flex items-center justify-center gap-2 text-xs font-medium transition-colors cursor-pointer',
                            'bg-sky-blue/15 text-firefly dark:bg-sky-blue/10 dark:text-sky-blue hover:bg-sky-blue/25 dark:hover:bg-sky-blue/20'
                        )}
                    >
                        <Icon name="agent" className="size-3.5 fill-firefly dark:fill-sky-blue" />
                        {t('iiClaw.agents.dialog.sidebar.title')}
                        {agents.length > 0 && (
                            <span className="text-[10px] font-normal text-charcoal/40 dark:text-white/30">
                                ({agents.length})
                            </span>
                        )}
                    </button>

                    <div className="flex flex-col sm:flex-row gap-4 sm:gap-6 mt-2 sm:h-[420px]">
                        {/* ===== Left side: Agent list (hidden on mobile) ===== */}
                        <div className="hidden sm:flex w-48 shrink-0 flex-col min-h-0">
                            <div className="flex items-center justify-between mb-3">
                                <h3 className="text-xs sm:text-sm font-semibold text-black dark:text-white">
                                    {t('iiClaw.agents.dialog.sidebar.title')}
                                    {agents.length > 0 && (
                                        <span className="ml-1.5 text-[10px] font-normal text-charcoal/40 dark:text-white/30">
                                            ({agents.length})
                                        </span>
                                    )}
                                </h3>
                                <button
                                    type="button"
                                    onClick={startNew}
                                    className={clsx(
                                        'w-7 h-7 rounded-lg flex items-center justify-center transition-colors cursor-pointer',
                                        'text-firefly dark:text-sky-blue hover:text-charcoal dark:hover:text-white',
                                        'bg-sky-blue/20 hover:bg-sky-blue/40 dark:bg-sky-blue/10 dark:hover:bg-sky-blue/20'
                                    )}
                                    title={t('iiClaw.agents.dialog.buttons.newAgent')}
                                >
                                    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" xmlns="http://www.w3.org/2000/svg">
                                        <path d="M7 1.75V12.25M1.75 7H12.25" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
                                    </svg>
                                </button>
                            </div>

                            <div className="flex-1 overflow-y-auto">
                                {loadingAgents ? (
                                    <div className="flex items-center justify-center h-24 text-xs text-charcoal/40 dark:text-white/30">
                                        {t('common.loading', 'Loading...')}
                                    </div>
                                ) : agents.length === 0 ? (
                                    <div className="flex flex-col items-center justify-center h-24 text-center">
                                        <p className="text-xs text-charcoal/40 dark:text-white/30">
                                            {t('iiClaw.agents.dialog.sidebar.empty')}
                                        </p>
                                        <p className="text-[10px] text-charcoal/30 dark:text-white/20 mt-0.5">
                                            {t('iiClaw.agents.dialog.sidebar.emptyHint')}
                                        </p>
                                    </div>
                                ) : (
                                    <div className="divide-y divide-charcoal/[0.06] dark:divide-white/[0.08]">
                                        {agents.map((agent) => {
                                            const isSelected = editingAgentId === agent.id
                                            return (
                                                <div
                                                    key={agent.id}
                                                    onClick={() => handleSelectAgent(agent)}
                                                    className={clsx(
                                                        'flex items-center gap-2.5 px-2.5 py-2.5 cursor-pointer transition-all rounded-md',
                                                        isSelected
                                                            ? 'bg-sky-blue/35 dark:bg-sky-blue/15'
                                                            : 'hover:bg-charcoal/[0.02] dark:hover:bg-white/[0.1]'
                                                    )}
                                                >
                                                    <div className="min-w-0 flex-1">
                                                        <p className="text-xs font-medium text-black dark:text-white truncate">
                                                            {agent.agent_name}
                                                        </p>
                                                        {agent.tag && (
                                                            <span className="inline-block mt-1 text-[10px] font-medium px-1.5 py-0.5 rounded-md
bg-[rgb(210,240,245)] text-gray-700 hover:bg-[rgb(190,230,240)] truncate max-w-full">
                                                                {agent.tag}
                                                            </span>
                                                        )}
                                                    </div>
                                                    <button
                                                        onClick={(e) => {
                                                            e.stopPropagation()
                                                            setConfirmDelete(agent.id)
                                                        }}
                                                        className={clsx(
                                                            'shrink-0 w-6 h-6 rounded-md flex items-center justify-center transition-colors cursor-pointer',
                                                            'text-charcoal/20 dark:text-white/25 hover:text-red hover:bg-red/10',
                                                        )}
                                                        title={t('iiClaw.agents.dialog.delete.confirm')}
                                                    >
                                                        <svg width="12" height="12" viewBox="0 0 12 12" fill="none" xmlns="http://www.w3.org/2000/svg">
                                                            <path d="M2.5 3.5H9.5M4.5 3.5V2.5C4.5 2.22386 4.72386 2 5 2H7C7.27614 2 7.5 2.22386 7.5 2.5V3.5M5 5.5V8.5M7 5.5V8.5M3.5 3.5L3.85 9.17C3.87 9.63 4.25 10 4.71 10H7.29C7.75 10 8.13 9.63 8.15 9.17L8.5 3.5" stroke="currentColor" strokeWidth="1" strokeLinecap="round" strokeLinejoin="round"/>
                                                        </svg>
                                                    </button>
                                                </div>
                                            )
                                        })}
                                    </div>
                                )}
                            </div>
                        </div>

                        {/* ===== Divider (hidden on mobile) ===== */}
                        <div className="hidden sm:block sm:w-px bg-charcoal/10 dark:bg-white/10 shrink-0" />

                        {/* ===== Right side: Wizard form or placeholder ===== */}
                        <div className="flex-1 min-w-0 flex flex-col">
                            {!formActive ? (
                                <div className="flex flex-col items-center justify-center h-full text-center px-8">
                                    <div className="w-12 h-12 rounded-full bg-sky-blue/20 dark:bg-sky-blue/10 flex items-center justify-center mb-3">
                                        <Icon name="agent" className="size-5 fill-firefly dark:fill-sky-blue" />
                                    </div>
                                    <p className="text-sm text-charcoal/50 dark:text-white/40">
                                        {t('iiClaw.agents.dialog.placeholder')}
                                    </p>
                                </div>
                            ) : (
                                <>
                                    <div className="mb-4">
                                        <StepIndicator currentStep={step} totalSteps={TOTAL_STEPS} />
                                    </div>

                                    <div className="flex-1 overflow-y-auto pr-1">
                                        {step === 1 && renderStep1()}
                                        {step === 2 && renderStep2()}
                                        {step === 3 && renderStep3()}
                                        {step === 4 && renderStep4()}
                                    </div>

                                    {error && (
                                        <p className="text-xs text-red bg-red/10 rounded-lg px-3 py-2 mt-3">
                                            {error}
                                        </p>
                                    )}

                                    <div className="flex items-center justify-between pt-3 mt-3 border-t border-charcoal/[0.06] dark:border-white/[0.06]">
                                        <Button
                                            variant="outline"
                                            size="sm"
                                            onClick={handleBack}
                                            disabled={step === 1 || submitting}
                                            className="dark:text-white dark:border-white/20 dark:hover:bg-white/5"
                                        >
                                            {t('iiClaw.agents.dialog.buttons.back')}
                                        </Button>

                                        <div className="flex gap-2">
                                            {step < TOTAL_STEPS ? (
                                                <Button
                                                    size="sm"
                                                    onClick={handleNext}
                                                    disabled={!canNext()}
                                                    className="bg-sky-blue text-charcoal hover:bg-sky-blue/80 dark:bg-sky-blue dark:text-charcoal dark:hover:bg-sky-blue/80"
                                                >
                                                    {t('iiClaw.agents.dialog.buttons.next')}
                                                </Button>
                                            ) : (
                                                <Button
                                                    size="sm"
                                                    onClick={handleSubmit}
                                                    disabled={submitting || !canNext()}
                                                    className="bg-sky-blue text-charcoal hover:bg-sky-blue/80 dark:bg-sky-blue dark:text-charcoal dark:hover:bg-sky-blue/80"
                                                >
                                                    {submitting
                                                        ? t('iiClaw.agents.dialog.buttons.saving')
                                                        : editingAgentId
                                                          ? t('iiClaw.agents.dialog.buttons.update')
                                                          : t('iiClaw.agents.dialog.buttons.create')}
                                                </Button>
                                            )}
                                        </div>
                                    </div>
                                </>
                            )}
                        </div>
                    </div>
                    {/* Mobile: Agent list overlay (inside DialogContent) */}
                    {mobileListOpen && (
                        <div className="sm:hidden absolute inset-0 z-50 bg-white dark:bg-charcoal rounded-xl flex flex-col">
                            <div className="flex items-center justify-between px-5 pt-5 pb-3 border-b border-charcoal/[0.06] dark:border-white/[0.06]">
                                <h3 className="text-sm font-semibold text-black dark:text-white">
                                    {t('iiClaw.agents.dialog.sidebar.title')}
                                    {agents.length > 0 && (
                                        <span className="ml-1.5 text-[10px] font-normal text-charcoal/40 dark:text-white/30">
                                            ({agents.length})
                                        </span>
                                    )}
                                </h3>
                                <button
                                    type="button"
                                    onClick={() => setMobileListOpen(false)}
                                    className="w-7 h-7 rounded-lg flex items-center justify-center text-charcoal/40 dark:text-white/40 hover:text-black dark:hover:text-white hover:bg-charcoal/5 dark:hover:bg-white/10 transition-colors cursor-pointer"
                                >
                                    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" xmlns="http://www.w3.org/2000/svg">
                                        <path d="M3.5 3.5L10.5 10.5M3.5 10.5L10.5 3.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
                                    </svg>
                                </button>
                            </div>
                            <div className="flex-1 overflow-y-auto px-3 py-2">
                                {loadingAgents ? (
                                    <div className="flex items-center justify-center h-24 text-xs text-charcoal/40 dark:text-white/30">
                                        {t('common.loading', 'Loading...')}
                                    </div>
                                ) : agents.length === 0 ? (
                                    <div className="flex flex-col items-center justify-center h-24 text-center">
                                        <p className="text-xs text-charcoal/40 dark:text-white/30">
                                            {t('iiClaw.agents.dialog.sidebar.empty')}
                                        </p>
                                        <p className="text-[10px] text-charcoal/30 dark:text-white/20 mt-0.5">
                                            {t('iiClaw.agents.dialog.sidebar.emptyHint')}
                                        </p>
                                    </div>
                                ) : (
                                    <div className="divide-y divide-charcoal/[0.06] dark:divide-white/[0.08]">
                                        {agents.map((agent) => {
                                            const isSelected = editingAgentId === agent.id
                                            return (
                                                <div
                                                    key={agent.id}
                                                    onClick={() => { handleSelectAgent(agent); setMobileListOpen(false) }}
                                                    className={clsx(
                                                        'flex items-center gap-2.5 px-3 py-3 cursor-pointer transition-all rounded-md',
                                                        isSelected
                                                            ? 'bg-sky-blue/35 dark:bg-sky-blue/15'
                                                            : 'hover:bg-charcoal/[0.04] dark:hover:bg-white/[0.1]'
                                                    )}
                                                >
                                                    <div className="min-w-0 flex-1">
                                                        <p className="text-sm font-medium text-black dark:text-white truncate">
                                                            {agent.agent_name}
                                                        </p>
                                                        {agent.tag && (
                                                            <span className="inline-block mt-1 text-[10px] font-medium px-1.5 py-0.5 rounded-md bg-[rgb(210,240,245)] text-gray-700 truncate max-w-full">
                                                                {agent.tag}
                                                            </span>
                                                        )}
                                                    </div>
                                                    <button
                                                        onClick={(e) => {
                                                            e.stopPropagation()
                                                            setConfirmDelete(agent.id)
                                                            setMobileListOpen(false)
                                                        }}
                                                        className={clsx(
                                                            'shrink-0 w-7 h-7 rounded-md flex items-center justify-center transition-colors cursor-pointer',
                                                            'text-charcoal/20 dark:text-white/25 hover:text-red hover:bg-red/10',
                                                        )}
                                                        title={t('iiClaw.agents.dialog.delete.confirm')}
                                                    >
                                                        <svg width="12" height="12" viewBox="0 0 12 12" fill="none" xmlns="http://www.w3.org/2000/svg">
                                                            <path d="M2.5 3.5H9.5M4.5 3.5V2.5C4.5 2.22386 4.72386 2 5 2H7C7.27614 2 7.5 2.22386 7.5 2.5V3.5M5 5.5V8.5M7 5.5V8.5M3.5 3.5L3.85 9.17C3.87 9.63 4.25 10 4.71 10H7.29C7.75 10 8.13 9.63 8.15 9.17L8.5 3.5" stroke="currentColor" strokeWidth="1" strokeLinecap="round" strokeLinejoin="round"/>
                                                        </svg>
                                                    </button>
                                                </div>
                                            )
                                        })}
                                    </div>
                                )}
                            </div>
                        </div>
                    )}
                </DialogContent>
            </Dialog>

            <AlertDialog open={!!confirmDelete} onOpenChange={(v) => { if (!v) setConfirmDelete(null) }}>
                <AlertDialogContent>
                    <AlertDialogHeader>
                        <AlertDialogTitle>{t('iiClaw.agents.dialog.delete.title')}</AlertDialogTitle>
                        <AlertDialogDescription>
                            {t('iiClaw.agents.dialog.delete.description')}
                        </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                        <AlertDialogCancel>{t('iiClaw.agents.dialog.delete.cancel')}</AlertDialogCancel>
                        <AlertDialogAction
                            onClick={async () => {
                                if (confirmDelete) {
                                    await handleDeleteAgent(confirmDelete)
                                    setConfirmDelete(null)
                                }
                            }}
                            className="bg-red text-white hover:bg-red/80"
                        >
                            {t('iiClaw.agents.dialog.delete.confirm')}
                        </AlertDialogAction>
                    </AlertDialogFooter>
                </AlertDialogContent>
            </AlertDialog>
        </>
    )
}

// ---------------------------------------------------------------------------
// Agent Card (grid item)
// ---------------------------------------------------------------------------

const AgentCard = ({
    name,
    description,
    icon,
    isFill = false,
    onClick,
}: {
    name: string
    description: string
    icon: string
    isFill?: boolean
    onClick: () => void
}) => (
    <div
        onClick={onClick}
        className={clsx(
            'group relative flex flex-col rounded-xl border transition-all cursor-pointer',
            'p-4',
            'border-sky-blue/80 bg-sky-blue/5 hover:bg-sky-blue/10 hover:border-sky-blue/40',
            'dark:border-sky-blue/20 dark:bg-sky-blue/[0.04] dark:hover:bg-sky-blue/[0.08] dark:hover:border-sky-blue/30'
        )}
    >
        <div className="w-9 h-9 rounded-lg bg-sky-blue/15 dark:bg-sky-blue/10 flex items-center justify-center mb-3">
            <Icon name={icon} className={clsx('size-4.5', isFill
                ? 'fill-firefly dark:fill-sky-blue'
                : 'stroke-firefly dark:stroke-sky-blue'
            )} />
        </div>
        <h3 className="text-sm font-semibold text-firefly dark:text-sky-blue mb-0.5">
            {name}
        </h3>
        <p className="text-[10px] leading-snug text-firefly/60 dark:text-sky-blue/50 line-clamp-2">
            {description}
        </p>
    </div>
)

// ---------------------------------------------------------------------------
// Agents Panel (main export)
// ---------------------------------------------------------------------------

const AgentsPanel = () => {
    const { t } = useTranslation()
    const [dialogOpen, setDialogOpen] = useState(false)
    const [editAgent, setEditAgent] = useState<UserAgent | null>(null)

    const handleOpenCreate = () => {
        setEditAgent(null)
        setDialogOpen(true)
    }

    return (
        <div className="flex-1 p-4 sm:p-6 md:p-8 overflow-y-auto bg-white dark:bg-charcoal">
            <div className="max-w-4xl mx-auto">
                <div className="mb-6 sm:mb-8">
                    <h1 className="text-xl sm:text-2xl font-bold text-black dark:text-white">
                        {t('iiClaw.agents.title')}
                    </h1>
                    <p className="text-xs sm:text-sm text-charcoal/50 dark:text-white/40 mt-1.5 sm:mt-2">
                        {t('iiClaw.agents.subtitle')}
                    </p>
                </div>

                {/* Custom your Agent — standalone card */}
                <div
                    onClick={handleOpenCreate}
                    className={clsx(
                        'flex items-center gap-4 rounded-xl border border-dashed cursor-pointer transition-all mb-6 sm:mb-8',
                        'px-4 py-4 sm:px-5 sm:py-5',
                        'border-sky-blue/50 bg-sky-blue/5 hover:bg-sky-blue/10',
                        'dark:border-sky-blue/30 dark:bg-sky-blue/[0.03] dark:hover:bg-sky-blue/[0.08]'
                    )}
                >
                    <div className="w-10 h-10 rounded-xl bg-sky-blue/20 dark:bg-sky-blue/15 flex items-center justify-center shrink-0">
                        <svg width="18" height="18" viewBox="0 0 14 14" fill="none" xmlns="http://www.w3.org/2000/svg">
                            <path d="M7 1.75V12.25M1.75 7H12.25" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" className="text-firefly dark:text-sky-blue" />
                        </svg>
                    </div>
                    <div>
                        <h3 className="text-sm sm:text-base font-semibold text-black dark:text-white">
                            {t('iiClaw.agents.customCard.title')}
                        </h3>
                        <p className="text-xs sm:text-sm text-charcoal/50 dark:text-white/40 mt-0.5">
                            {t('iiClaw.agents.customCard.description')}
                        </p>
                    </div>
                </div>

                {/* Available Agents */}
                <h2 className="text-sm sm:text-base font-semibold text-black dark:text-white mb-3 sm:mb-4">
                    {t('iiClaw.agents.availableAgents')}
                </h2>

                <div className="grid grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-2.5 sm:gap-3">
                    {BUILTIN_AGENTS.map((agent) => (
                        <AgentCard
                            key={agent.type}
                            name={t(agent.nameKey)}
                            description={t(agent.descKey)}
                            icon={agent.icon}
                            isFill={agent.isFill}
                            onClick={() => {}}
                        />
                    ))}
                </div>
            </div>

            <CreateAgentDialog
                open={dialogOpen}
                onOpenChange={setDialogOpen}
                onCreated={() => {}}
                editAgent={editAgent}
            />
        </div>
    )
}

export { AgentsPanel }
