import clsx from 'clsx'
import { Icon } from '@/components/ui/icon'

export type CoworkFolderStep = 'source' | 'build' | 'result'

interface CoworkFolderStepsProps {
    activeStep: CoworkFolderStep
    onSelectStep: (step: CoworkFolderStep) => void
}

const steps: {
    id: CoworkFolderStep
    label: string
    icon: string
}[] = [
    { id: 'source', label: 'Source', icon: 'folder-open' },
    { id: 'build', label: 'Build', icon: 'wrench' },
    { id: 'result', label: 'Result', icon: 'ai-magic' }
]

const CoworkFolderSteps = ({
    activeStep,
    onSelectStep
}: CoworkFolderStepsProps) => {
    return (
        <div className="flex items-center justify-center gap-x-3">
            {steps.map((step, index) => {
                const isActive = activeStep === step.id

                return (
                    <div key={step.id} className="flex items-center gap-x-3">
                        <button
                            type="button"
                            className="flex cursor-pointer items-center gap-x-2"
                            onClick={() => onSelectStep(step.id)}
                        >
                            <div
                                className={clsx(
                                    'flex size-7 items-center justify-center rounded-full',
                                    isActive
                                        ? 'bg-firefly/30 dark:bg-sky-blue/30'
                                        : 'border border-black/[0.58] dark:border-white/[0.58]'
                                )}
                            >
                                <Icon
                                    name={step.icon}
                                    className={clsx(
                                        isActive
                                            ? 'stroke-black dark:stroke-sky-blue fill-black dark:fill-sky-blue'
                                            : 'stroke-black/[0.58] dark:stroke-white/[0.58] fill-black/[0.58] dark:fill-white/[0.58]'
                                    )}
                                />
                            </div>
                            <p
                                className={clsx('text-base', {
                                    'font-semibold dark:text-white': isActive,
                                    'text-black/[0.58] dark:text-white/[0.58]':
                                        !isActive
                                })}
                            >
                                {step.label}
                            </p>
                        </button>
                        {index < steps.length - 1 && (
                            <Icon
                                name="line"
                                className="w-6 stroke-black dark:stroke-white md:w-12"
                            />
                        )}
                    </div>
                )
            })}
        </div>
    )
}

export default CoworkFolderSteps
