import { useState, useEffect, useCallback, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import clsx from 'clsx'

import { Switch } from '@/components/ui/switch'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Button } from '@/components/ui/button'
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
    iiClawService,
    type CronJob,
    type CronJobCreateRequest,
    type CronJobUpdateRequest,
    type CronJobRun,
    type CronJobTestResponse,
    type UserChannelInstance,
    type UserAgent,
} from '@/services/ii-claw.service'
import { CHANNEL_DEFS } from './channel-defs'
import { BUILTIN_AGENTS } from './agents'
import { useAuth } from '@/contexts/auth-context'
import { Icon } from '@/components/ui/icon'

// ---------------------------------------------------------------------------
// Agent ID helpers
// ---------------------------------------------------------------------------

const BUILTIN_AGENT_TYPES = new Set(BUILTIN_AGENTS.map((a) => a.type))

function agentIdToSelectValue(backendId: string | undefined | null): string {
    if (!backendId || backendId === 'general') return '_default'
    if (BUILTIN_AGENT_TYPES.has(backendId as never)) return `builtin:${backendId}`
    return backendId
}

function selectValueToAgentId(selectVal: string): string {
    if (selectVal === '_default') return ''
    if (selectVal.startsWith('builtin:')) return selectVal.replace('builtin:', '')
    return selectVal
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const SCHEDULE_TYPES = ['every', 'cron', 'at'] as const
type ScheduleType = (typeof SCHEDULE_TYPES)[number]

const ACTION_TYPES = ['channel_message', 'assistant_task'] as const
type ActionType = (typeof ACTION_TYPES)[number]

type EveryUnit = 'minutes' | 'hours' | 'days'

// Cron presets for user-friendly selection
const CRON_PRESETS = [
    { key: 'daily_9am', expr: '0 9 * * *', label: 'Daily at 9:00 AM' },
    { key: 'daily_midnight', expr: '0 0 * * *', label: 'Daily at midnight' },
    { key: 'daily_6pm', expr: '0 18 * * *', label: 'Daily at 6:00 PM' },
    { key: 'weekdays_9am', expr: '0 9 * * 1-5', label: 'Weekdays at 9:00 AM' },
    { key: 'weekdays_6pm', expr: '0 18 * * 1-5', label: 'Weekdays at 6:00 PM' },
    { key: 'weekly_monday', expr: '0 9 * * 1', label: 'Every Monday at 9:00 AM' },
    { key: 'weekly_friday', expr: '0 17 * * 5', label: 'Every Friday at 5:00 PM' },
    { key: 'twice_daily', expr: '0 9,18 * * *', label: 'Twice daily (9 AM & 6 PM)' },
    { key: 'every_6h', expr: '0 */6 * * *', label: 'Every 6 hours' },
    { key: 'monthly_first', expr: '0 9 1 * *', label: 'First of month at 9:00 AM' },
    { key: 'monthly_last_friday', expr: '0 17 * * 5#L', label: 'Last Friday of month at 5 PM' },
    { key: 'quarterly', expr: '0 9 1 1,4,7,10 *', label: 'Quarterly (Jan, Apr, Jul, Oct 1st)' },
    { key: 'custom', expr: '', label: 'Custom expression' },
] as const

const COMMON_TIMEZONES = [
    'UTC',
    'America/New_York',
    'America/Chicago',
    'America/Denver',
    'America/Los_Angeles',
    'Europe/London',
    'Europe/Paris',
    'Europe/Berlin',
    'Asia/Tokyo',
    'Asia/Shanghai',
    'Asia/Bangkok',
    'Asia/Ho_Chi_Minh',
    'Asia/Singapore',
    'Australia/Sydney',
] as const

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function describeCron(expr: string): string {
    const parts = String(expr).trim().split(/\s+/)
    if (parts.length < 5) return expr

    const [min, hour, dom, mon, dow] = parts

    // Check against known presets first
    const preset = CRON_PRESETS.find((p) => p.expr === expr)
    if (preset && preset.key !== 'custom') return preset.label

    // Build human-readable description
    const hourNum = parseInt(hour, 10)
    const minNum = parseInt(min, 10)
    const timeStr = !isNaN(hourNum) && !isNaN(minNum)
        ? `${hourNum % 12 || 12}:${String(minNum).padStart(2, '0')} ${hourNum >= 12 ? 'PM' : 'AM'}`
        : null

    // Every N hours
    if (min === '0' && hour.startsWith('*/')) {
        const n = parseInt(hour.slice(2), 10)
        return `Every ${n} hour${n > 1 ? 's' : ''}`
    }

    // Every N minutes
    if (min.startsWith('*/') && hour === '*') {
        const n = parseInt(min.slice(2), 10)
        return `Every ${n} min`
    }

    // Weekdays
    const dowMap: Record<string, string> = {
        '1': 'Mon', '2': 'Tue', '3': 'Wed', '4': 'Thu', '5': 'Fri', '6': 'Sat', '0': 'Sun', '7': 'Sun',
        '1-5': 'Weekdays', '0-6': 'Every day', '1,3,5': 'Mon/Wed/Fri', '2,4': 'Tue/Thu',
        '6,0': 'Weekends', '0,6': 'Weekends',
    }

    const dowLabel = dowMap[dow] || (dow === '*' ? null : dow)

    if (timeStr && dom === '*' && mon === '*') {
        if (dowLabel) return `${dowLabel} at ${timeStr}`
        return `Daily at ${timeStr}`
    }

    if (timeStr && dom !== '*' && mon === '*' && dow === '*') {
        const d = parseInt(dom, 10)
        const suffix = d === 1 ? 'st' : d === 2 ? 'nd' : d === 3 ? 'rd' : 'th'
        return `${d}${suffix} of month at ${timeStr}`
    }

    return expr
}

function formatSchedule(job: CronJob): string {
    const s = job.schedule
    switch (job.schedule_type) {
        case 'every': {
            const secs = Number(s.every_secs) || 0
            if (secs >= 86400) {
                const d = Math.round(secs / 86400)
                return `Every ${d} day${d > 1 ? 's' : ''}`
            }
            if (secs >= 3600) {
                const h = Math.round(secs / 3600)
                return `Every ${h} hour${h > 1 ? 's' : ''}`
            }
            if (secs >= 60) {
                const m = Math.round(secs / 60)
                return `Every ${m} min${m > 1 ? 's' : ''}`
            }
            return `Every ${secs}s`
        }
        case 'cron': {
            const desc = describeCron(String(s.expr || ''))
            const tz = s.tz ? ` (${s.tz})` : ''
            return `${desc}${tz}`
        }
        case 'at':
            return new Date(s.at as string).toLocaleString()
        default:
            return job.schedule_type
    }
}

function formatDuration(ms: number | null): string {
    if (ms === null) return '-'
    if (ms < 1000) return `${ms}ms`
    return `${(ms / 1000).toFixed(1)}s`
}

function formatTimeAgo(dateStr: string): string {
    const diff = Date.now() - new Date(dateStr).getTime()
    const mins = Math.floor(diff / 60000)
    if (mins < 1) return 'just now'
    if (mins < 60) return `${mins}m ago`
    const hours = Math.floor(mins / 60)
    if (hours < 24) return `${hours}h ago`
    const days = Math.floor(hours / 24)
    return `${days}d ago`
}

// ---------------------------------------------------------------------------
// Status Badge
// ---------------------------------------------------------------------------

const StatusBadge = ({ status }: { status: string }) => {
    const color = {
        ok: 'bg-green-5/15 text-green-5',
        running: 'bg-sky-blue/15 text-sky-blue',
        error: 'bg-red/15 text-red',
        timeout: 'bg-amber-500/15 text-amber-600 dark:text-amber-400',
    }[status] || 'bg-charcoal/5 text-charcoal/40 dark:bg-white/10 dark:text-white/40'

    return (
        <span className={clsx('text-[10px] font-medium px-1.5 py-0.5 rounded-full', color)}>
            {status}
        </span>
    )
}

// ---------------------------------------------------------------------------
// Channel + Bot Picker (shared between Post Message & AI Task)
// ---------------------------------------------------------------------------

const ChannelBotPicker = ({
    channelInstances,
    loadingInstances,
    selectedInstanceId,
    onSelect,
    label,
}: {
    channelInstances: UserChannelInstance[]
    loadingInstances: boolean
    selectedInstanceId: string
    onSelect: (instanceNameId: string, channelType: string, botName: string) => void
    label: string
}) => {
    const { t } = useTranslation()

    // Group instances by channel type
    const grouped: Record<string, UserChannelInstance[]> = {}
    for (const inst of channelInstances) {
        if (!grouped[inst.channel_type]) grouped[inst.channel_type] = []
        grouped[inst.channel_type].push(inst)
    }

    const channelDef = (type: string) => CHANNEL_DEFS.find((c) => c.name === type)

    return (
        <div className="space-y-1">
            <label className="text-[10px] text-charcoal/50 dark:text-white/40">
                {label}
            </label>
            {loadingInstances ? (
                <div className="h-9 flex items-center text-xs text-charcoal/40 dark:text-white/30">
                    {t('common.loading', 'Loading...')}
                </div>
            ) : channelInstances.length === 0 ? (
                <div className="h-9 flex items-center text-xs text-charcoal/40 dark:text-white/30">
                    {t('iiClaw.cronJobs.noChannelsConfigured')}
                </div>
            ) : (
                <Select
                    value={selectedInstanceId}
                    onValueChange={(val) => {
                        const inst = channelInstances.find((i) => i.instance_name_id === val)
                        if (inst) onSelect(inst.instance_name_id, inst.channel_type, inst.instance_name || inst.instance_name_id)
                    }}
                >
                    <SelectTrigger className="!h-9 !py-0 !px-3 text-sm !rounded-lg">
                        <SelectValue placeholder={t('iiClaw.cronJobs.selectChannelBot')} />
                    </SelectTrigger>
                    <SelectContent>
                        {Object.entries(grouped).map(([type, instances]) => (
                            <SelectGroup key={type}>
                                <SelectLabel className="flex items-center gap-2">
                                    <img
                                        src={channelDef(type)?.icon}
                                        alt={type}
                                        className="w-3.5 h-3.5 rounded object-contain"
                                    />
                                    {t(`iiClaw.channels.${type}.displayName`, type)}
                                </SelectLabel>
                                {instances.map((inst) => (
                                    <SelectItem key={inst.instance_name_id} value={inst.instance_name_id}>
                                        <div className="flex items-center gap-2">
                                            <span
                                                className={clsx('w-1.5 h-1.5 rounded-full shrink-0', {
                                                    'bg-green-5': inst.status === 'running' || inst.status === 'active',
                                                    'bg-yellow': inst.status === 'configured',
                                                    'bg-charcoal/20 dark:bg-white/30': !inst.status || inst.status === 'stopped',
                                                })}
                                            />
                                            {inst.instance_name || inst.instance_name_id}
                                        </div>
                                    </SelectItem>
                                ))}
                            </SelectGroup>
                        ))}
                    </SelectContent>
                </Select>
            )}
        </div>
    )
}

// ---------------------------------------------------------------------------
// History Dialog
// ---------------------------------------------------------------------------

const HistoryDialog = ({
    job,
    open,
    onOpenChange,
}: {
    job: CronJob | null
    open: boolean
    onOpenChange: (open: boolean) => void
}) => {
    const { t } = useTranslation()
    const { user } = useAuth()
    const [runs, setRuns] = useState<CronJobRun[]>([])
    const [loading, setLoading] = useState(false)

    useEffect(() => {
        if (open && job && user) {
            setLoading(true)
            iiClawService
                .getCronJobHistory(user.id, job.id, 20)
                .then(setRuns)
                .catch(() => setRuns([]))
                .finally(() => setLoading(false))
        }
    }, [open, job, user])

    if (!job) return null

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="max-w-[calc(100%-1rem)] sm:max-w-xl">
                <DialogHeader>
                    <DialogTitle className="dark:text-white">
                        {t('iiClaw.cronJobs.history')} — {job.name}
                    </DialogTitle>
                    <DialogDescription>
                        {t('iiClaw.cronJobs.historyDesc')}
                    </DialogDescription>
                </DialogHeader>

                <div className="max-h-[360px] overflow-y-auto mt-2">
                    {loading ? (
                        <div className="flex items-center justify-center h-24 text-xs text-charcoal/40 dark:text-white/30">
                            {t('common.loading', 'Loading...')}
                        </div>
                    ) : runs.length === 0 ? (
                        <div className="flex items-center justify-center h-24 text-xs text-charcoal/40 dark:text-white/30">
                            {t('iiClaw.cronJobs.noHistory')}
                        </div>
                    ) : (
                        <div className="divide-y divide-charcoal/[0.06] dark:divide-white/[0.08]">
                            {runs.map((run) => (
                                <div key={run.id} className="flex items-center gap-3 px-2 py-2.5">
                                    <StatusBadge status={run.status} />
                                    <div className="min-w-0 flex-1">
                                        <p className="text-xs text-black dark:text-white">
                                            {new Date(run.started_at).toLocaleString()}
                                        </p>
                                        {run.error_message && (
                                            <p className="text-[10px] text-red truncate mt-0.5">
                                                {run.error_message}
                                            </p>
                                        )}
                                    </div>
                                    <span className="text-[10px] text-charcoal/40 dark:text-white/30 shrink-0">
                                        {formatDuration(run.duration_ms)}
                                    </span>
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            </DialogContent>
        </Dialog>
    )
}

// ---------------------------------------------------------------------------
// Create Job Dialog
// ---------------------------------------------------------------------------

const CreateJobDialog = ({
    open,
    onOpenChange,
    onCreated,
    editJob,
}: {
    open: boolean
    onOpenChange: (open: boolean) => void
    onCreated: () => void
    editJob?: CronJob | null
}) => {
    const { t } = useTranslation()
    const { user } = useAuth()
    const isEdit = !!editJob

    // Form state
    const [name, setName] = useState('')
    const [label, setLabel] = useState('')
    const [oneShot, setOneShot] = useState(false)
    const [scheduleType, setScheduleType] = useState<ScheduleType>('every')
    const [actionType, setActionType] = useState<ActionType>('channel_message')

    // Schedule fields — every
    const [everyValue, setEveryValue] = useState('5')
    const [everyUnit, setEveryUnit] = useState<EveryUnit>('minutes')

    // Schedule fields — cron
    const [cronPreset, setCronPreset] = useState('weekdays_9am')
    const [cronCustomExpr, setCronCustomExpr] = useState('')
    const [cronTz, setCronTz] = useState('UTC')

    // Schedule fields — at
    const [atTime, setAtTime] = useState('')

    // Channel instances (loaded from API)
    const [channelInstances, setChannelInstances] = useState<UserChannelInstance[]>([])
    const [loadingInstances, setLoadingInstances] = useState(false)

    // Custom agents (loaded from API)
    const [customAgents, setCustomAgents] = useState<UserAgent[]>([])

    // Action fields — channel_message (Post Message)
    const [selectedInstanceId, setSelectedInstanceId] = useState('')
    const [selectedChannelType, setSelectedChannelType] = useState('')
    const [recipient, setRecipient] = useState('')
    const [message, setMessage] = useState('')

    // Action fields — assistant_task (AI Task)
    const [agentId, setAgentId] = useState('')
    const [context, setContext] = useState('')
    const [deliveryInstanceId, setDeliveryInstanceId] = useState('')
    const [deliveryChannelType, setDeliveryChannelType] = useState('')
    const [deliveryRecipient, setDeliveryRecipient] = useState('')

    const [submitting, setSubmitting] = useState(false)
    const [error, setError] = useState<string | null>(null)

    // Fetch user's channel instances and custom agents when dialog opens
    useEffect(() => {
        if (open && user) {
            setLoadingInstances(true)
            iiClawService
                .listUserChannels(user.id)
                .then(setChannelInstances)
                .catch(() => setChannelInstances([]))
                .finally(() => setLoadingInstances(false))
            iiClawService
                .listUserAgents()
                .then(setCustomAgents)
                .catch(() => setCustomAgents([]))
        }
    }, [open, user])

    const resetForm = () => {
        setName('')
        setLabel('')
        setOneShot(false)
        setScheduleType('every')
        setActionType('channel_message')
        setEveryValue('5')
        setEveryUnit('minutes')
        setCronPreset('weekdays_9am')
        setCronCustomExpr('')
        setCronTz('UTC')
        setAtTime('')
        setSelectedInstanceId('')
        setSelectedChannelType('')
        setRecipient('')
        setMessage('')
        setAgentId('')
        setContext('')
        setDeliveryInstanceId('')
        setDeliveryChannelType('')
        setDeliveryRecipient('')
        setError(null)
    }

    const populateFromJob = (job: CronJob) => {
        setName(job.name)
        setLabel(job.label || '')
        setOneShot(job.one_shot)

        // Schedule
        const st = job.schedule_type as ScheduleType
        setScheduleType(st)
        if (st === 'every') {
            const secs = Number(job.schedule.every_secs) || 300
            if (secs >= 86400 && secs % 86400 === 0) {
                setEveryValue(String(secs / 86400))
                setEveryUnit('days')
            } else if (secs >= 3600 && secs % 3600 === 0) {
                setEveryValue(String(secs / 3600))
                setEveryUnit('hours')
            } else {
                setEveryValue(String(Math.round(secs / 60)))
                setEveryUnit('minutes')
            }
        } else if (st === 'cron') {
            const expr = String(job.schedule.expr || '')
            const matchedPreset = CRON_PRESETS.find((p) => p.expr === expr)
            if (matchedPreset && matchedPreset.key !== 'custom') {
                setCronPreset(matchedPreset.key)
            } else {
                setCronPreset('custom')
                setCronCustomExpr(expr)
            }
            setCronTz(String(job.schedule.tz || 'UTC'))
        } else if (st === 'at') {
            const d = new Date(job.schedule.at as string)
            // Format for datetime-local input: YYYY-MM-DDTHH:mm
            const pad = (n: number) => String(n).padStart(2, '0')
            setAtTime(`${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`)
        }

        // Action
        const at = job.action_type as ActionType
        setActionType(at)
        if (at === 'channel_message') {
            setSelectedInstanceId(String(job.action.channel || ''))
            setRecipient(String(job.action.recipient || ''))
            setMessage(String(job.action.message || ''))
            // Try to resolve channel type from instance
            setSelectedChannelType(job.channel_type?.platform as string || '')
        } else if (at === 'assistant_task') {
            setAgentId(agentIdToSelectValue(String(job.action.agent_id || '')))
            setContext(String(job.action.context || ''))
            const delivery = job.action.delivery as Record<string, unknown> | undefined
            if (delivery) {
                setDeliveryInstanceId(String(delivery.channel || ''))
                setDeliveryRecipient(String(delivery.recipient || ''))
                setDeliveryChannelType(job.channel_type?.platform as string || '')
            }
        }

        setError(null)
    }

    useEffect(() => {
        if (open) {
            if (editJob) {
                populateFromJob(editJob)
            } else {
                resetForm()
            }
        }
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [open, editJob])

    const buildSchedule = (): Record<string, unknown> => {
        switch (scheduleType) {
            case 'every': {
                const num = parseInt(everyValue, 10) || 1
                const multiplier = { minutes: 60, hours: 3600, days: 86400 }[everyUnit]
                return { type: 'every', every_secs: num * multiplier }
            }
            case 'cron': {
                const expr = cronPreset === 'custom' ? cronCustomExpr : CRON_PRESETS.find((p) => p.key === cronPreset)?.expr || ''
                const s: Record<string, unknown> = { type: 'cron', expr }
                if (cronTz && cronTz !== 'UTC') s.tz = cronTz
                return s
            }
            case 'at':
                return { type: 'at', at: new Date(atTime).toISOString() }
        }
    }

    const buildAction = (): Record<string, unknown> => {
        switch (actionType) {
            case 'channel_message':
                return {
                    type: 'channel_message',
                    channel: selectedInstanceId,
                    recipient,
                    message,
                }
            case 'assistant_task':
                return {
                    type: 'assistant_task',
                    agent_id: selectValueToAgentId(agentId),
                    context,
                    delivery: {
                        type: 'channel_message',
                        channel: deliveryInstanceId,
                        recipient: deliveryRecipient,
                    },
                }
        }
    }

    const handleSubmit = async () => {
        if (!name.trim()) {
            setError(t('iiClaw.cronJobs.nameRequired'))
            return
        }

        setSubmitting(true)
        setError(null)
        try {
            const relevantChannelType = actionType === 'channel_message' ? selectedChannelType : deliveryChannelType

            if (isEdit && editJob) {
                const req: CronJobUpdateRequest = {
                    name: name.trim(),
                    enabled: editJob.enabled,
                    schedule: buildSchedule(),
                    action: buildAction(),
                    one_shot: oneShot,
                }
                if (label.trim()) req.label = label.trim()
                if (relevantChannelType) req.channel_type = { platform: relevantChannelType }
                await iiClawService.updateCronJob(user!.id, editJob.id, req)
            } else {
                const req: CronJobCreateRequest = {
                    name: name.trim(),
                    schedule: buildSchedule(),
                    action: buildAction(),
                    one_shot: oneShot,
                }
                if (label.trim()) req.label = label.trim()
                if (relevantChannelType) req.channel_type = { platform: relevantChannelType }
                await iiClawService.createCronJob(user!.id, req)
            }

            onCreated()
            onOpenChange(false)
        } catch (e: unknown) {
            setError(e instanceof Error ? e.message : 'Failed to create cron job')
        } finally {
            setSubmitting(false)
        }
    }

    const fieldClass = 'h-9 text-sm'
    const labelClass = 'text-[10px] text-charcoal/50 dark:text-white/40'
    const tabBtnClass = (active: boolean) => clsx(
        'px-3 py-1.5 rounded-lg text-xs font-medium transition-colors cursor-pointer',
        active
            ? 'bg-sky-blue/30 text-firefly dark:bg-sky-blue/15 dark:text-sky-blue'
            : 'text-charcoal/40 dark:text-white/40 hover:bg-charcoal/5 dark:hover:bg-white/5'
    )

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="max-w-[calc(100%-1rem)] sm:max-w-lg">
                <DialogHeader>
                    <DialogTitle className="dark:text-white">
                        {isEdit ? t('iiClaw.cronJobs.editJob') : t('iiClaw.cronJobs.createJob')}
                    </DialogTitle>
                    <DialogDescription>
                        {isEdit ? t('iiClaw.cronJobs.editJobDesc') : t('iiClaw.cronJobs.createJobDesc')}
                    </DialogDescription>
                </DialogHeader>

                <div className="space-y-4 mt-2 max-h-[60vh] overflow-y-auto pr-1">
                    {/* Name & Label */}
                    <div className="grid grid-cols-2 gap-3">
                        <div className="space-y-1">
                            <label className="text-xs font-medium text-black dark:text-white">
                                {t('iiClaw.cronJobs.jobName')} <span className="text-red">*</span>
                            </label>
                            <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. standup-reminder" className={fieldClass} />
                        </div>
                        <div className="space-y-1">
                            <label className="text-xs font-medium text-black dark:text-white">
                                {t('iiClaw.cronJobs.label')}
                            </label>
                            <Input value={label} onChange={(e) => setLabel(e.target.value)} placeholder="e.g. notifications" className={fieldClass} />
                        </div>
                    </div>

                    {/* One-shot */}
                    <div className="flex items-center gap-2">
                        <Switch checked={oneShot} onCheckedChange={setOneShot} />
                        <span className="text-xs text-charcoal/60 dark:text-white/50">
                            {t('iiClaw.cronJobs.oneShot')}
                        </span>
                    </div>

                    {/* ========================= Schedule ========================= */}
                    <div className="space-y-2">
                        <label className="text-xs font-semibold text-black dark:text-white">
                            {t('iiClaw.cronJobs.schedule')}
                        </label>
                        <div className="flex gap-2">
                            {SCHEDULE_TYPES.map((st) => (
                                <button
                                    key={st}
                                    type="button"
                                    onClick={() => setScheduleType(st)}
                                    className={tabBtnClass(scheduleType === st)}
                                >
                                    {t(`iiClaw.cronJobs.scheduleTypes.${st}`)}
                                </button>
                            ))}
                        </div>

                        {/* Every — value + unit */}
                        {scheduleType === 'every' && (
                            <div className="flex gap-2 items-end">
                                <div className="space-y-1 flex-1">
                                    <label className={labelClass}>
                                        {t('iiClaw.cronJobs.everyValue')}
                                    </label>
                                    <Input
                                        type="number"
                                        value={everyValue}
                                        onChange={(e) => setEveryValue(e.target.value)}
                                        placeholder="5"
                                        min="1"
                                        className={fieldClass}
                                    />
                                </div>
                                <div className="space-y-1 w-32">
                                    <label className={labelClass}>
                                        {t('iiClaw.cronJobs.everyUnit')}
                                    </label>
                                    <Select value={everyUnit} onValueChange={(v) => setEveryUnit(v as EveryUnit)}>
                                        <SelectTrigger className="!h-9 !py-0 !px-3 text-sm !rounded-lg">
                                            <SelectValue />
                                        </SelectTrigger>
                                        <SelectContent>
                                            <SelectItem value="minutes">{t('iiClaw.cronJobs.units.minutes')}</SelectItem>
                                            <SelectItem value="hours">{t('iiClaw.cronJobs.units.hours')}</SelectItem>
                                            <SelectItem value="days">{t('iiClaw.cronJobs.units.days')}</SelectItem>
                                        </SelectContent>
                                    </Select>
                                </div>
                            </div>
                        )}

                        {/* Cron — preset picker + timezone */}
                        {scheduleType === 'cron' && (
                            <div className="space-y-2">
                                <div className="space-y-1">
                                    <label className={labelClass}>
                                        {t('iiClaw.cronJobs.cronPreset')}
                                    </label>
                                    <Select value={cronPreset} onValueChange={setCronPreset}>
                                        <SelectTrigger className="!h-9 !py-0 !px-3 text-sm !rounded-lg">
                                            <SelectValue />
                                        </SelectTrigger>
                                        <SelectContent>
                                            {CRON_PRESETS.map((p) => (
                                                <SelectItem key={p.key} value={p.key}>
                                                    <div className="flex items-center gap-2">
                                                        <span>{t(`iiClaw.cronJobs.cronPresets.${p.key}`, p.label)}</span>
                                                        {p.expr && (
                                                            <span className="text-[10px] text-charcoal/30 dark:text-white/20 font-mono">
                                                                {p.expr}
                                                            </span>
                                                        )}
                                                    </div>
                                                </SelectItem>
                                            ))}
                                        </SelectContent>
                                    </Select>
                                </div>

                                {cronPreset === 'custom' && (
                                    <div className="space-y-1">
                                        <label className={labelClass}>
                                            {t('iiClaw.cronJobs.cronExpr')}
                                        </label>
                                        <Input
                                            value={cronCustomExpr}
                                            onChange={(e) => setCronCustomExpr(e.target.value)}
                                            placeholder="0 9 * * 1-5"
                                            className={clsx(fieldClass, 'font-mono')}
                                        />
                                        <p className="text-[9px] text-charcoal/30 dark:text-white/20">
                                            {t('iiClaw.cronJobs.cronExprHint')}
                                        </p>
                                    </div>
                                )}

                                <div className="space-y-1">
                                    <label className={labelClass}>
                                        {t('iiClaw.cronJobs.timezone')}
                                    </label>
                                    <Select value={cronTz} onValueChange={setCronTz}>
                                        <SelectTrigger className="!h-9 !py-0 !px-3 text-sm !rounded-lg">
                                            <SelectValue />
                                        </SelectTrigger>
                                        <SelectContent>
                                            {COMMON_TIMEZONES.map((tz) => (
                                                <SelectItem key={tz} value={tz}>{tz}</SelectItem>
                                            ))}
                                        </SelectContent>
                                    </Select>
                                </div>
                            </div>
                        )}

                        {/* At — datetime picker */}
                        {scheduleType === 'at' && (
                            <div className="space-y-1">
                                <label className={labelClass}>
                                    {t('iiClaw.cronJobs.runAt')}
                                </label>
                                <Input type="datetime-local" value={atTime} onChange={(e) => setAtTime(e.target.value)} className={fieldClass} />
                            </div>
                        )}
                    </div>

                    {/* ========================= Action ========================= */}
                    <div className="space-y-2">
                        <label className="text-xs font-semibold text-black dark:text-white">
                            {t('iiClaw.cronJobs.action')}
                        </label>
                        <div className="flex flex-wrap gap-2">
                            {ACTION_TYPES.map((at) => (
                                <button
                                    key={at}
                                    type="button"
                                    onClick={() => setActionType(at)}
                                    className={tabBtnClass(actionType === at)}
                                >
                                    {t(`iiClaw.cronJobs.actionTypes.${at}`)}
                                </button>
                            ))}
                        </div>

                        {/* Post Message */}
                        {actionType === 'channel_message' && (
                            <div className="space-y-2">
                                <ChannelBotPicker
                                    channelInstances={channelInstances}
                                    loadingInstances={loadingInstances}
                                    selectedInstanceId={selectedInstanceId}
                                    onSelect={(id, type) => {
                                        setSelectedInstanceId(id)
                                        setSelectedChannelType(type)
                                    }}
                                    label={t('iiClaw.cronJobs.actionFields.channelBot')}
                                />
                                <div className="space-y-1">
                                    <label className={labelClass}>
                                        {t('iiClaw.cronJobs.actionFields.recipient')}
                                    </label>
                                    <Input value={recipient} onChange={(e) => setRecipient(e.target.value)} placeholder="Channel ID" className={fieldClass} />
                                </div>
                                <div className="space-y-1">
                                    <label className={labelClass}>
                                        {t('iiClaw.cronJobs.actionFields.message')}
                                    </label>
                                    <Textarea value={message} onChange={(e) => setMessage(e.target.value)} placeholder="Hey team! Time for standup." className="text-sm min-h-[36px] !rounded-lg !px-3 !py-2" />
                                </div>
                            </div>
                        )}

                        {/* AI Task */}
                        {actionType === 'assistant_task' && (
                            <div className="space-y-2">
                                <div className="space-y-1">
                                    <label className={labelClass}>
                                        {t('iiClaw.cronJobs.actionFields.agentId')}
                                    </label>
                                    <Select value={agentId || '_default'} onValueChange={(v) => setAgentId(v === '_default' ? '' : v)}>
                                        <SelectTrigger className={fieldClass}>
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
                                <div className="space-y-1">
                                    <label className={labelClass}>
                                        {t('iiClaw.cronJobs.actionFields.context')}
                                    </label>
                                    <Textarea value={context} onChange={(e) => setContext(e.target.value)} placeholder="Summarize today's customer support tickets. Include counts by category and highlight any critical issues." className="text-sm min-h-[36px] !rounded-lg !px-3 !py-2" />
                                </div>

                                <div className="pt-2 border-t border-charcoal/[0.06] dark:border-white/[0.08]">
                                    <p className="text-[10px] font-semibold text-charcoal/50 dark:text-white/40 mb-2">
                                        {t('iiClaw.cronJobs.deliverTo')}
                                    </p>
                                    <ChannelBotPicker
                                        channelInstances={channelInstances}
                                        loadingInstances={loadingInstances}
                                        selectedInstanceId={deliveryInstanceId}
                                        onSelect={(id, type) => {
                                            setDeliveryInstanceId(id)
                                            setDeliveryChannelType(type)
                                        }}
                                        label={t('iiClaw.cronJobs.actionFields.channelBot')}
                                    />
                                    <div className="space-y-1 mt-2">
                                        <label className={labelClass}>
                                            {t('iiClaw.cronJobs.actionFields.recipient')}
                                        </label>
                                        <Input value={deliveryRecipient} onChange={(e) => setDeliveryRecipient(e.target.value)} placeholder="Channel ID" className={fieldClass} />
                                    </div>
                                </div>
                            </div>
                        )}
                    </div>

                    {/* Error */}
                    {error && (
                        <p className="text-xs text-red bg-red/10 rounded-lg px-3 py-2">
                            {error}
                        </p>
                    )}
                </div>

                {/* Actions */}
                <div className="flex gap-2 justify-end pt-3 border-t border-charcoal/[0.06] dark:border-white/[0.08]">
                    <Button
                        variant="outline"
                        size="sm"
                        onClick={() => onOpenChange(false)}
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
                            ? (isEdit ? t('iiClaw.cronJobs.saving') : t('iiClaw.cronJobs.creating'))
                            : (isEdit ? t('iiClaw.cronJobs.save') : t('iiClaw.cronJobs.create'))}
                    </Button>
                </div>
            </DialogContent>
        </Dialog>
    )
}

// ---------------------------------------------------------------------------
// Job Row
// ---------------------------------------------------------------------------

const JobRow = ({
    job,
    onToggle,
    onDelete,
    onHistory,
    onEdit,
    onTest,
}: {
    job: CronJob
    onToggle: (job: CronJob) => void
    onDelete: (job: CronJob) => void
    onHistory: (job: CronJob) => void
    onEdit: (job: CronJob) => void
    onTest: (job: CronJob) => void
}) => {
    const { t } = useTranslation()

    const iconBtnBase = 'rounded-lg flex items-center justify-center transition-colors cursor-pointer'

    return (
        <div
            className={clsx(
                'px-3 sm:px-5 py-3 sm:py-3.5 transition-colors',
                'hover:bg-charcoal/[0.02] dark:hover:bg-white/[0.03]'
            )}
        >
            {/* Row 1: switch + name + badge + (desktop: time + buttons) */}
            <div className="flex items-center gap-3 sm:gap-4">
                <Switch
                    checked={job.enabled}
                    onCheckedChange={() => onToggle(job)}
                />

                <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 sm:gap-2.5">
                        <p className={clsx(
                            'text-sm sm:text-base font-medium truncate',
                            job.enabled ? 'text-black dark:text-white' : 'text-charcoal/40 dark:text-white/30'
                        )}>
                            {job.name}
                        </p>
                        {job.label && (
                            <span className="text-[10px] sm:text-xs px-2 py-0.5 rounded-full bg-sky-blue/10 text-firefly dark:bg-sky-blue/10 dark:text-sky-blue hidden sm:inline">
                                {job.label}
                            </span>
                        )}
                        {job.one_shot && (
                            <span className="text-[10px] sm:text-xs px-2 py-0.5 rounded-full bg-amber-500/10 dark:bg-amber-500/15 text-amber-600 dark:text-amber-400 hidden sm:inline">
                                {t('iiClaw.cronJobs.oneShotBadge')}
                            </span>
                        )}
                    </div>
                    <p className="text-[11px] sm:text-xs text-charcoal/40 dark:text-white/30 mt-0.5">
                        {formatSchedule(job)}
                    </p>
                </div>

                {/* Action type badge */}
                <span className={clsx(
                    'text-[10px] sm:text-xs px-2 sm:px-2.5 py-0.5 sm:py-1 rounded-full shrink-0 font-medium',
                    job.action_type === 'channel_message'
                        ? 'bg-sky-blue/15 text-firefly dark:bg-sky-blue/10 dark:text-sky-blue'
                        : 'bg-sky-blue-3/20 text-firefly dark:bg-sky-blue-4/10 dark:text-sky-blue-4'
                )}>
                    {job.action_type === 'channel_message' ? t('iiClaw.cronJobs.actionTypes.channel_message') : t(`iiClaw.cronJobs.actionTypes.${job.action_type}`, job.action_type)}
                </span>

                {/* Time ago — desktop */}
                <span className="text-xs text-charcoal/30 dark:text-white/20 shrink-0 hidden md:block">
                    {formatTimeAgo(job.created_at)}
                </span>

                {/* Action buttons — desktop */}
                <div className="hidden sm:flex items-center gap-1 shrink-0">
                    <button type="button" onClick={() => onEdit(job)} className={clsx(iconBtnBase, 'w-8 h-8 text-firefly/40 dark:text-sky-blue/40 hover:text-firefly dark:hover:text-sky-blue hover:bg-sky-blue/10 dark:hover:bg-sky-blue/10')} title={t('iiClaw.cronJobs.edit')}>
                        <svg width="14" height="14" viewBox="0 0 12 12" fill="none" xmlns="http://www.w3.org/2000/svg">
                            <path d="M8.5 1.5L10.5 3.5M1.5 10.5L2 8.5L8.5 2L10 3.5L3.5 10L1.5 10.5Z" stroke="currentColor" strokeWidth="1" strokeLinecap="round" strokeLinejoin="round"/>
                        </svg>
                    </button>
                    <button type="button" onClick={() => onTest(job)} className={clsx(iconBtnBase, 'w-8 h-8 text-firefly/40 dark:text-sky-blue/40 hover:text-firefly dark:hover:text-sky-blue hover:bg-sky-blue/15 dark:hover:bg-sky-blue/10')} title={t('iiClaw.cronJobs.testJob')}>
                        <svg width="14" height="14" viewBox="0 0 12 12" fill="none" xmlns="http://www.w3.org/2000/svg">
                            <path d="M4 2.5V9.5L10 6L4 2.5Z" stroke="currentColor" strokeWidth="1" strokeLinecap="round" strokeLinejoin="round"/>
                        </svg>
                    </button>
                    <button type="button" onClick={() => onHistory(job)} className={clsx(iconBtnBase, 'w-8 h-8 text-firefly/40 dark:text-sky-blue/40 hover:text-firefly dark:hover:text-sky-blue hover:bg-sky-blue/10 dark:hover:bg-sky-blue/10')} title={t('iiClaw.cronJobs.history')}>
                        <svg width="14" height="14" viewBox="0 0 14 14" fill="none" xmlns="http://www.w3.org/2000/svg">
                            <path d="M7 3.5V7L9.5 8.5M12.5 7C12.5 10.0376 10.0376 12.5 7 12.5C3.96243 12.5 1.5 10.0376 1.5 7C1.5 3.96243 3.96243 1.5 7 1.5C10.0376 1.5 12.5 3.96243 12.5 7Z" stroke="currentColor" strokeWidth="1" strokeLinecap="round" strokeLinejoin="round"/>
                        </svg>
                    </button>
                    <button type="button" onClick={() => onDelete(job)} className={clsx(iconBtnBase, 'w-8 h-8 text-charcoal/20 dark:text-white/20 hover:text-red hover:bg-red/10 dark:hover:bg-red/10')} title={t('iiClaw.cronJobs.delete')}>
                        <svg width="14" height="14" viewBox="0 0 12 12" fill="none" xmlns="http://www.w3.org/2000/svg">
                            <path d="M2.5 3.5H9.5M4.5 3.5V2.5C4.5 2.22386 4.72386 2 5 2H7C7.27614 2 7.5 2.22386 7.5 2.5V3.5M5 5.5V8.5M7 5.5V8.5M3.5 3.5L3.85 9.17C3.87 9.63 4.25 10 4.71 10H7.29C7.75 10 8.13 9.63 8.15 9.17L8.5 3.5" stroke="currentColor" strokeWidth="1" strokeLinecap="round" strokeLinejoin="round"/>
                        </svg>
                    </button>
                </div>
            </div>

            {/* Row 2: mobile only — badges + time + action buttons */}
            <div className="flex sm:hidden items-center gap-2 mt-2 ml-[44px]">
                {job.label && (
                    <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-sky-blue/10 text-firefly dark:bg-sky-blue/10 dark:text-sky-blue">
                        {job.label}
                    </span>
                )}
                {job.one_shot && (
                    <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-amber-500/10 dark:bg-amber-500/15 text-amber-600 dark:text-amber-400">
                        {t('iiClaw.cronJobs.oneShotBadge')}
                    </span>
                )}
                <span className="text-[10px] text-charcoal/30 dark:text-white/20">
                    {formatTimeAgo(job.created_at)}
                </span>
                <div className="flex-1" />
                <div className="flex items-center gap-1">
                    <button type="button" onClick={() => onEdit(job)} className={clsx(iconBtnBase, 'w-7 h-7 text-firefly/40 dark:text-sky-blue/40 hover:text-firefly dark:hover:text-sky-blue hover:bg-sky-blue/10 dark:hover:bg-sky-blue/10')} title={t('iiClaw.cronJobs.edit')}>
                        <svg width="13" height="13" viewBox="0 0 12 12" fill="none" xmlns="http://www.w3.org/2000/svg">
                            <path d="M8.5 1.5L10.5 3.5M1.5 10.5L2 8.5L8.5 2L10 3.5L3.5 10L1.5 10.5Z" stroke="currentColor" strokeWidth="1" strokeLinecap="round" strokeLinejoin="round"/>
                        </svg>
                    </button>
                    <button type="button" onClick={() => onTest(job)} className={clsx(iconBtnBase, 'w-7 h-7 text-firefly/40 dark:text-sky-blue/40 hover:text-firefly dark:hover:text-sky-blue hover:bg-sky-blue/15 dark:hover:bg-sky-blue/10')} title={t('iiClaw.cronJobs.testJob')}>
                        <svg width="13" height="13" viewBox="0 0 12 12" fill="none" xmlns="http://www.w3.org/2000/svg">
                            <path d="M4 2.5V9.5L10 6L4 2.5Z" stroke="currentColor" strokeWidth="1" strokeLinecap="round" strokeLinejoin="round"/>
                        </svg>
                    </button>
                    <button type="button" onClick={() => onHistory(job)} className={clsx(iconBtnBase, 'w-7 h-7 text-firefly/40 dark:text-sky-blue/40 hover:text-firefly dark:hover:text-sky-blue hover:bg-sky-blue/10 dark:hover:bg-sky-blue/10')} title={t('iiClaw.cronJobs.history')}>
                        <svg width="13" height="13" viewBox="0 0 14 14" fill="none" xmlns="http://www.w3.org/2000/svg">
                            <path d="M7 3.5V7L9.5 8.5M12.5 7C12.5 10.0376 10.0376 12.5 7 12.5C3.96243 12.5 1.5 10.0376 1.5 7C1.5 3.96243 3.96243 1.5 7 1.5C10.0376 1.5 12.5 3.96243 12.5 7Z" stroke="currentColor" strokeWidth="1" strokeLinecap="round" strokeLinejoin="round"/>
                        </svg>
                    </button>
                    <button type="button" onClick={() => onDelete(job)} className={clsx(iconBtnBase, 'w-7 h-7 text-charcoal/20 dark:text-white/20 hover:text-red hover:bg-red/10 dark:hover:bg-red/10')} title={t('iiClaw.cronJobs.delete')}>
                        <svg width="13" height="13" viewBox="0 0 12 12" fill="none" xmlns="http://www.w3.org/2000/svg">
                            <path d="M2.5 3.5H9.5M4.5 3.5V2.5C4.5 2.22386 4.72386 2 5 2H7C7.27614 2 7.5 2.22386 7.5 2.5V3.5M5 5.5V8.5M7 5.5V8.5M3.5 3.5L3.85 9.17C3.87 9.63 4.25 10 4.71 10H7.29C7.75 10 8.13 9.63 8.15 9.17L8.5 3.5" stroke="currentColor" strokeWidth="1" strokeLinecap="round" strokeLinejoin="round"/>
                        </svg>
                    </button>
                </div>
            </div>
        </div>
    )
}

// ---------------------------------------------------------------------------
// Filter Chip (dropdown-style)
// ---------------------------------------------------------------------------

const FilterChip = ({
    label,
    value,
    options,
    onChange,
}: {
    label: string
    value: string
    options: { value: string; label: string }[]
    onChange: (value: string) => void
}) => {
    const isActive = value !== 'all'
    return (
        <Select value={value} onValueChange={onChange}>
            <SelectTrigger
                className={clsx(
                    '!h-8 !py-0 !px-2.5 !rounded-lg text-[11px] font-medium !gap-1 !w-auto !min-w-0 border transition-colors',
                    isActive
                        ? 'bg-sky-blue/10 border-sky-blue/30 text-firefly dark:bg-sky-blue/10 dark:border-sky-blue/20 dark:text-sky-blue'
                        : 'bg-white dark:bg-[#A6FFFF0D] border-charcoal/10 dark:border-white/15 text-charcoal/50 dark:text-white/40'
                )}
            >
                <span className="shrink-0">{label}:</span>
                <SelectValue />
            </SelectTrigger>
            <SelectContent className="min-w-[120px]">
                {options.map((opt) => (
                    <SelectItem key={opt.value} value={opt.value} className="text-xs">
                        {opt.label}
                    </SelectItem>
                ))}
            </SelectContent>
        </Select>
    )
}

// ---------------------------------------------------------------------------
// Cron Jobs Panel
// ---------------------------------------------------------------------------

const CronJobsPanel = () => {
    const { t } = useTranslation()
    const { user } = useAuth()

    const [jobs, setJobs] = useState<CronJob[]>([])
    const [loading, setLoading] = useState(true)
    const [createOpen, setCreateOpen] = useState(false)
    const [editTarget, setEditTarget] = useState<CronJob | null>(null)
    const [editOpen, setEditOpen] = useState(false)
    const [historyTarget, setHistoryTarget] = useState<CronJob | null>(null)
    const [historyOpen, setHistoryOpen] = useState(false)
    const [confirmDelete, setConfirmDelete] = useState<CronJob | null>(null)
    const [deleting, setDeleting] = useState(false)
    const [testResult, setTestResult] = useState<{ job: CronJob; result: CronJobTestResponse['result'] } | null>(null)

    // Filters
    const [search, setSearch] = useState('')
    const [filterEnabled, setFilterEnabled] = useState<'all' | 'enabled' | 'disabled'>('all')
    const [filterSchedule, setFilterSchedule] = useState<'all' | 'every' | 'cron' | 'at'>('all')
    const [filterLabel, setFilterLabel] = useState<string>('all')

    const fetchJobs = useCallback(async () => {
        if (!user) return
        setLoading(true)
        try {
            const list = await iiClawService.listCronJobs(user.id)
            setJobs(list)
        } catch {
            setJobs([])
        } finally {
            setLoading(false)
        }
    }, [user])

    useEffect(() => {
        fetchJobs()
    }, [fetchJobs])

    const handleToggle = async (job: CronJob) => {
        if (!user) return
        try {
            await iiClawService.toggleCronJob(user.id, job.id, !job.enabled)
            setJobs((prev) =>
                prev.map((j) => (j.id === job.id ? { ...j, enabled: !j.enabled } : j))
            )
        } catch {
            fetchJobs()
        }
    }

    const handleDelete = async () => {
        if (!user || !confirmDelete) return
        setDeleting(true)
        try {
            await iiClawService.deleteCronJob(user.id, confirmDelete.id)
            setJobs((prev) => prev.filter((j) => j.id !== confirmDelete.id))
        } catch {
            // ignore
        } finally {
            setDeleting(false)
            setConfirmDelete(null)
        }
    }

    const handleHistory = (job: CronJob) => {
        setHistoryTarget(job)
        setHistoryOpen(true)
    }

    const handleEdit = (job: CronJob) => {
        setEditTarget(job)
        setEditOpen(true)
    }

    const handleTest = async (job: CronJob) => {
        if (!user) return
        try {
            const resp = await iiClawService.testCronJob(user.id, job.id)
            setTestResult({ job, result: resp.result })
        } catch (e: unknown) {
            const msg = e instanceof Error ? e.message : 'Test failed'
            setTestResult({ job, result: { status: 'error', id: job.id, error: msg } })
        }
    }

    const enabledCount = jobs.filter((j) => j.enabled).length

    const labels = useMemo(() => {
        const set = new Set<string>()
        jobs.forEach((j) => { if (j.label) set.add(j.label) })
        return Array.from(set).sort()
    }, [jobs])

    const filteredJobs = useMemo(() => {
        let result = jobs
        if (search.trim()) {
            const q = search.toLowerCase()
            result = result.filter((j) => j.name.toLowerCase().includes(q) || (j.label && j.label.toLowerCase().includes(q)))
        }
        if (filterEnabled !== 'all') {
            result = result.filter((j) => filterEnabled === 'enabled' ? j.enabled : !j.enabled)
        }
        if (filterSchedule !== 'all') {
            result = result.filter((j) => j.schedule_type === filterSchedule)
        }
        if (filterLabel !== 'all') {
            result = result.filter((j) => j.label === filterLabel)
        }
        return result
    }, [jobs, search, filterEnabled, filterSchedule, filterLabel])

    const hasActiveFilters = search.trim() !== '' || filterEnabled !== 'all' || filterSchedule !== 'all' || filterLabel !== 'all'

    return (
        <div className="flex-1 p-4 sm:p-6 md:p-8 overflow-y-auto bg-white dark:bg-charcoal">
            <div className="max-w-4xl mx-auto">
                {/* Header */}
                <div className="flex items-start justify-between mb-6 sm:mb-8">
                    <div>
                        <h1 className="text-xl sm:text-2xl font-bold text-black dark:text-white">
                            {t('iiClaw.cronJobs.title')}
                        </h1>
                        <p className="text-xs sm:text-sm text-charcoal/50 dark:text-white/40 mt-1.5 sm:mt-2">
                            {t('iiClaw.cronJobs.subtitle')}{' '}
                            <span className="text-black dark:text-white font-medium">{enabledCount}</span>{' '}
                            {t('iiClaw.cronJobs.active')}.
                        </p>
                    </div>
                    <Button
                        size="sm"
                        onClick={() => setCreateOpen(true)}
                        className="bg-sky-blue text-charcoal hover:bg-sky-blue/80 dark:bg-sky-blue dark:text-charcoal dark:hover:bg-sky-blue/80"
                    >
                        {t('iiClaw.cronJobs.create')}
                    </Button>
                </div>

                {/* Search & Filters */}
                {jobs.length > 0 && (
                    <div className="flex flex-wrap items-center gap-2 mb-3">
                        {/* Search */}
                        <div className="relative flex-1 min-w-[180px]">
                            <svg width="14" height="14" viewBox="0 0 14 14" fill="none" xmlns="http://www.w3.org/2000/svg" className="absolute left-2.5 top-1/2 -translate-y-1/2 text-charcoal/30 dark:text-white/25">
                                <path d="M6.5 11C9.26142 11 11.5 8.76142 11.5 6C11.5 3.23858 9.26142 1 6.5 1C3.73858 1 1.5 3.23858 1.5 6C1.5 8.76142 3.73858 11 6.5 11ZM10.5 10.5L13 13" stroke="currentColor" strokeWidth="1" strokeLinecap="round"/>
                            </svg>
                            <Input
                                value={search}
                                onChange={(e) => setSearch(e.target.value)}
                                placeholder={t('iiClaw.cronJobs.searchPlaceholder')}
                                className="h-8 text-xs pl-8 pr-3"
                            />
                        </div>

                        {/* Enabled filter */}
                        <FilterChip
                            label={t('iiClaw.cronJobs.filters.enabled')}
                            value={filterEnabled}
                            options={[
                                { value: 'all', label: t('iiClaw.cronJobs.filters.all') },
                                { value: 'enabled', label: t('iiClaw.cronJobs.filters.enabledOnly') },
                                { value: 'disabled', label: t('iiClaw.cronJobs.filters.disabledOnly') },
                            ]}
                            onChange={(v) => setFilterEnabled(v as typeof filterEnabled)}
                        />

                        {/* Schedule filter */}
                        <FilterChip
                            label={t('iiClaw.cronJobs.filters.schedule')}
                            value={filterSchedule}
                            options={[
                                { value: 'all', label: t('iiClaw.cronJobs.filters.all') },
                                { value: 'every', label: t('iiClaw.cronJobs.scheduleTypes.every') },
                                { value: 'cron', label: t('iiClaw.cronJobs.scheduleTypes.cron') },
                                { value: 'at', label: t('iiClaw.cronJobs.scheduleTypes.at') },
                            ]}
                            onChange={(v) => setFilterSchedule(v as typeof filterSchedule)}
                        />

                        {/* Label filter */}
                        {labels.length > 0 && (
                            <FilterChip
                                label={t('iiClaw.cronJobs.filters.label')}
                                value={filterLabel}
                                options={[
                                    { value: 'all', label: t('iiClaw.cronJobs.filters.all') },
                                    ...labels.map((l) => ({ value: l, label: l })),
                                ]}
                                onChange={setFilterLabel}
                            />
                        )}

                        {/* Clear filters */}
                        {hasActiveFilters && (
                            <button
                                type="button"
                                onClick={() => { setSearch(''); setFilterEnabled('all'); setFilterSchedule('all'); setFilterLabel('all') }}
                                className="text-[10px] text-charcoal/40 dark:text-white/30 hover:text-charcoal dark:hover:text-white transition-colors cursor-pointer px-1"
                            >
                                {t('iiClaw.cronJobs.filters.clear')}
                            </button>
                        )}
                    </div>
                )}

                {/* Job List */}
                <div className="rounded-2xl border border-grey-2 dark:border-grey/30 bg-sidebar-bg dark:bg-white/[0.04] overflow-hidden">
                    {loading ? (
                        <div className="flex items-center justify-center h-32 text-sm text-charcoal/40 dark:text-white/30">
                            {t('common.loading', 'Loading...')}
                        </div>
                    ) : jobs.length === 0 ? (
                        <div className="flex flex-col items-center justify-center h-40 text-center px-6">
                            <div className="w-12 h-12 rounded-full bg-charcoal/5 dark:bg-white/5 flex items-center justify-center mb-3">
                                <svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg" className="opacity-30">
                                    <path d="M10 5V10L13 12M18 10C18 14.4183 14.4183 18 10 18C5.58172 18 2 14.4183 2 10C2 5.58172 5.58172 2 10 2C14.4183 2 18 5.58172 18 10Z" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                                </svg>
                            </div>
                            <p className="text-sm text-charcoal/40 dark:text-white/30">
                                {t('iiClaw.cronJobs.noJobs')}
                            </p>
                            <p className="text-[10px] text-charcoal/30 dark:text-white/20 mt-1">
                                {t('iiClaw.cronJobs.noJobsHint')}
                            </p>
                        </div>
                    ) : filteredJobs.length === 0 ? (
                        <div className="flex items-center justify-center h-24 text-xs text-charcoal/40 dark:text-white/30">
                            {t('iiClaw.cronJobs.noMatchingJobs')}
                        </div>
                    ) : (
                        <div className="divide-y divide-charcoal/[0.06] dark:divide-white/[0.08]">
                            {filteredJobs.map((job) => (
                                <JobRow
                                    key={job.id}
                                    job={job}
                                    onToggle={handleToggle}
                                    onDelete={setConfirmDelete}
                                    onHistory={handleHistory}
                                    onEdit={handleEdit}
                                    onTest={handleTest}
                                />
                            ))}
                        </div>
                    )}
                </div>
            </div>

            {/* Create Dialog */}
            <CreateJobDialog
                open={createOpen}
                onOpenChange={setCreateOpen}
                onCreated={fetchJobs}
            />

            {/* History Dialog */}
            <HistoryDialog
                job={historyTarget}
                open={historyOpen}
                onOpenChange={setHistoryOpen}
            />

            {/* Edit Dialog */}
            <CreateJobDialog
                open={editOpen}
                onOpenChange={setEditOpen}
                onCreated={fetchJobs}
                editJob={editTarget}
            />

            {/* Delete Confirmation */}
            <AlertDialog open={!!confirmDelete} onOpenChange={(v) => { if (!v) setConfirmDelete(null) }}>
                <AlertDialogContent>
                    <AlertDialogHeader>
                        <AlertDialogTitle>
                            {t('iiClaw.cronJobs.confirmDeleteTitle')}
                        </AlertDialogTitle>
                        <AlertDialogDescription>
                            {t('iiClaw.cronJobs.confirmDeleteDesc', { name: confirmDelete?.name })}
                        </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                        <AlertDialogCancel disabled={deleting}>
                            {t('common.cancel', 'Cancel')}
                        </AlertDialogCancel>
                        <AlertDialogAction
                            onClick={handleDelete}
                            disabled={deleting}
                            className="bg-red text-white hover:bg-red/80"
                        >
                            {deleting ? t('iiClaw.cronJobs.deleting') : t('iiClaw.cronJobs.delete')}
                        </AlertDialogAction>
                    </AlertDialogFooter>
                </AlertDialogContent>
            </AlertDialog>

            {/* Test Result */}
            <AlertDialog open={!!testResult} onOpenChange={(v) => { if (!v) setTestResult(null) }}>
                <AlertDialogContent>
                    <AlertDialogHeader>
                        <AlertDialogTitle className="flex items-center gap-2">
                            {testResult?.result.status === 'ok' ? (
                                <span className="w-2 h-2 rounded-full bg-green-5 shrink-0" />
                            ) : (
                                <span className="w-2 h-2 rounded-full bg-red shrink-0" />
                            )}
                            {t('iiClaw.cronJobs.testResult')} — {testResult?.job.name}
                        </AlertDialogTitle>
                        <AlertDialogDescription asChild>
                            <div className="space-y-2 mt-2">
                                <div className="flex items-center gap-2">
                                    <StatusBadge status={testResult?.result.status || 'error'} />
                                    {testResult?.result.action_type && (
                                        <span className="text-[10px] text-charcoal/40 dark:text-white/30">
                                            {testResult.result.action_type}
                                        </span>
                                    )}
                                </div>
                                {testResult?.result.message && (
                                    <p className="text-xs text-green-5 bg-green-5/5 dark:bg-green-5/10 rounded-lg px-3 py-2">
                                        {testResult.result.message}
                                    </p>
                                )}
                                {testResult?.result.error && (
                                    <p className="text-xs text-red bg-red/5 dark:bg-red/10 rounded-lg px-3 py-2">
                                        {testResult.result.error}
                                    </p>
                                )}
                            </div>
                        </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                        <AlertDialogAction className="bg-sky-blue text-charcoal hover:bg-sky-blue/80 dark:bg-sky-blue dark:text-charcoal dark:hover:bg-sky-blue/80">
                            {t('common.ok', 'OK')}
                        </AlertDialogAction>
                    </AlertDialogFooter>
                </AlertDialogContent>
            </AlertDialog>
        </div>
    )
}

export { CronJobsPanel }
