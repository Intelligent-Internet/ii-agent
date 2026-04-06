import { Icon } from './ui/icon'
import { QUESTION_MODE } from '@/typings'
import { cn } from '@/lib/utils'
import { useTranslation } from 'react-i18next'
import { useIsSageTheme } from '@/hooks/use-is-sage-theme'
import { isTauri } from '@/utils/is-tauri'

interface ModeSelectorProps {
    selectedMode: QUESTION_MODE
    hide?: boolean
    onSelect: (mode: QUESTION_MODE) => void
}

const ModeSelector = ({ selectedMode, hide, onSelect }: ModeSelectorProps) => {
    const { t } = useTranslation()
    const isSage = useIsSageTheme()
    const modes = [
        {
            type: QUESTION_MODE.CHAT,
            icon: 'chat-fill',
            label: t('question.mode.chat')
        },
        {
            type: QUESTION_MODE.AGENT,
            icon: 'agent-fill',
            label: t('question.mode.agent')
        },
        {
            type: QUESTION_MODE.COWORK,
            icon: 'messages',
            label: 'II-Cowork'
        }
    ].filter((mode) => isTauri || mode.type !== QUESTION_MODE.COWORK)

    if (hide) return null

    return (
        <div className="hidden md:flex items-end">
            {modes.map((mode) => {
                const isActive = selectedMode === mode.type

                return (
                    <button
                        key={mode.type}
                        onClick={() => onSelect(mode.type)}
                        className={cn(
                            'flex items-center gap-x-[6px] px-4 py-2 rounded-tl-xl rounded-tr-xl text-xs cursor-pointer',
                            isActive
                                ? 'bg-charcoal dark:bg-sky-blue-2 text-sky-blue-2 dark:text-black font-semibold'
                                : 'bg-charcoal/10 dark:bg-sky-blue-2/10 text-black/50 dark:text-white/50',
                            isSage &&
                                (isActive
                                    ? 'dark:bg-sky-blue-3'
                                    : 'dark:bg-sky-blue-3/10 text-black dark:text-white')
                        )}
                    >
                        <Icon
                            name={mode.icon}
                            className={cn(
                                `size-4 ${isActive ? 'fill-sky-blue-2 dark:fill-black' : 'fill-black/30 dark:fill-white/30'}`,
                                isSage &&
                                    (isActive
                                        ? 'dark:fill-black'
                                        : 'dark:fill-white')
                            )}
                        />
                        <span className="hidden md:inline">{mode.label}</span>
                    </button>
                )
            })}
        </div>
    )
}

export default ModeSelector
