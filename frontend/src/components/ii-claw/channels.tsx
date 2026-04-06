import { useState, useEffect, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import clsx from 'clsx'

import { Switch } from '@/components/ui/switch'
import { Input } from '@/components/ui/input'
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
import { iiClawService, type UserChannelInstance, type UserAgent } from '@/services/ii-claw.service'
import { CHANNEL_DEFS, type ChannelDef, type ChannelField } from './channel-defs'
import { BUILTIN_AGENTS } from './agents'
import { useAuth } from '@/contexts/auth-context'
import { Icon } from '@/components/ui/icon'

/**
 * Generate a unique instance_name_id: {channel_type}_{random_id}
 * e.g. "discord_a1b2c3d4"
 */
function generateInstanceNameId(channelType: string): string {
    const randomId = Math.random().toString(36).substring(2, 10)
    return `${channelType.toLowerCase()}_${randomId}`
}

// ---------------------------------------------------------------------------
// Agent ID helpers: convert between backend value and Select value
// ---------------------------------------------------------------------------

const BUILTIN_AGENT_TYPES = new Set(BUILTIN_AGENTS.map((a) => a.type))

/** Backend value → Select value */
function agentIdToSelectValue(backendId: string | undefined | null): string {
    if (!backendId || backendId === 'general') return '_default'
    if (BUILTIN_AGENT_TYPES.has(backendId as never)) return `builtin:${backendId}`
    return backendId // custom agent UUID
}

/** Select value → backend value */
function selectValueToAgentId(selectVal: string): string {
    if (selectVal === '_default') return ''
    if (selectVal.startsWith('builtin:')) return selectVal.replace('builtin:', '')
    return selectVal // custom agent UUID
}

// ---------------------------------------------------------------------------
// Configure Dialog
// ---------------------------------------------------------------------------

type EditMode = { type: 'new' } | { type: 'edit'; instance: UserChannelInstance }

const ConfigureDialog = ({
    channel,
    open,
    onOpenChange,
    onConfigured,
}: {
    channel: ChannelDef | null
    open: boolean
    onOpenChange: (open: boolean) => void
    onConfigured: () => void
}) => {
    const { t } = useTranslation()
    const { user } = useAuth()

    // Left panel: bot list
    const [instances, setInstances] = useState<UserChannelInstance[]>([])
    const [loadingInstances, setLoadingInstances] = useState(false)
    const [removingInstance, setRemovingInstance] = useState<string | null>(null)
    const [mobileListOpen, setMobileListOpen] = useState(false)

    // Agent selector
    const [customAgents, setCustomAgents] = useState<UserAgent[]>([])
    const [agentId, setAgentId] = useState('')

    // Right panel: form
    const [editMode, setEditMode] = useState<EditMode | null>(null)
    const [botName, setBotName] = useState('')
    const [fieldValues, setFieldValues] = useState<Record<string, string>>({})
    const [showAdvanced, setShowAdvanced] = useState(false)
    const [showSteps, setShowSteps] = useState(false)
    const [submitting, setSubmitting] = useState(false)
    const [error, setError] = useState<string | null>(null)
    const [confirmRemove, setConfirmRemove] = useState<string | null>(null)
    const [editingName, setEditingName] = useState(false)
    const [editedName, setEditedName] = useState('')
    const [newInstanceId, setNewInstanceId] = useState('')

    const instanceNameId = editMode?.type === 'edit'
        ? editMode.instance.instance_name_id
        : newInstanceId

    const fetchInstances = useCallback(async () => {
        if (!channel || !user) return
        setLoadingInstances(true)
        try {
            const list = await iiClawService.listUserChannels(user.id, channel.name)
            setInstances(list)
        } catch {
            setInstances([])
        } finally {
            setLoadingInstances(false)
        }
    }, [channel, user])

    const fetchCustomAgents = useCallback(async () => {
        try {
            const list = await iiClawService.listUserAgents()
            setCustomAgents(list)
        } catch {
            setCustomAgents([])
        }
    }, [])

    // Fetch instances when dialog opens — default to "new" form
    useEffect(() => {
        if (open && channel) {
            fetchInstances()
            fetchCustomAgents()
            resetForm()
            setNewInstanceId(generateInstanceNameId(channel.name))
            setEditMode({ type: 'new' })
        }
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [open, channel, fetchInstances, fetchCustomAgents])

    const resetForm = () => {
        if (channel) {
            const initial: Record<string, string> = {}
            channel.fields.forEach((f) => {
                initial[f.key] = ''
            })
            setFieldValues(initial)
            setBotName('')
            setAgentId('')
            setShowAdvanced(false)
            setShowSteps(false)
            setError(null)
        }
    }

    const startNew = () => {
        resetForm()
        setEditingName(false)
        if (channel) {
            setNewInstanceId(generateInstanceNameId(channel.name))
        }
        setEditMode({ type: 'new' })
    }

    const startEdit = (inst: UserChannelInstance) => {
        if (!channel) return
        setEditingName(false)
        setEditedName('')
        setBotName(inst.instance_name || inst.instance_name_id)
        setAgentId(agentIdToSelectValue(inst.agent_id))
        // Pre-fill fields from config_json
        const initial: Record<string, string> = {}
        channel.fields.forEach((f) => {
            const configVal = inst.config_json?.[f.key]
            if (configVal !== undefined && configVal !== null) {
                if (Array.isArray(configVal)) {
                    initial[f.key] = configVal.join(', ')
                } else {
                    initial[f.key] = String(configVal)
                }
            } else {
                initial[f.key] = ''
            }
        })
        setFieldValues(initial)
        setShowAdvanced(false)
        setShowSteps(false)
        setError(null)
        setEditMode({ type: 'edit', instance: inst })
    }

    if (!channel) return null

    const basicFields = channel.fields.filter((f) => !f.advanced)
    const advancedFields = channel.fields.filter((f) => f.advanced)
    const setupSteps = t(`iiClaw.channels.${channel.name}.setupSteps`, { returnObjects: true }) as string[]

    const handleSubmit = async () => {
        if (!user) {
            setError('User not authenticated')
            return
        }

        if (editMode?.type === 'new') {
            if (!botName.trim()) {
                setError(t('iiClaw.channels.botNameRequired', 'Bot name is required'))
                return
            }
        }

        // Only validate required fields for new bots — editing can leave blank to keep current
        if (editMode?.type === 'new') {
            const missing = channel.fields
                .filter((f) => f.required && !fieldValues[f.key]?.trim())
                .map((f) => t(`iiClaw.channels.${channel.name}.fields.${f.key}`))
            if (missing.length > 0) {
                setError(`${t('iiClaw.channels.required')}: ${missing.join(', ')}`)
                return
            }
        }

        setSubmitting(true)
        setError(null)
        try {
            const fields: Record<string, string | number | boolean | string[]> = {}
            for (const [key, val] of Object.entries(fieldValues)) {
                if (!val.trim()) continue
                const fieldDef = channel.fields.find((f) => f.key === key)
                if (fieldDef?.type === 'number') {
                    fields[key] = parseInt(val.trim(), 10)
                } else if (fieldDef?.type === 'boolean') {
                    fields[key] = val.trim().toLowerCase() === 'true'
                } else if (fieldDef?.type === 'list') {
                    fields[key] = val.split(',').map((s) => s.trim()).filter(Boolean)
                } else {
                    fields[key] = val.trim()
                }
            }

            if (editMode?.type === 'edit') {
                // PUT to update existing bot
                const updatePayload: Record<string, unknown> = {}
                if (editingName && editedName.trim()) {
                    updatePayload.instance_name = editedName.trim()
                }
                if (Object.keys(fields).length > 0) {
                    updatePayload.fields = fields
                }
                const resolvedAgentId = selectValueToAgentId(agentId)
                if (resolvedAgentId) {
                    updatePayload.agent_id = resolvedAgentId
                }
                await iiClawService.updateUserChannel(
                    user.id,
                    editMode.instance.instance_name_id,
                    updatePayload
                )
            } else {
                // POST to create new bot
                const resolvedAgentId = selectValueToAgentId(agentId)
                await iiClawService.configureUserChannel(user.id, instanceNameId, {
                    channel_type: channel.name,
                    instance_name: botName.trim(),
                    fields,
                    agent_id: resolvedAgentId || undefined,
                })
            }

            resetForm()
            setEditingName(false)
            setEditedName('')
            setEditMode(null)
            onConfigured()
            await fetchInstances()
        } catch (e: unknown) {
            const msg =
                e instanceof Error ? e.message : 'Failed to configure channel'
            setError(msg)
        } finally {
            setSubmitting(false)
        }
    }

    const handleRemoveInstance = async (nameId: string) => {
        if (!user) return
        setRemovingInstance(nameId)
        try {
            await iiClawService.removeUserChannel(user.id, nameId)
            if (editMode?.type === 'edit' && editMode.instance.instance_name_id === nameId) {
                setEditMode(null)
            }
            onConfigured()
            await fetchInstances()
        } catch (e: unknown) {
            const msg = e instanceof Error ? e.message : 'Failed to remove bot'
            setError(msg)
        } finally {
            setRemovingInstance(null)
        }
    }

    const isEditing = editMode?.type === 'edit'

    const renderField = (field: ChannelField) => {
        const isSecret = field.type === 'secret'
        const placeholder = isEditing && isSecret ? '••••••••' : field.placeholder

        return (
            <div key={field.key} className="space-y-1.5">
                <label className="text-xs sm:text-sm font-medium text-black dark:text-white flex items-center gap-2">
                    {t(`iiClaw.channels.${channel.name}.fields.${field.key}`)}
                    {field.required && !isEditing && (
                        <span className="text-red-500 text-xs">*</span>
                    )}
                    {isSecret && (
                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-600 dark:text-amber-400 font-normal">
                            {t('iiClaw.channels.secret')}
                        </span>
                    )}
                    {isEditing && isSecret && (
                        <span className="text-[10px] text-charcoal/30 dark:text-white/20 font-normal">
                            {t('iiClaw.channels.leaveBlankToKeep', 'leave blank to keep current')}
                        </span>
                    )}
                </label>
                {field.type === 'boolean' ? (
                    <div className="flex items-center gap-2">
                        <Switch
                            checked={fieldValues[field.key] === 'true'}
                            onCheckedChange={(checked) =>
                                setFieldValues((prev) => ({
                                    ...prev,
                                    [field.key]: checked ? 'true' : 'false'
                                }))
                            }
                        />
                        <span className="text-xs text-charcoal/50 dark:text-white/40">
                            {fieldValues[field.key] === 'true' ? 'Enabled' : 'Disabled'}
                        </span>
                    </div>
                ) : (
                    <Input
                        type={field.type === 'secret' ? 'password' : 'text'}
                        placeholder={placeholder}
                        value={fieldValues[field.key] || ''}
                        onChange={(e) =>
                            setFieldValues((prev) => ({
                                ...prev,
                                [field.key]: e.target.value
                            }))
                        }
                        className="h-10 text-sm"
                    />
                )}
                {field.type === 'list' && (
                    <p className="text-[10px] text-charcoal/40 dark:text-white/30">
                        {t('iiClaw.channels.commaSeparated')}
                    </p>
                )}
            </div>
        )
    }

    return (
        <>
        <Dialog
            open={open}
            onOpenChange={(v) => {
                if (v && channel) {
                    resetForm()
                    setNewInstanceId(generateInstanceNameId(channel.name))
                    setEditMode({ type: 'new' })
                }
                onOpenChange(v)
            }}
        >
            <DialogContent className="max-w-[calc(100%-1rem)] sm:max-w-2xl md:max-w-3xl">
                <DialogHeader>
                    <div className="flex items-center gap-3">
                        <img
                            src={channel.icon}
                            alt={channel.name}
                            className="w-10 h-10 rounded-xl shrink-0 object-contain"
                        />
                        <div>
                            <DialogTitle className="dark:text-white">
                                {t('iiClaw.channels.configure')} {t(`iiClaw.channels.${channel.name}.displayName`)}
                            </DialogTitle>
                            <DialogDescription className="mt-1">
                                {t(`iiClaw.channels.${channel.name}.quickSetup`)}
                            </DialogDescription>
                        </div>
                    </div>
                </DialogHeader>

                {/* Mobile: button to open bot list */}
                <button
                    type="button"
                    onClick={() => setMobileListOpen(true)}
                    className={clsx(
                        'sm:hidden w-full h-9 rounded-lg flex items-center justify-center gap-2 text-xs font-medium transition-colors cursor-pointer',
                        'bg-sky-blue/15 text-firefly dark:bg-sky-blue/10 dark:text-sky-blue hover:bg-sky-blue/25 dark:hover:bg-sky-blue/20'
                    )}
                >
                    {t('iiClaw.channels.yourBots', 'Your Bots')}
                    {instances.length > 0 && (
                        <span className="text-[10px] font-normal text-charcoal/40 dark:text-white/30">
                            ({instances.length})
                        </span>
                    )}
                </button>

                <div className="flex flex-col sm:flex-row gap-4 sm:gap-6 mt-2 sm:h-[360px]">
                    {/* ===== Left side: Bot instances list (hidden on mobile) ===== */}
                    <div className="hidden sm:flex w-52 shrink-0 flex-col min-h-0">
                        <div className="flex items-center justify-between mb-3">
                            <h3 className="text-xs sm:text-sm font-semibold text-black dark:text-white">
                                {t('iiClaw.channels.yourBots', 'Your Bots')}
                                {instances.length > 0 && (
                                    <span className="ml-1.5 text-[10px] font-normal text-charcoal/40 dark:text-white/30">
                                        ({instances.length})
                                    </span>
                                )}
                            </h3>
                            <button
                                type="button"
                                onClick={startNew}
                                className={clsx(
                                    'w-7 h-7 rounded-lg flex items-center justify-center transition-colors cursor-pointer',
                                    'text-firefly dark:text-sky-blue hover:text-charcoal dark:hover:text-white',
                                    'bg-sky-blue/20 hover:bg-sky-blue/40 dark:bg-sky-blue/10 dark:hover:bg-sky-blue/20',
                                    editMode?.type === 'new' && 'bg-sky-blue/40 dark:bg-sky-blue/20 text-charcoal dark:text-white'
                                )}
                                title={t('iiClaw.channels.addBot', 'Add Bot')}
                            >
                                <svg width="14" height="14" viewBox="0 0 14 14" fill="none" xmlns="http://www.w3.org/2000/svg">
                                    <path d="M7 1.75V12.25M1.75 7H12.25" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
                                </svg>
                            </button>
                        </div>

                        <div className="flex-1 overflow-y-auto">
                            {loadingInstances ? (
                                <div className="flex items-center justify-center h-24 text-xs text-charcoal/40 dark:text-white/30">
                                    {t('common.loading', 'Loading...')}
                                </div>
                            ) : instances.length === 0 ? (
                                <div className="flex flex-col items-center justify-center h-24 text-center">
                                    <p className="text-xs text-charcoal/40 dark:text-white/30">
                                        {t('iiClaw.channels.noBots', 'No bots configured yet')}
                                    </p>
                                    <p className="text-[10px] text-charcoal/30 dark:text-white/20 mt-0.5">
                                        {t('iiClaw.channels.noBotsHint', 'Click + to create one')}
                                    </p>
                                </div>
                            ) : (
                                <div className="divide-y divide-charcoal/[0.06] dark:divide-white/[0.08]">
                                    {instances.map((inst) => {
                                        const isSelected = editMode?.type === 'edit' && editMode.instance.instance_name_id === inst.instance_name_id
                                        return (
                                            <div
                                                key={inst.instance_name_id}
                                                onClick={() => startEdit(inst)}
                                                className={clsx(
                                                    'flex items-center gap-2.5 px-2.5 py-2.5 cursor-pointer transition-all',
                                                    isSelected
                                                        ? 'bg-charcoal/[0.04] dark:bg-white/[0.08]'
                                                        : 'hover:bg-charcoal/[0.02] dark:hover:bg-white/[0.05]'
                                                )}
                                            >
                                                <div className="min-w-0 flex-1">
                                                    <p className="text-xs font-medium text-black dark:text-white truncate">
                                                        {inst.instance_name || inst.instance_name_id}
                                                    </p>
                                                    <div className="flex items-center gap-1.5 mt-0.5">
                                                        <span
                                                            className={clsx('w-1.5 h-1.5 rounded-full shrink-0', {
                                                                'bg-green-5': inst.status === 'running' || inst.status === 'active',
                                                                'bg-yellow dark:bg-yellow': inst.status === 'configured',
                                                                'bg-charcoal/20 dark:bg-white/30': !inst.status || inst.status === 'stopped',
                                                            })}
                                                        />
                                                        <span className="text-[10px] text-charcoal/40 dark:text-white/40">
                                                            {inst.status === 'active' ? 'active' : 'error'}
                                                        </span>
                                                    </div>
                                                </div>
                                                <button
                                                    onClick={(e) => {
                                                        e.stopPropagation()
                                                        setConfirmRemove(inst.instance_name_id)
                                                    }}
                                                    disabled={removingInstance === inst.instance_name_id}
                                                    className={clsx(
                                                        'shrink-0 w-6 h-6 rounded-md flex items-center justify-center transition-colors cursor-pointer',
                                                        'text-charcoal/20 dark:text-white/25 hover:text-red hover:bg-red/10',
                                                        'disabled:opacity-40 disabled:cursor-not-allowed'
                                                    )}
                                                    title={t('iiClaw.channels.remove', 'Remove')}
                                                >
                                                    {removingInstance === inst.instance_name_id ? (
                                                        <span className="text-[10px]">...</span>
                                                    ) : (
                                                        <svg width="12" height="12" viewBox="0 0 12 12" fill="none" xmlns="http://www.w3.org/2000/svg">
                                                            <path d="M2.5 3.5H9.5M4.5 3.5V2.5C4.5 2.22386 4.72386 2 5 2H7C7.27614 2 7.5 2.22386 7.5 2.5V3.5M5 5.5V8.5M7 5.5V8.5M3.5 3.5L3.85 9.17C3.87 9.63 4.25 10 4.71 10H7.29C7.75 10 8.13 9.63 8.15 9.17L8.5 3.5" stroke="currentColor" strokeWidth="1" strokeLinecap="round" strokeLinejoin="round"/>
                                                        </svg>
                                                    )}
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

                    {/* ===== Right side: Config form ===== */}
                    <div className="flex-1 min-w-0 overflow-y-auto pr-1">
                        {editMode === null ? (
                            <div className="flex flex-col items-center justify-center h-full text-center px-8">
                                <div className="w-12 h-12 rounded-full bg-charcoal/5 dark:bg-white/5 flex items-center justify-center mb-3">
                                    <img
                                        src={channel.icon}
                                        alt={channel.name}
                                        className="w-6 h-6 rounded object-contain opacity-40"
                                    />
                                </div>
                                <p className="text-sm text-charcoal/50 dark:text-white/40">
                                    {instances.length > 0
                                        ? t('iiClaw.channels.selectOrCreate', 'Select a bot to edit, or click + to add a new one')
                                        : t('iiClaw.channels.clickToCreate', 'Click + to create your first bot')}
                                </p>
                                {instances.length === 0 && (
                                    <Button
                                        size="sm"
                                        variant="outline"
                                        className="mt-4 dark:text-white dark:border-white/20 dark:hover:bg-white/5"
                                        onClick={startNew}
                                    >
                                        {t('iiClaw.channels.addBot', 'Add Bot')}
                                    </Button>
                                )}
                            </div>
                        ) : (
                            <div className="space-y-4">
                                <div className="flex items-center justify-between gap-3 pb-3 border-b border-charcoal/[0.06] dark:border-white/[0.06]">
                                    <div className="flex items-center gap-2 min-w-0 flex-1">
                                        {editMode.type === 'new' ? (
                                            <h3 className="text-sm font-semibold text-black dark:text-white truncate">
                                                {t('iiClaw.channels.newBot', 'New Bot')}
                                            </h3>
                                        ) : editingName ? (
                                            <Input
                                                type="text"
                                                value={editedName}
                                                onChange={(e) => setEditedName(e.target.value)}
                                                className="h-8 text-sm font-semibold flex-1"
                                                autoFocus
                                                onKeyDown={(e) => {
                                                    if (e.key === 'Escape') {
                                                        setEditingName(false)
                                                        setEditedName('')
                                                    }
                                                }}
                                            />
                                        ) : (
                                            <>
                                                <h3 className="text-sm font-semibold text-black dark:text-white truncate">
                                                    {editMode.instance.instance_name || editMode.instance.instance_name_id}
                                                </h3>
                                                <button
                                                    type="button"
                                                    onClick={() => {
                                                        setEditedName(editMode.instance.instance_name || editMode.instance.instance_name_id)
                                                        setEditingName(true)
                                                    }}
                                                    className="shrink-0 w-6 h-6 rounded-md flex items-center justify-center text-charcoal/25 dark:text-white/20 hover:text-charcoal/60 dark:hover:text-white/50 hover:bg-charcoal/5 dark:hover:bg-white/5 transition-colors cursor-pointer"
                                                    title={t('iiClaw.channels.editName', 'Edit name')}
                                                >
                                                    <svg width="12" height="12" viewBox="0 0 12 12" fill="none" xmlns="http://www.w3.org/2000/svg">
                                                        <path d="M8.5 1.5L10.5 3.5M1.5 10.5L2 8.5L8.5 2L10 3.5L3.5 10L1.5 10.5Z" stroke="currentColor" strokeWidth="1" strokeLinecap="round" strokeLinejoin="round"/>
                                                    </svg>
                                                </button>
                                            </>
                                        )}
                                    </div>
                                    {editMode.type === 'edit' && (
                                        <div className="w-44 shrink-0">
                                            <Select value={agentId || '_default'} onValueChange={(v) => setAgentId(v === '_default' ? '' : v)}>
                                                <SelectTrigger className="!h-8 !w-full !px-2.5 !py-1 !rounded-lg text-sm [&_svg[class*='size-6']]:!size-4">
                                                    <SelectValue placeholder={t('iiClaw.channels.selectAgent', 'Select agent')} />
                                                </SelectTrigger>
                                                <SelectContent>
                                                    {customAgents.length > 0 && (
                                                        <SelectGroup>
                                                            <SelectLabel className="text-xs font-semibold text-charcoal/40 dark:text-white/30">
                                                                {t('iiClaw.channels.customAgents', 'Custom')}
                                                            </SelectLabel>
                                                            {customAgents.map((agent) => (
                                                                <SelectItem key={agent.id} value={agent.id} className="text-sm">
                                                                    <span className="flex items-center gap-2">
                                                                        <Icon name="agent" className="size-3.5 fill-charcoal/40 dark:fill-white/40" />
                                                                        {agent.agent_name}
                                                                        {agent.tag && (
                                                                            <span className="text-[10px] px-1 py-0.5 rounded bg-sky-blue/10 text-charcoal/50 dark:text-white/40">
                                                                                {agent.tag}
                                                                            </span>
                                                                        )}
                                                                    </span>
                                                                </SelectItem>
                                                            ))}
                                                        </SelectGroup>
                                                    )}
                                                    <SelectGroup>
                                                        <SelectLabel className="text-xs font-semibold text-charcoal/40 dark:text-white/30">
                                                            {t('iiClaw.channels.builtinAgents', 'Built-in')}
                                                        </SelectLabel>
                                                        <SelectItem value="_default" className="text-sm">
                                                            <span className="flex items-center gap-2">
                                                                <Icon name="agent" className="size-3.5 fill-charcoal/40 dark:fill-white/40" />
                                                                {t('iiClaw.agents.builtinAgents.general.name')}
                                                            </span>
                                                        </SelectItem>
                                                        {BUILTIN_AGENTS.filter((a) => a.type !== 'general').map((agent) => (
                                                            <SelectItem key={agent.type} value={`builtin:${agent.type}`} className="text-sm">
                                                                <span className="flex items-center gap-2">
                                                                    <Icon
                                                                        name={agent.icon}
                                                                        className={clsx('size-3.5', agent.isFill
                                                                            ? 'fill-charcoal/40 dark:fill-white/40'
                                                                            : 'stroke-charcoal/40 dark:stroke-white/40'
                                                                        )}
                                                                    />
                                                                    {t(agent.nameKey)}
                                                                </span>
                                                            </SelectItem>
                                                        ))}
                                                    </SelectGroup>
                                                </SelectContent>
                                            </Select>
                                        </div>
                                    )}
                                </div>

                                {/* Setup steps */}
                                {Array.isArray(setupSteps) && setupSteps.length > 0 && (
                                    <div>
                                        <button
                                            type="button"
                                            onClick={() => setShowSteps(!showSteps)}
                                            className="flex items-center gap-1.5 text-xs font-medium text-charcoal/40 dark:text-white/30 hover:text-charcoal dark:hover:text-white transition-colors cursor-pointer"
                                        >
                                            <span
                                                className={clsx(
                                                    'transition-transform inline-block',
                                                    showSteps && 'rotate-90'
                                                )}
                                            >
                                                ▶
                                            </span>
                                            {t('iiClaw.channels.setupSteps')} ({setupSteps.length})
                                        </button>
                                        {showSteps && (
                                            <ol className="mt-2 space-y-1.5 rounded-xl bg-charcoal/[0.03] dark:bg-white/[0.03] p-3 sm:p-4">
                                                {setupSteps.map((step, i) => (
                                                    <li
                                                        key={i}
                                                        className="text-xs sm:text-sm text-charcoal/70 dark:text-white/60 flex gap-2"
                                                    >
                                                        <span className="shrink-0 w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold bg-charcoal/10 dark:bg-white/10 text-charcoal/60 dark:text-white/50">
                                                            {i + 1}
                                                        </span>
                                                        {step}
                                                    </li>
                                                ))}
                                            </ol>
                                        )}
                                    </div>
                                )}

                                {/* Bot Name + Agent selector */}
                                {editMode.type === 'new' && (
                                    <div className="flex gap-3">
                                        <div className="flex-1 space-y-1.5">
                                            <label className="text-xs sm:text-sm font-medium text-black dark:text-white flex items-center gap-2">
                                                {t('iiClaw.channels.botName', 'Bot Name')}
                                                <span className="text-red text-xs">*</span>
                                            </label>
                                            <Input
                                                type="text"
                                                placeholder={t('iiClaw.channels.botNamePlaceholder', 'e.g. My Agent 1')}
                                                value={botName}
                                                onChange={(e) => setBotName(e.target.value)}
                                                className="h-10 text-sm"
                                            />
                                        </div>
                                        <div className="w-44 shrink-0 space-y-1.5">
                                            <label className="text-xs sm:text-sm font-medium text-black dark:text-white">
                                                {t('iiClaw.channels.agent', 'Agent')}
                                            </label>
                                            <Select value={agentId || '_default'} onValueChange={(v) => setAgentId(v === '_default' ? '' : v)}>
                                                <SelectTrigger className="!h-10 !w-full !px-2.5 !py-1.5 !rounded-lg text-sm [&_svg[class*='size-6']]:!size-4">
                                                    <SelectValue placeholder={t('iiClaw.channels.selectAgent', 'Select agent')} />
                                                </SelectTrigger>
                                                <SelectContent>
                                                    {customAgents.length > 0 && (
                                                        <SelectGroup>
                                                            <SelectLabel className="text-xs font-semibold text-charcoal/40 dark:text-white/30">
                                                                {t('iiClaw.channels.customAgents', 'Custom')}
                                                            </SelectLabel>
                                                            {customAgents.map((agent) => (
                                                                <SelectItem key={agent.id} value={agent.id} className="text-sm">
                                                                    <span className="flex items-center gap-2">
                                                                        <Icon name="agent" className="size-3.5 fill-charcoal/40 dark:fill-white/40" />
                                                                        {agent.agent_name}
                                                                        {agent.tag && (
                                                                            <span className="text-[10px] px-1 py-0.5 rounded bg-sky-blue/10 text-charcoal/50 dark:text-white/40">
                                                                                {agent.tag}
                                                                            </span>
                                                                        )}
                                                                    </span>
                                                                </SelectItem>
                                                            ))}
                                                        </SelectGroup>
                                                    )}
                                                    <SelectGroup>
                                                        <SelectLabel className="text-xs font-semibold text-charcoal/40 dark:text-white/30">
                                                            {t('iiClaw.channels.builtinAgents', 'Built-in')}
                                                        </SelectLabel>
                                                        <SelectItem value="_default" className="text-sm">
                                                            <span className="flex items-center gap-2">
                                                                <Icon name="agent" className="size-3.5 fill-charcoal/40 dark:fill-white/40" />
                                                                {t('iiClaw.agents.builtinAgents.general.name')}
                                                            </span>
                                                        </SelectItem>
                                                        {BUILTIN_AGENTS.filter((a) => a.type !== 'general').map((agent) => (
                                                            <SelectItem key={agent.type} value={`builtin:${agent.type}`} className="text-sm">
                                                                <span className="flex items-center gap-2">
                                                                    <Icon
                                                                        name={agent.icon}
                                                                        className={clsx('size-3.5', agent.isFill
                                                                            ? 'fill-charcoal/40 dark:fill-white/40'
                                                                            : 'stroke-charcoal/40 dark:stroke-white/40'
                                                                        )}
                                                                    />
                                                                    {t(agent.nameKey)}
                                                                </span>
                                                            </SelectItem>
                                                        ))}
                                                    </SelectGroup>
                                                </SelectContent>
                                            </Select>
                                        </div>
                                    </div>
                                )}

                                {/* Fields */}
                                <div className="space-y-3">
                                    {basicFields.map(renderField)}

                                    {advancedFields.length > 0 && (
                                        <>
                                            <button
                                                type="button"
                                                onClick={() => setShowAdvanced(!showAdvanced)}
                                                className="flex items-center gap-1.5 text-xs font-medium text-charcoal/40 dark:text-white/30 hover:text-charcoal dark:hover:text-white transition-colors cursor-pointer"
                                            >
                                                <span
                                                    className={clsx(
                                                        'transition-transform inline-block',
                                                        showAdvanced && 'rotate-90'
                                                    )}
                                                >
                                                    ▶
                                                </span>
                                                {t('iiClaw.channels.advanced')} ({advancedFields.length})
                                            </button>
                                            {showAdvanced && advancedFields.map(renderField)}
                                        </>
                                    )}
                                </div>

                                {error && (
                                    <p className="text-xs text-red bg-red/10 rounded-lg px-3 py-2">
                                        {error}
                                    </p>
                                )}

                                <div className="flex gap-2 justify-end pt-3 border-t border-charcoal/[0.06] dark:border-white/[0.06]">
                                    <Button
                                        variant="outline"
                                        size="sm"
                                        onClick={() => { resetForm(); if (channel) setNewInstanceId(generateInstanceNameId(channel.name)); setEditMode({ type: 'new' }) }}
                                        disabled={submitting}
                                        className="dark:text-white dark:border-white/20 dark:hover:bg-white/5"
                                    >
                                        {t('common.cancel', 'Cancel')}
                                    </Button>
                                    <Button
                                        size="sm"
                                        onClick={handleSubmit}
                                        disabled={submitting}
                                        className="bg-sky-blue text-charcoal hover:bg-sky-blue/80 dark:bg-sky-blue dark:text-charcoal dark:hover:bg-sky-blue/80"
                                    >
                                        {submitting
                                            ? t('iiClaw.channels.saving')
                                            : editMode.type === 'new'
                                              ? t('iiClaw.channels.addBot', 'Add Bot')
                                              : t('iiClaw.channels.update', 'Update')}
                                    </Button>
                                </div>
                            </div>
                        )}
                    </div>
                </div>

                {/* Mobile: Bot list overlay (inside DialogContent) */}
                {mobileListOpen && (
                    <div className="sm:hidden absolute inset-0 z-50 bg-white dark:bg-charcoal rounded-xl flex flex-col">
                        <div className="flex items-center justify-between px-5 pt-5 pb-3 border-b border-charcoal/[0.06] dark:border-white/[0.06]">
                            <h3 className="text-sm font-semibold text-black dark:text-white">
                                {t('iiClaw.channels.yourBots', 'Your Bots')}
                                {instances.length > 0 && (
                                    <span className="ml-1.5 text-[10px] font-normal text-charcoal/40 dark:text-white/30">
                                        ({instances.length})
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
                            {loadingInstances ? (
                                <div className="flex items-center justify-center h-24 text-xs text-charcoal/40 dark:text-white/30">
                                    {t('common.loading', 'Loading...')}
                                </div>
                            ) : instances.length === 0 ? (
                                <div className="flex flex-col items-center justify-center h-24 text-center">
                                    <p className="text-xs text-charcoal/40 dark:text-white/30">
                                        {t('iiClaw.channels.noBots', 'No bots configured yet')}
                                    </p>
                                    <p className="text-[10px] text-charcoal/30 dark:text-white/20 mt-0.5">
                                        {t('iiClaw.channels.noBotsHint', 'Click + to create one')}
                                    </p>
                                </div>
                            ) : (
                                <div className="divide-y divide-charcoal/[0.06] dark:divide-white/[0.08]">
                                    {instances.map((inst) => {
                                        const isSelected = editMode?.type === 'edit' && editMode.instance.instance_name_id === inst.instance_name_id
                                        return (
                                            <div
                                                key={inst.instance_name_id}
                                                onClick={() => { startEdit(inst); setMobileListOpen(false) }}
                                                className={clsx(
                                                    'flex items-center gap-2.5 px-3 py-3 cursor-pointer transition-all rounded-md',
                                                    isSelected
                                                        ? 'bg-sky-blue/35 dark:bg-sky-blue/15'
                                                        : 'hover:bg-charcoal/[0.04] dark:hover:bg-white/[0.1]'
                                                )}
                                            >
                                                <div className="min-w-0 flex-1">
                                                    <p className="text-sm font-medium text-black dark:text-white truncate">
                                                        {inst.instance_name || inst.instance_name_id}
                                                    </p>
                                                    <div className="flex items-center gap-1.5 mt-0.5">
                                                        <span
                                                            className={clsx('w-1.5 h-1.5 rounded-full shrink-0', {
                                                                'bg-green-5': inst.status === 'running' || inst.status === 'active',
                                                                'bg-yellow dark:bg-yellow': inst.status === 'configured',
                                                                'bg-charcoal/20 dark:bg-white/30': !inst.status || inst.status === 'stopped',
                                                            })}
                                                        />
                                                        <span className="text-[10px] text-charcoal/40 dark:text-white/40">
                                                            {inst.status === 'active' ? 'active' : 'error'}
                                                        </span>
                                                    </div>
                                                </div>
                                                <button
                                                    onClick={(e) => {
                                                        e.stopPropagation()
                                                        setConfirmRemove(inst.instance_name_id)
                                                        setMobileListOpen(false)
                                                    }}
                                                    disabled={removingInstance === inst.instance_name_id}
                                                    className={clsx(
                                                        'shrink-0 w-7 h-7 rounded-md flex items-center justify-center transition-colors cursor-pointer',
                                                        'text-charcoal/20 dark:text-white/25 hover:text-red hover:bg-red/10',
                                                        'disabled:opacity-40 disabled:cursor-not-allowed'
                                                    )}
                                                    title={t('iiClaw.channels.remove', 'Remove')}
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

        <AlertDialog open={!!confirmRemove} onOpenChange={(v) => { if (!v) setConfirmRemove(null) }}>
            <AlertDialogContent>
                <AlertDialogHeader>
                    <AlertDialogTitle>
                        {t('iiClaw.channels.confirmRemoveTitle', 'Remove bot?')}
                    </AlertDialogTitle>
                    <AlertDialogDescription>
                        {t('iiClaw.channels.confirmRemoveDesc', 'Are you sure you want to remove "{{name}}"? This action cannot be undone.', { name: confirmRemove })}
                    </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                    <AlertDialogCancel disabled={!!removingInstance}>
                        {t('common.cancel', 'Cancel')}
                    </AlertDialogCancel>
                    <AlertDialogAction
                        onClick={async () => {
                            if (confirmRemove) {
                                await handleRemoveInstance(confirmRemove)
                                setConfirmRemove(null)
                            }
                        }}
                        disabled={!!removingInstance}
                        className="bg-red text-white hover:bg-red/80"
                    >
                        {removingInstance
                            ? t('iiClaw.channels.removing', 'Removing...')
                            : t('iiClaw.channels.remove', 'Remove')}
                    </AlertDialogAction>
                </AlertDialogFooter>
            </AlertDialogContent>
        </AlertDialog>
        </>
    )
}

// ---------------------------------------------------------------------------
// Channel Card
// ---------------------------------------------------------------------------

const ChannelCard = ({
    channel,
    botCount,
    onConfigure
}: {
    channel: ChannelDef
    botCount: number
    onConfigure: (channel: ChannelDef) => void
}) => {
    const { t } = useTranslation()
    const connected = botCount > 0

    return (
        <div
            className={clsx(
                'group relative flex flex-col justify-between rounded-2xl border transition-all',
                'p-4 sm:p-5',
                'border-grey-2 bg-sidebar-bg hover:shadow-md hover:border-sky-blue/50',
                'dark:border-grey/30 dark:bg-white/[0.04] dark:hover:border-sky-blue/40 dark:hover:shadow-lg dark:hover:shadow-black/40'
            )}
        >
            <div>
                <div className="flex items-start justify-between mb-3 sm:mb-4">
                    <img
                        src={channel.icon}
                        alt={channel.name}
                        className="w-10 h-10 sm:w-11 sm:h-11 rounded-xl shrink-0 object-contain"
                    />
                    {connected && (
                        <span className="text-[10px] sm:text-xs font-medium px-2 py-0.5 rounded-full bg-sky-blue/30 text-firefly dark:bg-sky-blue/20 dark:text-sky-blue">
                            {botCount} {botCount === 1 ? 'bot' : 'bots'}
                        </span>
                    )}
                </div>

                <h3 className="text-sm sm:text-base font-semibold text-black dark:text-white mb-1">
                    {t(`iiClaw.channels.${channel.name}.displayName`)}
                </h3>
                <p className="text-xs sm:text-sm text-charcoal/50 dark:text-white/40 leading-relaxed line-clamp-2">
                    {t(`iiClaw.channels.${channel.name}.description`)}
                </p>
            </div>

            <div className="flex items-center justify-between mt-3 sm:mt-4">
                <span
                    className={clsx(
                        'text-[10px] sm:text-xs font-medium px-2 sm:px-2.5 py-0.5 sm:py-1 rounded-full inline-flex items-center gap-1.5',
                        {
                            'bg-green-5/15 text-green-5 dark:bg-green-5/20 dark:text-green-5': connected,
                            'bg-charcoal/5 text-charcoal/40 dark:bg-white/10 dark:text-white/40': !connected
                        }
                    )}
                >
                    <span
                        className={clsx('w-1.5 h-1.5 rounded-full', {
                            'bg-green-5': connected,
                            'bg-charcoal/20 dark:bg-white/25': !connected
                        })}
                    />
                    {connected
                        ? t('iiClaw.channels.status.connected')
                        : t('iiClaw.channels.status.disconnected')}
                </span>
                <button
                    onClick={() => onConfigure(channel)}
                    className={clsx(
                        'text-[10px] sm:text-xs font-medium px-3 py-1.5 rounded-lg transition-colors cursor-pointer',
                        'bg-sky-blue/30 text-firefly hover:bg-sky-blue/50 hover:text-charcoal',
                        'dark:bg-sky-blue/15 dark:text-sky-blue dark:hover:bg-sky-blue/25'
                    )}
                >
                    {t('iiClaw.channels.configure')}
                </button>
            </div>
        </div>
    )
}

// ---------------------------------------------------------------------------
// Channels Panel
// ---------------------------------------------------------------------------

const ChannelsPanel = () => {
    const { t } = useTranslation()
    const { user } = useAuth()
    const [botCounts, setBotCounts] = useState<Record<string, number>>(
        () => Object.fromEntries(CHANNEL_DEFS.map((ch) => [ch.name, 0]))
    )
    const [configureTarget, setConfigureTarget] = useState<ChannelDef | null>(null)
    const [dialogOpen, setDialogOpen] = useState(false)

    const refreshBotCounts = useCallback(async () => {
        if (!user) return
        try {
            const all = await iiClawService.listUserChannels(user.id)
            const counts: Record<string, number> = {}
            CHANNEL_DEFS.forEach((ch) => { counts[ch.name] = 0 })
            all.forEach((inst) => {
                if (counts[inst.channel_type] !== undefined) {
                    counts[inst.channel_type]++
                }
            })
            setBotCounts(counts)
        } catch {
            // Keep existing counts on error
        }
    }, [user])

    useEffect(() => {
        refreshBotCounts()
    }, [refreshBotCounts])

    const handleConfigure = (ch: ChannelDef) => {
        setConfigureTarget(ch)
        setDialogOpen(true)
    }

    const handleConfigured = () => {
        refreshBotCounts()
    }

    const totalBots = Object.values(botCounts).reduce((a, b) => a + b, 0)

    return (
        <div className="flex-1 p-4 sm:p-6 md:p-8 overflow-y-auto bg-white dark:bg-charcoal">
            <div className="max-w-4xl mx-auto">
                <div className="mb-6 sm:mb-8">
                    <h1 className="text-xl sm:text-2xl font-bold text-black dark:text-white">
                        {t('iiClaw.channels.title')}
                    </h1>
                    <p className="text-xs sm:text-sm text-charcoal/50 dark:text-white/40 mt-1.5 sm:mt-2">
                        {t('iiClaw.channels.subtitle')}{' '}
                        <span className="text-black dark:text-white font-medium">
                            {totalBots}
                        </span>{' '}
                        {totalBots === 1 ? 'bot' : 'bots'} {t('iiClaw.channels.connected')}.
                    </p>
                </div>

                <div className="grid grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3 sm:gap-4">
                    {CHANNEL_DEFS.map((channel) => (
                        <ChannelCard
                            key={channel.name}
                            channel={channel}
                            botCount={botCounts[channel.name] || 0}
                            onConfigure={handleConfigure}
                        />
                    ))}
                </div>
            </div>

            <ConfigureDialog
                channel={configureTarget}
                open={dialogOpen}
                onOpenChange={setDialogOpen}
                onConfigured={handleConfigured}
            />
        </div>
    )
}

export { ChannelsPanel }
