import * as SelectPrimitive from '@radix-ui/react-select'
import clsx from 'clsx'
import { ChevronDownIcon } from 'lucide-react'

import { PROVIDERS_NAME, getProviderKey } from '@/constants/models'
import {
    selectAvailableModels,
    selectSelectedModel,
    setSelectedModel,
    useAppDispatch,
    useAppSelector
} from '@/state'
import {
    Select,
    SelectContent,
    SelectItem
} from '@/components/ui/select'
import type { IModel } from '@/typings/settings'

interface CoworkModelSelectorProps {
    className?: string
}

// Providers whose default svg is painted white (for dark bgs). On light mode
// we either swap to a *-dark.svg sibling (openai, anthropic) or use a CSS
// brightness-0 filter to darken the white paths in place (custom).
const LIGHT_SRC_OVERRIDE: Record<string, string> = {
    openai: '/images/openai-dark.svg',
    anthropic: '/images/anthropic-dark.svg'
}
const INVERTS_IN_LIGHT_MODE = new Set(['custom'])

// Mirror the active-state styling of the Chat / All files tab buttons in
// cowork-chat-box.tsx — but apply it as a :hover (and :data-[state=open])
// effect so the selector visually "presses in" when the user rolls over or
// opens it, identical to how a tab becomes active.
const TRIGGER_CLASS = clsx(
    'group relative flex h-7 cursor-pointer items-center gap-2 rounded-full',
    'border border-sky-blue px-3 text-xs font-semibold outline-none',
    'transition-colors',
    // Idle — same as an inactive tab button
    'border-firefly text-firefly dark:border-sky-blue dark:text-sky-blue',
    // Hover / open — same as the active tab button
    'hover:bg-firefly hover:border-firefly hover:text-sky-blue-2',
    'dark:hover:bg-sky-blue dark:hover:border-sky-blue-2 dark:hover:text-black',
    'data-[state=open]:bg-firefly data-[state=open]:border-firefly data-[state=open]:text-sky-blue-2',
    'dark:data-[state=open]:bg-sky-blue dark:data-[state=open]:border-sky-blue-2 dark:data-[state=open]:text-black',
    'disabled:cursor-not-allowed disabled:opacity-50'
)

interface ProviderIconProps {
    providerKey: string
    className?: string
}

const ProviderIcon = ({ providerKey, className }: ProviderIconProps) => {
    if (!PROVIDERS_NAME[providerKey]) return null
    const defaultSrc = `/images/${providerKey}.svg`
    const lightSrc = LIGHT_SRC_OVERRIDE[providerKey]
    const invertInLight = INVERTS_IN_LIGHT_MODE.has(providerKey)

    // Case 1: separate light-mode asset exists — render two <img>s toggled
    // by tailwind's dark: variant. Keeps each asset pristine.
    if (lightSrc) {
        return (
            <>
                <img
                    src={lightSrc}
                    alt={providerKey}
                    className={clsx('shrink-0 object-contain dark:hidden', className)}
                />
                <img
                    src={defaultSrc}
                    alt={providerKey}
                    className={clsx(
                        'hidden shrink-0 object-contain dark:block',
                        className
                    )}
                />
            </>
        )
    }

    // Case 2: no separate asset and the svg is white-filled — darken it on
    // light mode via brightness-0 (white → black); leave it untouched on dark.
    if (invertInLight) {
        return (
            <img
                src={defaultSrc}
                alt={providerKey}
                className={clsx(
                    'shrink-0 object-contain brightness-0 dark:brightness-100',
                    className
                )}
            />
        )
    }

    // Case 3: asset is a rasterised/pattern image that renders fine on both
    // backgrounds (gemini, google, …). Use as-is.
    return (
        <img
            src={defaultSrc}
            alt={providerKey}
            className={clsx('shrink-0 object-contain', className)}
        />
    )
}

const renderTriggerLabel = (model: IModel | null | undefined) => {
    if (!model) {
        return <span>No model</span>
    }
    const providerKey = getProviderKey(model)
    return (
        <>
            <ProviderIcon providerKey={providerKey} className="size-4" />
            <span className="max-w-[140px] truncate">{model.model}</span>
        </>
    )
}

const CoworkModelSelector = ({ className }: CoworkModelSelectorProps) => {
    const dispatch = useAppDispatch()
    const availableModels = useAppSelector(selectAvailableModels)
    const selectedModelId = useAppSelector(selectSelectedModel)

    const hasModels = availableModels.length > 0
    const effectiveModel =
        availableModels.find((model) => model.id === selectedModelId) ??
        availableModels[0] ??
        null
    // Pass undefined (not '') to Radix when nothing is selected so the
    // trigger remains in uncontrolled-empty state rather than flashing a
    // placeholder. Radix Select treats empty string as a real value.
    const triggerValue = effectiveModel?.id

    return (
        <Select
            value={triggerValue}
            onValueChange={(id) => dispatch(setSelectedModel(id))}
            disabled={!hasModels}
        >
            <SelectPrimitive.Trigger
                data-slot="select-trigger"
                className={clsx(TRIGGER_CLASS, className)}
                aria-label="Select model"
            >
                {renderTriggerLabel(effectiveModel)}
                <SelectPrimitive.Icon asChild>
                    <ChevronDownIcon className="size-3.5 opacity-70" />
                </SelectPrimitive.Icon>
            </SelectPrimitive.Trigger>
            <SelectContent className="dark:bg-[#121716] dark:text-white">
                {availableModels.map((model) => {
                    const providerKey = getProviderKey(model)
                    return (
                        <SelectItem
                            key={model.id}
                            value={model.id}
                            className="dark:focus:text-white dark:focus:bg-sky-blue/10"
                        >
                            <div className="flex items-center gap-2">
                                <ProviderIcon
                                    providerKey={providerKey}
                                    className="size-4"
                                />
                                <span className="truncate">{model.model}</span>
                            </div>
                        </SelectItem>
                    )
                })}
            </SelectContent>
        </Select>
    )
}

export default CoworkModelSelector
